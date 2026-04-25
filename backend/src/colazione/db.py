"""Async SQLAlchemy engine + session management.

Sprint 1.3: skeleton del layer DB. Le route useranno `get_session` come
FastAPI dependency, le migrazioni Alembic useranno l'engine sync con
URL derivata.

Vedi `docs/STACK-TECNICO.md` §3 (PostgreSQL 16, psycopg3 async).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from colazione.config import get_settings


class Base(DeclarativeBase):
    """Base ORM dichiarativa. Tutti i modelli ereditano da qui.

    I modelli vivono in `colazione/models/` (uno per entità, vedi
    Sprint 1.7).
    """


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Singleton dell'engine async (lazy init)."""
    global _engine, _session_factory
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.debug,
            pool_pre_ping=True,
        )
        _session_factory = async_sessionmaker(
            _engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Factory di sessioni async, condivisa per tutti i call site."""
    if _session_factory is None:
        get_engine()  # inizializza
    assert _session_factory is not None
    return _session_factory


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Context manager async per usi standalone (script CLI, test, ecc.).

    Esempio::

        async with session_scope() as session:
            result = await session.execute(text("SELECT 1"))
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency. Yields una sessione per request.

    Uso::

        from fastapi import Depends
        from colazione.db import get_session

        @router.get("/foo")
        async def foo(session: AsyncSession = Depends(get_session)):
            ...
    """
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def dispose_engine() -> None:
    """Chiude l'engine. Da chiamare al shutdown app."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
