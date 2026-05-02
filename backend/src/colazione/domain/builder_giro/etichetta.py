"""Etichette dei giri materiali — Sprint 7.7 MR 3 (giro) + MR 6 (variante).

Il modulo espone DUE funzioni pure, indipendenti, entrambe DB-agnostic:

1. ``calcola_etichetta_giro`` (MR 3) — etichetta-su-giro con 6
   categorie (``feriale | sabato | domenica | festivo | data_specifica
   | personalizzata``). Non più applicata al persister (rimossa in
   MR 5), resta esposta per uso futuro/diagnostico.

2. ``calcola_etichetta_variante`` (MR 6) — etichetta-su-variante con
   3 categorie operative (``Lavorativo | Prefestivo | Festivo``) +
   formati speciali per data unica e mix. È la versione visualizzata
   in UI dal Sprint 7.7 MR 6 in poi.

Le due funzioni sono separate perché classificano cose diverse:
- MR 3 risponde a "che tipo di giro è" (un giro feriale, un giro
  domenicale, ecc.)
- MR 6 risponde a "che tipo di variante è" usando la categorizzazione
  semantica utente (festivo include domeniche, prefestivo = vigilia).

Entrambe ricevono solo iterable di date + festività set, niente DB.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from colazione.domain.calendario import tipo_giorno, tipo_giorno_categoria

# Stringhe ammesse per `calcola_etichetta_giro`. Sincronizzate con il
# CHECK su `giro_materiale.etichetta_tipo` (MR 3, mantenuto come
# riferimento per future estensioni).
ETICHETTE_AMMESSE: frozenset[str] = frozenset(
    {"feriale", "sabato", "domenica", "festivo", "data_specifica", "personalizzata"}
)

# Mapping interno usato da `calcola_etichetta_variante` per produrre
# label UI. Le tre chiavi corrispondono a `tipo_giorno_categoria`.
_LABEL_CATEGORIA: dict[str, str] = {
    "lavorativo": "Lavorativo",
    "prefestivo": "Prefestivo",
    "festivo": "Festivo",
}
# Ordine deterministico per il caso misto (calendariale: lavorativo
# prima, prefestivo medio, festivo ultimo).
_ORDINE_CATEGORIE: tuple[str, ...] = ("lavorativo", "prefestivo", "festivo")


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


def calcola_etichetta_variante(
    dates_apply: Iterable[date],
    festivita: frozenset[date],
) -> str:
    """Etichetta UI semantica per una variante calendariale (Sprint 7.7 MR 6).

    Decisione utente 2026-05-02 (memoria
    ``feedback_etichetta_categoria_variante.md``): il pianificatore
    deve vedere SUBITO se la variante riguarda lavorativi, prefestivi
    o festivi — non il testo grezzo PdE (``"Circola giornalmente.
    Soppresso..."``). Le 3 categorie operative seguono la
    classificazione di ``tipo_giorno_categoria``:

    Output:

    - ``"Solo DD/MM/YYYY"`` se la variante vale per UNA sola data.
    - ``"Lavorativo · N date"`` se tutte le date sono lavorative.
    - ``"Prefestivo · N date"`` se tutte le date sono prefestive.
    - ``"Festivo · N date"`` se tutte le date sono festive (incluse
      domeniche).
    - ``"Misto: A+B[+C] · N date"`` se la variante mescola categorie
      diverse (label uniche in ordine calendariale, joinate con ``+``).
    - ``"(nessuna data)"`` se l'iterable è vuoto.

    Args:
        dates_apply: date in cui la variante si applica (tipico:
            ``variante.dates_apply`` del builder, oppure
            ``[date.fromisoformat(s) for s in dates_apply_json]``
            quando si parte dal DB).
        festivita: festività rilevanti per gli anni coperti DA E
            includendo il giorno successivo (per riconoscere il
            prefestivo del 31/12 servono le festività del 1/1 anno+1).
            Caller responsabile della costruzione.

    Esempi:

        >>> from datetime import date
        >>> calcola_etichetta_variante([date(2026, 5, 4)], frozenset())
        'Solo 04/05/2026'
        >>> calcola_etichetta_variante([], frozenset())
        '(nessuna data)'
    """
    date_uniche = sorted(set(dates_apply))
    n = len(date_uniche)

    if n == 0:
        return "(nessuna data)"

    if n == 1:
        return f"Solo {date_uniche[0].strftime('%d/%m/%Y')}"

    tipi = {tipo_giorno_categoria(d, festivita) for d in date_uniche}
    suffix = f"{n} date"

    if len(tipi) == 1:
        unico = next(iter(tipi))
        return f"{_LABEL_CATEGORIA[unico]} · {suffix}"

    presenti = [_LABEL_CATEGORIA[t] for t in _ORDINE_CATEGORIE if t in tipi]
    return f"Misto: {'+'.join(presenti)} · {suffix}"
