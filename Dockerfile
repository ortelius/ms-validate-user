FROM cgr.dev/chainguard/python:latest-dev AS builder
COPY . /app
RUN cd /app && pip install -r requirements.txt

FROM cgr.dev/chainguard/python:3.11.2@sha256:54b8f7aa6420173981c82ab19009ab3ba8ae2b0aec59f2910379682790cb8684
ENV DB_HOST localhost
ENV DB_NAME postgres
ENV DB_USER postgres
ENV DB_PASS postgres
ENV DB_PORT 5432

COPY --from=builder /app /app
COPY --from=builder /home/nonroot/.local /home/nonroot/.local

WORKDIR /app

EXPOSE 8080
ENV PATH=$PATH:/home/nonroot/.local/bin

ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
