"""Test unitari split_cv (Sprint 7.4 MR 1).

I test costruiscono `GiroBlocco` direttamente in memoria senza DB:
lo splitter è puro, dipende solo da campi pythonici degli ORM
(`ora_inizio`, `ora_fine`, `stazione_da_codice`, `stazione_a_codice`).

Il test integration di `lista_stazioni_cv_ammesse` richiede DB e
include il seed di un `Depot` minimale; salta se SKIP_DB_TESTS=1.
"""

from __future__ import annotations

import os
from datetime import time

import pytest

from colazione.domain.builder_pdc.split_cv import (
    MAX_LIVELLI_SPLIT,
    STAZIONI_CV_DEROGA,
    _eccede_limiti,
    _trova_punto_split,
    lista_stazioni_cv_ammesse,
    split_e_build_giornata,
)
from colazione.models.giri import GiroBlocco


# =====================================================================
# Helper costruzione fixture
# =====================================================================


def _gb(
    id_: int,
    ora_inizio: tuple[int, int],
    ora_fine: tuple[int, int],
    stazione_da: str,
    stazione_a: str,
) -> GiroBlocco:
    """Costruisce un `GiroBlocco` minimale con orari + stazioni."""
    return GiroBlocco(
        id=id_,
        seq=id_,
        tipo_blocco="commerciale",
        corsa_commerciale_id=id_,
        corsa_materiale_vuoto_id=None,
        ora_inizio=time(ora_inizio[0], ora_inizio[1]),
        ora_fine=time(ora_fine[0], ora_fine[1]),
        stazione_da_codice=stazione_da,
        stazione_a_codice=stazione_a,
    )


# =====================================================================
# _eccede_limiti
# =====================================================================


class _DraftStub:
    """Stub minimale per testare _eccede_limiti senza costruire un draft
    completo via _build_giornata_pdc."""

    def __init__(
        self, prestazione_min: int, condotta_min: int, is_notturno: bool = False
    ) -> None:
        self.prestazione_min = prestazione_min
        self.condotta_min = condotta_min
        self.is_notturno = is_notturno


def test_eccede_limiti_standard_prestazione_oltre_510() -> None:
    draft = _DraftStub(prestazione_min=600, condotta_min=300, is_notturno=False)
    assert _eccede_limiti(draft) is True  # type: ignore[arg-type]


def test_eccede_limiti_notturno_prestazione_oltre_420() -> None:
    draft = _DraftStub(prestazione_min=500, condotta_min=300, is_notturno=True)
    assert _eccede_limiti(draft) is True  # type: ignore[arg-type]


def test_eccede_limiti_condotta_oltre_330() -> None:
    draft = _DraftStub(prestazione_min=500, condotta_min=400, is_notturno=False)
    assert _eccede_limiti(draft) is True  # type: ignore[arg-type]


def test_eccede_limiti_entro_limiti() -> None:
    draft = _DraftStub(prestazione_min=500, condotta_min=300, is_notturno=False)
    assert _eccede_limiti(draft) is False  # type: ignore[arg-type]


# =====================================================================
# split_e_build_giornata — caso base no-split
# =====================================================================


def test_giornata_corta_no_split() -> None:
    """3 blocchi su 3h → entro limiti, niente split."""
    blocchi = [
        _gb(1, (8, 0), (9, 0), "FIO", "MIL"),
        _gb(2, (9, 30), (10, 30), "MIL", "BGM"),
        _gb(3, (11, 0), (12, 0), "BGM", "FIO"),
    ]
    rami = split_e_build_giornata(
        numero_giornata=1,
        variante_calendario="GG",
        blocchi_giro=blocchi,
        stazioni_cv={"FIO", "MIL", "BGM"},
    )
    assert len(rami) == 1
    ramo = rami[0]
    assert ramo.violazioni == []
    assert ramo.prestazione_min <= 510
    assert ramo.condotta_min <= 330


# =====================================================================
# Split semplice in 2 rami
# =====================================================================


def test_giornata_eccede_split_in_due_rami() -> None:
    """Giornata di ~10h con CV ammesso a metà → 2 rami entrambi entro limiti.

    Prestazione totale senza split: 8 ore di condotta + 80' accessori +
    30' presa/fine = ~600 min, eccede il cap 510.
    Stazione CV nel punto di mezzo (MIL) → split in 2 rami da ~4h
    ciascuno.
    """
    blocchi = [
        _gb(1, (6, 0), (8, 0), "FIO", "BGM"),
        _gb(2, (8, 30), (10, 30), "BGM", "MIL"),
        _gb(3, (11, 0), (13, 0), "MIL", "BGM"),
        _gb(4, (13, 30), (15, 30), "BGM", "FIO"),
    ]
    rami = split_e_build_giornata(
        numero_giornata=1,
        variante_calendario="GG",
        blocchi_giro=blocchi,
        stazioni_cv={"MIL"},  # Solo MIL ammessa CV
    )
    assert len(rami) == 2
    # Ogni ramo entro limiti
    for r in rami:
        assert r.prestazione_min <= 510, (
            f"ramo presta {r.prestazione_min} > 510"
        )
        assert r.condotta_min <= 330, f"ramo condotta {r.condotta_min} > 330"
    # Sequenza geografica preservata: ramo 1 finisce a MIL, ramo 2 inizia a MIL
    assert rami[0].stazione_fine == "MIL"
    assert rami[1].stazione_inizio == "MIL"


def test_split_costruisce_rami_con_propri_accessori() -> None:
    """Ogni ramo del split deve avere PRESA/ACCp/ACCa/FINE proprio."""
    blocchi = [
        _gb(1, (6, 0), (8, 0), "FIO", "BGM"),
        _gb(2, (8, 30), (10, 30), "BGM", "MIL"),
        _gb(3, (11, 0), (13, 0), "MIL", "BGM"),
        _gb(4, (13, 30), (15, 30), "BGM", "FIO"),
    ]
    rami = split_e_build_giornata(
        numero_giornata=1,
        variante_calendario="GG",
        blocchi_giro=blocchi,
        stazioni_cv={"MIL"},
    )
    assert len(rami) == 2
    for r in rami:
        tipi = [b.tipo_evento for b in r.blocchi]
        assert tipi[0] == "PRESA", f"primo blocco non è PRESA: {tipi}"
        assert tipi[1] == "ACCp", f"secondo blocco non è ACCp: {tipi}"
        assert tipi[-1] == "FINE", f"ultimo blocco non è FINE: {tipi}"
        assert tipi[-2] == "ACCa", f"penultimo blocco non è ACCa: {tipi}"


# =====================================================================
# Nessun punto di split possibile → violazione resta
# =====================================================================


def test_no_stazione_cv_violazione_resta() -> None:
    """Giornata che eccede limiti ma nessuna stazione del giro è in
    stazioni_cv → 1 ramo solo, con violazione marcata."""
    blocchi = [
        _gb(1, (6, 0), (8, 0), "S_A", "S_B"),
        _gb(2, (8, 30), (10, 30), "S_B", "S_C"),
        _gb(3, (11, 0), (13, 0), "S_C", "S_B"),
        _gb(4, (13, 30), (15, 30), "S_B", "S_A"),
    ]
    rami = split_e_build_giornata(
        numero_giornata=1,
        variante_calendario="GG",
        blocchi_giro=blocchi,
        stazioni_cv={"FIO", "TIRANO"},  # nessuna corrisponde
    )
    assert len(rami) == 1
    assert rami[0].violazioni  # almeno una violazione presente


def test_un_solo_blocco_no_split_possibile() -> None:
    """1 blocco: anche se eccede, non si può splittare."""
    blocchi = [_gb(1, (4, 0), (15, 0), "FIO", "TIRANO")]
    rami = split_e_build_giornata(
        numero_giornata=1,
        variante_calendario="GG",
        blocchi_giro=blocchi,
        stazioni_cv={"FIO", "TIRANO"},
    )
    assert len(rami) == 1
    assert rami[0].violazioni  # eccede ma non splittabile


def test_blocchi_vuoti_ritorna_lista_vuota() -> None:
    rami = split_e_build_giornata(
        numero_giornata=1,
        variante_calendario="GG",
        blocchi_giro=[],
        stazioni_cv={"FIO"},
    )
    assert rami == []


# =====================================================================
# Ricorsione
# =====================================================================


def test_giornata_molto_lunga_split_ricorsivo() -> None:
    """Giornata di ~14h con 6 blocchi, stazioni CV ai punti 1, 3, 5 →
    almeno 2 split (3 rami)."""
    blocchi = [
        _gb(1, (5, 0), (7, 0), "FIO", "MIL"),
        _gb(2, (7, 30), (9, 30), "MIL", "BGM"),
        _gb(3, (10, 0), (12, 0), "BGM", "MIL"),
        _gb(4, (12, 30), (14, 30), "MIL", "BGM"),
        _gb(5, (15, 0), (17, 0), "BGM", "MIL"),
        _gb(6, (17, 30), (19, 30), "MIL", "FIO"),
    ]
    rami = split_e_build_giornata(
        numero_giornata=1,
        variante_calendario="GG",
        blocchi_giro=blocchi,
        stazioni_cv={"MIL"},
    )
    # Almeno 2 split = 3 rami
    assert len(rami) >= 3
    for r in rami:
        # Tutti i rami entro i limiti dopo split ricorsivo
        cap = 420 if r.is_notturno else 510
        assert r.prestazione_min <= cap, (
            f"ramo presta {r.prestazione_min} > {cap}"
        )
        assert r.condotta_min <= 330


# =====================================================================
# _trova_punto_split granulare
# =====================================================================


def test_trova_punto_split_primo_valido_greedy() -> None:
    """Greedy: ritorna il primo blocco che produce ramo A entro limiti."""
    # 4 blocchi, stazione CV su tutti gli arrivi.
    # Il primo blocco da solo è entro limiti → return 0.
    blocchi = [
        _gb(1, (6, 0), (7, 0), "FIO", "MIL"),
        _gb(2, (7, 30), (8, 30), "MIL", "BGM"),
        _gb(3, (9, 0), (10, 0), "BGM", "MIL"),
        _gb(4, (10, 30), (11, 30), "MIL", "FIO"),
    ]
    punto = _trova_punto_split(
        numero_giornata=1,
        variante_calendario="GG",
        blocchi_giro=blocchi,
        stazioni_cv={"MIL", "BGM"},
    )
    # Il primo blocco da solo (~1h prestazione totale incl accessori)
    # è entro limiti, quindi greedy ritorna 0.
    assert punto == 0


def test_trova_punto_split_nessuna_stazione_cv() -> None:
    blocchi = [
        _gb(1, (6, 0), (8, 0), "S_A", "S_B"),
        _gb(2, (8, 30), (10, 30), "S_B", "S_C"),
    ]
    assert (
        _trova_punto_split(
            numero_giornata=1,
            variante_calendario="GG",
            blocchi_giro=blocchi,
            stazioni_cv={"FIO"},
        )
        is None
    )


def test_trova_punto_split_meno_di_due_blocchi() -> None:
    blocchi = [_gb(1, (6, 0), (8, 0), "FIO", "MIL")]
    assert (
        _trova_punto_split(
            numero_giornata=1,
            variante_calendario="GG",
            blocchi_giro=blocchi,
            stazioni_cv={"FIO", "MIL"},
        )
        is None
    )


# =====================================================================
# Costanti modulo
# =====================================================================


def test_max_livelli_split_costante() -> None:
    assert MAX_LIVELLI_SPLIT == 5


def test_stazioni_cv_deroga_costante() -> None:
    assert "MORTARA" in STAZIONI_CV_DEROGA
    assert "TIRANO" in STAZIONI_CV_DEROGA


# =====================================================================
# Integration test DB: lista_stazioni_cv_ammesse
# =====================================================================


pytestmark_db = pytest.mark.skipif(
    os.getenv("SKIP_DB_TESTS") == "1",
    reason="DB not configured for tests",
)


@pytestmark_db
@pytest.mark.asyncio
async def test_lista_stazioni_cv_ammesse_unisce_depositi_e_deroghe() -> None:
    """Verifica che la funzione restituisca depositi PdC azienda
    + deroghe `MORTARA`/`TIRANO`. Test seed-and-verify pulito."""
    from colazione.db import dispose_engine, session_scope
    from colazione.models.anagrafica import Azienda, Depot, Stazione

    # Vincolo DB azienda.codice: ~'^[a-z0-9_]+$' (migration 0001).
    azienda_codice = "test_splitcv_azienda"
    stazione_codice = "TSTSPLCVSTZ"

    async with session_scope() as session:
        # Cleanup pregresso
        await session.execute(
            Depot.__table__.delete().where(
                Depot.codice.like("TEST_SPLITCV_%")
            )
        )
        await session.execute(
            Stazione.__table__.delete().where(
                Stazione.codice.like("TEST_SPLITCV_%")
            )
        )
        await session.execute(
            Azienda.__table__.delete().where(
                Azienda.codice == azienda_codice
            )
        )
        await session.flush()

        azienda = Azienda(codice=azienda_codice, nome="Test Split CV")
        session.add(azienda)
        await session.flush()

        stazione = Stazione(
            codice=stazione_codice,
            nome="Stazione Deposito Test",
            azienda_id=azienda.id,
        )
        session.add(stazione)
        await session.flush()

        depot = Depot(
            codice="TEST_SPLITCV_DEPO",
            display_name="Deposito Test PdC",
            azienda_id=azienda.id,
            stazione_principale_codice=stazione_codice,
            tipi_personale_ammessi="PdC",
            is_attivo=True,
        )
        session.add(depot)
        await session.flush()

        result = await lista_stazioni_cv_ammesse(session, azienda.id)

        assert stazione_codice in result
        assert "MORTARA" in result
        assert "TIRANO" in result

        # Cleanup
        await session.execute(
            Depot.__table__.delete().where(
                Depot.codice == "TEST_SPLITCV_DEPO"
            )
        )
        await session.execute(
            Stazione.__table__.delete().where(
                Stazione.codice == stazione_codice
            )
        )
        await session.execute(
            Azienda.__table__.delete().where(
                Azienda.codice == azienda_codice
            )
        )
        await session.commit()

    await dispose_engine()
