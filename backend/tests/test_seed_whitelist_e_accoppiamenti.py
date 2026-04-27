"""Test integration Sprint 5.2 — script seed whitelist + accoppiamenti.

Verifica:
- happy path: lo script popola materiali famiglia, whitelist, accoppiamenti
- idempotenza: 2 esecuzioni consecutive non duplicano (counter skip)
- errori espliciti: pattern stazione 0/N match, materiale mancante,
  accoppiamento non normalizzato, azienda inesistente
- dry_run: tutto in transazione, rollback, 0 scritture persistite

Setup completamente isolato (azienda + sedi + stazioni TEST_SEED_*) per
non interferire con altri test del DB.

Set ``SKIP_DB_TESTS=1`` per saltare.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

from colazione.db import dispose_engine, session_scope

# Lo script seed vive in scripts/, non in src/. Aggiungo a sys.path per import.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# ruff: noqa: E402  (import dopo sys.path manipulation)
from seed_whitelist_e_accoppiamenti import (
    SeedError,
    _MaterialeFamiglia,
    seed_all,
)

pytestmark = pytest.mark.skipif(
    os.getenv("SKIP_DB_TESTS") == "1",
    reason="DB not configured for tests",
)

# =====================================================================
# Setup isolato
# =====================================================================

_TEST_AZIENDA_CODICE = "trenord_test_seed"

# 6 sedi mock (codici TEST_SEED_*, codice_breve formato ^[A-Z]{2,8}$)
_TEST_SEDI: list[tuple[str, str]] = [
    ("TEST_SEED_FIO", "TFIO"),
    ("TEST_SEED_NOV", "TNOV"),
    ("TEST_SEED_CAM", "TCAM"),
    ("TEST_SEED_LEC", "TLEC"),
    ("TEST_SEED_CRE", "TCRE"),
    ("TEST_SEED_ISE", "TISE"),
]

# 12 stazioni mock (codici TEST_SEED_*, nomi reali per il pattern matching)
_TEST_STAZIONI: list[tuple[str, str]] = [
    ("TSGAR", "Milano P. Garibaldi"),
    ("TSCEN", "Milano Centrale"),
    ("TSLAM", "Milano Lambrate"),
    ("TSROG", "Milano Rogoredo"),
    ("TSGRP", "Milano Greco Pirelli"),
    ("TSCAD", "Milano Cadorna"),
    ("TSBOV", "Milano Bovisa"),
    ("TSSAR", "Saronno"),
    ("TSSEV", "Seveso"),
    ("TSLCO", "Lecco"),
    ("TSCRE", "Cremona"),
    ("TSISE", "Iseo"),
]

# Whitelist usando i codici delle sedi mock (override di WHITELIST_TRENORD).
# I pattern restano uguali ai default del seed di produzione.
_TEST_WHITELIST: dict[str, list[str]] = {
    "TEST_SEED_FIO": [
        "%MILANO%GARIBALDI%",
        "%MILANO%CENTRALE%",
        "%MILANO%LAMBRATE%",
        "%MILANO%ROGOREDO%",
        "%MILANO%GRECO%PIRELLI%",
    ],
    "TEST_SEED_NOV": [
        "%MILANO%CADORNA%",
        "%MILANO%BOVISA%",
        "Saronno",
    ],
    "TEST_SEED_CAM": [
        "Seveso",
        "Saronno",
    ],
    "TEST_SEED_LEC": ["Lecco"],
    "TEST_SEED_CRE": ["Cremona"],
    "TEST_SEED_ISE": ["Iseo"],
}

# Materiali: 16 famiglie create dallo script.
# Whitelist: 13 entry (5+3+2+1+1+1, Saronno×2 sedi).
# Accoppiamenti: 6 di 8 testabili in isolamento. Esclusi ATR115+ATR125 e
# ATR125+ATR125 perché ATR115/ATR125 sono pezzi del seed 0002 (azienda
# trenord reale, vincolo UNIQUE globale su codice — non riproducibili
# nell'azienda mock `trenord_test_seed`).
_EXPECTED_MATERIALI = 16
_EXPECTED_WHITELIST = 13
_EXPECTED_ACCOPPIAMENTI = 6

# Accoppiamenti testabili in isolamento (escludono ATR115/ATR125).
_TEST_ACCOPPIAMENTI: list[tuple[str, str]] = [
    ("ETR421", "ETR421"),
    ("ETR425", "ETR526"),
    ("ETR526", "ETR526"),
    ("ETR204", "ETR204"),
    ("E464", "MD"),
    ("E464", "Vivalto"),
]


async def _wipe_seed_test_data() -> None:
    """Pulisce TUTTO il setup isolato del test (azienda + sedi +
    stazioni + materiali ETR + righe correlate).

    Ordine FK-safe:
      whitelist → accoppiamenti → stazioni → sedi → materiali ETR → azienda
    """
    async with session_scope() as session:
        # whitelist (FK su sede + stazione)
        await session.execute(
            text(
                "DELETE FROM localita_stazione_vicina "
                "WHERE localita_manutenzione_id IN ("
                "  SELECT id FROM localita_manutenzione WHERE codice LIKE 'TEST_SEED_%'"
                ")"
            )
        )
        await session.execute(
            text("DELETE FROM localita_stazione_vicina WHERE stazione_codice LIKE 'TS%'")
        )
        # accoppiamenti FK su materiale_tipo. I codici ETR*/ATR*/ALe*/E464/
        # Vivalto/MD/TAF coprono i 16 materiali famiglia creati dallo script.
        await session.execute(
            text(
                "DELETE FROM materiale_accoppiamento_ammesso "
                "WHERE materiale_a_codice IN "
                "  (SELECT codice FROM materiale_tipo WHERE azienda_id IN "
                "   (SELECT id FROM azienda WHERE codice = :cod))"
                "OR materiale_b_codice IN "
                "  (SELECT codice FROM materiale_tipo WHERE azienda_id IN "
                "   (SELECT id FROM azienda WHERE codice = :cod))"
            ),
            {"cod": _TEST_AZIENDA_CODICE},
        )
        # sedi mock
        await session.execute(
            text("DELETE FROM localita_manutenzione WHERE codice LIKE 'TEST_SEED_%'")
        )
        # stazioni mock
        await session.execute(text("DELETE FROM stazione WHERE codice LIKE 'TS%'"))
        # tutti i materiali dell'azienda mock (16 famiglie create dallo script)
        await session.execute(
            text(
                "DELETE FROM materiale_tipo WHERE azienda_id IN "
                "(SELECT id FROM azienda WHERE codice = :cod)"
            ),
            {"cod": _TEST_AZIENDA_CODICE},
        )
        # azienda mock
        await session.execute(
            text("DELETE FROM azienda WHERE codice = :cod"),
            {"cod": _TEST_AZIENDA_CODICE},
        )


async def _setup_isolated_db() -> int:
    """Crea azienda + 6 sedi + 12 stazioni isolate. Ritorna ``azienda_id``."""
    async with session_scope() as session:
        # azienda
        result = await session.execute(
            text(
                "INSERT INTO azienda (codice, nome) "
                f"VALUES ('{_TEST_AZIENDA_CODICE}', 'Trenord Test Seed') "
                "RETURNING id"
            )
        )
        azienda_id = int(result.scalar_one())

        # sedi
        for codice, codice_breve in _TEST_SEDI:
            await session.execute(
                text(
                    "INSERT INTO localita_manutenzione "
                    "(codice, codice_breve, nome_canonico, azienda_id) "
                    f"VALUES ('{codice}', '{codice_breve}', '{codice}', {azienda_id})"
                )
            )

        # stazioni
        for codice, nome in _TEST_STAZIONI:
            await session.execute(
                text(
                    "INSERT INTO stazione (codice, nome, azienda_id) "
                    f"VALUES ('{codice}', '{nome.replace(chr(39), chr(39) + chr(39))}', "
                    f"{azienda_id})"
                )
            )

    return azienda_id


# =====================================================================
# Fixtures
# =====================================================================


@pytest.fixture(autouse=True)
async def clean_state() -> None:
    """Wipe pre + post (FK leftover su test successivi)."""
    await _wipe_seed_test_data()
    yield
    await _wipe_seed_test_data()


@pytest.fixture(scope="module", autouse=True)
async def cleanup_engine() -> None:
    yield
    await dispose_engine()


# =====================================================================
# Test happy path
# =====================================================================


async def test_seed_happy_path() -> None:
    """Setup isolato + seed_all → 16 materiali + 13 whitelist + 6 accoppiamenti."""
    await _setup_isolated_db()

    async with session_scope() as session:
        report = await seed_all(
            session,
            _TEST_AZIENDA_CODICE,
            whitelist=_TEST_WHITELIST,
            accoppiamenti=_TEST_ACCOPPIAMENTI,
        )

    assert report.materiali_inseriti == _EXPECTED_MATERIALI, report
    assert report.materiali_skippati == 0, report
    assert report.whitelist_inserite == _EXPECTED_WHITELIST, report
    assert report.whitelist_skippate == 0, report
    assert report.accoppiamenti_inseriti == _EXPECTED_ACCOPPIAMENTI, report
    assert report.accoppiamenti_skippati == 0, report

    # Verifica righe persistite (filtra per azienda mock)
    async with session_scope() as session:
        n_mat = (
            await session.execute(
                text(
                    "SELECT COUNT(*) FROM materiale_tipo WHERE azienda_id IN "
                    "(SELECT id FROM azienda WHERE codice = :cod)"
                ),
                {"cod": _TEST_AZIENDA_CODICE},
            )
        ).scalar_one()
        n_white = (
            await session.execute(
                text(
                    "SELECT COUNT(*) FROM localita_stazione_vicina WHERE stazione_codice LIKE 'TS%'"
                )
            )
        ).scalar_one()
        n_accop = (
            await session.execute(
                text(
                    "SELECT COUNT(*) FROM materiale_accoppiamento_ammesso "
                    "WHERE materiale_a_codice IN "
                    "  (SELECT codice FROM materiale_tipo WHERE azienda_id IN "
                    "   (SELECT id FROM azienda WHERE codice = :cod))"
                ),
                {"cod": _TEST_AZIENDA_CODICE},
            )
        ).scalar_one()
    assert n_mat == _EXPECTED_MATERIALI
    assert n_white == _EXPECTED_WHITELIST
    assert n_accop == _EXPECTED_ACCOPPIAMENTI


async def test_seed_etr521_non_in_accoppiamenti() -> None:
    """ETR521 è esplicitamente NON accoppiabile (decisione utente)."""
    await _setup_isolated_db()

    async with session_scope() as session:
        await seed_all(
            session,
            _TEST_AZIENDA_CODICE,
            whitelist=_TEST_WHITELIST,
            accoppiamenti=_TEST_ACCOPPIAMENTI,
        )

    async with session_scope() as session:
        n_accop_521 = (
            await session.execute(
                text(
                    "SELECT COUNT(*) FROM materiale_accoppiamento_ammesso "
                    "WHERE materiale_a_codice = 'ETR521' "
                    "OR materiale_b_codice = 'ETR521'"
                )
            )
        ).scalar_one()
    assert n_accop_521 == 0, "ETR521 non deve apparire in accoppiamenti"


# =====================================================================
# Idempotenza
# =====================================================================


async def test_seed_idempotente_seconda_run_zero_inserts() -> None:
    """Seconda esecuzione: tutti i record già presenti → 0 inserts, N skip."""
    await _setup_isolated_db()

    async with session_scope() as session:
        await seed_all(
            session,
            _TEST_AZIENDA_CODICE,
            whitelist=_TEST_WHITELIST,
            accoppiamenti=_TEST_ACCOPPIAMENTI,
        )

    async with session_scope() as session:
        report = await seed_all(
            session,
            _TEST_AZIENDA_CODICE,
            whitelist=_TEST_WHITELIST,
            accoppiamenti=_TEST_ACCOPPIAMENTI,
        )

    assert report.materiali_inseriti == 0
    assert report.materiali_skippati == _EXPECTED_MATERIALI
    assert report.whitelist_inserite == 0
    assert report.whitelist_skippate == _EXPECTED_WHITELIST
    assert report.accoppiamenti_inseriti == 0
    assert report.accoppiamenti_skippati == _EXPECTED_ACCOPPIAMENTI


# =====================================================================
# Errori
# =====================================================================


async def test_seed_pattern_zero_match_solleva() -> None:
    """Pattern che non matcha alcuna stazione → SeedError esplicito."""
    await _setup_isolated_db()

    bad_whitelist = {
        "TEST_SEED_FIO": ["%STAZIONE_INESISTENTE%"],
    }

    async with session_scope() as session:
        with pytest.raises(SeedError, match="non matcha nessuna stazione"):
            await seed_all(session, _TEST_AZIENDA_CODICE, whitelist=bad_whitelist)


async def test_seed_pattern_multi_match_solleva() -> None:
    """Pattern che matcha N>1 stazioni → SeedError con candidate listate."""
    await _setup_isolated_db()

    # %MILANO% matcha 7 stazioni (Garibaldi/Centrale/Lambrate/Rogoredo/
    # Greco/Cadorna/Bovisa)
    bad_whitelist = {
        "TEST_SEED_FIO": ["%MILANO%"],
    }

    async with session_scope() as session:
        with pytest.raises(SeedError, match="matcha 7 stazioni"):
            await seed_all(session, _TEST_AZIENDA_CODICE, whitelist=bad_whitelist)


async def test_seed_azienda_inesistente_solleva() -> None:
    """Azienda non in DB → SeedError."""
    await _setup_isolated_db()

    async with session_scope() as session:
        with pytest.raises(SeedError, match="non trovata"):
            await seed_all(session, "azienda_inesistente_xyz")


async def test_seed_localita_inesistente_solleva() -> None:
    """Sede della whitelist non presente per l'azienda → SeedError."""
    await _setup_isolated_db()

    bad_whitelist = {
        "TEST_SEED_INESISTENTE": ["%MILANO%CENTRALE%"],
    }

    async with session_scope() as session:
        with pytest.raises(SeedError, match="Località 'TEST_SEED_INESISTENTE'"):
            await seed_all(session, _TEST_AZIENDA_CODICE, whitelist=bad_whitelist)


async def test_seed_accoppiamento_non_normalizzato_solleva() -> None:
    """Accoppiamento (a, b) con a > b → SeedError."""
    await _setup_isolated_db()

    bad_accoppiamenti = [("ETR526", "ETR421")]  # 526 > 421 lex

    async with session_scope() as session:
        with pytest.raises(SeedError, match="non normalizzato"):
            await seed_all(
                session,
                _TEST_AZIENDA_CODICE,
                whitelist=_TEST_WHITELIST,
                accoppiamenti=bad_accoppiamenti,
            )


async def test_seed_accoppiamento_materiale_mancante_solleva() -> None:
    """Accoppiamento con materiale non creato dalla sezione 1 → SeedError."""
    await _setup_isolated_db()

    only_etr421 = [
        _MaterialeFamiglia(
            codice="ETR421",
            nome_commerciale="ETR421",
            famiglia="Caravaggio (Rock)",
            n_casse=4,
            pezzi_inventario=[],
        ),
    ]
    # Accoppiamento ETR526+ETR526: ETR526 non creato → errore in sezione 3
    bad_accoppiamenti = [("ETR526", "ETR526")]

    async with session_scope() as session:
        with pytest.raises(SeedError, match="Materiale 'ETR526'"):
            await seed_all(
                session,
                _TEST_AZIENDA_CODICE,
                materiali=only_etr421,
                whitelist=_TEST_WHITELIST,
                accoppiamenti=bad_accoppiamenti,
            )


# =====================================================================
# Dry run
# =====================================================================


async def test_seed_dry_run_non_scrive() -> None:
    """``dry_run=True``: counter popolato ma DB resta vuoto (rollback)."""
    await _setup_isolated_db()

    async with session_scope() as session:
        report = await seed_all(
            session,
            _TEST_AZIENDA_CODICE,
            whitelist=_TEST_WHITELIST,
            accoppiamenti=_TEST_ACCOPPIAMENTI,
            dry_run=True,
        )

    # Counter sì, DB no
    assert report.materiali_inseriti == _EXPECTED_MATERIALI
    assert report.whitelist_inserite == _EXPECTED_WHITELIST
    assert report.accoppiamenti_inseriti == _EXPECTED_ACCOPPIAMENTI

    async with session_scope() as session:
        n_mat = (
            await session.execute(
                text(
                    "SELECT COUNT(*) FROM materiale_tipo WHERE azienda_id IN "
                    "(SELECT id FROM azienda WHERE codice = :cod)"
                ),
                {"cod": _TEST_AZIENDA_CODICE},
            )
        ).scalar_one()
        n_white = (
            await session.execute(
                text(
                    "SELECT COUNT(*) FROM localita_stazione_vicina WHERE stazione_codice LIKE 'TS%'"
                )
            )
        ).scalar_one()
        n_accop = (
            await session.execute(
                text(
                    "SELECT COUNT(*) FROM materiale_accoppiamento_ammesso "
                    "WHERE materiale_a_codice IN "
                    "  (SELECT codice FROM materiale_tipo WHERE azienda_id IN "
                    "   (SELECT id FROM azienda WHERE codice = :cod))"
                ),
                {"cod": _TEST_AZIENDA_CODICE},
            )
        ).scalar_one()
    assert n_mat == 0, "Dry-run non deve scrivere materiali"
    assert n_white == 0, "Dry-run non deve scrivere whitelist"
    assert n_accop == 0, "Dry-run non deve scrivere accoppiamenti"
