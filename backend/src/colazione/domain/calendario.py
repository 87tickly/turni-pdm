"""Calendario ufficiale italiano — helper Sprint 7.7 MR 2.

Funzioni pure (no DB) per calcolare:

- ``pasqua_gregoriana(anno)``: data della Pasqua gregoriana per un anno
  qualsiasi (algoritmo Anonymous Gregorian / Meeus-Jones-Butcher).
- ``pasquetta(anno)``: lunedì dell'Angelo (Pasqua + 1 giorno).
- ``festivita_italiane_fisse(anno)``: lista delle 10 festività
  nazionali fisse italiane in date concrete per l'anno.
- ``festivita_italiane(anno)``: festività fisse + Pasqua + Pasquetta.
- ``tipo_giorno(data, festivita_set)``: classifica una data come
  ``"feriale" | "sabato" | "domenica" | "festivo"``.

Le festività locali (Sant'Ambrogio per Milano, patroni regionali)
NON sono qui — vivono come righe ``FestivitaUfficiale`` con
``azienda_id`` valorizzato (il builder le aggiunge alla set di
festività attive per quell'azienda).

Decisione utente 2026-05-02 (memoria
`project_refactor_varianti_giri_separati_TODO.md`): il calendario è
prerequisito del refactor "varianti → giri separati con etichette
parlanti". Già qui esposto come API così il frontend può usarlo per
visualizzazione + il builder lo userà per cluster A1 più sensato in
Sprint 7.7.3.
"""

from __future__ import annotations

from datetime import date


def pasqua_gregoriana(anno: int) -> date:
    """Data della Pasqua per l'anno indicato (calendario gregoriano).

    Algoritmo Anonymous Gregorian (Meeus-Jones-Butcher), valido per
    qualsiasi anno gregoriano. Non dipende da librerie esterne.

    Esempi noti:
    - 2025 → 20 aprile
    - 2026 → 5 aprile
    - 2027 → 28 marzo
    """
    a = anno % 19
    b = anno // 100
    c = anno % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    L = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * L) // 451
    mese = (h + L - 7 * m + 114) // 31
    giorno = ((h + L - 7 * m + 114) % 31) + 1
    return date(anno, mese, giorno)


def pasquetta(anno: int) -> date:
    """Lunedì dell'Angelo = Pasqua + 1 giorno."""
    p = pasqua_gregoriana(anno)
    return date.fromordinal(p.toordinal() + 1)


# Festività nazionali italiane fisse (giorno, mese, nome).
# Riferimento: Legge 27 maggio 1949, n. 260.
_FESTIVITA_FISSE: tuple[tuple[int, int, str], ...] = (
    (1, 1, "Capodanno"),
    (6, 1, "Epifania"),
    (25, 4, "Festa della Liberazione"),
    (1, 5, "Festa del Lavoro"),
    (2, 6, "Festa della Repubblica"),
    (15, 8, "Ferragosto"),
    (1, 11, "Ognissanti"),
    (8, 12, "Immacolata Concezione"),
    (25, 12, "Natale"),
    (26, 12, "Santo Stefano"),
)


def festivita_italiane_fisse(anno: int) -> list[tuple[date, str]]:
    """Le 10 festività nazionali italiane fisse per l'anno indicato.

    Ordine cronologico crescente. Ritorna `(data, nome)` per ogni
    festività.
    """
    return [(date(anno, mese, giorno), nome) for giorno, mese, nome in _FESTIVITA_FISSE]


def festivita_italiane(anno: int) -> list[tuple[date, str]]:
    """Tutte le festività nazionali italiane (fisse + mobili) per l'anno.

    Include: 10 fisse + Pasqua + Pasquetta. Ordinato per data
    crescente.
    """
    out: list[tuple[date, str]] = list(festivita_italiane_fisse(anno))
    out.append((pasqua_gregoriana(anno), "Pasqua"))
    out.append((pasquetta(anno), "Lunedì dell'Angelo"))
    out.sort(key=lambda x: x[0])
    return out


# Tipo di giorno: stringa contratto verso il builder.
TipoGiorno = str  # Literal["feriale", "sabato", "domenica", "festivo"]


def tipo_giorno(data: date, festivita: frozenset[date]) -> TipoGiorno:
    """Classifica una data come feriale / sabato / domenica / festivo.

    Convenzione (decisione utente 2026-05-02): ``festivo`` ha
    precedenza su tutto — un festivo che cade di sabato è ``festivo``
    (es. 25 aprile 2026 = sabato + Liberazione → festivo). Se la data
    non è festiva: ``sabato`` o ``domenica`` per il weekend, altrimenti
    ``feriale``.

    ``festivita`` è il set delle festività nazionali + locali per
    l'anno della data (caller è responsabile di costruirlo via
    `festivita_italiane(anno)` + festività azienda).
    """
    if data in festivita:
        return "festivo"
    weekday = data.weekday()  # 0=Mon, 6=Sun
    if weekday == 5:
        return "sabato"
    if weekday == 6:
        return "domenica"
    return "feriale"


# Categorizzazione utente Sprint 7.7 MR 6 (decisione 2026-05-02):
# 3 categorie operative per l'etichetta UI delle varianti calendariali.
TipoGiornoCategoria = str  # Literal["lavorativo", "prefestivo", "festivo"]


def tipo_giorno_categoria(
    data: date,
    festivita: frozenset[date],
) -> TipoGiornoCategoria:
    """Classifica una data secondo le categorie utente Sprint 7.7 MR 6.

    Decisione utente 2026-05-02 (memoria
    ``feedback_etichetta_categoria_variante.md``): l'etichetta UI
    della variante deve essere semantica e sintetica, non il testo
    grezzo PdE (``"Circola giornalmente. Soppresso..."``). Categorie:

    - ``"festivo"``  — festività nazionale O locale azienda O domenica.
      Le domeniche sono sempre festivo (Trenord turni "F").
    - ``"prefestivo"`` — vigilia di un giorno festivo, ovvero il
      giorno *successivo* è festivo. Esempi: tutti i sabati (perché
      domenica = festivo), il venerdì 24/4/2026 (perché 25/4 =
      Liberazione).
    - ``"lavorativo"`` — tutto il resto: lun-ven non festivo e non
      vigilia di festivo.

    ``festivita`` è il set delle festività nazionali + locali rilevanti
    per gli anni coperti dalla data e dal giorno seguente. Il caller è
    responsabile di costruirlo includendo anche l'anno successivo se
    la data è il 31 dicembre (per riconoscere il prefestivo di
    Capodanno).
    """
    # 1) Festivo prevale: festività ufficiale O domenica.
    if data in festivita or data.weekday() == 6:
        return "festivo"

    # 2) Prefestivo: il giorno successivo è festivo (festività
    #    ufficiale O domenica). Le date oltre il set delle festività
    #    note ricadono comunque su domenica (controllo weekday).
    next_day = date.fromordinal(data.toordinal() + 1)
    if next_day in festivita or next_day.weekday() == 6:
        return "prefestivo"

    # 3) Default: lavorativo.
    return "lavorativo"
