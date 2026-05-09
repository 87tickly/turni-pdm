"""Riposo intraturno §11.5 NORMATIVA-PDC — Sprint 8.2 MR-PD7b-2.

Implementa la regola RIGIDA §11.5:
- **11h** standard tra due giornate consecutive (= gap minimo
  fine_prestazione_i → inizio_prestazione_i+1).
- **14h** dopo una giornata che finisce tra **00:01 e 01:00**.
- **16h** dopo una giornata **notturna** (fine tra **00:01 e 05:00**).

Il modulo:
1. Calcola il riposo richiesto in funzione dell'ora di fine
   prestazione della giornata precedente.
2. Calcola il riposo effettivo come gap fra fine_prestazione[i] e
   inizio_prestazione[i+1] (con wrap-around modulo 24h).
3. Valida e popola il campo ``riposo_min_post`` di ogni
   ``GiornataPdcDraft`` (poi persistito in
   ``TurnoPdcGiornata.riposo_min`` dal builder MVP).

Per l'**ultima giornata del ciclo**, il "successivo" è la **giornata 1
del ciclo successivo** (wrap-around). Il calcolo aggiunge
``ciclo_giorni - n_giornate_attive_definite`` notti di "stacco settimanale"
+ il gap effettivo del wrap. Vedi §11.4 per la validazione settimanale
di quel gap (MR-PD7b-3).
"""

from __future__ import annotations

import logging
from datetime import time

from colazione.domain.builder_pdc.builder import _GiornataPdcDraft

logger = logging.getLogger(__name__)


# =====================================================================
# Costanti normativa
# =====================================================================

#: Riposo intraturno minimo standard fra giornate consecutive (NORMATIVA §11.5).
RIPOSO_INTRATURNO_STD_MIN: int = 11 * 60  # 11h

#: Riposo aumentato a 14h se la giornata precedente finisce tra 00:01 e 01:00.
RIPOSO_INTRATURNO_FINE_TARDA_MIN: int = 14 * 60  # 14h

#: Riposo aumentato a 16h dopo giornata notturna (fine tra 00:01 e 05:00).
RIPOSO_INTRATURNO_NOTTURNO_MIN: int = 16 * 60  # 16h


# =====================================================================
# Calcolo riposo richiesto
# =====================================================================


def riposo_richiesto_min(fine_prestazione: time) -> int:
    """Cap di riposo richiesto in funzione dell'ora di fine prestazione.

    NORMATIVA-PDC §11.5:
    - fine ∈ [00:01-01:00]: 14h (riposo allungato per fine "tardi").
    - fine ∈ [00:01-05:00]: 16h (riposo aumentato per giornata notturna).
    - altrimenti: 11h standard.

    NB: la fascia notturna 00:01-05:00 INCLUDE 00:01-01:00. Per la
    classificazione precedente (entry 269 SEVERO S1 fix `is_cap_notturno`),
    la "notturna" ha la priorità (più lunga), quindi:
    - fine ∈ [00:01-01:00]: 14h
    - fine ∈ (01:00-05:00]: 16h
    - altrimenti: 11h
    Decisione interpretativa NINO: la regola §11.5 letterale dice
    "dopo una giornata che finisce tra 00:01 e 01:00 → 14h, dopo una
    notturna (00:01-05:00) → 16h". Letteralmente le due categorie si
    sovrappongono nell'intervallo [00:01-01:00]. Adottiamo la **più
    cautelativa = 16h** quando entrambe si applicherebbero (= fine in
    [00:01-01:00]). Conservativo per il PdC, sovra-strict per il builder.

    Args:
        fine_prestazione: ora di fine prestazione della giornata
            precedente (``time(h, m)``).

    Returns:
        Cap richiesto in minuti.
    """
    h = fine_prestazione.hour
    m = fine_prestazione.minute
    minuto_assoluto = h * 60 + m

    # Notturno [00:01-05:00] (1..299 minuti) → 16h.
    # Decisione conservativa: include anche [00:01-01:00] perché 16 > 14.
    if 1 <= minuto_assoluto < 300:
        return RIPOSO_INTRATURNO_NOTTURNO_MIN

    # Tutto il resto (incluso 00:00 esatto): standard 11h.
    return RIPOSO_INTRATURNO_STD_MIN


# =====================================================================
# Calcolo riposo effettivo
# =====================================================================


def riposo_effettivo_min(
    fine_prestazione_prec: time,
    inizio_prestazione_succ: time,
) -> int:
    """Gap minuti fra fine giornata i e inizio giornata i+1.

    Assume che le due giornate siano in giorni calendariali consecutivi
    (= il PdC riposa 1 notte fra le due). Calcolo:

    ``gap = (24*60 - to_min(fine_prec)) + to_min(inizio_succ)``

    Esempi:
    - fine 22:00, inizio 09:00 successivo: 2h + 9h = 11h ✅ standard.
    - fine 23:30, inizio 13:30 successivo: 0h30 + 13h30 = 14h ✅ tarda.
    - fine 03:00, inizio 19:00 successivo: 21h + 19h = 40h (riposo lungo).

    Args:
        fine_prestazione_prec: time fine giornata i.
        inizio_prestazione_succ: time inizio giornata i+1.

    Returns:
        Gap in minuti.
    """
    fine_min = fine_prestazione_prec.hour * 60 + fine_prestazione_prec.minute
    inizio_min = inizio_prestazione_succ.hour * 60 + inizio_prestazione_succ.minute
    return (24 * 60 - fine_min) + inizio_min


# =====================================================================
# Validazione e popolamento riposo_min_post
# =====================================================================


def calcola_e_valida_riposi_intraturno(
    drafts: list[_GiornataPdcDraft],
) -> list[str]:
    """Calcola ``riposo_min_post`` per ogni giornata + valida §11.5.

    **Side effect**: imposta ``draft.riposo_min_post`` su ogni elemento
    di ``drafts``. Il valore è il gap effettivo verso la giornata
    successiva (modulo lista, ultima giornata → indice 0 wrap-around).

    **Validazione**: per ogni coppia (i, i+1), confronta
    ``riposo_effettivo`` con ``riposo_richiesto_min(fine_i)``. Se
    insufficiente, aggiunge violazione testuale.

    Per l'ULTIMA giornata del ciclo (i = N-1), il gap "settimanale"
    è scope §11.4 (MR-PD7b-3, validatore separato). Qui calcoliamo
    SOLO il gap raw fine_N → inizio_1 (= notte singola, sotto-stima
    del riposo settimanale reale che include più notti). Il
    `riposo_min_post` dell'ultima giornata viene popolato col gap
    settimanale stimato come 24h*1 + (24h - fine) + inizio (= almeno
    24h vero), che è un placeholder finché §11.4 non lo raffina.

    Args:
        drafts: lista di ``GiornataPdcDraft`` post-build, ordinata per
            ``numero_giornata``.

    Returns:
        Lista violazioni testuali per il caller (vuota se tutto ok).
        Formato: ``"riposo_intraturno_insufficiente:G{i}->G{j}:richiesti_{N}min:effettivi_{M}min"``.
    """
    violazioni: list[str] = []
    n = len(drafts)
    if n == 0:
        return violazioni

    for idx in range(n):
        prec = drafts[idx]
        # Successiva: idx+1 mod N (wrap-around)
        succ = drafts[(idx + 1) % n]

        if idx < n - 1:
            # Coppia interna (1 sola notte fra le due).
            riposo_eff = riposo_effettivo_min(
                prec.fine_prestazione, succ.inizio_prestazione
            )
            riposo_req = riposo_richiesto_min(prec.fine_prestazione)
            prec.riposo_min_post = riposo_eff
            if riposo_eff < riposo_req:
                violazioni.append(
                    f"riposo_intraturno_insufficiente:"
                    f"G{prec.numero_giornata}->G{succ.numero_giornata}:"
                    f"richiesti_{riposo_req}min:"
                    f"effettivi_{riposo_eff}min"
                )
        else:
            # Ultima giornata: gap "settimanale" (verso giornata 1
            # del ciclo successivo). Stima: almeno 1 notte + gap raw.
            # §11.4 raffina (MR-PD7b-3).
            gap_singola_notte = riposo_effettivo_min(
                prec.fine_prestazione, succ.inizio_prestazione
            )
            # Aggiungo +24h per stima conservativa (1 notte di stacco
            # in più; il vero riposo settimanale è ≥62h da §11.4).
            prec.riposo_min_post = gap_singola_notte + 24 * 60

    return violazioni


__all__ = [
    "RIPOSO_INTRATURNO_FINE_TARDA_MIN",
    "RIPOSO_INTRATURNO_NOTTURNO_MIN",
    "RIPOSO_INTRATURNO_STD_MIN",
    "calcola_e_valida_riposi_intraturno",
    "riposo_effettivo_min",
    "riposo_richiesto_min",
]
