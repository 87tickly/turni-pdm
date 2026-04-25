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

# Install project (without re-installing deps)
RUN uv sync --no-dev

EXPOSE 8000

CMD ["uvicorn", "colazione.main:app", "--host", "0.0.0.0", "--port", "8000"]
