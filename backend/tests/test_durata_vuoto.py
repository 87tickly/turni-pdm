"""Test per durata_vuoto.py (Sprint 8.3 MR-S2).

MR-S2 chiude S2 HIGH critica entry 284 (durata vuoto rientro 60 min
hardcoded) + S1 HIGH critica piano entry 285 (fallback geometrico
opzione B-semplificata SEVERO).

Test focus:
- Helper pure: `_durata_min_da_orari` (cross-mezzanotte gestito).
- Aggregazione mediana per coppia + per stazione.
- `calcola_durata_vuoto_min` strategia 4-livelli (hit diretto →
  speculare → baseline → default).
- Async mock: `costruisci_lookup_durate` filtra `is_cancellata` +
  raggruppa in 2 dict.
"""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from colazione.domain.builder_giro.durata_vuoto import (
    DURATA_VUOTO_DEFAULT_MIN,
    _durata_min_da_orari,
    aggrega_baseline_per_stazione,
    aggrega_durate_per_coppia,
    calcola_durata_vuoto_min,
    costruisci_lookup_durate,
)

# =====================================================================
# _durata_min_da_orari (S4 LOW: cross-mezzanotte gestito)
# =====================================================================


def test_durata_min_da_orari_caso_normale() -> None:
    """Caso normale: arrivo > partenza nello stesso giorno."""
    assert _durata_min_da_orari(time(8, 0), time(9, 30)) == 90
    assert _durata_min_da_orari(time(0, 0), time(0, 1)) == 1
    assert _durata_min_da_orari(time(14, 15), time(16, 45)) == 150


def test_durata_min_da_orari_cross_mezzanotte() -> None:
    """Cross-mezzanotte: parte 23:30, arriva 00:15 K+1 → 45 min."""
    assert _durata_min_da_orari(time(23, 30), time(0, 15)) == 45
    assert _durata_min_da_orari(time(22, 0), time(2, 0)) == 240


def test_durata_min_da_orari_zero() -> None:
    """Stesso istante: durata 0 (NON negativa)."""
    assert _durata_min_da_orari(time(10, 0), time(10, 0)) == 0


# =====================================================================
# aggrega_durate_per_coppia (mediana, raggruppamento, determinismo)
# =====================================================================


def test_aggrega_durate_per_coppia_singola_corsa() -> None:
    """1 corsa per coppia → mediana = durata di quella corsa."""
    triple = [("LECCO", "CERTOSA", 60)]
    out = aggrega_durate_per_coppia(triple)
    assert out == {("LECCO", "CERTOSA"): 60}


def test_aggrega_durate_per_coppia_mediana_n_dispari() -> None:
    """3 corse stessa coppia: mediana = valore centrale."""
    triple = [
        ("LECCO", "CERTOSA", 55),
        ("LECCO", "CERTOSA", 60),
        ("LECCO", "CERTOSA", 75),
    ]
    out = aggrega_durate_per_coppia(triple)
    assert out == {("LECCO", "CERTOSA"): 60}


def test_aggrega_durate_per_coppia_mediana_n_pari() -> None:
    """4 corse stessa coppia: mediana = media dei 2 centrali."""
    triple = [
        ("LECCO", "CERTOSA", 50),
        ("LECCO", "CERTOSA", 60),
        ("LECCO", "CERTOSA", 70),
        ("LECCO", "CERTOSA", 80),
    ]
    out = aggrega_durate_per_coppia(triple)
    # mediana = (60 + 70) / 2 = 65
    assert out == {("LECCO", "CERTOSA"): 65}


def test_aggrega_durate_per_coppia_raggruppa_per_coppia() -> None:
    """Coppie distinte → entry distinte. Verifica raggruppamento."""
    triple = [
        ("LECCO", "CERTOSA", 60),
        ("CERTOSA", "LECCO", 65),
        ("TIRANO", "CERTOSA", 150),
    ]
    out = aggrega_durate_per_coppia(triple)
    assert out == {
        ("LECCO", "CERTOSA"): 60,
        ("CERTOSA", "LECCO"): 65,
        ("TIRANO", "CERTOSA"): 150,
    }


def test_aggrega_durate_per_coppia_vuoto() -> None:
    """Iterable vuoto → dict vuoto."""
    assert aggrega_durate_per_coppia([]) == {}


# =====================================================================
# aggrega_baseline_per_stazione (touch origine OR destinazione)
# =====================================================================


def test_aggrega_baseline_per_stazione_singolo_touch() -> None:
    """1 corsa: la stazione di origine e quella di destinazione hanno
    entrambe baseline = durata della corsa."""
    triple = [("LECCO", "CERTOSA", 60)]
    out = aggrega_baseline_per_stazione(triple)
    assert out == {"LECCO": 60, "CERTOSA": 60}


def test_aggrega_baseline_per_stazione_mediana_multi_touch() -> None:
    """Stazione tocca multiple corse di durate diverse: mediana."""
    # CERTOSA tocca 3 corse (tutte arrivano lì): 60, 90, 120 → mediana 90
    # LECCO tocca 1 corsa: 60
    # MILANO tocca 1 corsa: 90
    # TIRANO tocca 1 corsa: 120
    triple = [
        ("LECCO", "CERTOSA", 60),
        ("MILANO", "CERTOSA", 90),
        ("TIRANO", "CERTOSA", 120),
    ]
    out = aggrega_baseline_per_stazione(triple)
    assert out["CERTOSA"] == 90
    assert out["LECCO"] == 60
    assert out["MILANO"] == 90
    assert out["TIRANO"] == 120


def test_aggrega_baseline_per_stazione_vuoto() -> None:
    """Iterable vuoto → dict vuoto."""
    assert aggrega_baseline_per_stazione([]) == {}


# =====================================================================
# calcola_durata_vuoto_min (4 livelli di fallback)
# =====================================================================


def test_calcola_durata_hit_diretto() -> None:
    """Coppia (X, Y) presente in lookup → ritorna quella durata."""
    lookup = {("LECCO", "CERTOSA"): 60}
    assert (
        calcola_durata_vuoto_min(
            "LECCO",
            "CERTOSA",
            durata_lookup=lookup,
        )
        == 60
    )


def test_calcola_durata_hit_speculare() -> None:
    """Coppia (X, Y) miss diretto ma (Y, X) presente → ritorna quella
    durata (= stessa infrastruttura percorsa al contrario)."""
    lookup = {("CERTOSA", "LECCO"): 65}
    # cerco (LECCO, CERTOSA) → miss diretto, hit speculare (CERTOSA, LECCO)
    assert (
        calcola_durata_vuoto_min(
            "LECCO",
            "CERTOSA",
            durata_lookup=lookup,
        )
        == 65
    )


def test_calcola_durata_diretto_prevale_speculare() -> None:
    """Se ENTRAMBE le direzioni sono in lookup, vince la diretta
    (ordine di valutazione: prima diretto, poi speculare)."""
    lookup = {
        ("LECCO", "CERTOSA"): 60,
        ("CERTOSA", "LECCO"): 65,
    }
    assert (
        calcola_durata_vuoto_min(
            "LECCO",
            "CERTOSA",
            durata_lookup=lookup,
        )
        == 60
    )


def test_calcola_durata_fallback_geometrico_max_delle_due_stazioni() -> None:
    """Miss diretto + speculare ma baseline disponibile per ENTRAMBE
    le stazioni: ritorna max(baseline_origine, baseline_destinazione,
    fallback_default).

    Scenario realistico TIRANO→CERTOSA (deposito FIO):
    - lookup miss perché nessuno fa corse commerciali verso depositi
    - baseline TIRANO = 150 (corsa più tipica TIRANO-MI)
    - baseline CERTOSA = 60 (corse regionali brevi)
    - max(150, 60, 60) = 150 → stima ragionevole vuoto rientro
    """
    baseline = {"TIRANO": 150, "CERTOSA": 60}
    durata = calcola_durata_vuoto_min(
        "TIRANO",
        "CERTOSA",
        durata_lookup={},
        baseline_per_stazione=baseline,
    )
    assert durata == 150


def test_calcola_durata_fallback_geometrico_solo_origine() -> None:
    """Baseline disponibile solo per origine: max(baseline, default)."""
    baseline = {"TIRANO": 150}
    durata = calcola_durata_vuoto_min(
        "TIRANO",
        "DESCONOSCIUTA",
        durata_lookup={},
        baseline_per_stazione=baseline,
    )
    assert durata == 150


def test_calcola_durata_fallback_geometrico_solo_destinazione() -> None:
    """Baseline disponibile solo per destinazione: max(baseline, default)."""
    baseline = {"CERTOSA": 80}
    durata = calcola_durata_vuoto_min(
        "DESCONOSCIUTA",
        "CERTOSA",
        durata_lookup={},
        baseline_per_stazione=baseline,
    )
    assert durata == 80


def test_calcola_durata_fallback_geometrico_baseline_sotto_default_alza_a_60() -> None:
    """Se baseline < default, prevale default 60 (= conservative)."""
    baseline = {"X": 30, "Y": 40}
    durata = calcola_durata_vuoto_min(
        "X",
        "Y",
        durata_lookup={},
        baseline_per_stazione=baseline,
    )
    assert durata == 60  # max(30, 40, 60) = 60


def test_calcola_durata_fallback_default_60() -> None:
    """Niente in lookup, niente baseline → fallback 60."""
    durata = calcola_durata_vuoto_min(
        "X",
        "Y",
        durata_lookup={},
        baseline_per_stazione={},
    )
    assert durata == DURATA_VUOTO_DEFAULT_MIN
    assert durata == 60


def test_calcola_durata_lookup_e_baseline_none_default() -> None:
    """Param None invece di dict vuoto: stesso comportamento (fallback)."""
    durata = calcola_durata_vuoto_min(
        "X",
        "Y",
        durata_lookup=None,
        baseline_per_stazione=None,
    )
    assert durata == 60


def test_calcola_durata_fallback_default_custom() -> None:
    """Param `fallback_default` override: stima minima diversa da 60."""
    durata = calcola_durata_vuoto_min(
        "X",
        "Y",
        fallback_default=120,
    )
    assert durata == 120


# =====================================================================
# costruisci_lookup_durate (async mocked) — integrazione filtri DB
# =====================================================================


def _row(
    o: str,
    d: str,
    *,
    min_tratta: int | None = None,
    h_p: int = 0,
    m_p: int = 0,
    h_a: int = 0,
    m_a: int = 0,
) -> SimpleNamespace:
    """Fixture per riga risultato Database (mock di Row.codice_*)."""
    return SimpleNamespace(
        codice_origine=o,
        codice_destinazione=d,
        min_tratta=min_tratta,
        ora_partenza=time(h_p, m_p),
        ora_arrivo=time(h_a, m_a),
    )


@pytest.mark.asyncio
async def test_costruisci_lookup_durate_riga_con_min_tratta() -> None:
    """Caso felice: 2 righe DB con `min_tratta` popolato → lookup
    contiene mediana per coppia + baseline per stazione."""
    rows = [
        _row("LECCO", "CERTOSA", min_tratta=60),
        _row("LECCO", "CERTOSA", min_tratta=70),
        _row("CERTOSA", "MILANO", min_tratta=20),
    ]
    fake_result = MagicMock()
    fake_result.__iter__.return_value = iter(rows)
    fake_session = MagicMock()
    fake_session.execute = AsyncMock(return_value=fake_result)

    durata_per_coppia, baseline_per_stazione = await costruisci_lookup_durate(
        fake_session,
        azienda_id=1,
        valido_da=date(2026, 6, 1),
        valido_a=date(2026, 6, 30),
    )
    # Mediana coppia (LECCO, CERTOSA): mediana(60, 70) = 65
    assert durata_per_coppia[("LECCO", "CERTOSA")] == 65
    assert durata_per_coppia[("CERTOSA", "MILANO")] == 20
    # Baseline per stazione: LECCO tocca 2 corse (60, 70) → 65
    # CERTOSA tocca 3 corse (60, 70, 20) → mediana 60
    # MILANO tocca 1 corsa (20) → 20
    assert baseline_per_stazione["LECCO"] == 65
    assert baseline_per_stazione["CERTOSA"] == 60
    assert baseline_per_stazione["MILANO"] == 20


@pytest.mark.asyncio
async def test_costruisci_lookup_durate_min_tratta_null_calcola_da_orari() -> None:
    """Riga con `min_tratta=None`: calcola da `(arrivo - partenza)`
    gestendo cross-mezzanotte."""
    rows = [
        _row("X", "Y", min_tratta=None, h_p=23, m_p=30, h_a=0, m_a=15),
    ]
    fake_result = MagicMock()
    fake_result.__iter__.return_value = iter(rows)
    fake_session = MagicMock()
    fake_session.execute = AsyncMock(return_value=fake_result)

    durata_per_coppia, _ = await costruisci_lookup_durate(
        fake_session,
        azienda_id=1,
        valido_da=date(2026, 6, 1),
        valido_a=date(2026, 6, 30),
    )
    # 23:30 → 00:15 cross-mezzanotte = 45 min
    assert durata_per_coppia[("X", "Y")] == 45


@pytest.mark.asyncio
async def test_costruisci_lookup_durate_min_tratta_zero_skip() -> None:
    """Riga con `min_tratta=0` (corsa "appena" creata, dato sporco):
    skippata difensivamente. Non entra nel lookup."""
    rows = [
        _row("X", "Y", min_tratta=0),
        _row("X", "Y", min_tratta=0, h_p=10, m_p=0, h_a=10, m_a=0),
    ]
    fake_result = MagicMock()
    fake_result.__iter__.return_value = iter(rows)
    fake_session = MagicMock()
    fake_session.execute = AsyncMock(return_value=fake_result)

    durata_per_coppia, baseline_per_stazione = await costruisci_lookup_durate(
        fake_session,
        azienda_id=1,
        valido_da=date(2026, 6, 1),
        valido_a=date(2026, 6, 30),
    )
    # Tutte skippate → dict vuoti
    assert durata_per_coppia == {}
    assert baseline_per_stazione == {}


@pytest.mark.asyncio
async def test_costruisci_lookup_durate_no_corse_ritorna_dict_vuoti() -> None:
    """Programma senza corse attive → tupla di dict vuoti."""
    fake_result = MagicMock()
    fake_result.__iter__.return_value = iter([])
    fake_session = MagicMock()
    fake_session.execute = AsyncMock(return_value=fake_result)

    durata_per_coppia, baseline_per_stazione = await costruisci_lookup_durate(
        fake_session,
        azienda_id=1,
        valido_da=date(2026, 6, 1),
        valido_a=date(2026, 6, 30),
    )
    assert durata_per_coppia == {}
    assert baseline_per_stazione == {}


@pytest.mark.asyncio
async def test_costruisci_lookup_durate_decimal_min_tratta_convertito() -> None:
    """min_tratta arriva come Decimal dal DB (Numeric column): convertito
    a int senza perdita per valori interi."""
    rows = [
        _row("X", "Y", min_tratta=Decimal("75")),  # type: ignore[arg-type]
    ]
    fake_result = MagicMock()
    fake_result.__iter__.return_value = iter(rows)
    fake_session = MagicMock()
    fake_session.execute = AsyncMock(return_value=fake_result)

    durata_per_coppia, _ = await costruisci_lookup_durate(
        fake_session,
        azienda_id=1,
        valido_da=date(2026, 6, 1),
        valido_a=date(2026, 6, 30),
    )
    assert durata_per_coppia[("X", "Y")] == 75
