FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.5.1 /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN UV_LINK_MODE=copy uv sync --locked --no-dev --no-install-project

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY src/ ./src/
COPY alembic.ini ./
COPY alembic/ ./alembic/

# 배포 커밋 — 버전 등록 시 versions·version_changes.git_commit에 기록 (CD build-arg)
ARG GIT_COMMIT=""
ENV GIT_COMMIT=${GIT_COMMIT}

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1