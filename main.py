# Copyright (c) 2021 Linux Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import logging
import os
from time import sleep
from typing import List, Optional

import jwt
import psycopg2
import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.exc import InterfaceError, OperationalError, StatementError

# Init Globals
service_name = 'ortelius-ms-validate-user'
db_conn_retry = 3

# Init FastAPI
app = FastAPI(
    title=service_name,
    description=service_name
)
# Init db connection
db_host = os.getenv("DB_HOST", "localhost")
db_name = os.getenv("DB_NAME", "postgres")
db_user = os.getenv("DB_USER", "postgres")
db_pass = os.getenv("DB_PASS", "postgres")
db_port = os.getenv("DB_PORT", "5432")
id_rsa_pub = os.getenv("RSA_FILE", "/app/keys/id_rsa.pub")

public_key = ''
if (os.path.exists(id_rsa_pub)):
    public_key = open(id_rsa_pub, 'r').read()

engine = create_engine("postgresql+psycopg2://" + db_user + ":" + db_pass + "@" + db_host + ":" + db_port + "/" + db_name, pool_pre_ping=True)

# health check endpoint
class StatusMsg(BaseModel):
    status: str
    service_name: Optional[str] = None


@app.get("/health")
async def health(response: Response) -> StatusMsg:
    try:
        with engine.connect() as connection:
            conn = connection.connection
            cursor = conn.cursor()
            cursor.execute('SELECT 1')
            if cursor.rowcount > 0:
                return {"status": 'UP', "service_name": service_name}
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {"status": 'DOWN'}

    except Exception as err:
        print(str(err))
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": 'DOWN'}
# end health check

# validate user endpoint
class Message(BaseModel):
    detail: str


class DomainList(BaseModel):
    domains: List[int] = list()


@app.get('/msapi/validateuser')
async def validateuser(request: Request, domains: Optional[str] = Query(None, regex="^[y|Y|n|N]$")) -> DomainList:
    result = []                                # init result to be empty
    userid = -1                                # init userid to -1
    uuid = ''                                  # init uuid to blank
    global public_key                          # allow update of global var

    try:
        #Retry logic for failed query
        no_of_retry = db_conn_retry
        attempt = 1;
        while True:
            try:
                with engine.connect() as connection:
                    conn = connection.connection
                    authorized = False      # init to not authorized

                    if (not os.path.exists(id_rsa_pub)):
                        try:
                            cursor = conn.cursor() 
                            cursor.execute("select bootstrap from dm.dm_tableinfo limit 1") 
                            row = cursor.fetchone()
                            while row:
                                public_key = base64.b64decode(row[0]).decode("utf-8")
                                row = cursor.fetchone()
                            cursor.close()  
                        except Exception as err:
                            print(str(err))

                    token = request.cookies.get('token', None)  # get the login token from the cookies
                    print(token)
                    print(public_key)
                    if (token is None):                        # no token the fail
                        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization Failed")
                    try:
                        decoded = jwt.decode(token, public_key, algorithms=["RS256"])  # decypt token
                        userid = decoded.get('sub', None)           # get userid from token
                        uuid = decoded.get('jti', None)             # get uuid from token
                        if (userid is None):                        # no userid fail
                            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid userid")
                        if (uuid is None):                          # no uuid fail
                            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid login token")
                    except jwt.InvalidTokenError as err:
                        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(err)) from None

                    csql = "DELETE from dm.dm_user_auth where lastseen < current_timestamp at time zone 'UTC' - interval '1 hours'"  # remove stale logins
                    sql = "select count(*) from dm.dm_user_auth where id = (%s) and jti = (%s)"  # see if the user id authorized
        
                    cursor = conn.cursor()  # init cursor
                    cursor.execute(csql)   # exec delete query
                    cursor.close()         # close the cursor so don't have a connection leak
                    conn.commit()          # commit the delete and free up lock
        
                    params = tuple([userid, uuid])   # setup parameters to count(*) query
                    cursor = conn.cursor()      # init cursor
                    cursor.execute(sql, params)  # run the query
        
                    row = cursor.fetchone()     # fetch a row
                    rowcnt = 0                  # init counter
                    while row:                  # loop until there are no more rows
                        rowcnt = row[0]         # get the 1st column data
                        row = cursor.fetchone()  # get the next row
                    cursor.close()              # close the cursor so don't have a connection leak
        
                    if (rowcnt > 0):            # > 0 means that user is authorized
                        authorized = True       # set authorization to True
                        usql = "update dm.dm_user_auth set lastseen = current_timestamp at time zone 'UTC' where id = (%s) and jti = (%s)"  # sql to update the last seen timestamp
                        params = tuple([userid, uuid])       # setup parameters to update query
                        cursor = conn.cursor()          # init cursor
                        cursor.execute(usql, params)    # run the query
                        cursor.close()                  # close the cursor so don't have a connection leak
                        conn.commit()                   # commit the update and free up lock
        
                    if (not authorized):       # fail API call if not authorized
                        conn.close()
                        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization Failed")
        
                    if (domains is not None and domains.lower() == 'y'):    # get the list of domains for the user if domains=Y
                        domainid = -1
                        sql = "SELECT domainid FROM dm.dm_user WHERE id = (%s)"
                        cursor = conn.cursor()  # init cursor
                        params = tuple([userid])
                        cursor.execute(sql, params)
                        row = cursor.fetchone()
                        while row:
                            domainid = row[0]
                            row = cursor.fetchone()
                        cursor.close()
        
                        sql = """WITH RECURSIVE parents AS
                                    (SELECT
                                            id              AS id,
                                            ARRAY [id]      AS ancestry,
                                            NULL :: INTEGER AS parent,
                                            id              AS start_of_ancestry
                                        FROM dm.dm_domain
                                        WHERE
                                            domainid IS NULL and status = 'N'
                                        UNION
                                        SELECT
                                            child.id                                    AS id,
                                            array_append(p.ancestry, child.id)          AS ancestry,
                                            child.domainid                              AS parent,
                                            coalesce(p.start_of_ancestry, child.domainid) AS start_of_ancestry
                                        FROM dm.dm_domain child
                                            INNER JOIN parents p ON p.id = child.domainid AND child.status = 'N'
                                        )
                                        SELECT ARRAY_AGG(c)
                                        FROM
                                        (SELECT DISTINCT UNNEST(ancestry)
                                            FROM parents
                                            WHERE id = (%s) OR (%s) = ANY(parents.ancestry)) AS CT(c)"""
        
                        cursor = conn.cursor()  # init cursor
                        params = tuple([domainid, domainid])
                        cursor.execute(sql, params)
                        row = cursor.fetchone()
                        while row:
                            result = row[0]
                            row = cursor.fetchone()
                    conn.close()
                return {"domains": result}
                
            except (InterfaceError, OperationalError) as ex:
                if attempt < no_of_retry:
                    sleep_for = 0.2
                    logging.error(
                        "Database connection error: {} - sleeping for {}s"
                        " and will retry (attempt #{} of {})".format(
                            ex, sleep_for, attempt, no_of_retry
                        )
                    )
                    #200ms of sleep time in cons. retry calls 
                    sleep(sleep_for)
                    attempt += 1
                    continue
                else:
                    raise

    except HTTPException:
        raise
    except Exception as err:
        print(str(err))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(err)) from None

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)
