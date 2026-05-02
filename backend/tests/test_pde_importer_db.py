"""Integration test pde_importer (DB reale) — Sprint 3.7 (delta-sync).

Richiede Postgres locale via `docker compose up -d db` + migrazioni
applicate (azienda 'trenord' seed + 0004 row_hash).

⚠️ TEST DISTRUTTIVO ⚠️

Il `_wipe_corse` autouse cancella **TUTTE** le corse, turni, giri,
programmi, stazioni del DB (no WHERE filtrante). È stato pensato per
un DB di CI temporaneo, ma su un DB di sviluppo con dati reali (es.
PdE Trenord 2025-2026 importato dall'utente, 6.536 corse persistenti
sul volume Docker `colazione_pgdata`) **distrugge i dati di lavoro**.

Per questa ragione, dal 2026-05-01 (entry 67) il modulo è skippato di
default. Per eseguirlo:

    ALLOW_DESTRUCTIVE_DB_TESTS=1 uv run pytest tests/test_pde_importer_db.py

Settare la variabile **solo** in CI o su DB temporanei usa-e-getta.
Mai su DB di sviluppo con dati di lavoro.

Set `SKIP_DB_TESTS=1` per saltare anche se la variabile sopra è
attiva (override di emergenza).

Usa la fixture canonica `tests/fixtures/pde_sample.xlsx` (38 righe
Trenord).

Coverage del nuovo modello "ogni riga PdE = una riga DB":
- **No-train-left-behind**: COUNT(*) DB = righe lette dal file (38)
- Idempotenza globale via SHA-256 file: re-import = skip
- Force re-import: tutti gli id stabili (kept=38, create=0, delete=0)
- Modifica fixture in-place tramite `--force` su file diverso → simulazione delta
- Round-trip: una corsa specifica con row_hash valorizzato
- Edge cases: azienda inesistente, file mancante
- Invariante post-import (COUNT(*) == hash unici)
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

# Doppia guardia:
# 1. SKIP_DB_TESTS=1 → skip universale (no DB, es. unit-only run)
# 2. Default (ALLOW_DESTRUCTIVE_DB_TESTS != "1") → skip per
#    proteggere dati di sviluppo. Vedi docstring del modulo per
#    quando attivare il flag.
pytestmark = [
    pytest.mark.skipif(
        os.getenv("SKIP_DB_TESTS") == "1",
        reason="DB not configured for tests",
    ),
    pytest.mark.skipif(
        os.getenv("ALLOW_DESTRUCTIVE_DB_TESTS") != "1",
        reason=(
            "Test DISTRUTTIVO: il _wipe_corse cancella TUTTE le corse/"
            "turni/giri/stazioni del DB senza WHERE. Skip di default per "
            "proteggere dati di lavoro. Settare ALLOW_DESTRUCTIVE_DB_TESTS=1 "
            "per eseguirlo (vedi docstring del modulo)."
        ),
    ),
]

FIXTURE = Path(__file__).parent / "fixtures" / "pde_sample.xlsx"
FIXTURE_N_ROWS = 38  # righe nella fixture (ground truth)


# =====================================================================
# Helpers di cleanup
# =====================================================================


async def _wipe_corse(session: AsyncSession) -> None:
    """Cancella corse + composizioni + run + stazioni.

    Sprint 5.6: ordine esteso per gestire FK aggiunte (whitelist sede,
    accoppiamenti materiali, depot.stazione_principale_codice). Le
    tabelle figlie vanno svuotate prima delle stazioni.

    Sprint 7.5 fix: aggiunto `DELETE FROM turno_pdc` come prima
    istruzione. `turno_pdc_blocco.{corsa_commerciale_id,
    corsa_materiale_vuoto_id}` sono FK RESTRICT — senza pulire i
    turni PdC, il wipe corse fallisce con `ForeignKeyViolation`.
    """
    # FK RESTRICT su turno_pdc_blocco → corse: pulire i turni PRIMA.
    await session.execute(text("DELETE FROM turno_pdc"))
    # Wipe entità che dipendono da giri (se eventualmente presenti).
    # Sprint 7.7 MR 3: giro_variante droppato (ora 1 giornata = 1 sequenza
    # canonica, niente step intermedio).
    await session.execute(text("DELETE FROM corsa_materiale_vuoto"))
    await session.execute(text("DELETE FROM giro_blocco"))
    await session.execute(text("DELETE FROM giro_giornata"))
    await session.execute(text("DELETE FROM giro_materiale"))
    # Wipe filtri/composizioni dei programmi (riferiscono materiale_tipo).
    await session.execute(text("DELETE FROM programma_regola_assegnazione"))
    await session.execute(text("DELETE FROM programma_materiale"))
    # Wipe whitelist sede + accoppiamenti (fk a stazione/materiale_tipo).
    await session.execute(text("DELETE FROM localita_stazione_vicina"))
    await session.execute(text("DELETE FROM materiale_accoppiamento_ammesso"))
    # Sgancia depot.stazione_principale_codice prima di cancellare stazioni.
    await session.execute(text("UPDATE depot SET stazione_principale_codice = NULL"))
    # Sgancia materiale_tipo.localita_manutenzione_default_id prima di
    # cancellare località (non serve qui ma per coerenza wipe).
    # Wipe corse + run + stazioni (ordine FK-safe).
    await session.execute(text("DELETE FROM corsa_composizione"))
    await session.execute(text("DELETE FROM corsa_commerciale"))
    await session.execute(text("DELETE FROM corsa_import_run"))
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
# Primo import — "no train left behind"
# =====================================================================


async def test_first_import_no_train_left_behind() -> None:
    """INVARIANTE CRITICA: ogni riga del file PdE diventa una riga in DB.

    La fixture ha 38 righe → DB deve avere esattamente 38 corse. Questa
    è la garanzia anti-perdita-dati di Sprint 3.7.
    """
    summary = await importa_pde(FIXTURE, azienda_codice="trenord")
    assert summary.skipped is False
    assert summary.n_total == FIXTURE_N_ROWS
    assert summary.n_create == FIXTURE_N_ROWS
    assert summary.n_delete == 0
    assert summary.n_kept == 0
    assert summary.run_id is not None

    async with session_scope() as session:
        n = await session.scalar(select(text("COUNT(*)")).select_from(CorsaCommerciale))
        assert n == FIXTURE_N_ROWS, (
            f"PERDITA DATI: {FIXTURE_N_ROWS} righe nel PdE → {n} corse in DB."
        )


async def test_first_import_creates_n_composizioni() -> None:
    """Ogni corsa ha 9 composizioni → 38×9 = 342."""
    await importa_pde(FIXTURE, azienda_codice="trenord")
    async with session_scope() as session:
        n = await session.scalar(select(text("COUNT(*)")).select_from(CorsaComposizione))
        assert n == FIXTURE_N_ROWS * 9


async def test_first_import_run_completed_with_delta_note() -> None:
    summary = await importa_pde(FIXTURE, azienda_codice="trenord")
    async with session_scope() as session:
        run = await session.get(CorsaImportRun, summary.run_id)
        assert run is not None
        assert run.completed_at is not None
        assert run.n_corse == FIXTURE_N_ROWS
        assert run.n_corse_create == FIXTURE_N_ROWS
        # n_corse_update viene riusato per "deleted" in delta-sync
        assert run.n_corse_update == 0
        assert run.source_hash is not None
        assert len(run.source_hash) == 64
        assert run.source_file == "pde_sample.xlsx"
        assert run.note is not None
        assert "delta-sync" in run.note
        assert "kept=0" in run.note
        assert "create=38" in run.note


async def test_first_import_creates_stazioni_with_fk_valid() -> None:
    """Stazioni create al volo, ogni corsa ha FK valida origine + destinazione."""
    await importa_pde(FIXTURE, azienda_codice="trenord")
    async with session_scope() as session:
        n_stazioni = await session.scalar(select(text("COUNT(*)")).select_from(text("stazione")))
        assert n_stazioni >= 10
        result = await session.execute(
            text("""
                SELECT COUNT(*) FROM corsa_commerciale c
                JOIN stazione so ON so.codice = c.codice_origine
                JOIN stazione sd ON sd.codice = c.codice_destinazione
            """)
        )
        assert result.scalar_one() == FIXTURE_N_ROWS


async def test_row_hash_populated_and_unique() -> None:
    """Ogni corsa ha row_hash 64-char unico (SHA-256 della riga del PdE)."""
    await importa_pde(FIXTURE, azienda_codice="trenord")
    async with session_scope() as session:
        result = await session.execute(
            select(CorsaCommerciale.row_hash).select_from(CorsaCommerciale)
        )
        hashes = [h for (h,) in result.all()]
        assert len(hashes) == FIXTURE_N_ROWS
        for h in hashes:
            assert len(h) == 64
            assert all(c in "0123456789abcdef" for c in h)
        # Tutte le 38 righe della fixture sono distinte → 38 hash unici
        assert len(set(hashes)) == FIXTURE_N_ROWS


# =====================================================================
# Idempotenza file (SHA-256 globale)
# =====================================================================


async def test_reimport_same_file_is_skipped() -> None:
    """Stesso SHA-256 file → skip totale, run riusato."""
    summary1 = await importa_pde(FIXTURE, azienda_codice="trenord")
    summary2 = await importa_pde(FIXTURE, azienda_codice="trenord")

    assert summary2.skipped is True
    assert summary2.skip_reason is not None
    assert summary2.run_id == summary1.run_id

    async with session_scope() as session:
        n_run = await session.scalar(select(text("COUNT(*)")).select_from(CorsaImportRun))
        assert n_run == 1


# =====================================================================
# Force re-import: delta-sync con file invariato → tutti id stabili
# =====================================================================


async def test_reimport_with_force_keeps_all_ids_stable() -> None:
    """--force su stesso file: kept=38 (tutti hash matchano), create=0, delete=0.

    Verifica forte di stabilità id: re-import del PdE invariato non
    cancella nulla. Pronto per Sprint 4 (giri materiali su corsa.id).
    """
    summary1 = await importa_pde(FIXTURE, azienda_codice="trenord")

    # Snapshot id prima del re-import
    async with session_scope() as session:
        result = await session.execute(
            select(CorsaCommerciale.id, CorsaCommerciale.row_hash).order_by(CorsaCommerciale.id)
        )
        ids_before = {h: cid for cid, h in result.all()}

    summary2 = await importa_pde(FIXTURE, azienda_codice="trenord", force=True)

    assert summary2.skipped is False
    assert summary2.n_total == FIXTURE_N_ROWS
    assert summary2.n_kept == FIXTURE_N_ROWS  # tutte invariate
    assert summary2.n_create == 0
    assert summary2.n_delete == 0
    assert summary2.run_id != summary1.run_id

    # Stabilità id: stessi (id, row_hash) prima e dopo
    async with session_scope() as session:
        result = await session.execute(
            select(CorsaCommerciale.id, CorsaCommerciale.row_hash).order_by(CorsaCommerciale.id)
        )
        ids_after = {h: cid for cid, h in result.all()}
    assert ids_before == ids_after, "id non stabili: re-import senza modifiche ha cambiato gli id"

    # Composizioni totali e run totali coerenti
    async with session_scope() as session:
        n_corse = await session.scalar(select(text("COUNT(*)")).select_from(CorsaCommerciale))
        n_comp = await session.scalar(select(text("COUNT(*)")).select_from(CorsaComposizione))
        n_run = await session.scalar(select(text("COUNT(*)")).select_from(CorsaImportRun))
        assert n_corse == FIXTURE_N_ROWS
        assert n_comp == FIXTURE_N_ROWS * 9
        assert n_run == 2


# =====================================================================
# Round-trip
# =====================================================================


async def test_corsa_round_trip_first_row() -> None:
    """Treno 13 (riga 0 fixture) salvato in DB ha campi attesi."""
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
        assert len(corsa.row_hash) == 64


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
    with pytest.raises(ValueError, match="non trovata"):
        await importa_pde(FIXTURE, azienda_codice="nonesisto")


async def test_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        await importa_pde(Path("/tmp/file-che-non-esiste.xlsx"), azienda_codice="trenord")
