# Copyright (c) 2021 Linux Foundation
# Licensed under the Apache License, Version 2.0

import base64
import hashlib
import logging
import os

# Added for email sending
import smtplib
import ssl
from datetime import datetime, timedelta
from email.message import EmailMessage
from time import sleep
from typing import Optional

import jwt
import uvicorn
from fastapi import (
    BackgroundTasks,
    FastAPI,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)

# Import HTMLResponse to serve the HTML page
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import create_engine, text
from sqlalchemy.exc import InterfaceError, OperationalError

# Init Globals
service_name = "ortelius-ms-validate-user"
db_conn_retry = 3
# Configure logging to show info-level messages
logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(message)s")

# Init FastAPI
app = FastAPI(title=service_name, description=service_name)

# --- Database Configuration ---
db_host = os.getenv("DB_HOST", "localhost")
db_name = os.getenv("DB_NAME", "postgres")
db_user = os.getenv("DB_USER", "postgres")
db_pass = os.getenv("DB_PASS", "postgres")
db_port = os.getenv("DB_PORT", "5432")
id_rsa_pub = os.getenv("RSA_FILE", "/app/keys/id_rsa.pub")

# --- Email Server (SMTP) Configuration ---
# To send real emails, set the following environment variables.
# If these are not set, emails will be printed to the console instead.
# Example for Gmail:
# SMTP_HOST=smtp.gmail.com
# SMTP_PORT=587
# SMTP_USER=your_email@gmail.com
# SENDER_EMAIL=your_email@gmail.com
# SMTP_PASSWORD=your_gmail_app_password  (Note: Use an "App Password" for Gmail if 2FA is enabled)
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "")


public_key = ""
if os.path.exists(id_rsa_pub):
    public_key = open(id_rsa_pub, "r").read()

engine = create_engine(
    f"postgresql+psycopg2://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}",
    pool_pre_ping=True,
)

# JWT secret for password reset tokens (different from login tokens!)
RESET_SECRET_KEY = os.getenv("RESET_SECRET_KEY", "change-this-secret")
RESET_ALGORITHM = "HS256"
RESET_TOKEN_EXPIRE_MINUTES = 30


def create_password_reset_token(username: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": username, "exp": expire}
    return jwt.encode(to_encode, RESET_SECRET_KEY, algorithm=RESET_ALGORITHM)


def verify_password_reset_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, RESET_SECRET_KEY, algorithms=[RESET_ALGORITHM])
        return payload.get("sub")
    except Exception:
        return None


# -----------------------------
# Health check endpoint
# -----------------------------
class StatusMsg(BaseModel):
    status: str = ""
    service_name: str = ""


@app.get("/health")
async def health(response: Response) -> StatusMsg:
    try:
        with engine.connect() as connection:
            conn = connection.connection
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            if cursor.rowcount > 0:
                return StatusMsg(status="UP", service_name=service_name)
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return StatusMsg(status="DOWN", service_name=service_name)
    except Exception as err:
        print(str(err))
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return StatusMsg(status="DOWN", service_name=service_name)


# -----------------------------
# validate user endpoint
# -----------------------------
class Message(BaseModel):
    detail: str = ""


class DomainList(BaseModel):
    domains: list[int] = []


@app.get("/msapi/validateuser")
async def validateuser(request: Request, domains: Optional[str] = Query(None, regex="^[y|Y|n|N]$")) -> DomainList:
    # (existing validateuser code unchanged)
    userid = -1
    uuid = ""
    global public_key
    domlist = DomainList()
    try:
        no_of_retry = db_conn_retry
        attempt = 1
        while True:
            try:
                with engine.connect() as connection:
                    conn = connection.connection
                    authorized = False

                    if not os.path.exists(id_rsa_pub):
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

                    token = request.cookies.get("token", None)
                    if token is None:
                        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization Failed")
                    try:
                        decoded = jwt.decode(token, public_key, algorithms=["RS256"])
                        userid = decoded.get("sub", None)
                        uuid = decoded.get("jti", None)
                        if userid is None or uuid is None:
                            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid login token")
                    except jwt.InvalidTokenError as err:
                        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(err)) from None

                    csql = "DELETE from dm.dm_user_auth where lastseen < current_timestamp at time zone 'UTC' - interval '1 hours'"
                    sqlstmt = "select count(*) from dm.dm_user_auth where id = (%s) and jti = (%s)"

                    cursor = conn.cursor()
                    cursor.execute(csql)
                    cursor.close()
                    conn.commit()

                    params = tuple([userid, uuid])
                    cursor = conn.cursor()
                    cursor.execute(sqlstmt, params)
                    row = cursor.fetchone()
                    rowcnt = 0
                    while row:
                        rowcnt = row[0]
                        row = cursor.fetchone()
                    cursor.close()

                    if rowcnt > 0:
                        authorized = True
                        usql = "update dm.dm_user_auth set lastseen = current_timestamp at time zone 'UTC' where id = (%s) and jti = (%s)"
                        params = tuple([userid, uuid])
                        cursor = conn.cursor()
                        cursor.execute(usql, params)
                        cursor.close()
                        conn.commit()

                    if not authorized:
                        conn.close()
                        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization Failed")

                    if domains is not None and domains.lower() == "y":
                        domainid = -1
                        sqlstmt = "SELECT domainid FROM dm.dm_user WHERE id = (%s)"
                        cursor = conn.cursor()
                        params = tuple([userid])
                        cursor.execute(sqlstmt, params)
                        row = cursor.fetchone()
                        while row:
                            domainid = row[0] if row[0] else -1
                            row = cursor.fetchone()
                        cursor.close()

                        sqlstmt = """WITH RECURSIVE parents AS
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

                        cursor = conn.cursor()
                        params = tuple([domainid, domainid])
                        cursor.execute(sqlstmt, params)
                        row = cursor.fetchone()
                        while row:
                            domainid = row[0] if row[0] else -1
                            domlist.domains.append(domainid)
                            row = cursor.fetchone()
                    conn.close()
                return domlist

            except (InterfaceError, OperationalError) as ex:
                if attempt < no_of_retry:
                    sleep_for = 0.2
                    logging.error(
                        "Database connection error: %s - sleeping for %d seconds and will retry (attempt #%d of %d)",
                        ex,
                        sleep_for,
                        attempt,
                        no_of_retry,
                    )
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


# -----------------------------
# Forgot username / password
# -----------------------------
# PAYLOAD MODELS
class ForgotUsernamePayload(BaseModel):
    email: EmailStr


class ForgotPasswordPayload(BaseModel):
    username: str


class ResetPasswordPayload(BaseModel):
    token: str
    new_password: str


def send_email(to: str, subject: str, body: str):
    """
    Sends an email using SMTP configuration from environment variables.
    Falls back to printing the email to the console if not configured.
    """
    # Check if all required SMTP environment variables are set
    if not all([SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SENDER_EMAIL]):
        logging.warning("Email server not configured. Simulating email sending:")
        print("-----------------------------------------------------------------")
        print(f"To: {to}")
        print(f"Subject: {subject}")
        print("-----------------------------------------------------------------")
        print(body)
        print("-----------------------------------------------------------------")
        return

    # Create the email message
    msg = EmailMessage()
    msg.set_content(body)
    msg["Subject"] = subject
    msg["From"] = SENDER_EMAIL
    msg["To"] = to

    # Create a secure SSL context
    context = ssl.create_default_context()

    try:
        logging.info(f"Connecting to SMTP server at {SMTP_HOST}:{SMTP_PORT} to send email...")
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls(context=context)  # Upgrade the connection to be secure
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
            logging.info(f"Email sent successfully to {to}")
    except smtplib.SMTPAuthenticationError as e:
        logging.error(f"SMTP Authentication Error: Failed to send email. Please check credentials. Details: {e}")
    except smtplib.SMTPConnectError as e:
        logging.error(f"SMTP Connection Error: Failed to connect to the server. Check SMTP_HOST and SMTP_PORT. Details: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred while sending email: {e}")


# ------------------------------------------------------------------------------------
# Login Help Landing Page
# ------------------------------------------------------------------------------------
@app.get("/loginhelp", response_class=HTMLResponse)
async def get_login_help_page():
    # Check if the email server is configured
    email_configured = all([SMTP_HOST, SMTP_USER, SMTP_PASSWORD, SENDER_EMAIL])

    disabled_attribute = ""
    warning_message_html = ""

    if not email_configured:
        disabled_attribute = "disabled"
        warning_message_html = """
        <div style="padding: 1rem; margin-bottom: 1rem; border: 1px solid #dc3545; border-radius: 5px; background-color: #f8d7da; color: #721c24;">
            <strong>Feature Disabled</strong>
            <p style="margin: 0.5rem 0 0 0;">The 'Forgot Username' and 'Forgot Password' features are unavailable because the email server has not been configured by the administrator.</p>
        </div>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <title>Login Help</title>
    <style>
      body {{
        font-family: sans-serif;
        background-color: #f2f2f2;
        display: flex;
        justify-content: center;
        align-items: center;
        height: 100vh;
        margin: 0;
      }}
      .container {{
        background-color: #fff;
        padding: 2rem;
        border-radius: 5px;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        width: 400px;
        text-align: center;
      }}
      h1 {{
        margin-bottom: 1.5rem;
      }}
      h2 {{
          margin-top: 0;
      }}
      .form-group {{
        margin-bottom: 1rem;
        text-align: left;
      }}
      label {{
        display: block;
        margin-bottom: 0.5rem;
      }}
      input[type="email"], input[type="text"] {{
        width: 100%;
        padding: 0.5rem;
        border: 1px solid #ccc;
        border-radius: 3px;
        box-sizing: border-box;
      }}
      #message {{
        margin-top: 1rem;
        font-size: 0.9rem;
        text-align: center;
      }}
      .error {{ color: red; }}
      .success {{ color: green; }}
      button {{
        width: 100%;
        padding: 0.75rem;
        background-color: #3d3a4b;
        color: #fff;
        border: none;
        border-radius: 3px;
        cursor: pointer;
        font-size: 1rem;
        margin-top: 0.5rem;
      }}
       button.secondary {{
        background-color: #6c757d;
      }}
      button:disabled {{
        background-color: #ccc;
        cursor: not-allowed;
      }}
    </style>
    </head>
    <body>

    <div class="container">
      <h1>Login Help</h1>

      {warning_message_html}

      <div id="initial-choice">
        <p>What do you need help with?</p>
        <button id="show-username-form-btn" {disabled_attribute}>Forgot Username</button>
        <button id="show-password-form-btn" {disabled_attribute}>Forgot Password</button>
      </div>

      <form id="username-form" style="display:none;" novalidate>
        <h2>Recover Username</h2>
        <p>Enter your email address to receive your username.</p>
        <div class="form-group">
            <label for="email">Email Address</label>
            <input type="email" id="email" name="email" required>
        </div>
        <button type="submit">Send Username</button>
        <button type="button" class="back-btn secondary">Back</button>
      </form>

      <form id="password-form" style="display:none;" novalidate>
        <h2>Reset Password</h2>
        <p>Enter your username to receive a password reset link.</p>
        <div class="form-group">
            <label for="username">Username</label>
            <input type="text" id="username" name="username" required>
        </div>
        <button type="submit">Send Reset Link</button>
        <button type="button" class="back-btn secondary">Back</button>
      </form>

      <div id="message"></div>
    </div>

    <script>
      const initialChoiceDiv = document.getElementById('initial-choice');
      const usernameForm = document.getElementById('username-form');
      const passwordForm = document.getElementById('password-form');
      const messageDiv = document.getElementById('message');

      function showInitialChoice() {{
        usernameForm.style.display = 'none';
        passwordForm.style.display = 'none';
        initialChoiceDiv.style.display = 'block';
        messageDiv.textContent = '';
      }}

      document.getElementById('show-username-form-btn').addEventListener('click', () => {{
        initialChoiceDiv.style.display = 'none';
        usernameForm.style.display = 'block';
      }});

      document.getElementById('show-password-form-btn').addEventListener('click', () => {{
        initialChoiceDiv.style.display = 'none';
        passwordForm.style.display = 'block';
      }});

      document.querySelectorAll('.back-btn').forEach(btn => {{
        btn.addEventListener('click', showInitialChoice);
      }});

      async function handleFormSubmit(event, url, payload) {{
          event.preventDefault();
          const submitBtn = event.target.querySelector('button[type="submit"]');
          const originalBtnText = submitBtn.textContent;
          submitBtn.disabled = true;
          submitBtn.textContent = 'Sending...';
          messageDiv.textContent = '';

          try {{
              const response = await fetch(url, {{
                  method: 'POST',
                  headers: {{ 'Content-Type': 'application/json' }},
                  body: JSON.stringify(payload)
              }});
              const data = await response.json();
              if (response.ok) {{
                  messageDiv.textContent = data.detail;
                  messageDiv.className = 'success';
                  event.target.style.display = 'none'; // Hide form
                  initialChoiceDiv.style.display = 'block'; // Show choices again
              }} else {{
                  messageDiv.textContent = 'Error: ' + data.detail;
                  messageDiv.className = 'error';
              }}
          }} catch (error) {{
              messageDiv.textContent = 'An unexpected error occurred.';
              messageDiv.className = 'error';
          }} finally {{
              submitBtn.disabled = false;
              submitBtn.textContent = originalBtnText;
          }}
      }}

      usernameForm.addEventListener('submit', (event) => {{
          const email = document.getElementById('email').value;
          handleFormSubmit(event, '/forgot-username', {{ email }});
      }});

      passwordForm.addEventListener('submit', (event) => {{
          const username = document.getElementById('username').value;
          handleFormSubmit(event, '/forgot-password', {{ username }});
      }});
    </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.post("/forgot-username", response_model=Message)
async def forgot_username(payload: ForgotUsernamePayload, background_tasks: BackgroundTasks):
    # Security check: Prevent use if not configured
    if not all([SMTP_HOST, SMTP_USER, SMTP_PASSWORD, SENDER_EMAIL]):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Email service is not configured.")

    with engine.connect() as conn:
        sql = text("SELECT name FROM dm.dm_user WHERE email = :email LIMIT 1")
        result = conn.execute(sql, {"email": payload.email}).fetchone()
        if result:
            username = result[0]
            background_tasks.add_task(send_email, payload.email, "Your Username", f"Your username is: {username}")

    return {"detail": "If an account with that email exists, your username has been sent."}


@app.post("/forgot-password", response_model=Message)
async def forgot_password(payload: ForgotPasswordPayload, background_tasks: BackgroundTasks, request: Request):
    # Security check: Prevent use if not configured
    if not all([SMTP_HOST, SMTP_USER, SMTP_PASSWORD, SENDER_EMAIL]):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Email service is not configured.")

    with engine.connect() as conn:
        sql = text("SELECT email FROM dm.dm_user WHERE name = :username LIMIT 1")
        result = conn.execute(sql, {"username": payload.username}).fetchone()
        if result:
            email = result[0]
            token = create_password_reset_token(payload.username)

            # Create a full URL based on the request's host
            base_url = str(request.base_url)
            reset_link = f"{base_url}reset-password?token={token}"

            # Create the email body with the expiration notice
            email_body = f"You have requested to reset your password.\n\nClick this link to proceed:\n{reset_link}\n\nFor your security, this link is only valid for 30 minutes."

            background_tasks.add_task(
                send_email,
                email,
                "Password Reset",
                email_body,
            )

    return {"detail": "If an account with that username exists, a reset link has been sent."}


def encrypt_password(password: str) -> str:
    """
    Hashes a password using SHA-256 and then encodes the raw hash in Base64.
    This mimics the functionality of the provided Java code.
    """
    sha256_hasher = hashlib.sha256()
    sha256_hasher.update(password.encode("utf-8"))
    hash_digest = sha256_hasher.digest()
    base64_encoded_hash = base64.b64encode(hash_digest).decode("ascii")
    return base64_encoded_hash


# ------------------------------------------------------------------------------------
# Reset Password Page and Endpoint
# ------------------------------------------------------------------------------------
@app.get("/reset-password", response_class=HTMLResponse)
async def get_reset_password_page(token: str):
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
    <title>Password Reset</title>
    <style>
      body {
        font-family: sans-serif;
        background-color: #f2f2f2;
        display: flex;
        justify-content: center;
        align-items: center;
        height: 100vh;
        margin: 0;
      }
      .container {
        background-color: #fff;
        padding: 2rem;
        border-radius: 5px;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        width: 350px;
      }
      h1 {
        text-align: center;
        margin-bottom: 1.5rem;
      }
      .form-group {
        margin-bottom: 1rem;
      }
      label {
        display: block;
        margin-bottom: 0.5rem;
      }
      input[type="password"] {
        width: 100%;
        padding: 0.5rem;
        border: 1px solid #ccc;
        border-radius: 3px;
        box-sizing: border-box;
      }
      #message {
        margin-top: 1rem;
        font-size: 0.9rem;
        text-align: center;
      }
      .error {
        color: red;
      }
      .success {
        color: green;
        line-height: 1.5;
      }
      .success a {
        color: #0056b3;
      }
      button {
        width: 100%;
        padding: 0.75rem;
        background-color: #3d3a4b;
        color: #fff;
        border: none;
        border-radius: 3px;
        cursor: pointer;
        font-size: 1rem;
      }
      button:disabled {
        background-color: #ccc;
        cursor: not-allowed;
      }
    </style>
    </head>
    <body>

    <div class="container">
      <h1>Reset Password</h1>
      <form id="reset-form">
        <div class="form-group">
          <label for="password">New Password</label>
          <input type="password" id="password" name="password" required>
        </div>
        <div class="form-group">
          <label for="confirm-password">Confirm New Password</label>
          <input type="password" id="confirm-password" name="confirm-password" required>
        </div>
        <button type="submit" id="submit-btn" disabled>Reset Password</button>
      </form>
      <div id="message"></div>
    </div>

    <script>
      const passwordInput = document.getElementById('password');
      const confirmPasswordInput = document.getElementById('confirm-password');
      const messageDiv = document.getElementById('message');
      const submitBtn = document.getElementById('submit-btn');
      const resetForm = document.getElementById('reset-form');

      // Get the token from the URL
      const urlParams = new URLSearchParams(window.location.search);
      const token = urlParams.get('token');

      function checkPasswords() {
        if (passwordInput.value !== '' && passwordInput.value === confirmPasswordInput.value) {
          messageDiv.textContent = '';
          submitBtn.disabled = false;
        } else {
          submitBtn.disabled = true;
          if (confirmPasswordInput.value !== '') {
              messageDiv.textContent = 'Passwords do not match.';
              messageDiv.className = 'error';
          } else {
              messageDiv.textContent = '';
          }
        }
      }

      passwordInput.addEventListener('keyup', checkPasswords);
      confirmPasswordInput.addEventListener('keyup', checkPasswords);

      resetForm.addEventListener('submit', async function(event) {
        event.preventDefault();

        if (!token) {
            messageDiv.textContent = 'Error: No reset token found.';
            messageDiv.className = 'error';
            return;
        }

        const new_password = passwordInput.value;
        submitBtn.disabled = true;
        submitBtn.textContent = 'Resetting...';

        try {
            const response = await fetch('/reset-password', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    token: token,
                    new_password: new_password
                })
            });

            const data = await response.json();

            if (response.ok) {
                // Use innerHTML to render the message and the fallback link
                messageDiv.innerHTML = `
                  <p>${data.detail} You will be redirected shortly to the login page.</p>
                  <p>If you are not redirected, <a href="/dmadminweb/Home">click here to continue</a>.</p>
                `;
                messageDiv.className = 'success';
                resetForm.innerHTML = ''; // Clear the form on success

                // Redirect to the home page after a 3-second delay
                setTimeout(function() {
                    window.location.href = '/dmadminweb/Home';
                }, 3000); // 3000 milliseconds = 3 seconds
            } else {
                messageDiv.textContent = 'Error: ' + data.detail;
                messageDiv.className = 'error';
                submitBtn.disabled = false;
                submitBtn.textContent = 'Reset Password';
            }
        } catch (error) {
            messageDiv.textContent = 'An unexpected error occurred. Please try again.';
            messageDiv.className = 'error';
            submitBtn.disabled = false;
            submitBtn.textContent = 'Reset Password';
        }
      });
    </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.post("/reset-password", response_model=Message)
async def reset_password(payload: ResetPasswordPayload):
    username = verify_password_reset_token(payload.token)
    if not username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token",
        )

    hashed_pw = encrypt_password(payload.new_password)

    with engine.connect() as conn:
        # Use a transaction to ensure the update is atomic
        with conn.begin():
            sql = text("UPDATE dm.dm_user SET passhash = :pw, modified = EXTRACT(EPOCH FROM now())::integer WHERE name = :username")
            conn.execute(sql, {"pw": hashed_pw, "username": username})

    return {"detail": "Password has been reset successfully."}


if __name__ == "__main__":
    uvicorn.run(app, port=5000)
