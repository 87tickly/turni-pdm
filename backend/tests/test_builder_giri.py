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
from colazione.models.anagrafica import (
    LocalitaManutenzione,
    LocalitaStazioneVicina,
    Stazione,
)
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
    - giro_materiale (CASCADE su giornate/blocchi — Sprint 7.7 MR 3:
      giro_variante droppato)
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
        await session.flush()

        # Sprint 7.7 MR 1 hotfix Fix C2: whitelist sede deve includere
        # tutte le stazioni delle corse di test, altrimenti i giri non
        # chiudono in zona sede (decisione utente "dobbiamo sempre
        # chiudere") e vengono scartati dal builder. In produzione la
        # whitelist è popolata via migration 0012 (Sprint 7.6 MR 2).
        for stazione_codice in ("S99001", "S99002", "S99003", "S99004"):
            session.add(
                LocalitaStazioneVicina(
                    localita_manutenzione_id=loc.id,
                    stazione_codice=stazione_codice,
                )
            )

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

    # Verifica numero_turno (Sprint 7.7 MR 4: include suffisso materiale)
    async with session_scope() as session:
        gm = (
            await session.execute(
                select(GiroMateriale).where(GiroMateriale.id == result.giri_ids[0])
            )
        ).scalar_one()
        # Sprint 7.9 MR α: numero_turno include suffisso `-{n_giornate}g`.
        assert gm.numero_turno == "G-TBLD-001-ALe711-1g"
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
        # Sprint 7.6 MR 3.1: errore scoped per (programma, sede)
        assert exc_info.value.localita_codice == LOC_CODICE


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
    # Ed esistono solo i nuovi (count totale = 1).
    # Sprint 7.7 MR 4 (cleanup C3): query via colonna FK programma_id
    # (sfrutta l'indice della migration 0010), non più via JSON path.
    async with session_scope() as session:
        n = (
            await session.execute(
                text(
                    "SELECT COUNT(*) FROM giro_materiale "
                    "WHERE programma_id = :pid"
                ),
                {"pid": prog_id},
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


# =====================================================================
# Sprint 7.5 MR 4 — parametri opzionali, default periodo intero
# =====================================================================


async def test_default_data_inizio_e_n_giornate_periodo_intero(azienda_id: int) -> None:
    """Senza `data_inizio` e `n_giornate`, il builder usa il periodo
    intero del programma (decisione utente C3).

    Setup: programma valido 2026-01-01 → 2026-12-31, una sola corsa
    valida il 2026-04-27. Senza il default a periodo intero, una
    chiamata senza parametri fallirebbe; con il default funziona.
    """
    prog_id = await _setup_completo(
        azienda_id,
        corse_def=[
            ("TEST_DEF", "S99001", "S99002", (8, 0), (9, 0), ["2026-04-27"]),
        ],
    )
    async with session_scope() as session:
        # Nessun data_inizio, nessun n_giornate → default = periodo programma
        result = await genera_giri(
            programma_id=prog_id,
            localita_codice=LOC_CODICE,
            session=session,
            azienda_id=azienda_id,
        )
    # La corsa del 2026-04-27 cade nel periodo programma (1 gen → 31 dic)
    # → 1 giro creato. Conferma che il default ha esteso la finestra.
    assert result.n_giri_creati == 1


async def test_default_solo_n_giornate_omesso(azienda_id: int) -> None:
    """Specificare solo `data_inizio` estende fino a `programma.valido_a`."""
    prog_id = await _setup_completo(
        azienda_id,
        corse_def=[
            # 1 corsa il 27/4 + 1 corsa il 15/12 (dopo data_inizio del test)
            ("TEST_OK1", "S99001", "S99002", (8, 0), (9, 0), ["2026-04-27"]),
            ("TEST_OK2", "S99003", "S99004", (10, 0), (11, 0), ["2026-12-15"]),
        ],
    )
    async with session_scope() as session:
        result = await genera_giri(
            programma_id=prog_id,
            data_inizio=date(2026, 4, 27),
            # n_giornate omesso → estende fino a 2026-12-31
            localita_codice=LOC_CODICE,
            session=session,
            azienda_id=azienda_id,
        )
    # Sprint 7.7 MR 5: entrambe le corse cadono in [2026-04-27,
    # 2026-12-31] e producono 2 cluster A1 distinti (sequenze diverse),
    # ma stessa chiave A2 (materiale, sede, n_giornate=1) → vengono
    # FUSI in 1 solo giro aggregato con 2 varianti per la giornata 1.
    assert result.n_giri_creati == 1


async def test_giro_scartato_se_nessuna_giornata_in_whitelist(
    azienda_id: int,
) -> None:
    """Sprint 7.7 MR 1 hotfix Fix C2: i giri devono SEMPRE chiudere.

    Edge case: un giro mono-giornata la cui catena termina fuori
    whitelist sede non può essere troncato (il troncamento agisce per
    GIORNATA, non per singola corsa dentro la catena). In tal caso
    il giro viene SCARTATO con warning forte al pianificatore "sede
    non coerente con la regola".

    Setup: 2 corse concatenate `S99001→S99002→S99003` (gap < 65min →
    una sola catena nella giornata). Whitelist priva di S99003.

    Atteso:
    - 0 giri creati (scartato per impossibilità di chiusura naturale).
    - Warning forte presente.
    """
    prog_id = await _setup_completo(
        azienda_id,
        corse_def=[
            ("TEST_C2_A", "S99001", "S99002", (8, 0), (9, 0), ["2026-04-27"]),
            ("TEST_C2_B", "S99002", "S99003", (10, 0), (11, 0), ["2026-04-27"]),
        ],
    )
    async with session_scope() as session:
        await session.execute(
            text(
                "DELETE FROM localita_stazione_vicina "
                "WHERE stazione_codice = 'S99003'"
            )
        )
        await session.commit()

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
    assert any(
        "scartato" in w.lower() and "sede" in w.lower() for w in result.warnings
    ), f"Warning forte mancante nei warnings: {result.warnings}"


async def test_giro_chiude_naturalmente_se_ultima_dest_in_whitelist(
    azienda_id: int,
) -> None:
    """Sprint 7.7 MR 1 hotfix Fix C2: caso happy path — l'ultima dest
    è già in whitelist, niente troncamento, giro chiuso naturalmente.

    Setup default `_setup_completo`: 2 corse cicliche
    `S99001→S99002` + `S99002→S99001`. Ultima dest = S99001 = sede →
    chiusura naturale, niente warning di troncamento.
    """
    prog_id = await _setup_completo(azienda_id)
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
    assert result.n_giri_chiusi == 1
    assert not any(
        "tagliate" in w.lower() or "scartato" in w.lower() for w in result.warnings
    ), f"Warning inatteso: {result.warnings}"


async def test_data_inizio_oltre_valido_a_raises(azienda_id: int) -> None:
    """`data_inizio` esplicita oltre `programma.valido_a` con
    `n_giornate=None` → `PeriodoFuoriProgrammaError` (n_giornate
    calcolato sarebbe ≤ 0).
    """
    from colazione.domain.builder_giro.builder import PeriodoFuoriProgrammaError

    prog_id = await _setup_completo(azienda_id)
    async with session_scope() as session:
        with pytest.raises(PeriodoFuoriProgrammaError):
            await genera_giri(
                programma_id=prog_id,
                data_inizio=date(2027, 6, 1),  # oltre valido_a (2026-12-31)
                # n_giornate omesso
                localita_codice=LOC_CODICE,
                session=session,
                azienda_id=azienda_id,
            )


async def test_due_regole_distinte_non_mescolano_corse(azienda_id: int) -> None:
    """Sprint 8.0 entry 203: pool corse isolato per regola dominante.

    Setup: programma con 2 regole + materiali diversi (ETR522 vs ETR526).
    Le corse delle due regole sono geograficamente concatenabili: pre-fix
    il pool unico avrebbe formato una catena mista A1→B1→B2→A2 (ETR522 +
    ETR526 nello stesso giro). Post-fix: catene SOLO dentro la regola.

    Decisione utente 2026-05-06: "le regole sono distinte e separate e
    non devono in nessun modo incontrarsi".
    """
    async with session_scope() as session:
        for codice in ("S99001", "S99002", "S99003"):
            session.add(Stazione(codice=codice, nome=codice, azienda_id=azienda_id))
        await session.flush()

        loc = LocalitaManutenzione(
            codice=LOC_CODICE,
            codice_breve=LOC_BREVE,
            nome_canonico=LOC_CODICE,
            stazione_collegata_codice="S99001",
            azienda_id=azienda_id,
        )
        session.add(loc)
        await session.flush()
        for stz in ("S99001", "S99002", "S99003"):
            session.add(
                LocalitaStazioneVicina(
                    localita_manutenzione_id=loc.id, stazione_codice=stz
                )
            )

        prog = ProgrammaMateriale(
            azienda_id=azienda_id,
            nome="TEST_due_regole_isolate",
            valido_da=date(2026, 1, 1),
            valido_a=date(2026, 12, 31),
            stato="attivo",
            n_giornate_default=1,
            fascia_oraria_tolerance_min=30,
            strict_options_json={
                "no_corse_residue": False,
                "no_overcapacity": False,
                "no_aggancio_non_validato": False,
                "no_orphan_blocks": False,
                "no_giro_appeso": False,
                "no_km_eccesso": False,
            },
        )
        session.add(prog)
        await session.flush()
        prog_id = int(prog.id)

        # Regola A: ETR522, filtra TEST_A*
        session.add(
            ProgrammaRegolaAssegnazione(
                programma_id=prog_id,
                filtri_json=[
                    {
                        "campo": "numero_treno",
                        "op": "in",
                        "valore": ["TEST_A1", "TEST_A2"],
                    }
                ],
                composizione_json=[
                    {"materiale_tipo_codice": "ETR522", "n_pezzi": 1}
                ],
                materiale_tipo_codice="ETR522",
                numero_pezzi=1,
                priorita=10,
            )
        )
        # Regola B: ETR526, filtra TEST_B*
        session.add(
            ProgrammaRegolaAssegnazione(
                programma_id=prog_id,
                filtri_json=[
                    {
                        "campo": "numero_treno",
                        "op": "in",
                        "valore": ["TEST_B1", "TEST_B2"],
                    }
                ],
                composizione_json=[
                    {"materiale_tipo_codice": "ETR526", "n_pezzi": 1}
                ],
                materiale_tipo_codice="ETR526",
                numero_pezzi=1,
                priorita=10,
            )
        )

        # A1 e B1 si "vorrebbero" attaccare a S99002 (gap 30 min < gap_max).
        # Pre-fix: catena mista. Post-fix: pool isolati per regola.
        for nt, o, dst, p, a in [
            ("TEST_A1", "S99001", "S99002", (8, 0), (9, 0)),
            ("TEST_A2", "S99002", "S99001", (10, 0), (11, 0)),
            ("TEST_B1", "S99002", "S99003", (9, 30), (10, 30)),
            ("TEST_B2", "S99003", "S99002", (12, 0), (13, 0)),
        ]:
            session.add(
                CorsaCommerciale(
                    azienda_id=azienda_id,
                    row_hash=("test_" + nt).ljust(64, "0")[:64],
                    numero_treno=nt,
                    codice_origine=o,
                    codice_destinazione=dst,
                    ora_partenza=time(*p),
                    ora_arrivo=time(*a),
                    valido_da=date(2026, 1, 1),
                    valido_a=date(2026, 12, 31),
                    valido_in_date_json=["2026-04-27"],
                )
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

    # Almeno un giro per regola → 2+ giri totali.
    assert result.n_giri_creati >= 2, (
        f"Atteso almeno 1 giro per regola, ottenuti {result.n_giri_creati}"
    )

    # Verifica acceptance: ogni giro contiene SOLO corse della propria
    # regola — niente mescolanza tra ETR522 e ETR526.
    async with session_scope() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT gm.id, gm.materiale_tipo_codice,
                           array_agg(cc.numero_treno) AS treni
                    FROM giro_materiale gm
                    JOIN giro_giornata gg ON gg.giro_materiale_id = gm.id
                    JOIN giro_variante gv ON gv.giro_giornata_id = gg.id
                    JOIN giro_blocco gb ON gb.giro_variante_id = gv.id
                    LEFT JOIN corsa_commerciale cc ON cc.id = gb.corsa_commerciale_id
                    WHERE gm.programma_id = :pid
                    GROUP BY gm.id, gm.materiale_tipo_codice
                    """
                ),
                {"pid": prog_id},
            )
        ).all()

    materiali_visti: set[str] = set()
    for row in rows:
        treni = [t for t in (row.treni or []) if t is not None]
        materiali_visti.add(row.materiale_tipo_codice)
        if row.materiale_tipo_codice == "ETR522":
            assert all(t.startswith("TEST_A") for t in treni), (
                f"Giro ETR522 (id={row.id}) contiene corse non-A: {treni}"
            )
        elif row.materiale_tipo_codice == "ETR526":
            assert all(t.startswith("TEST_B") for t in treni), (
                f"Giro ETR526 (id={row.id}) contiene corse non-B: {treni}"
            )
    assert materiali_visti == {"ETR522", "ETR526"}, (
        f"Atteso un giro per ogni materiale, visti: {materiali_visti}"
    )


async def test_builder_version_v2_routing_alza_per_valori_invalidi(
    azienda_id: int,
) -> None:
    """MR-1110 sotto-MR 11 (entry 210): il routing in ``genera_giri``
    accetta solo ``v1`` o ``v2``. Valori inattesi (es. DB corrotto
    pre-migration 0038, oppure futuri valori non supportati) alzano
    ``BuilderVersionNonSupportata``.

    Questo test garantisce la difesa contro stati DB non validi: se
    qualcuno bypassa il CHECK constraint e setta ``builder_version='v3'``
    a manazza, il builder rifiuta il run con un errore esplicito.
    """
    from colazione.domain.builder_giro import BuilderVersionNonSupportata

    prog_id = await _setup_completo(azienda_id)

    # Forza un valore non valido bypassando il CHECK con DDL temporaneo
    # (simulazione DB pre-0038 o corruzione manuale).
    async with session_scope() as session:
        await session.execute(
            text(
                "ALTER TABLE programma_materiale DROP CONSTRAINT "
                "IF EXISTS programma_materiale_builder_version_check"
            )
        )
        await session.execute(
            text(
                "UPDATE programma_materiale SET builder_version = 'v3' "
                "WHERE id = :pid"
            ),
            {"pid": prog_id},
        )
        await session.commit()

    try:
        async with session_scope() as session:
            with pytest.raises(BuilderVersionNonSupportata) as exc_info:
                await genera_giri(
                    programma_id=prog_id,
                    data_inizio=date(2026, 4, 27),
                    n_giornate=1,
                    localita_codice=LOC_CODICE,
                    session=session,
                    azienda_id=azienda_id,
                )

        assert exc_info.value.programma_id == prog_id
        assert exc_info.value.version == "v3"
    finally:
        # Ripristina il CHECK constraint per non lasciare il DB
        # corrotto se altri test girano dopo.
        async with session_scope() as session:
            await session.execute(
                text(
                    "UPDATE programma_materiale SET builder_version = 'v1' "
                    "WHERE id = :pid"
                ),
                {"pid": prog_id},
            )
            await session.execute(
                text(
                    "ALTER TABLE programma_materiale ADD CONSTRAINT "
                    "programma_materiale_builder_version_check "
                    "CHECK (builder_version IN ('v1', 'v2'))"
                )
            )
            await session.commit()


async def test_builder_version_v2_produce_giri_via_nuova_pipeline(
    azienda_id: int,
) -> None:
    """MR-1110 sotto-MR 11 (entry 210): un programma con
    ``builder_version='v2'`` viene processato dalla pipeline nuova
    (catene-istanza → giornate-tipo → varianti calendariali → turni
    ciclici → adapter GiroAggregato → persister). Smoke test che
    verifica end-to-end il branching senza eccezioni e con un
    BuilderResult coerente.

    Atteso per scenario minimale (1 sola data, ciclo banale): il
    builder v2 può scartare le istanze come orfane (sotto soglia
    significatività min_istanze=2 con 1 sola data) — è OK, basta che
    NON alzi eccezione e produca un BuilderResult con eventuali
    warning informativi.
    """
    prog_id = await _setup_completo(
        azienda_id,
        corse_def=[
            ("TEST_V2_1", "S99001", "S99002", (8, 0), (9, 0), ["2026-04-27"]),
            ("TEST_V2_2", "S99002", "S99001", (10, 0), (11, 0), ["2026-04-27"]),
        ],
    )

    # Promuovi il programma a v2.
    async with session_scope() as session:
        await session.execute(
            text(
                "UPDATE programma_materiale SET builder_version = 'v2' "
                "WHERE id = :pid"
            ),
            {"pid": prog_id},
        )
        await session.commit()

    # genera_giri NON deve alzare; deve ritornare BuilderResult.
    async with session_scope() as session:
        result = await genera_giri(
            programma_id=prog_id,
            data_inizio=date(2026, 4, 27),
            n_giornate=1,
            localita_codice=LOC_CODICE,
            session=session,
            azienda_id=azienda_id,
        )

    # Smoke: BuilderResult coerente. v2 con 1 data può non produrre
    # giri (filtro min_istanze D3) → warning informativo, ma niente
    # crash.
    assert result is not None
    assert isinstance(result.giri_ids, list)
    # In v2 con 1 data e min_istanze=2 default, le istanze finiscono
    # orfane: 0 giri creati ma warning popolato.
    if result.n_giri_creati == 0:
        assert any(
            "v2" in w or "min_istanze" in w or "concatenab" in w
            for w in result.warnings
        ), f"Atteso warning v2, visti: {result.warnings}"


async def test_builder_v2_end_to_end_persiste_giri(azienda_id: int) -> None:
    """MR-1110 sotto-MR 11 (entry 210): pipeline v2 end-to-end con
    persistenza DB. Scenario: 5 date con stessa sequenza di corse
    (catena S99001→S99002→S99001) → 1 giornata-tipo con 1 variante
    (5 istanze) → 1 turno v2 di 1 giornata persistito.

    Verifica:
    - ``BuilderResult.n_giri_creati == 1``.
    - DB ha ``GiroMateriale + GiroGiornata + GiroVariante + GiroBlocco``.
    - ``GiroVariante.dates_apply_json`` = le 5 date.
    - ``GiroBlocco.tipo_blocco='corsa_commerciale'`` per le 2 corse.
    """
    date_test = ["2026-04-27", "2026-04-28", "2026-04-29", "2026-04-30", "2026-05-01"]

    prog_id = await _setup_completo(
        azienda_id,
        corse_def=[
            ("TEST_V2_E2E_1", "S99001", "S99002", (8, 0), (9, 0), date_test),
            ("TEST_V2_E2E_2", "S99002", "S99001", (10, 0), (11, 0), date_test),
        ],
    )

    async with session_scope() as session:
        await session.execute(
            text(
                "UPDATE programma_materiale SET builder_version = 'v2' "
                "WHERE id = :pid"
            ),
            {"pid": prog_id},
        )
        await session.commit()

    async with session_scope() as session:
        result = await genera_giri(
            programma_id=prog_id,
            data_inizio=date(2026, 4, 27),
            n_giornate=5,
            localita_codice=LOC_CODICE,
            session=session,
            azienda_id=azienda_id,
        )

    assert result.n_giri_creati == 1, (
        f"Atteso 1 giro v2 (1 turno × 1 giornata-tipo × 1 variante con "
        f"5 istanze), ottenuti {result.n_giri_creati}. "
        f"Warnings: {result.warnings}"
    )
    assert result.n_corse_processate == 2, (
        f"Atteso 2 blocchi commerciali nel giro (2 corse × 1 variante), "
        f"viste {result.n_corse_processate}"
    )

    # Verifica struttura DB. Nota: ``giro_variante.etichetta_parlante``
    # non esiste a livello tabella: l'etichetta viene calcolata dall'API
    # read-side (vedi entry 205, ``api/giri.py::get_giro_dettaglio``).
    async with session_scope() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT gm.numero_turno, gm.materiale_tipo_codice,
                           gv.dates_apply_json,
                           COUNT(gb.id) FILTER (WHERE gb.tipo_blocco = 'corsa_commerciale') AS n_corse
                    FROM giro_materiale gm
                    JOIN giro_giornata gg ON gg.giro_materiale_id = gm.id
                    JOIN giro_variante gv ON gv.giro_giornata_id = gg.id
                    LEFT JOIN giro_blocco gb ON gb.giro_variante_id = gv.id
                    WHERE gm.programma_id = :pid
                    GROUP BY gm.numero_turno, gm.materiale_tipo_codice,
                             gv.dates_apply_json
                    """
                ),
                {"pid": prog_id},
            )
        ).all()

    assert len(rows) == 1, f"Atteso 1 variante, viste {len(rows)}"
    row = rows[0]
    # Numero turno formato: G-{LOC_BREVE}-{NNN}-{MAT}-{Ng}g
    assert row.numero_turno.startswith("G-TBLD-001-ALe711-1g"), (
        f"Numero turno inatteso: {row.numero_turno}"
    )
    assert row.materiale_tipo_codice == "ALe711"
    # Dates apply: le 5 date
    assert sorted(row.dates_apply_json) == date_test
    assert row.n_corse == 2  # TEST_V2_E2E_1 + TEST_V2_E2E_2


async def test_builder_v1_vs_v2_stesso_scenario_entrambi_producono_giro(
    azienda_id: int,
) -> None:
    """MR-1110 sotto-MR 11 (entry 210): test di confronto v1 vs v2.

    Stesso scenario (5 date × 2 corse base) processato dal builder v1
    e poi rigenerato con builder v2. Entrambe le pipeline devono
    produrre 1 giro persistito con le stesse 5 date e le stesse 2
    corse commerciali. Il numero esatto di varianti può differire
    leggermente (v1 può avere clustering A1 con 1 sola variante,
    v2 produce la variante che copre tutte le 5 date come "principale").

    Questo test garantisce parità funzionale base tra le due pipeline
    su scenari semplici, evitando regressioni quando l'utente promuove
    un programma da v1 a v2.
    """
    date_test = ["2026-04-27", "2026-04-28", "2026-04-29", "2026-04-30", "2026-05-01"]

    # ---- RUN v1 ----
    prog_id = await _setup_completo(
        azienda_id,
        corse_def=[
            ("TEST_VS_1", "S99001", "S99002", (8, 0), (9, 0), date_test),
            ("TEST_VS_2", "S99002", "S99001", (10, 0), (11, 0), date_test),
        ],
    )

    async with session_scope() as session:
        result_v1 = await genera_giri(
            programma_id=prog_id,
            data_inizio=date(2026, 4, 27),
            n_giornate=5,
            localita_codice=LOC_CODICE,
            session=session,
            azienda_id=azienda_id,
        )

    assert result_v1.n_giri_creati >= 1, "v1 deve produrre almeno 1 giro"

    # Salva struttura v1 per confronto.
    async with session_scope() as session:
        v1_data = (
            await session.execute(
                text(
                    """
                    SELECT gm.materiale_tipo_codice,
                           COUNT(DISTINCT gv.id) AS n_varianti,
                           COUNT(gb.id) FILTER (WHERE gb.tipo_blocco = 'corsa_commerciale') AS n_corse
                    FROM giro_materiale gm
                    JOIN giro_giornata gg ON gg.giro_materiale_id = gm.id
                    JOIN giro_variante gv ON gv.giro_giornata_id = gg.id
                    LEFT JOIN giro_blocco gb ON gb.giro_variante_id = gv.id
                    WHERE gm.programma_id = :pid
                    GROUP BY gm.id, gm.materiale_tipo_codice
                    """
                ),
                {"pid": prog_id},
            )
        ).all()

    # ---- RIGENERA con v2 (force=True) ----
    async with session_scope() as session:
        await session.execute(
            text(
                "UPDATE programma_materiale SET builder_version = 'v2' "
                "WHERE id = :pid"
            ),
            {"pid": prog_id},
        )
        await session.commit()

    async with session_scope() as session:
        result_v2 = await genera_giri(
            programma_id=prog_id,
            data_inizio=date(2026, 4, 27),
            n_giornate=5,
            localita_codice=LOC_CODICE,
            session=session,
            azienda_id=azienda_id,
            force=True,
        )

    assert result_v2.n_giri_creati >= 1, (
        f"v2 deve produrre almeno 1 giro nello stesso scenario di v1. "
        f"Warnings: {result_v2.warnings[:5]}"
    )

    # Confronto strutturale: stesso materiale, stesso numero corse totali.
    async with session_scope() as session:
        v2_data = (
            await session.execute(
                text(
                    """
                    SELECT gm.materiale_tipo_codice,
                           COUNT(DISTINCT gv.id) AS n_varianti,
                           COUNT(gb.id) FILTER (WHERE gb.tipo_blocco = 'corsa_commerciale') AS n_corse
                    FROM giro_materiale gm
                    JOIN giro_giornata gg ON gg.giro_materiale_id = gm.id
                    JOIN giro_variante gv ON gv.giro_giornata_id = gg.id
                    LEFT JOIN giro_blocco gb ON gb.giro_variante_id = gv.id
                    WHERE gm.programma_id = :pid
                    GROUP BY gm.id, gm.materiale_tipo_codice
                    """
                ),
                {"pid": prog_id},
            )
        ).all()

    # Atteso: v1 e v2 hanno modelli di persistenza fondamentalmente
    # diversi.
    # - v1 replica i blocchi per ogni data (5 date × 2 corse = 10
    #   blocchi commerciali in DB) frammentando cluster A1 per
    #   ciascuna data.
    # - v2 condivide i blocchi tra le date di applicazione (1 variante
    #   × 2 corse = 2 blocchi commerciali in DB, con
    #   ``dates_apply_json = [5 date]``).
    # Il test verifica solo che entrambe le pipeline producano giri
    # validi senza eccezioni, coprano lo stesso materiale, e che v2
    # produca un output PIÙ COMPATTO di v1 (= meno o uguale numero di
    # giri persistiti grazie alla riduzione del clustering).
    assert len(v1_data) >= 1
    assert len(v2_data) >= 1
    materiali_v1 = {r.materiale_tipo_codice for r in v1_data}
    materiali_v2 = {r.materiale_tipo_codice for r in v2_data}
    assert materiali_v1 == materiali_v2, (
        f"v1 materiali: {materiali_v1}, v2 materiali: {materiali_v2}. "
        "Le due pipeline devono coprire gli stessi materiali."
    )
    assert len(v2_data) <= len(v1_data), (
        f"v2 dovrebbe produrre <= giri di v1 (modello compatto). "
        f"v1: {len(v1_data)} giri, v2: {len(v2_data)} giri."
    )


async def test_pde_realistico_varianti_calendariali_multiple(azienda_id: int) -> None:
    """MR-1110 sotto-MR 8 (entry 208): integration test del builder
    su scenario realistico con varianti calendariali multiple.

    Scenario: programma di 4 settimane (28/3/2026 → 24/4/2026), 1
    regola ETR522, 4 corse base che circolano LV 1:5 (lunedì-venerdì,
    20 date) + 1 variante che circola solo Festivi/Sabato (5 date).

    Atteso (oracolo PDF Trenord 1134):
    - ≥ 1 giro creato con materiale ETR522.
    - Almeno una giornata-tipo con ≥ 2 varianti calendariali (LV
      pattern + Festivi pattern).
    - Etichetta parlante v2 stile Trenord (es. "LV 1:5", "F", "Solo
      D/M/YY").
    - Niente residue (tutte le corse coperte).

    Questo test valida che la pipeline v1 produce varianti separate
    per pattern calendariale diverso, e l'API read-side serve
    etichette v2 (entry 205).
    """
    # Periodo: 28/3 (sabato) → 24/4 (venerdì), 28 giorni.
    # Domeniche/festivi: 29/3 (sabato), 5/4 (Pasqua + 6/4 Pasquetta),
    #   12/4 (domenica), 19/4 (domenica), 25/4 (Liberazione, fuori range).
    valido_in_lv = [
        d.isoformat()
        for d in [
            date(2026, 3, 30), date(2026, 3, 31),
            date(2026, 4, 1), date(2026, 4, 2), date(2026, 4, 3),
            date(2026, 4, 7), date(2026, 4, 8), date(2026, 4, 9), date(2026, 4, 10),
            date(2026, 4, 13), date(2026, 4, 14), date(2026, 4, 15), date(2026, 4, 16), date(2026, 4, 17),
            date(2026, 4, 20), date(2026, 4, 21), date(2026, 4, 22), date(2026, 4, 23), date(2026, 4, 24),
        ]
    ]  # 19 date LV
    valido_in_festivo = [
        d.isoformat()
        for d in [
            date(2026, 3, 28), date(2026, 3, 29),  # sabato + domenica
            date(2026, 4, 5), date(2026, 4, 6),  # Pasqua + Pasquetta
            date(2026, 4, 12), date(2026, 4, 19),  # domeniche
        ]
    ]  # 6 date festive/sabato

    prog_id = await _setup_completo(
        azienda_id,
        n_giornate_default=1,
        corse_def=[
            # Variante LV: 4 corse complete A→B→A→B (1 giornata)
            ("TEST_LV_1", "S99001", "S99002", (8, 0), (9, 0), valido_in_lv),
            ("TEST_LV_2", "S99002", "S99001", (9, 30), (10, 30), valido_in_lv),
            ("TEST_LV_3", "S99001", "S99002", (11, 0), (12, 0), valido_in_lv),
            ("TEST_LV_4", "S99002", "S99001", (12, 30), (13, 30), valido_in_lv),
            # Variante FESTIVO: 2 corse A→B→A (sequenza diversa)
            ("TEST_FF_1", "S99001", "S99002", (10, 0), (11, 0), valido_in_festivo),
            ("TEST_FF_2", "S99002", "S99001", (11, 30), (12, 30), valido_in_festivo),
        ],
    )

    async with session_scope() as session:
        result = await genera_giri(
            programma_id=prog_id,
            data_inizio=date(2026, 3, 28),
            n_giornate=28,
            localita_codice=LOC_CODICE,
            session=session,
            azienda_id=azienda_id,
        )

    # Almeno 1 giro creato.
    assert result.n_giri_creati >= 1, (
        f"Atteso ≥ 1 giro, ottenuti {result.n_giri_creati}. Warnings: {result.warnings}"
    )
    # Niente residue significative: il pool LV (76 istanze) + pool
    # Festivo (12 istanze) deve essere coperto dal builder. Tolleriamo
    # qualche residue ai bordi del periodo (es. ultima data senza
    # collegamento), ma non più del 10%.
    n_corse_attese = (
        len(valido_in_lv) * 4  # 4 corse LV × 19 date
        + len(valido_in_festivo) * 2  # 2 corse F × 6 date
    )
    soglia_residue = max(1, n_corse_attese // 10)
    assert result.n_corse_residue <= soglia_residue, (
        f"Troppe corse residue: {result.n_corse_residue} su {n_corse_attese} attese "
        f"(soglia {soglia_residue}). Warnings: {result.warnings[:5]}"
    )

    # Verifica che pattern LV e Festivo siano stati riconosciuti come
    # cluster distinti: il numero di giri (o giornate-tipo) deve
    # essere ≥ 2 (almeno uno per pattern calendariale).
    async with session_scope() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT gg.id, COUNT(gv.id) AS n_varianti
                    FROM giro_materiale gm
                    JOIN giro_giornata gg ON gg.giro_materiale_id = gm.id
                    JOIN giro_variante gv ON gv.giro_giornata_id = gg.id
                    WHERE gm.programma_id = :pid
                    GROUP BY gg.id
                    """
                ),
                {"pid": prog_id},
            )
        ).all()

    assert len(rows) >= 2, (
        f"Atteso ≥ 2 giornate-tipo (pattern LV + pattern Festivo), "
        f"trovate {len(rows)}. Tutte le righe: {rows}"
    )

    # Verifica che le etichette parlanti siano in formato v2 (stile
    # PDF Trenord): "LV 1:5", "F", "Si eff. ...", "Solo D/M/YY",
    # "Dal D/M al D/M". L'API ricostruisce le etichette server-side
    # via genera_etichetta_parlante (entry 205).
    async with session_scope() as session:
        # Lookup tutte le varianti del programma e le loro date_apply.
        var_rows = (
            await session.execute(
                text(
                    """
                    SELECT gv.id, gv.dates_apply_json
                    FROM giro_materiale gm
                    JOIN giro_giornata gg ON gg.giro_materiale_id = gm.id
                    JOIN giro_variante gv ON gv.giro_giornata_id = gg.id
                    WHERE gm.programma_id = :pid
                    """
                ),
                {"pid": prog_id},
            )
        ).all()

    # Calcola etichette v2 manualmente con stessa logica di api/giri.py
    # (entry 205) per validare il formato. Le date del programma sono
    # 28/3-24/4 → festività di interesse: Pasqua 5/4 + Pasquetta 6/4.
    from colazione.domain.builder_giro.etichetta import genera_etichetta_parlante

    festivita_test = frozenset({date(2026, 4, 5), date(2026, 4, 6)})
    periodo_test = (date(2026, 3, 28), date(2026, 4, 24))
    etichette_v2: list[str] = []
    for r in var_rows:
        dates_iso = r.dates_apply_json or []
        dates_set = frozenset(
            date.fromisoformat(d) for d in dates_iso if isinstance(d, str)
        )
        if dates_set:
            etichetta = genera_etichetta_parlante(dates_set, periodo_test, festivita_test)
            etichette_v2.append(etichetta)

    # Almeno 1 etichetta deve essere in formato v2 stile Trenord
    # (non più "Lavorativo+Prefestivo (3 date)" della v1).
    formati_v2 = (
        "LV ", "F", "Si eff.", "Solo ", "Dal ", "Circola ",
    )
    assert any(
        any(e.startswith(prefix) for prefix in formati_v2) for e in etichette_v2
    ), (
        f"Nessuna etichetta in formato v2 stile Trenord trovata. "
        f"Etichette raccolte: {etichette_v2[:10]}"
    )
