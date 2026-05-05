"""Test unitari Sprint 7.9 MR η.1 — auto-suggerimento deposito PdC.

Coverage delle pure functions di formattazione/ordinamento aggiunte a
``simulazione.py``. La logica di simulazione FR riusa
``_aggiungi_dormite_fr`` e ``_calcola_violazioni_cap_fr`` già testati
da ``test_builder_pdc_eta.py``; qui copriamo solo il layer nuovo
(``_motivo`` e l'ordinamento di ``DepositoSuggerimento``).
"""

from __future__ import annotations

from colazione.domain.builder_pdc.simulazione import (
    DepositoSuggerimento,
    _motivo,
)


def _make_suggerimento(
    *,
    n_dormite_fr: int = 0,
    n_fr_cap_violazioni: int = 0,
    stazione_sede_fallback: bool = False,
) -> DepositoSuggerimento:
    return DepositoSuggerimento(
        deposito_pdc_id=1,
        deposito_pdc_codice="TEST",
        deposito_pdc_display="Test",
        stazione_principale_codice="TEST_STAZ",
        n_dormite_fr=n_dormite_fr,
        n_fr_cap_violazioni=n_fr_cap_violazioni,
        fr_cap_violazioni=[],
        prestazione_totale_min=480,
        condotta_totale_min=300,
        n_giornate=5,
        stazione_sede_fallback=stazione_sede_fallback,
        motivo="",
    )


# =====================================================================
# _motivo
# =====================================================================


def test_motivo_cap_violato_e_sempre_sconsigliato() -> None:
    """Cap FR violato: il motivo deve avvertire indipendentemente dal rank."""
    s = _make_suggerimento(n_dormite_fr=5, n_fr_cap_violazioni=2)
    assert "Cap FR violato" in _motivo(0, s)
    assert "sconsigliato" in _motivo(0, s)
    assert "Cap FR violato" in _motivo(2, s)


def test_motivo_fallback_stazione_avvisa_stima_approssimativa() -> None:
    """Senza stazione_principale_codice: stima approssimativa."""
    s = _make_suggerimento(stazione_sede_fallback=True)
    assert "approssimativa" in _motivo(0, s)
    assert "non configurata" in _motivo(0, s)


def test_motivo_zero_fr_rank_zero_e_migliore() -> None:
    """0 FR e rank 0: 'Migliore — nessuna dormita FR'."""
    s = _make_suggerimento(n_dormite_fr=0)
    txt = _motivo(0, s)
    assert "Migliore" in txt
    assert "nessuna dormita" in txt.lower()


def test_motivo_zero_fr_rank_non_zero_no_migliore() -> None:
    """0 FR ma non rank 0: solo 'Nessuna dormita FR' (no 'Migliore')."""
    s = _make_suggerimento(n_dormite_fr=0)
    txt = _motivo(2, s)
    assert "Migliore" not in txt
    assert "Nessuna dormita FR" in txt


def test_motivo_fr_positivo_rank_zero_dichiara_migliore_disponibile() -> None:
    """Top-1 con FR>0: 'Migliore disponibile — N FR'."""
    s = _make_suggerimento(n_dormite_fr=2)
    txt = _motivo(0, s)
    assert "Migliore disponibile" in txt
    assert "2 FR" in txt


def test_motivo_fr_positivo_rank_non_zero_solo_count() -> None:
    """Rank>0 con FR>0: solo 'N FR nel ciclo' (no 'Migliore')."""
    s = _make_suggerimento(n_dormite_fr=3)
    txt = _motivo(2, s)
    assert "Migliore" not in txt
    assert "3 FR" in txt
    assert "ciclo" in txt


# =====================================================================
# Precedenza: cap violato > fallback > FR count
# =====================================================================


def test_motivo_cap_violato_sovrascrive_fallback() -> None:
    """Se ci sono cap violati E fallback, vince il messaggio cap."""
    s = _make_suggerimento(
        n_dormite_fr=5, n_fr_cap_violazioni=1, stazione_sede_fallback=True
    )
    assert "Cap FR violato" in _motivo(0, s)


def test_motivo_fallback_sovrascrive_fr_zero() -> None:
    """Senza cap, ma fallback: il messaggio fallback ha priorità su 'Migliore'."""
    s = _make_suggerimento(n_dormite_fr=0, stazione_sede_fallback=True)
    assert "approssimativa" in _motivo(0, s)
    assert "Migliore" not in _motivo(0, s)
