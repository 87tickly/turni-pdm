"""Conteggio diagnostico turni PdC orfani (deposito_pdc_id IS NULL).

Sprint 8.2 MR-PD2: la migration 0043 cancella i turni orfani prima di
applicare il vincolo NOT NULL. Questo script conta quanti record
verrebbero cancellati senza eseguire la DELETE — utile per validare
l'impatto in produzione.

Uso: ``railway run --service backend uv run python scripts/check_turni_orfani.py``
oppure locale: ``cd backend && uv run python scripts/check_turni_orfani.py``.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Aggiungi src/ al path: gli script standalone non ereditano da
# `[tool.pytest.ini_options].pythonpath`. Pattern coerente con altri
# script in `backend/scripts/`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import text  # noqa: E402

from colazione.db import session_scope  # noqa: E402


async def _main() -> None:
    async with session_scope() as session:
        orfani = (
            await session.execute(
                text("SELECT COUNT(*) FROM turno_pdc WHERE deposito_pdc_id IS NULL")
            )
        ).scalar()
        totali = (
            await session.execute(text("SELECT COUNT(*) FROM turno_pdc"))
        ).scalar()
        print(f"turni_orfani={orfani}")
        print(f"turni_totali={totali}")
        if totali:
            pct = (orfani or 0) / totali * 100
            print(f"percentuale_orfani={pct:.1f}%")


if __name__ == "__main__":
    asyncio.run(_main())
