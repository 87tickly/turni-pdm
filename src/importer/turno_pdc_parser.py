"""
Parser turno PdC — schema v2.

Input:  PDF Trenord "Turni PdC rete RFI" (formato M 704 Rev.4)
Output: lista di ParsedPdcTurn con giornate, blocchi Gantt e note periodicita'.

Regole documentate in `.claude/skills/turno-pdc-reader.md`.

Geometria del PDF (verificata su pagine 2+ del turno AROR_C):
- Header: parole orizzontali y~11 (IMPIANTO, TURNO, PROFILO, DAL, AL)
- Numero giornata: orizzontale, size=12, x_0~10-17 (ancora di banda)
- Periodicita': orizzontale, size=10, sopra il numero giornata
- Orari prestazione: orizzontale, size=8.5, testo `[HH:MM]`
- Asse orario: size=5.5, numeri 3..24..3
- Stats: size=6.5, colonna destra x>720 (Lav/Cct/Km/Not/Rip)
- Etichette blocchi Gantt: **testo ruotato** (upright=False).
  Lettura: concateno i caratteri della stessa colonna X ordinati per Y
  crescente, poi inverto la stringa risultante.
- Stazioni: orizzontali ai bordi del Gantt (size=7, testo tipo ARON, DOMO)
- Pagina finale turno: "Note sulla periodicita' dei treni" — testo libero
  con date in formato dd/mm/yyyy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import pdfplumber


# ══════════════════════════════════════════════════════════════════
# DATACLASS
# ══════════════════════════════════════════════════════════════════

@dataclass
class ParsedPdcBlock:
    seq: int
    block_type: str  # train|coach_transfer|cv_partenza|cv_arrivo|meal|scomp|available
    train_id: str = ""
    vettura_id: str = ""
    from_station: str = ""
    to_station: str = ""
    start_time: str = ""
    end_time: str = ""
    accessori_maggiorati: bool = False


@dataclass
class ParsedPdcDay:
    day_number: int
    periodicita: str                # LMXGVSD, D, SD, LMXGVS, LMXGV, S
    start_time: str = ""
    end_time: str = ""
    lavoro_min: int = 0
    condotta_min: int = 0
    km: int = 0
    notturno: bool = False
    riposo_min: int = 0
    is_disponibile: bool = False
    blocks: list[ParsedPdcBlock] = field(default_factory=list)


@dataclass
class ParsedPdcNote:
    train_id: str
    periodicita_text: str = ""
    non_circola_dates: list[str] = field(default_factory=list)  # YYYY-MM-DD
    circola_extra_dates: list[str] = field(default_factory=list)


@dataclass
class ParsedPdcTurn:
    codice: str                     # AROR_C
    planning: str = ""
    impianto: str = ""
    profilo: str = "Condotta"
    valid_from: str = ""            # YYYY-MM-DD
    valid_to: str = ""
    source_pages: list[int] = field(default_factory=list)
    days: list[ParsedPdcDay] = field(default_factory=list)
    notes: list[ParsedPdcNote] = field(default_factory=list)


# ══════════════════════════════════════════════════════════════════
# COSTANTI / REGEX
# ══════════════════════════════════════════════════════════════════

# Codici periodicita' accettati (ordine: piu' specifico prima)
PERIODICITA_CODES = (
    "LMXGVSD", "LMXGVS", "LMXGV", "LMXG", "LMX",
    "SD", "GV", "VSD",
    "S", "D", "V", "G",
)

# Header pagina (apertura turno)
HEADER_RE = re.compile(
    r"IMPIANTO:\s*(?P<impianto>\S+).*?"
    r"TURNO:\s*\[(?P<codice>[A-Z0-9_]+)\]\s*\[(?P<planning>\d+)\].*?"
    r"PROFILO:\s*(?P<profilo>\S+).*?"
    r"DAL:\s*(?P<dal>\d{2}/\d{2}/\d{4})\s+"
    r"AL:\s*(?P<al>\d{2}/\d{2}/\d{4})",
    re.DOTALL,
)

# Numero giornata + orari prestazione: "1 [18:20] [00:25]"
DAY_RE = re.compile(r"^\s*(\d{1,2})\s*\[(\d{1,2}:\d{2})\]\s*\[(\d{1,2}:\d{2})\]")

# Stats riga destra: "06:05 03:22 184 si 15:45" (accetta sì / si / no)
STATS_RE = re.compile(
    r"(\d{1,2}:\d{2})\s+(\d{1,2}:\d{2})\s+(\d+)\s+(s[iì]|SI|si|no|NO)\s+(\d{1,2}:\d{2})",
    re.IGNORECASE,
)

# Page footer "Pagina N di M"
FOOTER_PAGE_RE = re.compile(r"Pagina\s+(\d+)\s+di\s+(\d+)")

# Italian date dd/mm/yyyy
DATE_IT_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")

# Note periodicita' treni (pagina finale turno)
NOTE_TITLE_RE = re.compile(r"Note\s+sulla\s+periodicit[aà]'?\s+dei\s+treni", re.IGNORECASE)
NOTE_TRAIN_LINE_RE = re.compile(r"Treno\s+(\d{3,6})\s*[-–]\s*(.+)", re.IGNORECASE)


# ══════════════════════════════════════════════════════════════════
# UTILITY
# ══════════════════════════════════════════════════════════════════

def _hhmm_to_min(s: str) -> int:
    try:
        h, m = s.strip().split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return 0


def _it_to_iso_date(d: str) -> str:
    """'23/02/2026' -> '2026-02-23'. Lascia invariato se non parsabile."""
    try:
        day, month, year = d.split("/")
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    except Exception:
        return d


def _reverse(s: str) -> str:
    return s[::-1]


# ══════════════════════════════════════════════════════════════════
# ESTRAZIONE ETICHETTE VERTICALI (blocchi Gantt)
# ══════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════
# ASSE ORARIO + CONVERSIONE x -> HH:MM
# ══════════════════════════════════════════════════════════════════

def _find_axis_y(words: list[dict], band_top: float, band_bot: float) -> Optional[float]:
    """Trova la riga Y dell'asse orario: quella con piu' numeri 1-24 size 5-6.

    L'asse ha 25 tick (3,4,...,24,1,2,3) tutti allineati sulla stessa Y.
    """
    from collections import Counter
    smalls = [w for w in words
              if w.get("upright", True)
              and 5 <= w.get("size", 0) <= 6
              and band_top <= w["top"] <= band_bot
              and re.fullmatch(r"\d{1,2}", w["text"].strip())]
    if not smalls:
        return None
    y_quant = Counter(round(w["top"] / 2) * 2 for w in smalls)
    axis_y, n = max(y_quant.items(), key=lambda kv: kv[1])
    if n < 15:
        return None
    return float(axis_y)


def _build_axis_ticks(words: list[dict], axis_y: float) -> list[tuple]:
    """Ritorna lista di tick orari: (x_start, x_center, x_end, hour) ordinata per x."""
    ticks = []
    for w in words:
        if not w.get("upright", True):
            continue
        if not (5 <= w.get("size", 0) <= 6):
            continue
        if abs(w["top"] - axis_y) > 2:
            continue
        m = re.fullmatch(r"(\d{1,2})", w["text"].strip())
        if not m:
            continue
        ticks.append((w["x0"], (w["x0"] + w["x1"]) / 2, w["x1"], int(m.group(1))))
    ticks.sort(key=lambda t: t[0])
    return ticks


def _x_to_hour(x: float, ticks: list[tuple]) -> Optional[int]:
    """Dato un X, ritorna l'ora del tick immediatamente a sinistra (<=x).

    (Fallback per casi in cui non si conosce il valore del minuto —
    usato raramente; per risultati precisi preferire _x_to_hour_for_minute.)
    """
    best = None
    for x_start, x_center, x_end, hour in ticks:
        if x_start - 2 <= x:
            best = hour
        else:
            break
    return best


def _x_to_hour_for_minute(x: float, minute: int,
                          ticks: list[tuple]) -> Optional[int]:
    """Mappa (x, minuto) -> ora usando la posizione attesa del minuto.

    Per ogni tick H con x_start=X_H, la posizione attesa di H:min e':
       x_atteso(H, min) = X_H + (min/60) * tick_width

    L'ora restituita e' quella per cui |x - x_atteso| e' minimo.
    Questo evita errori sui minuti grandi (es. :40, :50) che cadono
    geometricamente oltre il tick dell'ora successiva.
    """
    if not ticks:
        return None
    if len(ticks) < 2:
        return ticks[0][3]
    # Stima tick_width dal passo medio
    tick_width = (ticks[-1][0] - ticks[0][0]) / (len(ticks) - 1)
    if tick_width <= 0:
        return ticks[0][3]

    best_hour = None
    best_dist = float("inf")
    for x_start, _xc, _xe, hour in ticks:
        x_expected = x_start + (minute / 60.0) * tick_width
        dist = abs(x - x_expected)
        if dist < best_dist:
            best_dist = dist
            best_hour = hour
    return best_hour


def _extract_upper_minutes(words: list[dict], band_top: float,
                           axis_y: float) -> list[dict]:
    """Estrae i minuti SOPRA l'asse orario.

    Ritorna lista di {x, y, minute} ordinata per X crescente.
    I minuti sotto l'asse (secondari) sono ignorati.
    """
    mins = []
    for w in words:
        if not w.get("upright", True):
            continue
        if not (4 <= w.get("size", 0) <= 6.5):
            continue
        if not (band_top <= w["top"] < axis_y - 2):
            continue
        text = w["text"].strip()
        m = re.fullmatch(r"(\d{1,2})", text)
        if not m:
            continue
        mval = int(m.group(1))
        if mval > 59:
            continue
        mins.append({
            "x": (w["x0"] + w["x1"]) / 2,
            "x0": w["x0"],
            "y": w["top"],
            "minute": mval,
        })
    mins.sort(key=lambda d: d["x"])
    return mins


def _hhmm_fix_rollover(h_start: int, m_start: int,
                       h_end: int, m_end: int) -> tuple[str, str]:
    """Ritorna (start_time, end_time) corretti.

    Gestisce il caso in cui l'algoritmo geometrico assegna allo start
    un'ora troppo alta perche' il minuto "grande" (es. :40) finisce
    graficamente sotto l'ora successiva. Se start > end ma la
    differenza e' piccola (< 2 ore su orologio 24h), decrementiamo
    h_start di 1. Per differenze grandi (es. blocco notturno) non
    tocchiamo nulla.
    """
    start_total = h_start * 60 + m_start
    end_total = h_end * 60 + m_end
    if start_total > end_total:
        diff_backward = start_total - end_total  # quanti min "mancano"
        if diff_backward < 2 * 60:
            h_start = (h_start - 1) % 24
    return (f"{h_start:02d}:{m_start:02d}", f"{h_end:02d}:{m_end:02d}")


def _assign_minutes_to_blocks(blocks_with_x: list[tuple], upper_mins: list[dict],
                               ticks: list[tuple]) -> None:
    """Assegna start_time/end_time ai blocchi in ordine sequenziale.

    blocks_with_x: lista di (ParsedPdcBlock, x_label) ordinata per x_label.
    upper_mins: lista di minuti sopra l'asse ordinata per x.
    ticks: tick map dell'asse orario.

    Regole di consumo dei minuti (osservazione del layout Trenord):
    - `coach_transfer`, `meal`: 2 minuti (start, end)
    - `train`: dipende dai vicini
      * se precede `cv_arrivo`     -> 1 minuto (solo start, end coincide col CVa)
      * se segue  `cv_partenza`    -> 1 minuto (solo end, start coincide col CVp)
      * se tra due CV              -> 0 minuti (orari ereditati)
      * altrimenti                  -> 2 minuti
    - `cv_partenza`, `cv_arrivo`: 0 minuti (puntuali, ereditano)
    - `scomp`, `available`, `unknown`: ignorati
    """
    if not ticks or not upper_mins:
        return

    def _fmt(h: int, m: int) -> str:
        return f"{h:02d}:{m:02d}"

    def _convert(m_entry: dict) -> Optional[str]:
        h = _x_to_hour_for_minute(m_entry["x"], m_entry["minute"], ticks)
        if h is None:
            return None
        return _fmt(h, m_entry["minute"])

    idx = 0
    n_blocks = len(blocks_with_x)
    for i, (block, _lx) in enumerate(blocks_with_x):
        btype = block.block_type
        if btype not in ("train", "coach_transfer", "meal"):
            continue

        prev_type = blocks_with_x[i - 1][0].block_type if i > 0 else None
        next_type = blocks_with_x[i + 1][0].block_type if i + 1 < n_blocks else None

        # Decide consumo minuti
        has_start = True
        has_end = True
        if btype == "train":
            if prev_type == "cv_partenza":
                has_start = False
            if next_type == "cv_arrivo":
                has_end = False

        if not has_start and not has_end:
            continue

        # Popola start
        m_start_entry = m_end_entry = None
        if has_start and idx < len(upper_mins):
            m_start_entry = upper_mins[idx]
            idx += 1
        if has_end and idx < len(upper_mins):
            m_end_entry = upper_mins[idx]
            idx += 1

        s_txt = _convert(m_start_entry) if m_start_entry else ""
        e_txt = _convert(m_end_entry) if m_end_entry else ""

        # Correzione rollover solo se entrambi presenti
        if s_txt and e_txt:
            sh, sm = int(s_txt[:2]), int(s_txt[3:])
            eh, em = int(e_txt[:2]), int(e_txt[3:])
            s_txt, e_txt = _hhmm_fix_rollover(sh, sm, eh, em)

        if s_txt:
            block.start_time = s_txt
        if e_txt:
            block.end_time = e_txt


def _cluster_vertical_labels(words: list[dict], x_tol: float = 2.0) -> list[dict]:
    """Raggruppa le parole ruotate (upright=False) per colonna X.

    Una colonna = lettere verticali alla stessa X (entro x_tol).
    Per ogni colonna, concatena i caratteri ordinati per Y crescente
    (dall'alto verso il basso nella pagina) e **inverte** la stringa,
    perche' il testo ruotato e' scritto bottom-to-top nel PDF.

    Ritorna una lista di dict: {label, x0, x1, y_top, y_bot}
    """
    vwords = [w for w in words if not w.get("upright", True)]
    if not vwords:
        return []

    # Ordina per x poi y
    vwords.sort(key=lambda w: (w["x0"], w["top"]))

    columns: list[list[dict]] = []
    for w in vwords:
        # Cerca una colonna esistente con x simile
        placed = False
        for col in columns:
            if abs(col[-1]["x0"] - w["x0"]) <= x_tol:
                col.append(w)
                placed = True
                break
        if not placed:
            columns.append([w])

    labels = []
    for col in columns:
        col.sort(key=lambda w: w["top"])
        raw = "".join(w["text"] for w in col)
        label = _reverse(raw)
        labels.append({
            "label": label,
            "raw": raw,
            "x0": min(w["x0"] for w in col),
            "x1": max(w["x1"] for w in col),
            "y_top": min(w["top"] for w in col),
            "y_bot": max(w["bottom"] for w in col),
        })
    # Ordine di lettura: x crescente
    labels.sort(key=lambda l: l["x0"])
    return labels


def _classify_vertical_label(label: str) -> tuple[str, dict]:
    """Classifica un'etichetta verticale in tipo blocco + metadati.

    Ritorna (block_type, extras) dove extras puo' contenere train_id,
    vettura_id, stazione, accessori_maggiorati.

    block_type ∈ {'train', 'coach_transfer', 'cv_partenza', 'cv_arrivo',
                  'meal', 'scomp', 'available', 'unknown'}
    """
    s = label.strip()
    if not s:
        return "unknown", {}

    # ● -> accessori maggiorati
    accessori = False
    if "●" in s or "\u25cf" in s:
        accessori = True
        s = s.replace("●", "").replace("\u25cf", "").strip()

    # Vettura: inizia con '('
    if s.startswith("("):
        # "(2434 DOMO" -> vettura=2434, stazione=DOMO (se presente)
        rest = s[1:].strip()
        m = re.match(r"^(\d{3,5})\s*([A-Z]{2,6})?", rest)
        if m:
            return "coach_transfer", {
                "vettura_id": m.group(1),
                "to_station": (m.group(2) or "").strip(),
                "accessori_maggiorati": accessori,
            }

    # CVp <num> <staz>
    m = re.match(r"^CVp\s*(\d{3,5})\s*([A-Z]{2,6})?", s, re.IGNORECASE)
    if m:
        return "cv_partenza", {
            "train_id": m.group(1),
            "to_station": (m.group(2) or "").strip(),
        }

    # CVa <num> <staz>
    m = re.match(r"^CVa\s*(\d{3,5})\s*([A-Z]{2,6})?", s, re.IGNORECASE)
    if m:
        return "cv_arrivo", {
            "train_id": m.group(1),
            "to_station": (m.group(2) or "").strip(),
        }

    # REFEZ <staz>
    m = re.match(r"^REFEZ\s*([A-Z]{2,6})?", s, re.IGNORECASE)
    if m:
        return "meal", {"to_station": (m.group(1) or "").strip()}

    # S.COMP <staz>
    if s.upper().startswith("S.COMP") or s.upper().startswith("SCOMP"):
        m = re.match(r"^S\.?COMP\s*([A-Z]{2,6})?", s, re.IGNORECASE)
        st = (m.group(1) if m else "").strip()
        return "scomp", {"to_station": st}

    # Treno: inizia con cifre (4-5)
    m = re.match(r"^(\d{4,5})\s*([A-Za-z]{2,6})?", s)
    if m:
        return "train", {
            "train_id": m.group(1),
            "to_station": (m.group(2) or "").strip(),
            "accessori_maggiorati": accessori,
        }

    return "unknown", {"raw": s}


# ══════════════════════════════════════════════════════════════════
# CLUSTERIZZAZIONE BANDE Y PER GIORNATA
# ══════════════════════════════════════════════════════════════════

def _find_day_markers(words: list[dict]) -> list[dict]:
    """Identifica le parole che sono numeri di giornata (size>=10, x<20).

    Nel PDF, il numero giornata e' in grassetto size=12, posizionato a
    sinistra a x~10-17. E' il marker principale della banda Y della
    giornata.
    """
    markers = []
    for w in words:
        if not w.get("upright", True):
            continue
        if w.get("size", 0) < 10:
            continue
        if w["x0"] > 20:
            continue
        if not re.fullmatch(r"\d{1,2}", w["text"].strip()):
            continue
        markers.append(w)
    markers.sort(key=lambda w: w["top"])
    return markers


def _extract_day_from_band(words: list[dict], band_top: float,
                           band_bot: float, page_width: float) -> Optional[ParsedPdcDay]:
    """Estrae una ParsedPdcDay dalla banda Y [band_top, band_bot]."""
    in_band = [w for w in words if band_top - 1 <= w["top"] <= band_bot + 1]
    if not in_band:
        return None

    # 1. Numero giornata (size>=10, x<20)
    day_num_word = next(
        (w for w in in_band
         if w.get("upright", True) and w.get("size", 0) >= 10
         and w["x0"] < 20 and re.fullmatch(r"\d{1,2}", w["text"])),
        None,
    )
    if not day_num_word:
        return None
    day_number = int(day_num_word["text"])
    y_day = day_num_word["top"]

    # 2. Periodicita': parola orizzontale size>=10 SOPRA il numero giornata
    #    (y < y_day - qualche punto)
    periodicita = ""
    candidates = [w for w in in_band
                  if w.get("upright", True) and w.get("size", 0) >= 10
                  and w["x0"] < 80 and w["top"] < y_day - 3]
    # Prendi quello piu' vicino al numero (max y < y_day)
    candidates.sort(key=lambda w: -w["top"])
    for w in candidates:
        txt = w["text"].strip().upper()
        if txt in PERIODICITA_CODES:
            periodicita = txt
            break
    # Fallback: se non trovata, prova nella stessa riga
    if not periodicita:
        for w in in_band:
            if w.get("upright", True) and w["text"].strip().upper() in PERIODICITA_CODES:
                periodicita = w["text"].strip().upper()
                break
    if not periodicita:
        periodicita = "LMXGVSD"  # default

    # 3. Orari prestazione: due parole orizzontali size~8.5 tipo "[HH:MM]"
    #    vicino al numero giornata
    time_words = [w for w in in_band
                  if w.get("upright", True)
                  and re.fullmatch(r"\[\d{1,2}:\d{2}\]", w["text"])
                  and abs(w["top"] - y_day) < 6]
    time_words.sort(key=lambda w: w["x0"])
    start_time = end_time = ""
    if len(time_words) >= 2:
        start_time = time_words[0]["text"].strip("[]")
        end_time = time_words[1]["text"].strip("[]")

    # 4. Stats destra (colonna x>720): Lav, Cct, Km, Not, Rip
    stats_zone = [w for w in in_band if w["x0"] > 700 and w.get("upright", True)]
    stats_zone.sort(key=lambda w: (w["top"], w["x0"]))
    # Cerca la riga dei valori (sotto "Lav Cct Km Not Rip")
    stats_vals = []
    for w in stats_zone:
        t = w["text"].strip()
        if t in ("Lav", "Cct", "Km", "Not", "Rip"):
            continue
        stats_vals.append(t)
    lavoro_min = condotta_min = km = riposo_min = 0
    notturno = False
    if len(stats_vals) >= 5:
        try:
            lavoro_min = _hhmm_to_min(stats_vals[0])
            condotta_min = _hhmm_to_min(stats_vals[1])
            km = int(stats_vals[2])
            notturno = stats_vals[3].lower().startswith("s")
            riposo_min = _hhmm_to_min(stats_vals[4])
        except (ValueError, IndexError):
            pass

    # 5. Is disponibile? Cerca parola "Disponibile" (size grande) nella banda
    is_disponibile = any(
        w.get("upright", True)
        and w["text"].strip().lower() == "disponibile"
        and w.get("size", 0) >= 9
        for w in in_band
    )

    # 6. Blocchi: etichette verticali nella banda
    blocks: list[ParsedPdcBlock] = []
    if not is_disponibile:
        labels = _cluster_vertical_labels(in_band)
        blocks_with_x: list[tuple] = []
        seq = 0
        for lab in labels:
            btype, extras = _classify_vertical_label(lab["label"])
            if btype == "unknown":
                continue
            blk = ParsedPdcBlock(
                seq=seq,
                block_type=btype,
                train_id=extras.get("train_id", ""),
                vettura_id=extras.get("vettura_id", ""),
                from_station="",
                to_station=extras.get("to_station", ""),
                accessori_maggiorati=extras.get("accessori_maggiorati", False),
            )
            blocks.append(blk)
            blocks_with_x.append((blk, (lab["x0"] + lab["x1"]) / 2))
            seq += 1

        # 6b. Popola start_time/end_time dei blocchi via asse orario
        axis_y = _find_axis_y(in_band, band_top, band_bot)
        if axis_y is not None:
            ticks = _build_axis_ticks(in_band, axis_y)
            upper_mins = _extract_upper_minutes(in_band, band_top, axis_y)
            blocks_with_x.sort(key=lambda p: p[1])
            _assign_minutes_to_blocks(blocks_with_x, upper_mins, ticks)
    else:
        # Giornata disponibile: unico blocco 'available'
        blocks.append(ParsedPdcBlock(seq=0, block_type="available"))

    return ParsedPdcDay(
        day_number=day_number,
        periodicita=periodicita,
        start_time=start_time,
        end_time=end_time,
        lavoro_min=lavoro_min,
        condotta_min=condotta_min,
        km=km,
        notturno=notturno,
        riposo_min=riposo_min,
        is_disponibile=is_disponibile,
        blocks=blocks,
    )


# ══════════════════════════════════════════════════════════════════
# NOTE PERIODICITA' TRENI (pagina finale turno)
# ══════════════════════════════════════════════════════════════════

def _parse_train_notes(text: str) -> list[ParsedPdcNote]:
    """Parse la pagina di note periodicita' treni del turno.

    Esempio input:
      Treno 10226 - Circola il sabato e la domenica. Non circola
      27/12/2025, 03/01/2026. Circola 25/12/2025, 26/12/2025.

    Output: ParsedPdcNote per ogni treno citato.
    """
    notes: dict[str, ParsedPdcNote] = {}

    # Unisci multiline (tolgo newline tra virgole)
    text_flat = re.sub(r"\n(?=\d{1,2}/\d{1,2}/\d{4})", " ", text)
    text_flat = re.sub(r"\n(?=,)", " ", text_flat)

    for m in re.finditer(
        r"Treno\s+(\d{3,6})\s*[-–]\s*([^\n]*(?:\n(?!Treno\s+\d)[^\n]*)*)",
        text_flat,
        re.IGNORECASE,
    ):
        tid = m.group(1)
        body = m.group(2).strip()

        # Testo periodicita' (prima frase fino al primo '.')
        period_txt = body.split(".")[0].strip() + "."

        # Date "Non circola X, Y, Z"
        non_circ_block = re.search(r"Non\s+circola\s+([^.]+)", body, re.IGNORECASE)
        non_circ_dates = []
        if non_circ_block:
            for d in DATE_IT_RE.finditer(non_circ_block.group(1)):
                non_circ_dates.append(
                    f"{int(d.group(3)):04d}-{int(d.group(2)):02d}-{int(d.group(1)):02d}"
                )

        # Date "Circola X, Y, Z" (ma non dentro "Non circola")
        circ_block_text = re.sub(r"Non\s+circola[^.]+\.?", " ", body, flags=re.IGNORECASE)
        circ_block = re.search(
            r"(?:^|\.)?\s*Circola\s+(\d{1,2}/\d{1,2}/\d{4}[^.]*)",
            circ_block_text,
            re.IGNORECASE,
        )
        circ_extra_dates = []
        if circ_block:
            for d in DATE_IT_RE.finditer(circ_block.group(1)):
                circ_extra_dates.append(
                    f"{int(d.group(3)):04d}-{int(d.group(2)):02d}-{int(d.group(1)):02d}"
                )

        if tid in notes:
            # Mergiamo (lo stesso treno puo' apparire piu' volte)
            notes[tid].non_circola_dates = sorted(
                set(notes[tid].non_circola_dates) | set(non_circ_dates)
            )
            notes[tid].circola_extra_dates = sorted(
                set(notes[tid].circola_extra_dates) | set(circ_extra_dates)
            )
        else:
            notes[tid] = ParsedPdcNote(
                train_id=tid,
                periodicita_text=period_txt,
                non_circola_dates=sorted(set(non_circ_dates)),
                circola_extra_dates=sorted(set(circ_extra_dates)),
            )

    return list(notes.values())


# ══════════════════════════════════════════════════════════════════
# DRIVER PRINCIPALE
# ══════════════════════════════════════════════════════════════════

def parse_pdc_pdf(pdf_path: str) -> list[ParsedPdcTurn]:
    """Parse un PDF turno PdC e ritorna la lista di turni parsati."""
    turns: list[ParsedPdcTurn] = []
    current: Optional[ParsedPdcTurn] = None

    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            page_num = page_idx + 1
            text = page.extract_text() or ""

            # Identifica se e' pagina indice (prima pagina, senza IMPIANTO)
            if page_num == 1 or "IMPIANTO:" not in text:
                # Potenzialmente pagina di note/indice
                if current and NOTE_TITLE_RE.search(text):
                    current.notes.extend(_parse_train_notes(text))
                continue

            # Header turno
            hm = HEADER_RE.search(text)
            if hm:
                impianto = hm.group("impianto")
                codice = hm.group("codice")
                planning = hm.group("planning")

                # Stesso turno se impianto+codice coincidono
                if (current is None
                        or current.impianto != impianto
                        or current.codice != codice):
                    if current is not None:
                        turns.append(current)
                    current = ParsedPdcTurn(
                        codice=codice,
                        planning=planning,
                        impianto=impianto,
                        profilo=hm.group("profilo"),
                        valid_from=_it_to_iso_date(hm.group("dal")),
                        valid_to=_it_to_iso_date(hm.group("al")),
                        source_pages=[page_num],
                    )
                else:
                    current.source_pages.append(page_num)
            else:
                # Pagina non-turno e non-note: skip
                continue

            # Se la pagina contiene "Note sulla periodicita'" oltre all'header,
            # parse le note (pagina finale turno)
            if NOTE_TITLE_RE.search(text):
                current.notes.extend(_parse_train_notes(text))
                continue

            # Estrai le giornate dalla pagina via geometria
            try:
                words = page.extract_words(
                    x_tolerance=2, y_tolerance=2,
                    keep_blank_chars=False, use_text_flow=False,
                    extra_attrs=["fontname", "size", "upright"],
                )
            except Exception:
                continue

            markers = _find_day_markers(words)
            if not markers:
                continue

            for i, mk in enumerate(markers):
                # Banda centrata sul marker numero giornata:
                # ~60pt sopra (periodicita' + blocchi + testo sopra asse orario)
                # ~22pt sotto (asse orario + minuti sotto asse)
                # Evitiamo sovrapposizione con giornata successiva restringendo
                # al gap tra questo marker e il successivo (se presente).
                band_top = mk["top"] - 60
                if i > 0:
                    prev_bot = markers[i - 1]["top"] + 22
                    if prev_bot > band_top:
                        band_top = prev_bot
                band_bot = mk["top"] + 22
                if i + 1 < len(markers):
                    next_top = markers[i + 1]["top"] - 60
                    if next_top < band_bot:
                        band_bot = next_top
                day = _extract_day_from_band(words, band_top, band_bot, page.width)
                if day is None:
                    continue
                # Evita duplicati (stesso giorno + periodicita')
                if any(d.day_number == day.day_number and d.periodicita == day.periodicita
                        for d in current.days):
                    continue
                current.days.append(day)

        if current is not None:
            turns.append(current)

    return turns


# ══════════════════════════════════════════════════════════════════
# SALVATAGGIO IN DB (schema v2)
# ══════════════════════════════════════════════════════════════════

def save_parsed_turns_to_db(turns: list[ParsedPdcTurn],
                             db, source_file: str = "") -> dict:
    """Persiste i turni parsati usando i metodi CRUD schema v2.

    Chiama `db.clear_pdc_data()` prima per avere uno stato pulito.
    Ritorna le statistiche dell'import.
    """
    db.clear_pdc_data()

    for t in turns:
        turn_id = db.insert_pdc_turn(
            codice=t.codice, planning=t.planning, impianto=t.impianto,
            profilo=t.profilo, valid_from=t.valid_from, valid_to=t.valid_to,
            source_file=source_file,
        )
        for day in t.days:
            day_id = db.insert_pdc_turn_day(
                pdc_turn_id=turn_id,
                day_number=day.day_number,
                periodicita=day.periodicita,
                start_time=day.start_time, end_time=day.end_time,
                lavoro_min=day.lavoro_min, condotta_min=day.condotta_min,
                km=day.km, notturno=day.notturno,
                riposo_min=day.riposo_min, is_disponibile=day.is_disponibile,
            )
            for b in day.blocks:
                db.insert_pdc_block(
                    pdc_turn_day_id=day_id, seq=b.seq,
                    block_type=b.block_type,
                    train_id=b.train_id, vettura_id=b.vettura_id,
                    from_station=b.from_station, to_station=b.to_station,
                    start_time=b.start_time, end_time=b.end_time,
                    accessori_maggiorati=b.accessori_maggiorati,
                )
        for n in t.notes:
            db.insert_pdc_train_periodicity(
                pdc_turn_id=turn_id, train_id=n.train_id,
                periodicita_text=n.periodicita_text,
                non_circola_dates=n.non_circola_dates,
                circola_extra_dates=n.circola_extra_dates,
            )
    db.conn.commit()
    return db.get_pdc_stats()


# ══════════════════════════════════════════════════════════════════
# CLI DIAGNOSTICO
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    import json
    from dataclasses import asdict

    if len(sys.argv) < 2:
        print("Usage: python -m src.importer.turno_pdc_parser <file.pdf> [--full]")
        sys.exit(1)

    path = sys.argv[1]
    full = "--full" in sys.argv

    turns = parse_pdc_pdf(path)
    print(f"Turni estratti: {len(turns)}")
    for t in turns[: 3 if not full else None]:
        print(f"\n{'=' * 60}")
        print(f"  {t.codice} @ {t.impianto} [{t.planning}] {t.profilo}")
        print(f"  Validita': {t.valid_from} -> {t.valid_to}")
        print(f"  Giornate: {len(t.days)}")
        for d in t.days:
            disp = " [DISP]" if d.is_disponibile else ""
            blocks_info = ""
            if d.blocks:
                btypes = [b.block_type for b in d.blocks]
                blocks_info = f" blocks={btypes}"
            print(f"    g{d.day_number} {d.periodicita:<8} "
                  f"[{d.start_time}]-[{d.end_time}] "
                  f"Lav={d.lavoro_min:>3}m Cct={d.condotta_min:>3}m "
                  f"Km={d.km:>3} Rip={d.riposo_min:>4}m{disp}{blocks_info}")
        print(f"  Note treni: {len(t.notes)}")
        for n in t.notes[:3]:
            print(f"    - {n.train_id}: {n.periodicita_text[:60]}")
