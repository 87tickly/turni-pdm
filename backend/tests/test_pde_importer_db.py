"""Integration test pde_importer (DB reale) — Sprint 3.6.

Richiede Postgres locale via `docker compose up -d db` + migrazioni
applicate (azienda 'trenord' seed).

Set `SKIP_DB_TESTS=1` per saltare. Usa la fixture canonica
`tests/fixtures/pde_sample.xlsx` (38 righe Trenord).

Coverage:
- Primo import: 38 corse, 342 composizioni, run completato, stazioni create
- Idempotenza: re-import stesso file → skip (run riusato)
- Forza: --force → 0 create, 38 update (composizioni rimpiazzate)
- Round-trip: una corsa specifica letta dal DB matcha il parser
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.db import dispose_engine, session_scope
from colazione.importers.pde_importer import importa_pde
from colazione.models.corse import (
    CorsaCommerciale,
    CorsaComposizione,
    CorsaImportRun,
)

pytestmark = pytest.mark.skipif(
    os.getenv("SKIP_DB_TESTS") == "1",
    reason="DB not configured for tests",
)

FIXTURE = Path(__file__).parent / "fixtures" / "pde_sample.xlsx"


# =====================================================================
# Helpers di cleanup
# =====================================================================


async def _wipe_corse(session: AsyncSession) -> None:
    """Cancella tutte le corse + composizioni + run + stazioni orfane.

    Le composizioni cascadano via FK al delete della corsa, ma faccio
    DELETE espliciti per non dipendere da Postgres.
    """
    await session.execute(text("DELETE FROM corsa_composizione"))
    await session.execute(text("DELETE FROM corsa_commerciale"))
    await session.execute(text("DELETE FROM corsa_import_run"))
    # Stazioni: cancello quelle non riferite da nessun'altra tabella.
    # Nei test la fixture crea solo stazioni nuove, mai pre-esistenti
    # (il seed Trenord 0002 non popola `stazione`).
    await session.execute(text("DELETE FROM stazione"))


@pytest.fixture(autouse=True)
async def clean_state() -> None:
    """Wipe state prima di ogni test (ognuno è indipendente)."""
    async with session_scope() as session:
        await _wipe_corse(session)


@pytest.fixture(scope="module", autouse=True)
async def cleanup_engine() -> None:
    """Dispose async engine al termine del modulo."""
    yield
    await dispose_engine()


# =====================================================================
# Primo import
# =====================================================================


async def test_first_import_creates_38_corse() -> None:
    summary = await importa_pde(FIXTURE, azienda_codice="trenord")
    assert summary.skipped is False
    assert summary.n_create == 38
    assert summary.n_update == 0
    assert summary.run_id is not None

    async with session_scope() as session:
        n = await session.scalar(select(text("COUNT(*)")).select_from(CorsaCommerciale))
        assert n == 38


async def test_first_import_creates_342_composizioni() -> None:
    """38 corse × 9 composizioni per corsa = 342 record."""
    await importa_pde(FIXTURE, azienda_codice="trenord")
    async with session_scope() as session:
        n = await session.scalar(select(text("COUNT(*)")).select_from(CorsaComposizione))
        assert n == 342


async def test_first_import_run_completed() -> None:
    summary = await importa_pde(FIXTURE, azienda_codice="trenord")
    async with session_scope() as session:
        run = await session.get(CorsaImportRun, summary.run_id)
        assert run is not None
        assert run.completed_at is not None
        assert run.n_corse == 38
        assert run.n_corse_create == 38
        assert run.n_corse_update == 0
        assert run.source_hash is not None
        assert len(run.source_hash) == 64
        assert run.source_file == "pde_sample.xlsx"
        assert run.note is not None
        assert "warning" in run.note.lower()


async def test_first_import_upserts_stazioni_dynamically() -> None:
    """Le stazioni del PdE non sono pre-seedate: il import le crea."""
    await importa_pde(FIXTURE, azienda_codice="trenord")
    async with session_scope() as session:
        n_stazioni = await session.scalar(select(text("COUNT(*)")).select_from(text("stazione")))
        # La fixture ha 38 corse con varie stazioni. Mi aspetto >= 10 (tante linee diverse)
        assert n_stazioni >= 10
        # E ogni corsa deve avere FK valida (origine + destinazione presenti)
        result = await session.execute(
            text("""
            SELECT COUNT(*) FROM corsa_commerciale c
            JOIN stazione so ON so.codice = c.codice_origine
            JOIN stazione sd ON sd.codice = c.codice_destinazione
        """)
        )
        n_with_fk = result.scalar_one()
        assert n_with_fk == 38


# =====================================================================
# Idempotenza
# =====================================================================


async def test_reimport_same_file_is_skipped() -> None:
    summary1 = await importa_pde(FIXTURE, azienda_codice="trenord")
    summary2 = await importa_pde(FIXTURE, azienda_codice="trenord")

    assert summary2.skipped is True
    assert summary2.skip_reason is not None
    # Skip rinvia al run originale, non ne crea uno nuovo
    assert summary2.run_id == summary1.run_id
    # E il count totale di run resta 1
    async with session_scope() as session:
        n_run = await session.scalar(select(text("COUNT(*)")).select_from(CorsaImportRun))
        assert n_run == 1


async def test_reimport_with_force_overwrites_as_update() -> None:
    """--force riprocessa: 0 create, 38 update (le corse esistono già)."""
    summary1 = await importa_pde(FIXTURE, azienda_codice="trenord")
    summary2 = await importa_pde(FIXTURE, azienda_codice="trenord", force=True)

    assert summary2.skipped is False
    assert summary2.n_create == 0
    assert summary2.n_update == 38
    # Nuovo run creato (force = nuovo tracking)
    assert summary2.run_id != summary1.run_id

    # Le composizioni restano 342 (le 9 vecchie sostituite con 9 nuove)
    async with session_scope() as session:
        n_corse = await session.scalar(select(text("COUNT(*)")).select_from(CorsaCommerciale))
        n_comp = await session.scalar(select(text("COUNT(*)")).select_from(CorsaComposizione))
        n_run = await session.scalar(select(text("COUNT(*)")).select_from(CorsaImportRun))
        assert n_corse == 38
        assert n_comp == 342
        assert n_run == 2


# =====================================================================
# Round-trip — verifica che i dati salvati matchino il parser
# =====================================================================


async def test_corsa_round_trip_first_row() -> None:
    """Treno 13 (riga 0 fixture) salvato in DB ha campi attesi.

    Spec dalla fixture (verificata in test_pde_row_parser):
    - numero_treno = '13', rete = 'FN'
    - origine = S01066, destinazione = S01747
    - valido 14/12/2025 → 31/12/2026 (383 giorni)
    """
    await importa_pde(FIXTURE, azienda_codice="trenord")
    async with session_scope() as session:
        result = await session.execute(
            select(CorsaCommerciale).where(CorsaCommerciale.numero_treno == "13").limit(1)
        )
        corsa = result.scalar_one_or_none()
        assert corsa is not None
        assert corsa.rete == "FN"
        assert corsa.codice_origine == "S01066"
        assert corsa.codice_destinazione == "S01747"
        assert corsa.is_treno_garantito_feriale is True
        assert corsa.is_treno_garantito_festivo is False
        assert corsa.giorni_per_mese_json["gg_anno"] == 365
        assert len(corsa.valido_in_date_json) == 383


async def test_composizioni_round_trip_first_row() -> None:
    """La corsa treno 13 ha esattamente 9 composizioni (3×3)."""
    await importa_pde(FIXTURE, azienda_codice="trenord")
    async with session_scope() as session:
        result = await session.execute(
            select(CorsaCommerciale.id).where(CorsaCommerciale.numero_treno == "13").limit(1)
        )
        corsa_id = result.scalar_one()

        comp_result = await session.execute(
            select(CorsaComposizione).where(CorsaComposizione.corsa_commerciale_id == corsa_id)
        )
        composizioni = comp_result.scalars().all()
        assert len(composizioni) == 9
        keys = {(c.stagione, c.giorno_tipo) for c in composizioni}
        assert keys == {
            ("invernale", "feriale"),
            ("invernale", "sabato"),
            ("invernale", "festivo"),
            ("estiva", "feriale"),
            ("estiva", "sabato"),
            ("estiva", "festivo"),
            ("agosto", "feriale"),
            ("agosto", "sabato"),
            ("agosto", "festivo"),
        }


# =====================================================================
# Edge case
# =====================================================================


async def test_unknown_azienda_raises() -> None:
    """Codice azienda inesistente → ValueError chiaro."""
    with pytest.raises(ValueError, match="non trovata"):
        await importa_pde(FIXTURE, azienda_codice="nonesisto")


async def test_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        await importa_pde(Path("/tmp/file-che-non-esiste.xlsx"), azienda_codice="trenord")
