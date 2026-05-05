"""Test unitari Sprint 7.9 MR η — helper builder PdC per deposito + cap FR.

Coverage delle pure functions aggiunte:

- ``_calcola_violazioni_cap_fr`` — applica i cap normativi FR
  (1/sett, 3/28gg, NORMATIVA-PDC §10.6) al numero di dormite del
  ciclo e produce tag pronti per l'UI.
- ``_genera_codice_turno`` — codice turno PdC con/senza depot.

Niente DB: gli helper sono puri.
"""

from __future__ import annotations

from colazione.domain.builder_pdc.builder import (
    FR_MAX_PER_28GG,
    FR_MAX_PER_SETTIMANA,
    _calcola_violazioni_cap_fr,
    _genera_codice_turno,
)
from colazione.models.anagrafica import Depot
from colazione.models.giri import GiroMateriale

# =====================================================================
# _calcola_violazioni_cap_fr
# =====================================================================


def test_cap_fr_no_dormite_ritorna_vuoto() -> None:
    assert _calcola_violazioni_cap_fr(n_dormite_fr=0, ciclo_giorni=7) == []


def test_cap_fr_ciclo_zero_ritorna_vuoto() -> None:
    assert _calcola_violazioni_cap_fr(n_dormite_fr=2, ciclo_giorni=0) == []


def test_cap_fr_settimana_in_regola() -> None:
    """Ciclo 7gg con 1 FR = entro tetto 1/sett."""
    assert FR_MAX_PER_SETTIMANA == 1
    assert _calcola_violazioni_cap_fr(n_dormite_fr=1, ciclo_giorni=7) == []


def test_cap_fr_settimana_oltre_tetto_aggiunge_violazione() -> None:
    """Ciclo 7gg con 2 FR > tetto 1/sett."""
    out = _calcola_violazioni_cap_fr(n_dormite_fr=2, ciclo_giorni=7)
    assert any("fr_cap_settimanale" in v for v in out)


def test_cap_fr_due_settimane_due_dormite_in_regola() -> None:
    """Ciclo 14gg → tetto 2 FR (1/sett × 2). 2 dormite OK."""
    assert _calcola_violazioni_cap_fr(n_dormite_fr=2, ciclo_giorni=14) == []


def test_cap_fr_28gg_tre_dormite_in_regola() -> None:
    """4 settimane → tetto 4/sett, ma 28gg cap = 3 → 3 dormite ancora OK."""
    assert FR_MAX_PER_28GG == 3
    assert _calcola_violazioni_cap_fr(n_dormite_fr=3, ciclo_giorni=28) == []


def test_cap_fr_28gg_quattro_dormite_eccede_28gg() -> None:
    """4 settimane × 1/sett = tetto 4 (ok lato settimanale), ma cap
    28gg = 3 → 4 dormite eccede il cap mensile."""
    out = _calcola_violazioni_cap_fr(n_dormite_fr=4, ciclo_giorni=28)
    assert any("fr_cap_28gg" in v for v in out)


def test_cap_fr_ciclo_oltre_28gg_ignora_cap_mensile() -> None:
    """Per cicli > 28gg il cap mensile non si applica al singolo
    ciclo (è un vincolo a livello PdC che dipende dal mix di
    assegnazioni). Solo settimanale."""
    # Ciclo 35gg → 5 settimane → tetto settimanale 5. 4 dormite OK.
    assert _calcola_violazioni_cap_fr(n_dormite_fr=4, ciclo_giorni=35) == []
    # 6 dormite eccede settimanale (5).
    out = _calcola_violazioni_cap_fr(n_dormite_fr=6, ciclo_giorni=35)
    assert any("fr_cap_settimanale" in v for v in out)


# =====================================================================
# _genera_codice_turno
# =====================================================================


def _giro_stub(numero: str | None = "001-ETR526", giro_id: int = 42) -> GiroMateriale:
    g = GiroMateriale(numero_turno=numero)
    # bypass __init__ per impostare id (DB-bound)
    g.id = giro_id  # type: ignore[assignment]
    return g


def test_codice_turno_legacy_senza_depot() -> None:
    g = _giro_stub("001-ETR526")
    assert _genera_codice_turno(g) == "T-001-ETR526"


def test_codice_turno_legacy_giro_senza_numero_usa_id() -> None:
    g = _giro_stub(numero=None, giro_id=99)
    assert _genera_codice_turno(g) == "T-GIRO99"


def test_codice_turno_con_depot_prepend_codice() -> None:
    g = _giro_stub("001-ETR526")
    depot = Depot(codice="FIORENZA", display_name="Fiorenza", azienda_id=1)
    assert _genera_codice_turno(g, depot) == "T-FIORENZA-001-ETR526"


def test_codice_turno_con_depot_e_numero_lungo_taglio_a_48() -> None:
    """Il troncamento a 48 char (== VARCHAR(50) - 'T-') vale anche
    quando aggiungiamo il depot."""
    g = _giro_stub("X" * 60)
    depot = Depot(codice="FIORENZA", display_name="Fiorenza", azienda_id=1)
    out = _genera_codice_turno(g, depot)
    assert out.startswith("T-")
    assert len(out) == 50  # T- + 48
