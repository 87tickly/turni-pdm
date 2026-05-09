"""Riposo settimanale §11.4 NORMATIVA-PDC — Sprint 8.2 MR-PD7b-3.

Implementa la regola RIGIDA §11.4:
> "riposo settimanale ≥ 62 ore consecutive, dentro le quali devono
> ricadere almeno 2 giorni solari interi"

Validatore strutturale del turno (NON validazione persona-specifica:
quella richiede modello assegnazione persona ancora non in modello,
scope MR-PD7+ con il ruolo Gestione Personale).

Algoritmo "≥1 riposo settimanale ogni 7 giornate consecutive"
(raffinamento S4 SEVERO PIANO PD7b vs heuristic ``ciclo // 7`` sotto-permissiva):

1. Calcola i gap fra ogni coppia consecutive di giornate (incluso
   wrap-around N → 1 settimana dopo). I gap inter-giornata sono già
   in ``draft.riposo_min_post`` (popolato da MR-PD7b-2).
2. Itera giornate; per ognuna:
   - Se ``riposo_min_post >= 62*60`` → questa è "occorrenza riposo
     settimanale" → reset contatore "giornate consecutive senza riposo"
     a 0.
   - Altrimenti incrementa contatore.
   - Se contatore == 7 (= 7 giornate consecutive senza riposo
     settimanale) → violazione "no_riposo_settimanale_in_7gg".
3. Per ogni occorrenza riposo settimanale, verifica che includa
   ≥ 2 giorni solari interi. Se ``data_inizio_programma`` /
   ``data_fine_programma`` / ``festivita`` forniti + ``ciclo_giorni``
   noto, usa ``enumera_date_giornata`` per CALCOLARE le date concrete
   e contare i giorni solari interi reali. Altrimenti usa il proxy
   ``gap_min // (24*60)`` (= numero di "blocchi 24h" dentro la finestra,
   sotto-stima se la finestra parte a metà giornata).

Output: lista violazioni testuali, propagata come parte di
``violazioni_ciclo_extra`` al persister + finisce in
``generation_metadata_json.riposo_settimanale_violazioni``.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta

from colazione.domain.builder_pdc.builder import _GiornataPdcDraft
from colazione.domain.giornate_concrete import enumera_date_giornata

logger = logging.getLogger(__name__)


# =====================================================================
# Costanti normativa
# =====================================================================

#: Riposo settimanale minimo (NORMATIVA §11.4): 62 ore consecutive.
RIPOSO_SETTIMANALE_MIN_MIN: int = 62 * 60  # 3720

#: Numero minimo giorni solari interi richiesti dentro la finestra
#: di riposo settimanale (NORMATIVA §11.4).
GIORNI_SOLARI_INTERI_RICHIESTI: int = 2

#: Giornate consecutive senza riposo settimanale oltre cui si genera
#: violazione. NORMATIVA §11.4 lega il riposo "settimanale" al concetto
#: di settimana → max 7 giornate consecutive.
GIORNATE_CONSECUTIVE_MAX_SENZA_RIPOSO: int = 7


# =====================================================================
# Helper conteggio giorni solari interi
# =====================================================================


def _giorni_solari_interi_in_finestra(
    start: datetime, end: datetime
) -> int:
    """Conta giorni solari interi (00:00:00-23:59:59) dentro
    ``[start, end]``.

    Esempio: start = sabato 14:00, end = martedì 04:00 → finestra
    62h. Giorni interi inclusi: domenica e lunedì → 2.

    Args:
        start: timestamp inizio finestra (incluso).
        end: timestamp fine finestra (incluso).

    Returns:
        Numero giorni solari interi nella finestra.
    """
    if end <= start:
        return 0
    # Primo giorno solare intero successivo a start: il giorno SUCCESSIVO
    # alla data di start (00:00:00). Es. start sabato 14:00 → primo
    # giorno intero candidato = domenica 00:00:00.
    primo_intero = datetime.combine(
        start.date() + timedelta(days=1), time(0, 0, 0)
    )
    # Ultimo giorno solare intero precedente a end: il giorno PRECEDENTE
    # alla data di end (23:59:59). Es. end martedì 04:00 → ultimo
    # giorno intero = lunedì 23:59:59.
    ultimo_intero = datetime.combine(
        end.date() - timedelta(days=1), time(23, 59, 59)
    )
    if ultimo_intero < primo_intero:
        return 0
    return (ultimo_intero.date() - primo_intero.date()).days + 1


# =====================================================================
# Validatore principale
# =====================================================================


def valida_riposo_settimanale(
    drafts: list[_GiornataPdcDraft],
    *,
    ciclo_giorni: int | None = None,
    data_inizio_programma: date | None = None,
    data_fine_programma: date | None = None,
    festivita: frozenset[date] | None = None,
) -> list[str]:
    """Valida §11.4 sui drafts post-build.

    Prerequisito: ``drafts[i].riposo_min_post`` popolato da
    ``riposo_intraturno.calcola_e_valida_riposi_intraturno`` (MR-PD7b-2).

    Algoritmo "≥1 riposo settimanale ogni 7 giornate consecutive":
    - Itera giornate sequenzialmente con contatore
      ``giornate_da_ultimo_riposo``.
    - Se ``riposo_min_post[i] >= 62h`` → reset contatore + verifica
      ``giorni_solari_interi >= 2``.
    - Altrimenti incrementa contatore.
    - Se contatore == 7 → violazione "no riposo entro 7gg".

    Args:
        drafts: lista ``GiornataPdcDraft`` post-build, ordinata per
            ``numero_giornata``. ``riposo_min_post`` deve essere
            popolato (MR-PD7b-2).
        ciclo_giorni: durata del ciclo turno. Se None, defaults a
            ``len(drafts)``.
        data_inizio_programma, data_fine_programma, festivita: se
            forniti, abilita conteggio giorni solari interi REALE via
            ``enumera_date_giornata``. Altrimenti usa proxy
            ``gap_min // (24*60)``.

    Returns:
        Lista violazioni testuali. Vuota se §11.4 rispettata.
        Formati:
        - ``"riposo_settimanale_no_in_7gg:contatore_raggiunto_7"``
        - ``"riposo_settimanale_giorni_solari_insufficienti:G{i}_post:richiesti_2:effettivi_{n}"``
        - ``"riposo_settimanale_durata_insufficiente:G{i}_post:richiesti_3720min:effettivi_{n}min"``
    """
    violazioni: list[str] = []
    n = len(drafts)
    if n == 0:
        return violazioni

    ciclo = ciclo_giorni if ciclo_giorni is not None else n

    use_date_concrete = (
        data_inizio_programma is not None
        and data_fine_programma is not None
        and festivita is not None
    )

    contatore = 0
    riposi_settimanali_trovati = 0

    for idx in range(n):
        d = drafts[idx]
        gap_post = d.riposo_min_post

        if gap_post >= RIPOSO_SETTIMANALE_MIN_MIN:
            # Riposo settimanale candidato: verifica giorni solari interi.
            riposi_settimanali_trovati += 1

            n_giorni_interi = _conta_giorni_solari_per_riposo(
                d,
                drafts[(idx + 1) % n],
                gap_post,
                use_date_concrete=use_date_concrete,
                ciclo_giorni=ciclo,
                data_inizio_programma=data_inizio_programma,
                data_fine_programma=data_fine_programma,
                festivita=festivita,
            )

            if n_giorni_interi < GIORNI_SOLARI_INTERI_RICHIESTI:
                violazioni.append(
                    f"riposo_settimanale_giorni_solari_insufficienti:"
                    f"G{d.numero_giornata}_post:"
                    f"richiesti_{GIORNI_SOLARI_INTERI_RICHIESTI}:"
                    f"effettivi_{n_giorni_interi}"
                )

            contatore = 0
        else:
            contatore += 1
            if contatore >= GIORNATE_CONSECUTIVE_MAX_SENZA_RIPOSO:
                violazioni.append(
                    f"riposo_settimanale_no_in_7gg:"
                    f"contatore_raggiunto_{contatore}_a_G{d.numero_giornata}"
                )
                # Reset per evitare violazioni ripetute consecutive
                contatore = 0

    # Verifica numero minimo riposi settimanali per ciclo
    riposi_attesi_min = max(1, -(-ciclo // 7))  # ceil(ciclo / 7)
    if riposi_settimanali_trovati < riposi_attesi_min:
        violazioni.append(
            f"riposo_settimanale_numero_insufficiente:"
            f"trovati_{riposi_settimanali_trovati}:"
            f"attesi_min_{riposi_attesi_min}_per_ciclo_{ciclo}gg"
        )

    return violazioni


def _conta_giorni_solari_per_riposo(
    draft_pre: _GiornataPdcDraft,
    draft_post: _GiornataPdcDraft,
    gap_min: int,
    *,
    use_date_concrete: bool,
    ciclo_giorni: int,
    data_inizio_programma: date | None,
    data_fine_programma: date | None,
    festivita: frozenset[date] | None,
) -> int:
    """Conta i giorni solari interi nella finestra di riposo che SEGUE
    ``draft_pre`` e PRECEDE ``draft_post``.

    Se ``use_date_concrete`` + parametri programma forniti: usa
    ``enumera_date_giornata`` per costruire datetime concreti +
    ``_giorni_solari_interi_in_finestra``.

    Altrimenti: proxy ``gap_min // (24*60)`` come stima.
    """
    if not use_date_concrete:
        return gap_min // (24 * 60)

    assert data_inizio_programma is not None  # type narrow
    assert data_fine_programma is not None
    assert festivita is not None

    # Trova UNA data concreta per draft_pre (la prima del periodo).
    date_pre = enumera_date_giornata(
        numero_giornata=draft_pre.numero_giornata,
        variante_calendario=draft_pre.variante_calendario,
        ciclo_giorni=ciclo_giorni,
        data_inizio_programma=data_inizio_programma,
        data_fine_programma=data_fine_programma,
        festivita=festivita,
    )
    if not date_pre:
        # Nessuna data nel periodo: fallback proxy.
        return gap_min // (24 * 60)

    # Costruisce start/end timestamp.
    data_pre_first = date_pre[0]
    start_dt = datetime.combine(data_pre_first, draft_pre.fine_prestazione)
    end_dt = start_dt + timedelta(minutes=gap_min)
    return _giorni_solari_interi_in_finestra(start_dt, end_dt)


__all__ = [
    "GIORNATE_CONSECUTIVE_MAX_SENZA_RIPOSO",
    "GIORNI_SOLARI_INTERI_RICHIESTI",
    "RIPOSO_SETTIMANALE_MIN_MIN",
    "valida_riposo_settimanale",
]
