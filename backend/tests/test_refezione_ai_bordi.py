"""Test unit Sprint 7.10 MR α.4 — refezione inserita ai bordi del turno.

Coverage di ``_inserisci_refezione_ai_bordi`` (decisione utente:
*"se manca la refezione, puoi aggiungerla alla fine o all'inizio se
è nelle ore indicate"*):

- presa in finestra refezione → REFEZ prima della presa, +30 min
- fine in finestra → REFEZ dopo la fine, +30 min
- nessun bordo in finestra → invariato (la giornata resta con
  violazione ``refezione_mancante`` come pre-α.4)
- precedenza: bordo "presa" vince su "fine" se entrambi in finestra
"""

from __future__ import annotations

from datetime import time

from colazione.domain.builder_pdc.builder import (
    REFEZIONE_MIN_DURATA,
    _BloccoPdcDraft,
    _inserisci_refezione_ai_bordi,
)


def _make_blocco(*, ora_inizio: time, ora_fine: time, durata_min: int) -> _BloccoPdcDraft:
    return _BloccoPdcDraft(
        seq=1,
        tipo_evento="CONDOTTA",
        ora_inizio=ora_inizio,
        ora_fine=ora_fine,
        durata_min=durata_min,
        stazione_da_codice="A",
        stazione_a_codice="B",
    )


# =====================================================================
# Strategia 1: REFEZ prima della presa
# =====================================================================


def test_refez_inizio_presa_in_finestra_pranzo() -> None:
    """Presa alle 12:00 (in finestra 11:30-15:30) → REFEZ alle 11:30
    e prestazione +30."""
    drafts = [
        _make_blocco(ora_inizio=time(12, 0), ora_fine=time(15, 0), durata_min=180),
    ]
    ora_presa_min = 12 * 60  # 12:00
    ora_fine_min = 16 * 60  # 16:00
    prest = 240

    new_presa, new_fine, new_drafts, new_prest = _inserisci_refezione_ai_bordi(
        drafts=drafts,
        ora_presa=ora_presa_min,
        ora_fine_servizio=ora_fine_min,
        prestazione_min=prest,
    )

    assert new_presa == 11 * 60 + 30  # 11:30
    assert new_fine == ora_fine_min
    assert new_prest == prest + REFEZIONE_MIN_DURATA
    assert new_drafts[0].tipo_evento == "REFEZ"
    assert new_drafts[0].ora_inizio == time(11, 30)
    assert new_drafts[0].ora_fine == time(12, 0)
    assert new_drafts[0].durata_min == REFEZIONE_MIN_DURATA


def test_refez_inizio_presa_in_finestra_cena() -> None:
    """Presa alle 19:00 (in finestra 18:30-22:30) → REFEZ alle 18:30."""
    drafts = [
        _make_blocco(ora_inizio=time(19, 0), ora_fine=time(22, 0), durata_min=180),
    ]
    new_presa, _, new_drafts, _ = _inserisci_refezione_ai_bordi(
        drafts=drafts,
        ora_presa=19 * 60,
        ora_fine_servizio=23 * 60,
        prestazione_min=240,
    )
    assert new_presa == 18 * 60 + 30
    assert new_drafts[0].tipo_evento == "REFEZ"


# =====================================================================
# Strategia 2: REFEZ dopo la fine
# =====================================================================


def test_refez_fine_in_finestra_pranzo() -> None:
    """Presa alle 08:00 (NON in finestra), fine alle 12:00 (in finestra)
    → REFEZ alle 12:00-12:30, prestazione +30."""
    drafts = [
        _make_blocco(ora_inizio=time(9, 0), ora_fine=time(11, 30), durata_min=150),
    ]
    new_presa, new_fine, new_drafts, new_prest = _inserisci_refezione_ai_bordi(
        drafts=drafts,
        ora_presa=8 * 60,
        ora_fine_servizio=12 * 60,
        prestazione_min=240,
    )
    assert new_presa == 8 * 60  # invariato
    assert new_fine == 12 * 60 + 30
    assert new_prest == 240 + REFEZIONE_MIN_DURATA
    assert new_drafts[-1].tipo_evento == "REFEZ"
    assert new_drafts[-1].ora_inizio == time(12, 0)
    assert new_drafts[-1].ora_fine == time(12, 30)


def test_refez_fine_in_finestra_cena() -> None:
    """Presa alle 16:00 (NON in finestra: 11:30-15:30 finita, 18:30 non
    iniziata), fine alle 20:00 (in finestra cena 18:30-22:30) →
    REFEZ alla fine 20:00-20:30."""
    drafts = [
        _make_blocco(ora_inizio=time(17, 0), ora_fine=time(19, 30), durata_min=150),
    ]
    _, new_fine, new_drafts, _ = _inserisci_refezione_ai_bordi(
        drafts=drafts,
        ora_presa=16 * 60,  # 16:00 NON in finestra
        ora_fine_servizio=20 * 60,  # 20:00 in finestra cena
        prestazione_min=300,
    )
    assert new_fine == 20 * 60 + 30
    assert new_drafts[-1].tipo_evento == "REFEZ"


# =====================================================================
# Strategia 3: nessun bordo in finestra → invariato
# =====================================================================


def test_refez_nessun_bordo_in_finestra() -> None:
    """Presa alle 04:00 (NON in finestra), fine alle 09:00 (NON in finestra)
    → invariato, refezione resta mancante."""
    drafts = [
        _make_blocco(ora_inizio=time(5, 0), ora_fine=time(8, 0), durata_min=180),
    ]
    new_presa, new_fine, new_drafts, new_prest = _inserisci_refezione_ai_bordi(
        drafts=drafts,
        ora_presa=4 * 60,
        ora_fine_servizio=9 * 60,
        prestazione_min=300,
    )
    # Tutto invariato.
    assert new_presa == 4 * 60
    assert new_fine == 9 * 60
    assert new_prest == 300
    assert new_drafts == drafts
    assert all(d.tipo_evento != "REFEZ" for d in new_drafts)


# =====================================================================
# Precedenza
# =====================================================================


def test_refez_presa_vince_su_fine_se_entrambi_in_finestra() -> None:
    """Presa 12:00 e fine 14:00 (entrambi in finestra pranzo): la
    strategia 1 vince → REFEZ all'inizio."""
    drafts = [
        _make_blocco(ora_inizio=time(12, 30), ora_fine=time(13, 30), durata_min=60),
    ]
    new_presa, new_fine, new_drafts, _ = _inserisci_refezione_ai_bordi(
        drafts=drafts,
        ora_presa=12 * 60,
        ora_fine_servizio=14 * 60,
        prestazione_min=180,
    )
    # Strategia 1 (presa) ha vinto: REFEZ all'INIZIO, non alla fine.
    assert new_presa == 11 * 60 + 30
    assert new_fine == 14 * 60  # invariato
    assert new_drafts[0].tipo_evento == "REFEZ"
    assert new_drafts[-1].tipo_evento != "REFEZ"
