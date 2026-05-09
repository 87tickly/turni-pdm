"""Modulo facade pubblico per le primitive del builder PdC condivise
fra `builder.py`, `multi_turno.py`, `deposito_first.py`, `split_cv.py`
— Sprint 8.2 MR-PD-FIX-SEVERO 2 (S2).

**Motivazione** (SEVERO MR-PD3 finding S2 HIGH): prima di questo
modulo, `deposito_first.py`, `multi_turno.py`, `split_cv.py`
importavano direttamente dai simboli privati di `builder.py`
(``_BloccoPdcDraft``, ``_GiornataPdcDraft``, ``_t``, ``_from_min``,
``_build_giornata_pdc``, ``_aggiungi_dormite_fr``, ecc.). Anti-pattern:
i simboli underscore segnalano API privata che può cambiare senza
preavviso. Refactor o rimozione di `builder.py` (MR-PD-FIX-SEVERO 2
S2-bis previsto) rompevano i moduli consumatori.

Questo modulo espone gli stessi simboli con **nomi pubblici** (senza
underscore) come **re-export-rename** di quelli privati. I moduli
consumatori importano da qui, indipendentemente da come la
definizione si sposterà in futuro.

**Convenzione**: i simboli ESPORTATI da questo modulo costituiscono
l'**API stabile** del builder-base. Cambiarli richiede coordinamento
fra builder/deposito_first/multi_turno/split_cv. I simboli ``_xxx``
in `builder.py` restano interni e possono cambiare liberamente — i
consumatori non li toccano direttamente.

Riferimenti: vedi finding S2 in
``docs/critiche/SPRINT-8.2-MR-PD3-deposito-first.md``.
"""

from __future__ import annotations

from colazione.domain.builder_pdc.builder import (
    ACCESSORI_MIN_STANDARD,
    CONDOTTA_MAX_MIN,
    FINE_SERVIZIO_MIN,
    FR_MAX_PER_28GG,
    FR_MAX_PER_SETTIMANA,
    PRESA_SERVIZIO_MIN,
    PRESTAZIONE_MAX_NOTTURNO,
    PRESTAZIONE_MAX_STANDARD,
    REFEZIONE_FINESTRE,
    REFEZIONE_MIN_DURATA,
    REFEZIONE_SOGLIA_MIN,
    BuilderTurnoPdcResult,
    DepositoPdcNonTrovatoError,
    GiriEsistentiError,
    GiroNonTrovatoError,
    GiroVuotoError,
    _aggiungi_dormite_fr,
    _BloccoPdcDraft,
    _build_giornata_pdc,
    _calcola_violazioni_cap_fr,
    _diff,
    _from_min,
    _genera_codice_turno,
    _GiornataPdcDraft,
    _persisti_un_turno_pdc,
    _t,
)

# Re-export con nomi pubblici (rimuovo underscore leading).
BloccoPdcDraft = _BloccoPdcDraft
GiornataPdcDraft = _GiornataPdcDraft

aggiungi_dormite_fr = _aggiungi_dormite_fr
build_giornata_pdc = _build_giornata_pdc
calcola_violazioni_cap_fr = _calcola_violazioni_cap_fr
diff_minuti = _diff
from_minuti = _from_min
genera_codice_turno = _genera_codice_turno
persisti_un_turno_pdc = _persisti_un_turno_pdc
to_minuti = _t


__all__ = [
    "ACCESSORI_MIN_STANDARD",
    "BloccoPdcDraft",
    "BuilderTurnoPdcResult",
    "CONDOTTA_MAX_MIN",
    "DepositoPdcNonTrovatoError",
    "FINE_SERVIZIO_MIN",
    "FR_MAX_PER_28GG",
    "FR_MAX_PER_SETTIMANA",
    "GiornataPdcDraft",
    "GiriEsistentiError",
    "GiroNonTrovatoError",
    "GiroVuotoError",
    "PRESA_SERVIZIO_MIN",
    "PRESTAZIONE_MAX_NOTTURNO",
    "PRESTAZIONE_MAX_STANDARD",
    "REFEZIONE_FINESTRE",
    "REFEZIONE_MIN_DURATA",
    "REFEZIONE_SOGLIA_MIN",
    "aggiungi_dormite_fr",
    "build_giornata_pdc",
    "calcola_violazioni_cap_fr",
    "diff_minuti",
    "from_minuti",
    "genera_codice_turno",
    "persisti_un_turno_pdc",
    "to_minuti",
]
