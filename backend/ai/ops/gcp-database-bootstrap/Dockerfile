FROM ghcr.io/astral-sh/uv:0.11.19@sha256:b46b03ddfcfbf8f547af7e9eaefdf8a39c8cebcba7c98858d3162bd28cf536f6 AS uv

FROM python:3.14.6-slim-trixie@sha256:cea0e6040540fb2b965b6e7fb5ffa00871e632eef63719f0ea54bca189ce14a6 AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/opt/vfbiz/.venv/bin:${PATH}"

COPY --from=uv /uv /uvx /bin/

WORKDIR /opt/vfbiz
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-editable --group gcp-bootstrap

FROM cgr.dev/chainguard/python:latest@sha256:231d4a76e8521327dbb3c23094b2c41151501845d2656da3c1a0610981c496c5

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="/opt/vfbiz/.venv/lib/python3.14/site-packages"

WORKDIR /opt/vfbiz
COPY --from=builder /opt/vfbiz/.venv ./.venv
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
COPY scripts/__init__.py scripts/provision_document_ai_database_identities.py scripts/bootstrap_document_ai_database.py ./scripts/

USER 65532:65532

ENTRYPOINT ["/usr/bin/python3.14"]
CMD ["-m", "scripts.bootstrap_document_ai_database"]
