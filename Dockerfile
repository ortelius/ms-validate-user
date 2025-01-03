FROM cgr.dev/chainguard/python:latest-dev@sha256:d9e1598a9f44205d4182c0c54196f7dd6e73ac8cf15cf57ab063ac431b84b5f8 AS builder

COPY . /app

WORKDIR /app
ENV PATH=/home/nonroot/.local/bin:$PATH

# hadolint ignore=DL4006
RUN wget -q -O - https://install.python-poetry.org | python -
RUN poetry install --no-root;

FROM cgr.dev/chainguard/python:latest@sha256:f488e4481f27bb0e2c312a4e2e0383b7ddbc62dd03290ef7a5e9459fde32447b
USER nonroot
ENV DB_HOST localhost
ENV DB_NAME postgres
ENV DB_USER postgres
ENV DB_PASS postgres
ENV DB_PORT 5432

COPY --from=builder /app /app
COPY --from=builder /home/nonroot /home/nonroot

WORKDIR /app

EXPOSE 8080
ENV PATH=$PATH:/home/nonroot/.local/bin

HEALTHCHECK CMD curl --fail http://localhost:8080/health || exit 1

ENTRYPOINT ["poetry", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
