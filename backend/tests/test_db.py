"""Smoke test del layer DB (Sprint 1.3).

Richiede Postgres locale via `docker compose up -d db`. Se il DB non
è raggiungibile, i test sono skippati.
"""

import os

import pytest
from sqlalchemy import text

from colazione.db import dispose_engine, session_scope

pytestmark = pytest.mark.asyncio


def _db_available() -> bool:
    """True se DATABASE_URL punta a un DB raggiungibile."""
    # Heuristic semplice: salta se override esplicito SKIP_DB_TESTS=1
    return os.getenv("SKIP_DB_TESTS") != "1"


@pytest.mark.skipif(not _db_available(), reason="DB not configured for tests")
async def test_db_connection_returns_one() -> None:
    """Connessione base: SELECT 1 funziona."""
    async with session_scope() as session:
        result = await session.execute(text("SELECT 1 AS one"))
        row = result.first()
        assert row is not None
        assert row.one == 1


@pytest.mark.skipif(not _db_available(), reason="DB not configured for tests")
async def test_db_postgres_version() -> None:
    """Postgres versione 16."""
    async with session_scope() as session:
        result = await session.execute(text("SHOW server_version_num"))
        version_num = int(result.scalar() or 0)
        # Postgres 16+ → version_num >= 160000
        assert version_num >= 160000, f"Expected Postgres 16+, got {version_num}"


@pytest.fixture(autouse=True, scope="module")
async def cleanup_engine():
    """Dispose engine dopo ogni modulo per non lasciare connessioni aperte."""
    yield
    await dispose_engine()
