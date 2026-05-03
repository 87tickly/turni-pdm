# =====================================================================
# Backend Dockerfile — colazione FastAPI
# =====================================================================

FROM python:3.12-slim AS base

# Install uv from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (cached layer)
COPY pyproject.toml ./
COPY uv.lock* ./
RUN uv sync --no-dev --no-install-project

# Copy source
COPY src ./src
COPY alembic.ini* ./
COPY alembic ./alembic
COPY scripts ./scripts

# Install project (without re-installing deps)
RUN uv sync --no-dev

# Railway inietta $PORT dinamicamente; default 8000 in locale.
ENV PORT=8000
EXPOSE 8000

# Migration + start. `sh -c` necessario per espandere $PORT.
CMD ["sh", "-c", "alembic upgrade head && uvicorn colazione.main:app --host 0.0.0.0 --port ${PORT}"]
