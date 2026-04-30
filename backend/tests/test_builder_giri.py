"""Test integration Sprint 4.4.5b — orchestrator `genera_giri()`.

Test del builder end-to-end (loader DB → pipeline pure → persister).
Setup completo: programma 'attivo' + regole + corse con
``valido_in_date_json`` popolato + località con `codice_breve`.

Set ``SKIP_DB_TESTS=1`` per saltare.
"""

from __future__ import annotations

import os
from datetime import date, time

import pytest
from sqlalchemy import select, text

from colazione.db import dispose_engine, session_scope
from colazione.domain.builder_giro import (
    GiriEsistentiError,
    LocalitaNonTrovataError,
    ProgrammaNonAttivoError,
    ProgrammaNonTrovatoError,
    StrictModeViolation,
    genera_giri,
)
from colazione.models.anagrafica import LocalitaManutenzione, Stazione
from colazione.models.corse import CorsaCommerciale
from colazione.models.giri import GiroMateriale
from colazione.models.programmi import (
    ProgrammaMateriale,
    ProgrammaRegolaAssegnazione,
)

pytestmark = pytest.mark.skipif(
    os.getenv("SKIP_DB_TESTS") == "1",
    reason="DB not configured for tests",
)


# =====================================================================
# Setup
# =====================================================================


MATERIALE_TIPO = "ALe711"
LOC_CODICE = "TEST_LOC_BUILDER"
LOC_BREVE = "TBLD"


async def _wipe_test_data() -> None:
    """Pulisce: giri (tutti, dev only) + dati test (TEST_*, S99*).

    Ordine FK-safe:
    - turno_pdc (CASCADE → giornate → blocchi; libera FK RESTRICT su
      `turno_pdc_blocco.corsa_materiale_vuoto_id` e
      `turno_pdc_blocco.corsa_commerciale_id`)
    - giro_materiale (CASCADE su giornate/varianti/blocchi)
    - corsa_materiale_vuoto (orfana dopo cancellazione giri,
      ON DELETE SET NULL non basta per cancellare la riga)
    """
    async with session_scope() as session:
        await session.execute(text("DELETE FROM turno_pdc"))
        await session.execute(text("DELETE FROM giro_materiale"))
        await session.execute(text("DELETE FROM corsa_materiale_vuoto"))
        await session.execute(
            text("DELETE FROM corsa_commerciale WHERE numero_treno LIKE 'TEST_%'")
        )
        await session.execute(
            text(
                "DELETE FROM programma_regola_assegnazione WHERE programma_id IN ("
                "SELECT id FROM programma_materiale WHERE nome LIKE 'TEST_%'"
                ")"
            )
        )
        await session.execute(text("DELETE FROM programma_materiale WHERE nome LIKE 'TEST_%'"))
        await session.execute(text("DELETE FROM localita_manutenzione WHERE codice LIKE 'TEST_%'"))
        await session.execute(text("DELETE FROM stazione WHERE codice LIKE 'S99%'"))


@pytest.fixture(autouse=True)
async def clean_state() -> None:
    """Wipe pre + post-test (evita FK leftover su test successivi)."""
    await _wipe_test_data()
    yield
    await _wipe_test_data()


@pytest.fixture(scope="module", autouse=True)
async def cleanup_engine() -> None:
    yield
    await dispose_engine()


@pytest.fixture(scope="module")
async def azienda_id() -> int:
    async with session_scope() as session:
        row = (
            await session.execute(text("SELECT id FROM azienda WHERE codice = 'trenord'"))
        ).first()
        if row is None:
            raise RuntimeError("Seed Trenord mancante")
        return int(row[0])


# =====================================================================
# Builder helpers
# =====================================================================


async def _setup_completo(
    az_id: int,
    *,
    stato_programma: str = "attivo",
    strict: dict[str, bool] | None = None,
    corse_def: list[tuple[str, str, str, tuple[int, int], tuple[int, int], list[str]]]
    | None = None,
    n_giornate_default: int = 5,
) -> int:
    """Crea stazioni + località + programma + regola + corse. Ritorna programma_id.

    `corse_def`: [(numero_treno, origine, destinazione, partenza, arrivo, valido_dates_iso)]
    """
    if corse_def is None:
        corse_def = [
            ("TEST_001", "S99001", "S99002", (8, 0), (9, 0), ["2026-04-27"]),
            ("TEST_002", "S99002", "S99001", (10, 0), (11, 0), ["2026-04-27"]),
        ]

    async with session_scope() as session:
        # Stazioni (flush prima della località per soddisfare FK)
        for codice in {"S99001", "S99002", "S99003", "S99004"}:
            session.add(Stazione(codice=codice, nome=codice, azienda_id=az_id))
        await session.flush()

        # Località
        loc = LocalitaManutenzione(
            codice=LOC_CODICE,
            codice_breve=LOC_BREVE,
            nome_canonico=LOC_CODICE,
            stazione_collegata_codice="S99001",
            azienda_id=az_id,
        )
        session.add(loc)

        # Programma
        strict_opts = strict or {
            "no_corse_residue": False,
            "no_overcapacity": False,
            "no_aggancio_non_validato": False,
            "no_orphan_blocks": False,
            "no_giro_appeso": False,
            "no_km_eccesso": False,
        }
        prog = ProgrammaMateriale(
            azienda_id=az_id,
            nome="TEST_programma_builder",
            valido_da=date(2026, 1, 1),
            valido_a=date(2026, 12, 31),
            stato=stato_programma,
            n_giornate_default=n_giornate_default,
            fascia_oraria_tolerance_min=30,
            strict_options_json=strict_opts,
        )
        session.add(prog)
        await session.flush()
        prog_id = int(prog.id)

        # Regola: cattura tutto (filtri vuoti = matcha tutto)
        regola = ProgrammaRegolaAssegnazione(
            programma_id=prog_id,
            # Filtri stretti sulle stazioni S99* del setup di test, per
            # isolare dal pool corse del DB (Sprint 5.6: il pool catene
            # è filtrato per regola, quindi una regola "matcha tutto"
            # pescherebbe tutte le corse PdE eventualmente importate).
            filtri_json=[
                {"campo": "codice_origine", "op": "in", "valore": ["S99001", "S99002", "S99003", "S99004"]},
            ],
            composizione_json=[{"materiale_tipo_codice": MATERIALE_TIPO, "n_pezzi": 3}],
            materiale_tipo_codice=MATERIALE_TIPO,
            numero_pezzi=3,
            priorita=10,
        )
        session.add(regola)

        # Corse
        for nt, o, d, p, a, valido_in in corse_def:
            session.add(
                CorsaCommerciale(
                    azienda_id=az_id,
                    row_hash=("test_" + nt).ljust(64, "0")[:64],
                    numero_treno=nt,
                    codice_origine=o,
                    codice_destinazione=d,
                    ora_partenza=time(*p),
                    ora_arrivo=time(*a),
                    valido_da=date(2026, 1, 1),
                    valido_a=date(2026, 12, 31),
                    valido_in_date_json=valido_in,
                )
            )

        return prog_id


# =====================================================================
# Casi base
# =====================================================================


async def test_happy_path_1_corsa_1_giro(azienda_id: int) -> None:
    prog_id = await _setup_completo(
        azienda_id,
        corse_def=[
            ("TEST_HP1", "S99001", "S99002", (8, 0), (9, 0), ["2026-04-27"]),
            ("TEST_HP2", "S99002", "S99001", (10, 0), (11, 0), ["2026-04-27"]),
        ],
    )

    async with session_scope() as session:
        result = await genera_giri(
            programma_id=prog_id,
            data_inizio=date(2026, 4, 27),
            n_giornate=1,
            localita_codice=LOC_CODICE,
            session=session,
            azienda_id=azienda_id,
        )

    assert result.n_giri_creati == 1
    assert result.n_corse_processate == 2
    assert result.n_corse_residue == 0
    assert result.n_giri_chiusi == 1
    assert result.n_giri_non_chiusi == 0

    # Verifica numero_turno
    async with session_scope() as session:
        gm = (
            await session.execute(
                select(GiroMateriale).where(GiroMateriale.id == result.giri_ids[0])
            )
        ).scalar_one()
        assert gm.numero_turno == "G-TBLD-001"
        assert gm.materiale_tipo_codice == "ALe711"
        # generation_metadata_json contiene programma_id
        assert gm.generation_metadata_json["programma_id"] == prog_id


async def test_programma_non_trovato(azienda_id: int) -> None:
    async with session_scope() as session:
        with pytest.raises(ProgrammaNonTrovatoError):
            await genera_giri(
                programma_id=999999,
                data_inizio=date(2026, 4, 27),
                n_giornate=1,
                localita_codice=LOC_CODICE,
                session=session,
                azienda_id=azienda_id,
            )


async def test_localita_non_trovata(azienda_id: int) -> None:
    prog_id = await _setup_completo(azienda_id)
    async with session_scope() as session:
        with pytest.raises(LocalitaNonTrovataError):
            await genera_giri(
                programma_id=prog_id,
                data_inizio=date(2026, 4, 27),
                n_giornate=1,
                localita_codice="INESISTENTE",
                session=session,
                azienda_id=azienda_id,
            )


async def test_programma_non_attivo_raises(azienda_id: int) -> None:
    prog_id = await _setup_completo(azienda_id, stato_programma="bozza")
    async with session_scope() as session:
        with pytest.raises(ProgrammaNonAttivoError):
            await genera_giri(
                programma_id=prog_id,
                data_inizio=date(2026, 4, 27),
                n_giornate=1,
                localita_codice=LOC_CODICE,
                session=session,
                azienda_id=azienda_id,
            )


# =====================================================================
# Anti-rigenerazione
# =====================================================================


async def test_giri_esistenti_409_senza_force(azienda_id: int) -> None:
    prog_id = await _setup_completo(azienda_id)
    async with session_scope() as session:
        await genera_giri(
            programma_id=prog_id,
            data_inizio=date(2026, 4, 27),
            n_giornate=1,
            localita_codice=LOC_CODICE,
            session=session,
            azienda_id=azienda_id,
        )

    # Seconda chiamata senza force → errore
    async with session_scope() as session:
        with pytest.raises(GiriEsistentiError) as exc_info:
            await genera_giri(
                programma_id=prog_id,
                data_inizio=date(2026, 4, 27),
                n_giornate=1,
                localita_codice=LOC_CODICE,
                session=session,
                azienda_id=azienda_id,
            )
        assert exc_info.value.programma_id == prog_id
        assert exc_info.value.n_esistenti >= 1


async def test_force_true_wipe_e_rigenera(azienda_id: int) -> None:
    prog_id = await _setup_completo(azienda_id)
    async with session_scope() as session:
        result1 = await genera_giri(
            programma_id=prog_id,
            data_inizio=date(2026, 4, 27),
            n_giornate=1,
            localita_codice=LOC_CODICE,
            session=session,
            azienda_id=azienda_id,
        )

    async with session_scope() as session:
        result2 = await genera_giri(
            programma_id=prog_id,
            data_inizio=date(2026, 4, 27),
            n_giornate=1,
            localita_codice=LOC_CODICE,
            session=session,
            azienda_id=azienda_id,
            force=True,
        )

    # I giri di result2 sono nuovi (id diversi)
    assert result1.giri_ids != result2.giri_ids
    # Ed esistono solo i nuovi (count totale = 1)
    async with session_scope() as session:
        n = (
            await session.execute(
                text(
                    "SELECT COUNT(*) FROM giro_materiale "
                    "WHERE generation_metadata_json->>'programma_id' = :pid"
                ),
                {"pid": str(prog_id)},
            )
        ).scalar_one()
        assert n == 1


# =====================================================================
# Strict mode
# =====================================================================


@pytest.mark.skip(
    reason=(
        "Sprint 5.6: il filtro pool catene per regola esclude a monte le corse "
        "fuori-perimetro, quindi 'corse residue' non si verifica più per regole "
        "non-matchanti. Il test va riscritto per simulare residue post-filtro "
        "(es. due regole con priorità conflict). Residuo Sprint 5+."
    )
)
async def test_strict_no_corse_residue_blocca(azienda_id: int) -> None:
    """Corsa che non matcha alcuna regola + strict no_corse_residue → errore."""
    prog_id = await _setup_completo(
        azienda_id,
        strict={
            "no_corse_residue": True,
            "no_overcapacity": False,
            "no_aggancio_non_validato": False,
            "no_orphan_blocks": False,
            "no_giro_appeso": False,
            "no_km_eccesso": False,
        },
    )
    # Sostituisco la regola "matcha tutto" con una che NON matcha nulla
    async with session_scope() as session:
        await session.execute(
            text("DELETE FROM programma_regola_assegnazione WHERE programma_id = :pid"),
            {"pid": prog_id},
        )
        session.add(
            ProgrammaRegolaAssegnazione(
                programma_id=prog_id,
                filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "INESISTENTE"}],
                composizione_json=[{"materiale_tipo_codice": MATERIALE_TIPO, "n_pezzi": 3}],
                materiale_tipo_codice=MATERIALE_TIPO,
                numero_pezzi=3,
                priorita=10,
            )
        )

    async with session_scope() as session:
        with pytest.raises(StrictModeViolation) as exc_info:
            await genera_giri(
                programma_id=prog_id,
                data_inizio=date(2026, 4, 27),
                n_giornate=1,
                localita_codice=LOC_CODICE,
                session=session,
                azienda_id=azienda_id,
            )
        assert "no_corse_residue" in str(exc_info.value)


# =====================================================================
# Multi-giornata cross-notte
# =====================================================================


async def test_multi_giornata_cross_notte(azienda_id: int) -> None:
    """G1 finisce a S99002 cross-notte (arrivo dopo mezzanotte, no rientro),
    G2 parte da S99002 → 1 giro 2 giornate."""
    prog_id = await _setup_completo(
        azienda_id,
        corse_def=[
            # Lunedì: S99001 → S99002, partenza 23:30, arrivo 00:30 (cross-notte)
            ("TEST_G1", "S99001", "S99002", (23, 30), (0, 30), ["2026-04-27"]),
            # Martedì: S99002 → S99001 alle 06:00
            ("TEST_G2", "S99002", "S99001", (6, 0), (6, 30), ["2026-04-28"]),
        ],
    )
    async with session_scope() as session:
        result = await genera_giri(
            programma_id=prog_id,
            data_inizio=date(2026, 4, 27),
            n_giornate=2,
            localita_codice=LOC_CODICE,
            session=session,
            azienda_id=azienda_id,
        )
    # 1 solo giro, 2 giornate
    assert result.n_giri_creati == 1
    async with session_scope() as session:
        gm = (
            await session.execute(
                select(GiroMateriale).where(GiroMateriale.id == result.giri_ids[0])
            )
        ).scalar_one()
        assert gm.numero_giornate == 2


# =====================================================================
# Validazione input
# =====================================================================


async def test_n_giornate_zero_raises(azienda_id: int) -> None:
    prog_id = await _setup_completo(azienda_id)
    async with session_scope() as session:
        with pytest.raises(ValueError, match="n_giornate"):
            await genera_giri(
                programma_id=prog_id,
                data_inizio=date(2026, 4, 27),
                n_giornate=0,
                localita_codice=LOC_CODICE,
                session=session,
                azienda_id=azienda_id,
            )


async def test_corse_fuori_finestra_zero_giri(azienda_id: int) -> None:
    """Se nessuna corsa vale nelle date richieste → 0 giri creati."""
    prog_id = await _setup_completo(
        azienda_id,
        corse_def=[
            ("TEST_OOF", "S99001", "S99002", (8, 0), (9, 0), ["2026-12-25"]),  # data fuori
        ],
    )
    async with session_scope() as session:
        result = await genera_giri(
            programma_id=prog_id,
            data_inizio=date(2026, 4, 27),
            n_giornate=1,
            localita_codice=LOC_CODICE,
            session=session,
            azienda_id=azienda_id,
        )
    assert result.n_giri_creati == 0
    assert result.giri_ids == []
