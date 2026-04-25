"""Alembic env.py — supporto async + lettura DATABASE_URL da env.

Lo schema target è definito in `colazione.db.Base.metadata`. I modelli
ORM (Sprint 1.7) si registrano in metadata semplicemente facendo
`from colazione.models import *` qui sotto.

Per ora (Sprint 1.4) Base.metadata è vuoto: la migrazione 0001
(Sprint 1.5) creerà esplicitamente le tabelle senza fare affidamento
su autogenerate, perché lo schema è disegnato a mano in
`docs/SCHEMA-DATI-NATIVO.md`.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from colazione.config import get_settings
from colazione.db import Base

# Alembic Config object: accesso ai valori del .ini
config = context.config

# Setup logging Python da [loggers] / [handlers] / [formatters]
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override sqlalchemy.url con quella di runtime (env)
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

# Metadata target per autogenerate (vuoto in v0, popolato in 1.7)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Esegue le migrazioni in 'offline mode' (senza connettersi al DB)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Esegue le migrazioni in 'online mode' con connessione async."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point sync; lancia il loop async."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
