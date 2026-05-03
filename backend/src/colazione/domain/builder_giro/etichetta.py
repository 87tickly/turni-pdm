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
# Sprint 7.8 MR 3: sigle stile Trenord (PDF turno 1134) per il rendering
# compatto delle etichette varianti. Più corto = più leggibile sul
# Gantt. Ordine: matching `tipo_giorno_categoria`.
_SIGLA_CATEGORIA: dict[str, str] = {
    "lavorativo": "Lv",
    "prefestivo": "P",
    "festivo": "F",
}
# Ordine deterministico per il caso misto (calendariale: lavorativo
# prima, prefestivo medio, festivo ultimo).
_ORDINE_CATEGORIE: tuple[str, ...] = ("lavorativo", "prefestivo", "festivo")
# Sprint 7.8 MR 3: max numero di date elencate inline nelle etichette
# stile Trenord ("Si eff. 3-4-5/3" o "P escl. 21-28/3, 11/4"). Sopra
# questa soglia, l'etichetta degrada a `{Sigla} ({n} date)` per non
# saturare l'UI. Trenord usa tipicamente 3-5 date inline.
_MAX_DATE_INLINE: int = 5


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


def _format_date_short(d: date) -> str:
    """Formato data Trenord: DD/M (no anno, mese senza zero leading)."""
    return f"{d.day}/{d.month}"


def _format_date_list(dates: Iterable[date]) -> str:
    """Lista date compatte separate da virgola: 3/3, 4/3, 11/4."""
    return ", ".join(_format_date_short(d) for d in sorted(dates))


def calcola_etichetta_variante(
    dates_apply: Iterable[date],
    festivita: frozenset[date],
    periodo_categoria_dates: dict[str, frozenset[date]] | None = None,
) -> str:
    """Etichetta UI stile Trenord per una variante calendariale.

    Sprint 7.8 MR 3 (decisione utente 2026-05-03 + PDF turno 1134):
    riscrittura con sigle compatte (`Lv`/`F`/`P`) e formato
    inclusioni/esclusioni:

    - 1 data → ``"Solo DD/M/YY"`` (compatto).
    - 1 categoria, copre TUTTE le date di quella categoria nel periodo
      (dato `periodo_categoria_dates`) → ``"Lv"`` / ``"F"`` / ``"P"``.
    - 1 categoria, copre la maggior parte ma con N≤5 esclusioni
      (e ``periodo_categoria_dates`` fornito) →
      ``"Lv esclusi 21/3, 28/3, 11/4"``.
    - 1 categoria, copre poche date elencabili (n≤5) →
      ``"Si eff. 3/3, 4/3, 5/3"``.
    - 1 categoria, troppe date per elencare → ``"Lv (12 date)"``.
    - Più categorie → ``"Misto: Lv+F (N date)"`` (sigle joinate).
    - 0 date → ``"(nessuna data)"``.

    `periodo_categoria_dates` è opzionale: se omesso, la funzione opera
    senza confronto col periodo (no "esclusi" né "Lv" intero), quindi
    fallback semantico più conservativo (sempre numero date).

    Args:
        dates_apply: date in cui la variante si applica.
        festivita: festività rilevanti per gli anni coperti.
            Necessario per ``tipo_giorno_categoria`` (riconoscere
            festivi vs feriali vs prefestivi).
        periodo_categoria_dates: opzionale, mappa
            ``{"lavorativo": frozenset(date), "prefestivo": ...,
            "festivo": ...}`` con TUTTE le date del periodo della
            giornata-pattern raggruppate per categoria. Tipicamente
            costruito dal caller raccogliendo dates_apply di tutte le
            varianti della stessa giornata-K e applicando
            ``tipo_giorno_categoria``.

    Esempi:

        >>> from datetime import date
        >>> calcola_etichetta_variante([date(2026, 5, 4)], frozenset())
        'Solo 4/5/26'
        >>> calcola_etichetta_variante([], frozenset())
        '(nessuna data)'
    """
    date_uniche = sorted(set(dates_apply))
    n = len(date_uniche)

    if n == 0:
        return "(nessuna data)"

    if n == 1:
        d = date_uniche[0]
        return f"Solo {d.day}/{d.month}/{d.year % 100:02d}"

    tipi_per_data = {d: tipo_giorno_categoria(d, festivita) for d in date_uniche}
    tipi_unici = set(tipi_per_data.values())

    # Sprint 7.9 fix UX (decisione utente 2026-05-03): "Misto: Lv+F"
    # è criptico per chi non conosce le sigle. Sostituiamo con i nomi
    # estesi "Lavorativo+Festivo" per la categoria multi-tipo.
    if len(tipi_unici) > 1:
        nomi = [_LABEL_CATEGORIA[t] for t in _ORDINE_CATEGORIE if t in tipi_unici]
        return f"{'+'.join(nomi)} ({n} date)"

    # Mono-categoria: confronta col periodo se fornito.
    cat_unica = next(iter(tipi_unici))
    sigla = _SIGLA_CATEGORIA[cat_unica]

    if periodo_categoria_dates is not None:
        date_categoria_periodo = periodo_categoria_dates.get(cat_unica, frozenset())
        if date_categoria_periodo:
            esclusi = sorted(date_categoria_periodo - set(date_uniche))
            n_periodo = len(date_categoria_periodo)
            # Copertura totale → sigla pura
            if not esclusi:
                return sigla
            # Maggioranza coperta + esclusioni elencabili → "esclusi"
            if len(esclusi) <= _MAX_DATE_INLINE and n > n_periodo // 2:
                return f"{sigla} esclusi {_format_date_list(esclusi)}"
            # Minoranza coperta + date elencabili → "Si eff."
            if n <= _MAX_DATE_INLINE:
                return f"Si eff. {_format_date_list(date_uniche)} ({sigla})"
            # Troppe sia esclusi che incluse: fallback conteggio.
            return f"{sigla} ({n} di {n_periodo} date)"

    # Senza periodo: fallback su elenco esplicito o conteggio.
    # Sprint 7.9 fix UX: usa il nome esteso della categoria invece
    # della sigla per leggibilità ("Lavorativo · 12 date" invece di
    # "Lv (12 date)").
    label = _LABEL_CATEGORIA[cat_unica]
    if n <= _MAX_DATE_INLINE:
        return f"Si eff. {_format_date_list(date_uniche)} ({label})"
    return f"{label} · {n} date"
