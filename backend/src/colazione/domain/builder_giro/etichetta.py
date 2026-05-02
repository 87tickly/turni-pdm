"""Calcolo etichetta del giro materiale (Sprint 7.7 MR 3).

Funzione pura: dato l'insieme delle date di applicazione di tutte le
giornate di un giro e il set delle festività dell'anno, ritorna la
coppia ``(etichetta_tipo, etichetta_dettaglio)`` da scrivere su
``GiroMateriale``.

Decisione utente 2026-05-02 (memoria
``project_refactor_varianti_giri_separati_TODO.md``): l'enum è
collassato, niente codici PdE alias (``LV/SF/FX/GG``). Le 6 categorie
permettono al pianificatore di filtrare i giri per natura calendariale
senza ambiguità.

Categorie:

- ``feriale``  — tutte le date di applicazione del giro sono giorni
  feriali (lun-ven non festivi)
- ``sabato``   — tutte le date sono sabato non festivo
- ``domenica`` — tutte le date sono domenica non festiva
- ``festivo``  — tutte le date sono festività (nazionali o locali,
  anche cadenti di sabato/domenica)
- ``data_specifica`` — il giro vale per UNA sola data; il dettaglio
  riporta la data in formato ``DD/MM/YYYY``
- ``personalizzata`` — qualunque mix non riconducibile a una delle
  categorie monotipo; il dettaglio riporta il breakdown ordinato dei
  tipi giorno presenti (es. ``feriale+festivo``)

Il modulo è **DB-agnostic**. Non dipende dal tipo concreto di
``Giro``/``GiroAssegnato`` — riceve solo iterable di date, così la
stessa funzione si usa pre- e post-assegnazione.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from colazione.domain.calendario import tipo_giorno

# Stringhe ammesse, sincronizzate con il CHECK su `giro_materiale.etichetta_tipo`.
ETICHETTE_AMMESSE: frozenset[str] = frozenset(
    {"feriale", "sabato", "domenica", "festivo", "data_specifica", "personalizzata"}
)


def calcola_etichetta_giro(
    giornate_dates: Iterable[Iterable[date]],
    festivita: frozenset[date],
) -> tuple[str, str | None]:
    """Calcola etichetta del giro a partire dalle date di applicazione.

    Args:
        giornate_dates: per ogni giornata del giro, le date in cui la
            giornata-tipo si applica (output del clustering A1, oppure
            ``(giornata.data,)`` per giri non-clusterizzati). Tipico
            input: ``[g.dates_apply_or_data for g in giro.giornate]``.
        festivita: set di festività rilevanti (nazionali per l'azienda
            + locali per quell'azienda) per gli anni coperti dal giro.
            Caller costruisce con ``festivita_italiane(anno) +
            festività azienda`` o caricandole dal DB.

    Returns:
        Tupla ``(etichetta_tipo, etichetta_dettaglio)``:
        - ``etichetta_tipo``: una delle 6 stringhe in
          ``ETICHETTE_AMMESSE``.
        - ``etichetta_dettaglio``: ``None`` per le 4 categorie
          monotipo; ``"DD/MM/YYYY"`` per ``data_specifica``;
          breakdown joinato con ``+`` per ``personalizzata``
          (es. ``"feriale+festivo"``).

    Esempi:
        Giro vuoto (caso degenere) → ``personalizzata``:

        >>> calcola_etichetta_giro([], frozenset())
        ('personalizzata', None)

        Una sola data → ``data_specifica`` con dettaglio leggibile:

        >>> from datetime import date
        >>> calcola_etichetta_giro([[date(2026, 5, 4)]], frozenset())
        ('data_specifica', '04/05/2026')
    """
    date_giro: list[date] = []
    for dates in giornate_dates:
        date_giro.extend(dates)

    if not date_giro:
        return ("personalizzata", None)

    # Una sola data unica → etichetta data_specifica.
    date_uniche = sorted(set(date_giro))
    if len(date_uniche) == 1:
        return ("data_specifica", date_uniche[0].strftime("%d/%m/%Y"))

    tipi = {tipo_giorno(d, festivita) for d in date_giro}

    if tipi == {"feriale"}:
        return ("feriale", None)
    if tipi == {"sabato"}:
        return ("sabato", None)
    if tipi == {"domenica"}:
        return ("domenica", None)
    if tipi == {"festivo"}:
        return ("festivo", None)

    # Mix di tipi → personalizzata con breakdown ordinato.
    # Ordine deterministico: feriale, sabato, domenica, festivo (calendariale).
    ordine = ("feriale", "sabato", "domenica", "festivo")
    presenti = [t for t in ordine if t in tipi]
    return ("personalizzata", "+".join(presenti))
