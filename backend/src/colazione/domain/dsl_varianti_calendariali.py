"""Parser DSL etichette parlanti varianti calendariali Trenord — Sprint 8.3 S9.

Risponde a SEVERO post-Sprint S9 (entry 285): il parser MVP di
``enumera_date_giornata`` (entry 280) non riconosce le etichette parlanti
complesse del catalogo PdE Trenord 2026 e fa **fallback sovra-include**
sulla maggioranza delle varianti reali. Questo modulo aggiunge un parser
DSL dedicato che capisce le sintassi reali viste nei PDF turni Trenord.

Sintassi supportate (esempi reali da MR-1110-DESIGN.md):

- ``"LV 1:5"`` — Lavorativo dal 1° al 5° giorno settimana (lun-ven NON festivi).
- ``"LV 6"`` — Lavorativo del 6° giorno settimana (sabato NON festivo).
- ``"LV"`` — Lavorativi (default categoria, semantica
  ``tipo_giorno_categoria=='lavorativo'``).
- ``"F"`` — Festivi (domeniche + festività ufficiali nazionali/locali).
- ``"F escluso FpF"`` — Festivi esclusi i Festivi precedenti Festivo
  (es. Pasqua-domenica precede Pasquetta, o 25/4 sabato precede 26/4
  domenica festiva).
- ``"F escluso FpF ed escl. 22/3, 12/4, 1/5 e 2/6"`` — Festivi escluso
  FpF + escluse 4 date specifiche.
- ``"F esclusi 21/3, 11/4"`` — Festivi escluse date elencate (no FpF).
- ``"LV 1:5 escl. 22/3"`` — Lavorativi 1:5 escluse date.
- ``"LV esclusi 21/3, 28/3, 11/4"`` — Lavorativi esclusi date.
- ``"Si eff. 22/3, 12/4"`` — Si effettua SOLO le date elencate.
- ``"Si eff. 1/5 e 2/6"`` — idem (separatore "e" oltre a ",").
- ``"Circola Sabato Festivo"`` — Sabati che cadono su festività.
- ``"Solo 4/5/26"`` — Solo data specifica (anno 2-cifre).
- ``"GG"`` o ``""`` — Giornaliero (tutte le candidate).

Pattern non riconosciuti → ``None`` (fallback chiamante: sovra-include).
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Protocol

from colazione.domain.calendario import tipo_giorno_categoria

logger = logging.getLogger(__name__)


class FiltroVariante(Protocol):
    """Predicato di filtro per una data candidata.

    Ritorna ``True`` se la data appartiene alla variante.
    """

    def __call__(self, d: date, festivita: frozenset[date]) -> bool: ...


_DATE_TOKEN = re.compile(r"(\d{1,2})\s*/\s*(\d{1,2})(?:\s*/\s*(\d{2,4}))?")


def _parse_date_list(text: str, anno_default: int) -> list[date]:
    """Estrae lista date da una stringa (separatori virgola, 'e', spazi).

    Esempi:
    - ``"22/3, 12/4"`` → ``[22 mar, 12 apr]`` anno default
    - ``"1/5 e 2/6"`` → ``[1 mag, 2 giu]``
    - ``"22/3, 12/4, 1/5 e 2/6"`` → 4 date

    Args:
        text: testo che contiene le date.
        anno_default: anno da usare se la data non lo specifica
            (es. ``"22/3"`` senza anno).

    Returns:
        Lista di ``date``. Date malformate ignorate.
    """
    out: list[date] = []
    for match in _DATE_TOKEN.finditer(text):
        giorno = int(match.group(1))
        mese = int(match.group(2))
        anno_str = match.group(3)
        if anno_str:
            anno_int = int(anno_str)
            anno = 2000 + anno_int if anno_int < 100 else anno_int
        else:
            anno = anno_default
        try:
            out.append(date(anno, mese, giorno))
        except ValueError:
            logger.debug("Data malformata ignorata: %s/%s/%s", giorno, mese, anno)
    return out


def parse_variante_dsl(
    variante: str | None,
    *,
    anno_default: int,
) -> FiltroVariante | None:
    """Parsea l'etichetta parlante e ritorna un predicato di filtro.

    Args:
        variante: testo etichetta (case-insensitive con whitespace
            normalizzato). ``None`` o stringa vuota → ``None`` (=
            chiamante usa default "tutte le candidate").
        anno_default: anno da usare per parsing date senza anno
            esplicito. Tipicamente l'anno del programma corrente.

    Returns:
        Predicato che accetta ``(d: date, festivita: frozenset)`` e
        ritorna ``True`` se ``d`` appartiene alla variante. ``None``
        se la sintassi non è riconosciuta (chiamante decide fallback,
        di solito sovra-include conservativo).
    """
    if variante is None:
        return None
    txt = variante.strip()
    if not txt:
        return None
    txt_upper = txt.upper()

    # =================================================================
    # GG / Giornaliero
    # =================================================================
    if txt_upper in ("GG", "GIORNALIERO"):
        return lambda d, f: True

    # =================================================================
    # Solo D/M/YY
    # =================================================================
    m_solo = re.match(
        r"^SOLO\s+(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{2,4})\b",
        txt_upper,
    )
    if m_solo:
        giorno = int(m_solo.group(1))
        mese = int(m_solo.group(2))
        anno_int = int(m_solo.group(3))
        anno = 2000 + anno_int if anno_int < 100 else anno_int
        try:
            target = date(anno, mese, giorno)
            return lambda d, f, _t=target: d == _t
        except ValueError:
            return None

    # =================================================================
    # Si eff. <date list>
    # =================================================================
    m_sieff = re.match(r"^SI\s+EFF\.?\s+(.+)$", txt_upper)
    if m_sieff:
        date_list = frozenset(_parse_date_list(m_sieff.group(1), anno_default))
        if date_list:
            return lambda d, f, _dl=date_list: d in _dl
        return None

    # =================================================================
    # Circola Sabato Festivo
    # =================================================================
    if "CIRCOLA SABATO FESTIVO" in txt_upper:
        return lambda d, f: d.weekday() == 5 and d in f

    # =================================================================
    # LV [1:5|6|<n>:<m>] [esclusi/escl. <date list>]
    # =================================================================
    m_lv = re.match(r"^LV\b\s*(\d+\s*:\s*\d+|\d+)?", txt_upper)
    if m_lv:
        range_str = m_lv.group(1)
        date_escluse = _extract_date_escluse(txt, anno_default)

        if range_str is None:
            # "LV" generico = lavorativo (lun-ven NON festivo)
            return _lv_filter(weekday_min=0, weekday_max=4, date_escluse=date_escluse)
        elif ":" in range_str:
            wmin, wmax = (int(x.strip()) for x in range_str.split(":"))
            return _lv_filter(
                weekday_min=wmin - 1, weekday_max=wmax - 1, date_escluse=date_escluse
            )
        else:
            wn = int(range_str) - 1  # "LV 6" = sabato (weekday 5)
            return _lv_filter(
                weekday_min=wn, weekday_max=wn, date_escluse=date_escluse
            )

    # =================================================================
    # F [escluso FpF] [esclusi <date list>]
    # =================================================================
    if re.match(r"^F\b", txt_upper) or "FESTIVO" in txt_upper:
        escluso_fpf = "ESCLUSO FPF" in txt_upper
        date_escluse = _extract_date_escluse(txt, anno_default)

        def _f_filter(
            d: date,
            festivita: frozenset[date],
            _ef: bool = escluso_fpf,
            _de: frozenset[date] = date_escluse,
        ) -> bool:
            if d in _de:
                return False
            if tipo_giorno_categoria(d, festivita) != "festivo":
                return False
            if _ef:
                # FpF inline: d è festivo (verificato sopra) E d+1 è
                # anche festivo (festività ufficiale O domenica).
                # Calcolato qui per non dipendere da festivi_precedenti_festivo
                # che richiede festivita includere domeniche (non garantito
                # dal chiamante).
                next_day = d + timedelta(days=1)
                next_is_festivo = (
                    next_day in festivita or next_day.weekday() == 6
                )
                if next_is_festivo:
                    return False  # FpF escluso
            return True

        return _f_filter

    # Sintassi non riconosciuta
    return None


def _lv_filter(
    *,
    weekday_min: int,
    weekday_max: int,
    date_escluse: frozenset[date],
) -> FiltroVariante:
    """Costruisce un filtro lavorativo con range weekday + esclusioni."""

    def _filter(
        d: date,
        festivita: frozenset[date],
        _wmin: int = weekday_min,
        _wmax: int = weekday_max,
        _de: frozenset[date] = date_escluse,
    ) -> bool:
        if d in _de:
            return False
        wd = d.weekday()
        if wd < _wmin or wd > _wmax:
            return False
        # Lavorativo = NON festivo (NORMATIVA Trenord interpreta "LV"
        # come "non festa nazionale", incluso non-domenica per LV 1:5
        # già implicito dal range weekday).
        if d in festivita:
            return False
        return True

    return _filter


def _extract_date_escluse(testo: str, anno_default: int) -> frozenset[date]:
    """Estrae la lista date da clausole 'escl. ...' / 'esclusi ...' /
    'ed escl. ...' nel testo etichetta.

    Esempi pattern catturati:
    - ``"LV 1:5 escl. 22/3"`` → {22/3}
    - ``"LV esclusi 21/3, 28/3, 11/4"`` → 3 date
    - ``"F escluso FpF ed escl. 22/3, 12/4, 1/5 e 2/6"`` → 4 date
    - ``"F esclusi 22/3 e 12/4"`` → 2 date

    NB ``"escluso FpF"`` (senza date) viene gestito separatamente dal
    chiamante (``escluso_fpf`` flag), questo helper non lo intercetta.
    """
    # Cerca clausole esclusione (case-insensitive).
    # Pattern: "escl./esclusi/esclusi" seguiti da date list. Evita
    # match su "escluso FpF" (= no date subito dopo).
    matches = re.findall(
        r"\b(?:escl\.?|esclusi)\s+([\d\s/,e]+?)(?=\s+(?:e?\s*ed?\s+escl\.?|$|\.))",
        testo,
        flags=re.IGNORECASE,
    )
    # Fallback: pattern più semplice fino a fine stringa
    if not matches:
        m = re.search(
            r"\b(?:escl\.?|esclusi)\s+([\d\s/,e]+)$",
            testo,
            flags=re.IGNORECASE,
        )
        if m:
            matches = [m.group(1)]
    out: set[date] = set()
    for grp in matches:
        for d in _parse_date_list(grp, anno_default):
            out.add(d)
    return frozenset(out)


__all__ = ["FiltroVariante", "parse_variante_dsl"]
