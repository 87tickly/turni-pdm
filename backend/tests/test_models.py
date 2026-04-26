"""Smoke test dei modelli ORM (Sprint 1.7, aggiornato Sprint 4.1).

Verifica:
- Tutti i modelli si importano senza errori
- Si registrano sul `Base.metadata`
- Ogni nome tabella ORM corrisponde a una tabella reale del DB

Conteggio: 31 (modello v0.5 base) + 2 (Sprint 4.1: ProgrammaMateriale,
ProgrammaRegolaAssegnazione) = 33.
"""

import os

import pytest
from sqlalchemy import text

from colazione import models
from colazione.db import Base, session_scope

EXPECTED_TABLE_COUNT = 33


def _db_available() -> bool:
    return os.getenv("SKIP_DB_TESTS") != "1"


def test_models_register_on_metadata() -> None:
    """Tutti i modelli registrati sulla Base.metadata."""
    table_names = set(Base.metadata.tables.keys())
    assert len(table_names) == EXPECTED_TABLE_COUNT, (
        f"Expected {EXPECTED_TABLE_COUNT} tables, got {len(table_names)}"
    )


def test_models_all_exported() -> None:
    """`from colazione.models import *` espone le 31 classi previste."""
    assert len(models.__all__) == EXPECTED_TABLE_COUNT
    for name in models.__all__:
        assert hasattr(models, name), f"{name} listato in __all__ ma non importabile"


@pytest.mark.skipif(not _db_available(), reason="DB not configured for tests")
@pytest.mark.asyncio
async def test_models_match_db_tables() -> None:
    """I `__tablename__` ORM matchano le tabelle reali create da 0001."""
    orm_tables = set(Base.metadata.tables.keys())

    async with session_scope() as session:
        result = await session.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' AND tablename != 'alembic_version'"
            )
        )
        db_tables = {row.tablename for row in result.all()}

    missing_in_db = orm_tables - db_tables
    missing_in_orm = db_tables - orm_tables
    assert not missing_in_db, f"ORM ha tabelle non presenti in DB: {missing_in_db}"
    assert not missing_in_orm, f"DB ha tabelle non mappate in ORM: {missing_in_orm}"
