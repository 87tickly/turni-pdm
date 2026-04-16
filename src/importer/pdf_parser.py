"""
PDF parser for Trenord "Turno Materiale" Gantt-chart documents.

This parser is specifically designed for the landscape-oriented Gantt pages
found in Trenord material turn PDFs (~353 pages). Each data page shows:

  - A horizontal hour grid (hours 0..23) at a fixed y position
  - Multiple "day variant bands" stacked vertically, each representing
    a different schedule (e.g. weekdays, holidays, specific dates)
  - Within each band:
      * VERTICAL train IDs: individual digits stacked at the same x,
        read bottom-to-top (e.g. digits 6,0,6,0,1 top→bottom -> "10606")
      * VERTICAL station names: individual characters stacked at the same x,
        read bottom-to-top (e.g. A,N,O,M,E,R,C -> "CREMONA")
      * HORIZONTAL station names: full text labels along the route line
      * MINUTE values: 1-2 digit numbers positioned at dep/arr x-coordinates
      * Km values in the rightmost column

Key geometric constants (measured from real PDFs):
  - GRID_LEFT_X  = 135.8   (x position corresponding to hour 0)
  - HOUR_WIDTH   = 21.6    (pixels per hour)
  - Hour n is at x = 135.8 + n * 21.6

The x position of a minute value determines its hour:
  hour = floor((x - GRID_LEFT_X) / HOUR_WIDTH)

Uses pdfplumber for text extraction -- NO OCR needed (digital PDFs).
"""

import re
import math
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict

import pdfplumber

from ..database.db import Database, TrainSegment


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Grid geometry constants (measured from real Trenord Turno Materiale PDFs)
# ---------------------------------------------------------------------------
GRID_LEFT_X = 135.8       # x coordinate of hour 0 on the Gantt grid
HOUR_WIDTH_PX = 21.6      # pixels per hour on the Gantt grid

# Page regions
DATA_AREA_TOP_Y = 110.0   # y below which the data area starts
DATA_AREA_LEFT_X = 135.0  # x right of which is the Gantt chart area
PER_COLUMN_X = 655.0      # x of the "Per" column (right boundary of data)
KM_COLUMN_X = 695.0       # x of the "Km" column

# ---------------------------------------------------------------------------
# Font size thresholds (measured from real PDFs)
# ---------------------------------------------------------------------------
# Minute values: size ~4.1, font CIDFont+F1
MINUTE_SIZE_MIN = 3.0
MINUTE_SIZE_MAX = 5.2

# Vertical train ID digits: size ~5.4
VERT_DIGIT_SIZE_MIN = 4.0
VERT_DIGIT_SIZE_MAX = 6.5

# Horizontal station names: size ~5.9
STATION_H_SIZE_MIN = 5.0
STATION_H_SIZE_MAX = 7.0

# Vertical station name characters: size ~4.0-5.0
# Note: some chars (period ".", narrow "I") have size ~1.6 in CIDFont+F2
# We use a low minimum to capture ALL characters including punctuation
VERT_CHAR_SIZE_MIN = 1.0
VERT_CHAR_SIZE_MAX = 5.5

# Day index numbers: size ~10.3 at x ~75.5
DAY_INDEX_SIZE_MIN = 8.0
DAY_INDEX_SIZE_MAX = 14.0
DAY_INDEX_MAX_X = 100.0

# Validity label text: size ~5.9, at left margin
VALIDITY_SIZE_MIN = 5.0
VALIDITY_SIZE_MAX = 7.0
VALIDITY_MAX_X = 135.0

# Turno number: size ~19.6
TURNO_SIZE_MIN = 15.0

# Middle text (layover info): size ~10.3, in data area
MIDDLE_TEXT_SIZE_MIN = 8.0
MIDDLE_TEXT_SIZE_MAX = 14.0

# ---------------------------------------------------------------------------
# Clustering tolerances
# ---------------------------------------------------------------------------
# Tolerance for grouping characters at the "same x" (vertical text)
X_CLUSTER_TOL = 1.5

# Tolerance for grouping elements in the same y-band
Y_BAND_MERGE_TOL = 5.0

# Maximum y-spacing between consecutive digits of a vertical train ID
VERT_DIGIT_MAX_Y_GAP = 8.0

# Maximum y-spacing between consecutive chars of a vertical station name
VERT_CHAR_MAX_Y_GAP = 8.0

# Proximity for matching a minute value to a train (x distance)
MINUTE_TRAIN_X_PROXIMITY = 60.0

# How far a minute can be from the nearest station to still be associated
MINUTE_STATION_X_PROXIMITY = 200.0

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------
RE_TURNO = re.compile(r"[Tt]urno\s+(\d{4,6})")
RE_VALIDITY = re.compile(
    r"(LV|GG|Si\s+eff|Eff|Esclus|esclus|sab|dom|fest)"
    r"[.\s]",
    re.IGNORECASE,
)

# Material type (locomotiva/automotrice): codice che appare nella tabella
# "Impegno del materiale (n.pezzi)" sopra il Gantt. Le carrozze hanno codici
# minuscoli (npBDL, nBC-clim) e non ci interessano: ci interessa il mezzo
# di trazione (E464, E464N, E484, ETR425, ALn668, TAF, TSR, ecc.).
RE_LOCO = re.compile(
    r"^(E\d{3,4}[A-Z]?|ETR\d{2,4}|ALn?\d{2,4}|ALe\d{2,4}|TAF|TSR)$"
)

# ---------------------------------------------------------------------------
# Station name normalization
# ---------------------------------------------------------------------------
# Noise words that appear as horizontal text but are NOT station names
NOISE_WORDS = {
    "DI", "IL", "IN", "CON", "DA", "AL", "DEL", "PER",
    "PERCORRE", "BINARIO", "DESTRA", "SINISTRA", "RITARDO",
    "ENTRO", "ARRIVO", "PARTENZA", "MANOVRA", "STAZIONE",
    "DISPONIBILE", "TURNO", "TRENO", "ALLA", "ALLA", "DALLA",
}

# Hardcoded Trenord station name dictionary.
# Maps abbreviated forms (from vertical text) to canonical full names.
# Built from analysis of horizontal station labels across the full PDF.
STATION_NORMALIZE_MAP: dict[str, str] = {
    # ── MILANO stations ──
    # MI.P.GARIBALDI
    "MI.P.GAR": "MI.P.GARIBALDI",
    "MI.P.GA": "MI.P.GARIBALDI",
    "MPGAR": "MI.P.GARIBALDI",
    "MIPG": "MI.P.GARIBALDI",
    "MIP": "MI.P.GARIBALDI",
    "MP": "MI.P.GARIBALDI",
    # MI.CERTOSA
    "MI.CERT.": "MI.CERTOSA",
    "MI.CERT": "MI.CERTOSA",
    "MCERT": "MI.CERTOSA",
    "MIC": "MI.CERTOSA",
    "MILANO CERTOSA": "MI.CERTOSA",
    "MI CERTOSA": "MI.CERTOSA",
    # MILANO CENTRALE
    "MI.C.LE": "MILANO CENTRALE",
    "MICL": "MILANO CENTRALE",
    "MI.CLE": "MILANO CENTRALE",
    "MIL": "MILANO CENTRALE",
    # MILANO N.CADORNA
    "N.CAD": "MILANO N.CADORNA",
    "N.CADORNA": "MILANO N.CADORNA",
    "MNCAD": "MILANO N.CADORNA",
    "MI.N.CAD": "MILANO N.CADORNA",
    "MI.N.CA": "MILANO N.CADORNA",
    "MI.N.C": "MILANO N.CADORNA",
    "MI.N.CAD.": "MILANO N.CADORNA",
    "MIN": "MILANO N.CADORNA",
    "MINC": "MILANO N.CADORNA",
    "MILANO N.CADORNA COMO LAGO": "MILANO N.CADORNA",  # bad merge fix
    # MI.LAMBRATE
    "MI.LAMB.": "MI.LAMBRATE",
    "MI.LAMB": "MI.LAMBRATE",
    "MLAMB": "MI.LAMBRATE",
    # MI BOVISA FNM
    "MI.BOV": "MI BOVISA FNM",
    "MIBOV": "MI BOVISA FNM",
    "BOVFNM": "MI BOVISA FNM",
    "BOVFN": "MI BOVISA FNM",
    "BOVF": "MI BOVISA FNM",
    "BOV": "MI BOVISA FNM",
    # MI.GRECO PIRELLI
    "MI.GREC": "MI.GRECO PIRELLI",
    "MIGREC": "MI.GRECO PIRELLI",
    "MIGR": "MI.GRECO PIRELLI",
    "MIG": "MI.GRECO PIRELLI",
    # MILANO ROGOREDO
    "ROGOR": "MILANO ROGOREDO",
    "MI.ROG": "MILANO ROGOREDO",
    "MI.ROGOREDO": "MILANO ROGOREDO",
    "MIROG": "MILANO ROGOREDO",
    "MIRO": "MILANO ROGOREDO",
    # MI.S.CRISTOFORO
    "MI.S.CR.": "MI.S.CRISTOFORO",
    "MI.S.CR": "MI.S.CRISTOFORO",
    # NOVATE MILANESE
    "NOVAT": "NOVATE MILANESE",
    "NOVATEMI": "NOVATE MILANESE",
    # GARBAGNATE MILANESE
    "GARB": "GARBAGNATE MILANESE",
    "GARB.MIL": "GARBAGNATE MILANESE",
    "GARBAGNATE MIL.": "GARBAGNATE MILANESE",
    # CORMANO-CUSANO
    "CORMA": "CORMANO-CUSANO",
    # ── Linea BERGAMO / TREVIGLIO ──
    "TREVIG.": "TREVIGLIO",
    "TREVG": "TREVIGLIO",
    "TREV": "TREVIGLIO",
    "TRE": "TREVIGLIO",
    "BERG": "BERGAMO",
    "BER": "BERGAMO",
    "PONTESP": "PONTE S.PIETRO",
    "PONTES": "PONTE S.PIETRO",
    "PIOLT": "PIOLTELLO",
    "PIO": "PIOLTELLO",
    "CARN": "CARNATE",
    "CARNATE USMATE": "CARNATE",
    # ── Linea CREMONA / BRESCIA / EDOLO ──
    "CRE": "CREMONA",
    "BRE": "BRESCIA",
    "BRESC": "BRESCIA",
    "BRESCA": "BRESCIA",
    "BOZ": "BOZZOLO",
    "PIAD": "PIADENA",
    "OLMEN": "OLMENETA",
    # ── Linea NOVARA / DOMODOSSOLA ──
    "NOV": "NOVARA",
    "NO": "NOVARA",
    "NOVA": "NOVARA",
    "NOV.FN": "NOVARA FN",
    "NOV.FNM": "NOVARA FNM",
    "NOVARAFN": "NOVARA FN",
    "DOMO": "DOMODOSSOLA",
    "DOM": "DOMODOSSOLA",
    "ARO": "ARONA",
    "PREM": "PREMOSELLO",
    "PREMOSEL": "PREMOSELLO",
    # ── Linea COMO / LECCO ──
    "COMOL": "COMO LAGO",
    "COMOLAGO": "COMO LAGO",
    "COMOS.G": "COMO S.GIOVANNI",
    "COMOS.GIO": "COMO S.GIOVANNI",
    "COMOSGIO": "COMO S.GIOVANNI",
    "CO CAMERLATA": "COMO CAMERLATA",
    "LEC": "LECCO",
    "COL": "COLICO",
    "MOLT": "MOLTENO",
    "MER": "MERONE",
    # ── Linea VARESE / LAVENO ──
    "VA": "VARESE",
    "VAR": "VARESE",
    "VARE": "VARESE",
    "VARESEFN": "VARESE FN",
    "VARESEF": "VARESE FN",
    "VARESEC": "VARESE CASBENO",
    "LAVEN": "LAVENO FN",
    "LAVENOFN": "LAVENO FN",
    "LAVENOM": "LAVENO MOMBELLO",
    "LAV": "LAVENO FN",
    "GAL": "GALLARATE",
    "GALL": "GALLARATE",
    "GALLAR.": "GALLARATE",
    "BUST": "BUSTO ARSIZIO",
    "BUSTO": "BUSTO ARSIZIO",
    "BUS": "BUSTO ARSIZIO",
    "MAL": "MALNATE",
    "ALB": "ALBIZZATE",
    "ALBAIRAT": "ALBAIRATE",
    "LUI": "LUINO",
    "TRAD": "TRADATE",
    # ── Linea SARONNO / SEVESO ──
    "SAR": "SARONNO",
    "SEV": "SEVESO",
    "SER": "SEREGNO",
    "MED": "MEDA",
    "CANZO-A.": "CANZO-ASSO",
    "CANZ": "CANZO-ASSO",
    "CAMN": "CAMNAGO-LENTATE",
    "CAMNAGO": "CAMNAGO-LENTATE",
    "MIR": "MARIANO COMENSE",
    # ── Linea CHIASSO / STABIO ──
    "CHI": "CHIASSO",
    "MEND": "MENDRISIO",
    "MEN": "MENDRISIO",
    "STA": "STABIO",
    "CHIAVEN.": "CHIAVENNA",
    # ── Linea PAVIA / PIACENZA / ALESSANDRIA ──
    "PAV": "PAVIA",
    "PV": "PAVIA",
    "PAVIA(*": "PAVIA",
    "PIA": "PIACENZA",
    "PIAC": "PIACENZA",
    "ALESS": "ALESSANDRIA",
    "ALESSAN.": "ALESSANDRIA",
    "ALE": "ALESSANDRIA",
    "LOD": "LODI",
    "COD": "CODOGNO",
    "GAR": "GARLASCO",
    "FID": "FIDENZA",
    "BELGIOIO": "BELGIOIOSO",
    "CASALP.": "CASALPUSTERLENGO",
    "STRADEL.": "STRADELLA",
    "VOGH": "VOGHERA",
    "MORTA": "MORTARA",
    "ABBIATEG": "ABBIATEGRASSO",
    # ── Linea NOVI LIGURE / TORTONA ──
    "NOVI": "NOVI LIGURE",
    "NOVILI": "NOVI LIGURE",
    "NOVILIG": "NOVI LIGURE",
    "TOR": "TORTONA",
    # ── Linea VERONA ──
    "VR": "VERONA P.NUOVA",
    "VRP.N.": "VERONA P.NUOVA",
    "VRP.N": "VERONA P.NUOVA",
    "VERON": "VERONA P.NUOVA",
    # ── Linea EDOLO / ISEO ──
    "EDO": "EDOLO",
    "ISE": "ISEO",
    "IISEO": "ISEO",
    "ROV": "ROVATO",
    "PISO": "PISOGNE",
    "BRENO": "BRENO",
    "CEDEG": "CEDEGOLO",
    # ── Linea MONZA / SESTO ──
    "MONZ": "MONZA",
    "MON": "MONZA",
    "SES": "SESTO S.GIOVANNI",
    "SESTOSG": "SESTO S.GIOVANNI",
    "SESTOCL": "SESTO CALENDE",
    "BESANA": "BESANA BRIANZA",
    # ── Linea SONDRIO / TIRANO ──
    "SON": "SONDRIO",
    "TIR": "TIRANO",
    # ── MALPENSA ──
    "MALP.AT": "MALPENSA T1",
    "MALP.A": "MALPENSA T1",
    "MALP": "MALPENSA T1",
    "MALPAT": "MALPENSA T1",
    "PMAL": "MALPENSA T1",
    # ── PORTO CERESIO ──
    "PORTOC.": "PORTO CERESIO",
    # ── Altre ──
    "MANT": "MANTOVA",
    "PAR": "PARMA",
    "BOR": "BORGOMANERO",
    "PRE": "PREGNANA MILANESE",
    "SPE": "LOCATE TRIULZI",
    "SPEZIAC": "LA SPEZIA C.",
    "VEN": "VENEGONO",
    "VENTIMIG": "VENTIMIGLIA",
    "CAVATI.": "CAVATINO",
    "MEL": "MELEGNANO",
    "BORN": "BORNATO",
    "BORNATOC": "BORNATO",
    "CORT": "CORTEOLONA",
    "SALE": "SALE",
    "COMO": "COMO LAGO",
}


def normalize_station_name(raw: str) -> str:
    """
    Normalize an abbreviated station name to its canonical full form.

    Checks in order:
    1. Direct match in STATION_NORMALIZE_MAP
    2. If the name ends with ".", try without the dot
    3. If the name is a prefix of exactly one known full name, use that
    4. Return the raw name unchanged if no match found
    """
    if not raw or raw == "???":
        return raw

    upper = raw.upper().strip()

    # 1. Direct match
    if upper in STATION_NORMALIZE_MAP:
        return STATION_NORMALIZE_MAP[upper]

    # 2. Try without trailing dot
    if upper.endswith(".") and upper[:-1] in STATION_NORMALIZE_MAP:
        return STATION_NORMALIZE_MAP[upper[:-1]]

    # 3. Check if it's already a known full name
    known_full = set(STATION_NORMALIZE_MAP.values())
    if upper in known_full:
        return upper

    # 4. Prefix matching against known full names
    if len(upper) >= 4:
        matches = [full for full in known_full if full.startswith(upper)]
        if len(matches) == 1:
            return matches[0]

    return upper


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class ParsedSegment:
    """A single parsed train segment from the Gantt chart."""
    train_id: str = ""           # may contain multiple ids joined by "/"
    from_station: str = ""
    to_station: str = ""
    dep_time: str = ""          # HH:MM
    arr_time: str = ""          # HH:MM
    day_index: int = 0
    confidence: float = 1.0
    turno_id: str = ""
    km: str = ""
    validity_text: str = ""
    source_page: int = 0
    seq: int = 0
    raw_text: str = ""
    is_deadhead: bool = False    # vuoto/deadhead movement (suffix "i")
    is_accessory: bool = False   # first/last segment of the day
    segment_kind: str = "train"  # 'train' | 'cvl_cb'


@dataclass
class VerticalText:
    """A vertical text element reconstructed from individual characters."""
    text: str
    x: float               # shared x coordinate
    y_top: float            # y of topmost character
    y_bottom: float         # y of bottommost character
    char_count: int


@dataclass
class DayBand:
    """A horizontal band on the page representing one day variant."""
    y_min: float
    y_max: float
    day_index: int
    validity_text: str = ""


# ---------------------------------------------------------------------------
# Coordinate / time helpers
# ---------------------------------------------------------------------------

def x_to_hour(x: float) -> int:
    """
    Convert an x pixel coordinate to the corresponding hour (0-23).

    Uses the grid geometry: hour = floor((x - GRID_LEFT_X) / HOUR_WIDTH_PX)
    Clamped to [0, 23].

    A small epsilon (1e-6) is added before flooring to compensate for
    floating-point imprecision (e.g. 157.4-135.8 = 21.5999... not 21.6).
    """
    raw = (x - GRID_LEFT_X) / HOUR_WIDTH_PX + 1e-6
    return max(0, min(23, int(math.floor(raw))))


def x_to_time(x: float, minute_text: str) -> str:
    """
    Convert an x coordinate and minute text to an HH:MM time string.

    The hour is derived from the x position on the Gantt grid.
    The minute is the literal text value (0-59).
    """
    hour = x_to_hour(x)
    try:
        minute = int(minute_text)
    except ValueError:
        minute = 0
    if minute > 59:
        minute = 59
    return f"{hour:02d}:{minute:02d}"


# ---------------------------------------------------------------------------
# Text element extraction helpers
# ---------------------------------------------------------------------------

def _extract_words_with_attrs(page) -> list[dict]:
    """
    Extract all text elements from a pdfplumber page with position and size.

    Returns a list of dicts, each with keys:
        text, x0, top, x1, bottom, size
    """
    try:
        words = page.extract_words(
            extra_attrs=["size", "fontname"],
            keep_blank_chars=False,
            x_tolerance=1,
            y_tolerance=1,
        )
    except Exception:
        # Fallback without fontname if the version doesn't support it
        try:
            words = page.extract_words(
                extra_attrs=["size"],
                keep_blank_chars=False,
                x_tolerance=1,
                y_tolerance=1,
            )
        except Exception:
            words = page.extract_words(extra_attrs=["size"])

    result = []
    for w in words:
        size = w.get("size", 0)
        if isinstance(size, (list, tuple)):
            size = size[0] if size else 0
        result.append({
            "text": w.get("text", ""),
            "x0": float(w.get("x0", 0)),
            "top": float(w.get("top", 0)),
            "x1": float(w.get("x1", 0)),
            "bottom": float(w.get("bottom", 0)),
            "size": float(size),
            "fontname": w.get("fontname", ""),
        })
    return result


def _extract_chars_with_attrs(page) -> list[dict]:
    """
    Extract individual characters from a pdfplumber page with position and size.

    This is essential for reading VERTICAL text where pdfplumber's word
    extraction merges characters incorrectly or misses vertical stacking.

    Returns a list of dicts with keys:
        text, x0, top, x1, bottom, size, fontname
    """
    chars = page.chars
    result = []
    for c in chars:
        text = c.get("text", "").strip()
        if not text:
            continue
        size = c.get("size", 0)
        if isinstance(size, (list, tuple)):
            size = size[0] if size else 0
        result.append({
            "text": text,
            "x0": float(c.get("x0", 0)),
            "top": float(c.get("top", 0)),
            "x1": float(c.get("x1", 0)),
            "bottom": float(c.get("bottom", 0)),
            "size": float(size),
            "fontname": c.get("fontname", ""),
        })
    return result


# ---------------------------------------------------------------------------
# Page classification
# ---------------------------------------------------------------------------

def is_data_page(words: list[dict]) -> bool:
    """
    Determine if a page is a data page (has the Gantt hour grid).

    Data pages have the sequence "1 2 3 4 5 6 7 8 9 10 11..." rendered
    as individual number elements at a consistent y position (~103).
    We look for at least 10 of the hour numbers 1..23 within the expected
    y range.
    """
    hour_y_min = 95.0
    hour_y_max = 115.0
    hour_x_min = 140.0

    hour_hits = set()
    for w in words:
        if (w["top"] >= hour_y_min and w["top"] <= hour_y_max
                and w["x0"] >= hour_x_min
                and w["text"].isdigit()):
            val = int(w["text"])
            if 1 <= val <= 23:
                hour_hits.add(val)

    return len(hour_hits) >= 10


def extract_turno_number(words: list[dict]) -> str:
    """
    Extract the turno number from large text on the page.

    The turno number appears as a 4-digit number at size ~19.6 in the header.
    Also checks for "Turno XXXX" patterns in regular text.
    """
    # Strategy 1: Large standalone 4-digit number
    for w in words:
        if (w["text"].isdigit()
                and len(w["text"]) == 4
                and w["size"] >= TURNO_SIZE_MIN
                and w["top"] < DATA_AREA_TOP_Y):
            return w["text"]

    # Strategy 2: Concatenate all text and search for "Turno XXXX"
    all_text = " ".join(w["text"] for w in words if w["top"] < DATA_AREA_TOP_Y)
    m = RE_TURNO.search(all_text)
    if m:
        return m.group(1)

    # Strategy 3: Any 4-digit number in the header area
    for w in words:
        if (w["text"].isdigit()
                and len(w["text"]) == 4
                and w["top"] < 90):
            return w["text"]

    return ""


def extract_material_type(words: list[dict]) -> str:
    """
    Extract the rolling-stock locomotive code from the header page.

    The header of each turno materiale contains a table
    "Impegno del materiale (n.pezzi)" with rows like:
        Pezzo         Numero
        npBDL         2
        nBC-clim      10
        E464N         2
    Lowercase rows (npBDL, nBC-clim) are carriages; the uppercase row is the
    locomotive/self-propelled unit that identifies the material type of the
    giro. We return the first uppercase code matching RE_LOCO; if no anchor
    is found we still fall back to searching the entire header region.

    Returns the locomotive code (e.g. "E464N") or "" if not found.
    """
    if not words:
        return ""

    # Strategy 1: anchor on "Impegno", then scan the words below it.
    anchor = None
    for w in words:
        if w["text"].strip().startswith("Impegno"):
            anchor = w
            break

    if anchor is not None:
        y_start = anchor["top"]
        y_end = y_start + 200  # generous window to cover the 3-4 row table
        for w in words:
            if y_start <= w["top"] <= y_end:
                m = RE_LOCO.match(w["text"].strip())
                if m:
                    return m.group(1)

    # Strategy 2: fallback — scan the whole header area (above the Gantt grid).
    for w in words:
        if w["top"] < DATA_AREA_TOP_Y:
            m = RE_LOCO.match(w["text"].strip())
            if m:
                return m.group(1)

    return ""


# ---------------------------------------------------------------------------
# Vertical text reconstruction
# ---------------------------------------------------------------------------

def _cluster_by_x(items: list[dict], tol: float = X_CLUSTER_TOL) -> dict[float, list[dict]]:
    """
    Group items that share the same x0 coordinate (within tolerance).

    Returns a dict mapping the median x0 of each cluster to the items
    in that cluster, sorted by y (top).
    """
    if not items:
        return {}

    sorted_items = sorted(items, key=lambda c: c["x0"])
    clusters = []
    current_cluster = [sorted_items[0]]

    for item in sorted_items[1:]:
        if abs(item["x0"] - current_cluster[-1]["x0"]) <= tol:
            current_cluster.append(item)
        else:
            clusters.append(current_cluster)
            current_cluster = [item]
    clusters.append(current_cluster)

    result = {}
    for cluster in clusters:
        # Sort by y within cluster
        cluster.sort(key=lambda c: c["top"])
        median_x = cluster[len(cluster) // 2]["x0"]
        result[median_x] = cluster

    return result


def extract_vertical_train_ids(
    chars: list[dict],
    y_min: float,
    y_max: float,
) -> list[VerticalText]:
    """
    Find vertical train IDs within a y-band.

    Train IDs are 5 individual digits stacked vertically at the same x,
    with size ~5.4 and y-spacing ~5.4. They appear in the Gantt data area.

    The digits are read BOTTOM-TO-TOP to form the train number
    (same convention as vertical station names).
    Example: digits 6,0,6,0,1 at y=150.7..172.3 (top to bottom in PDF)
             -> reversed = "10606"

    Returns list of VerticalText with the reconstructed train IDs.
    """
    # Filter: single digits (or "i" suffix for deadhead/vuoto IDs),
    # correct size, in data area x range, in y band
    candidates = [
        c for c in chars
        if ((c["text"].isdigit() or c["text"].lower() in ("i", "v"))
            and len(c["text"]) == 1
            and VERT_DIGIT_SIZE_MIN <= c["size"] <= VERT_DIGIT_SIZE_MAX
            and c["x0"] > DATA_AREA_LEFT_X
            and c["x0"] < PER_COLUMN_X
            and c["top"] >= y_min
            and c["top"] <= y_max)
    ]

    if not candidates:
        return []

    # Group by x position
    x_groups = _cluster_by_x(candidates, tol=X_CLUSTER_TOL)

    train_ids = []
    for x_pos, group in x_groups.items():
        # Within this x column, find runs of consecutive digits
        # (y gap <= VERT_DIGIT_MAX_Y_GAP)
        runs = _split_into_runs(group, max_gap=VERT_DIGIT_MAX_Y_GAP)

        for run in runs:
            if len(run) < 4 or len(run) > 7:
                # Train IDs are typically 5 digits, allow 4-7 (6+ for deadhead with suffix)
                continue

            # Digits are stacked top-to-bottom in the PDF but represent
            # the train number read BOTTOM-TO-TOP (same as station names).
            # e.g. digits 6,0,6,0,1 (top→bottom) = train "10606" (bottom→top)
            text = "".join(c["text"] for c in reversed(run))

            # Validate: all-zeros is noise
            digits_only = re.sub(r'[^0-9]', '', text)
            if digits_only and digits_only == "0" * len(digits_only):
                continue
            # Must contain at least 4 digits
            if len(digits_only) < 4:
                continue

            train_ids.append(VerticalText(
                text=text,
                x=x_pos,
                y_top=run[0]["top"],
                y_bottom=run[-1]["top"],
                char_count=len(run),
            ))

    return train_ids


def extract_vertical_station_names(
    chars: list[dict],
    y_min: float,
    y_max: float,
) -> list[VerticalText]:
    """
    Find vertical station names within a y-band.

    Station names are individual letters stacked vertically at the same x,
    read BOTTOM-TO-TOP to get the station name.
    Example: chars A,N,O,M,E,R,C (top to bottom) -> reversed = "CREMONA"

    These appear at size ~4-5, in the data area.

    Returns list of VerticalText with the reconstructed station names.
    """
    # Filter: single letters (or period/dot for abbreviations),
    # correct size, in data area
    candidates = [
        c for c in chars
        if (len(c["text"]) == 1
            and (c["text"].isalpha() or c["text"] in ".'-/")
            and VERT_CHAR_SIZE_MIN <= c["size"] <= VERT_CHAR_SIZE_MAX
            and c["x0"] > DATA_AREA_LEFT_X
            and c["x0"] < PER_COLUMN_X
            and c["top"] >= y_min
            and c["top"] <= y_max)
    ]

    if not candidates:
        return []

    x_groups = _cluster_by_x(candidates, tol=X_CLUSTER_TOL)

    stations = []
    for x_pos, group in x_groups.items():
        runs = _split_into_runs(group, max_gap=VERT_CHAR_MAX_Y_GAP)

        for run in runs:
            if len(run) < 2:
                continue

            # Read bottom-to-top
            reversed_chars = list(reversed(run))
            text = "".join(c["text"] for c in reversed_chars).upper()

            # Skip if it looks like a number (digit run misclassified)
            if text.isdigit():
                continue
            # Skip very short strings that are probably noise
            if len(text) < 2:
                continue

            stations.append(VerticalText(
                text=text,
                x=x_pos,
                y_top=run[0]["top"],
                y_bottom=run[-1]["top"],
                char_count=len(run),
            ))

    return stations


def _split_into_runs(
    sorted_items: list[dict],
    max_gap: float,
) -> list[list[dict]]:
    """
    Split a list of items (sorted by y) into runs where consecutive items
    have y-gap <= max_gap.
    """
    if not sorted_items:
        return []

    runs = []
    current_run = [sorted_items[0]]

    for item in sorted_items[1:]:
        gap = item["top"] - current_run[-1]["top"]
        if gap <= max_gap:
            current_run.append(item)
        else:
            runs.append(current_run)
            current_run = [item]
    runs.append(current_run)

    return runs


# ---------------------------------------------------------------------------
# Horizontal element extraction
# ---------------------------------------------------------------------------

def extract_horizontal_stations(
    words: list[dict],
    y_min: float,
    y_max: float,
) -> list[dict]:
    """
    Find horizontal station name labels within a y-band.

    These are full-text station names rendered at size ~5.9, positioned
    along the route line. They indicate the sequence of stations.

    Multi-word station names (e.g. "MILANO" + "CERTOSA") are merged
    when words are at the same y level and close together in x.

    Returns list of word dicts with text, x0, top.
    """
    # Step 1: Collect raw station-sized words
    raw_words = []
    for w in words:
        if (w["top"] >= y_min and w["top"] <= y_max
                and w["x0"] > DATA_AREA_LEFT_X
                and w["x0"] < PER_COLUMN_X
                and STATION_H_SIZE_MIN <= w["size"] <= STATION_H_SIZE_MAX
                and any(ch.isalpha() for ch in w["text"])
                and len(w["text"]) >= 2):
            text_upper = w["text"].upper()
            # Skip validity-related text
            if any(skip in text_upper for skip in [
                "DISPONIBILE", "TURNO", "ESCLUS", "EFF.",
                "EFFETT", "FEST", "PERIOD",
            ]):
                continue
            if RE_VALIDITY.match(w["text"]):
                continue
            # Skip pure numbers
            cleaned = w["text"].replace(".", "").replace("-", "")
            if cleaned.isdigit():
                continue
            raw_words.append(w)

    if not raw_words:
        return []

    # Step 2: Sort by (y, x) and merge adjacent words into multi-word names
    raw_words.sort(key=lambda w: (w["top"], w["x0"]))

    merged = []
    i = 0
    while i < len(raw_words):
        current = dict(raw_words[i])  # copy
        # Try to merge with the next word(s) at the same y level
        j = i + 1
        while j < len(raw_words):
            nxt = raw_words[j]
            y_gap = abs(nxt["top"] - current["top"])
            x_gap = nxt["x0"] - current["x1"]
            if y_gap < 3.0 and 0 <= x_gap < 30.0:
                # Merge: extend text and x1
                current["text"] = current["text"] + " " + nxt["text"]
                current["x1"] = nxt["x1"]
                j += 1
            else:
                break
        merged.append(current)
        i = j

    # Step 3: Filter noise - remove non-station sentence fragments
    stations = []
    for w in merged:
        text_upper = w["text"].upper().strip()
        # Skip if ALL words are noise words
        word_parts = text_upper.replace(".", " ").replace("(", " ").replace(")", " ").split()
        real_parts = [p for p in word_parts if p not in NOISE_WORDS and len(p) > 1]
        if not real_parts:
            continue
        # Skip sentence-like text (4+ words with noise words = not a station)
        if len(word_parts) >= 4 and any(p in NOISE_WORDS for p in word_parts):
            continue
        stations.append(w)

    return stations


def extract_minute_values(
    words: list[dict],
    y_min: float,
    y_max: float,
) -> list[dict]:
    """
    Find minute values within a y-band.

    Minutes are 1-2 digit numbers (0-59) at size ~4.1, positioned at the
    x-coordinate of their corresponding departure or arrival point.

    Returns list of word dicts with text, x0, top, size.
    """
    minutes = []
    for w in words:
        text = w["text"].strip()
        if (text.isdigit()
                and len(text) <= 2
                and int(text) < 60
                and w["top"] >= y_min and w["top"] <= y_max
                and w["x0"] > DATA_AREA_LEFT_X
                and w["x0"] < PER_COLUMN_X
                and MINUTE_SIZE_MIN <= w["size"] <= MINUTE_SIZE_MAX):
            minutes.append(w)
    return minutes


def extract_km_values(
    words: list[dict],
    y_min: float,
    y_max: float,
) -> list[dict]:
    """
    Find km values in the Km column for this band.
    """
    kms = []
    for w in words:
        if (w["x0"] >= KM_COLUMN_X
                and w["top"] >= y_min and w["top"] <= y_max
                and w["text"].replace(".", "").replace(",", "").isdigit()):
            kms.append(w)
    return kms


# ---------------------------------------------------------------------------
# Day band detection
# ---------------------------------------------------------------------------

def detect_day_bands(
    words: list[dict],
    page_height: float = 612.0,
) -> list[DayBand]:
    """
    Identify the day variant bands on a data page.

    Day variant bands are horizontal stripes, each containing one schedule
    variant. They are identified by:
    1. Day index numbers (size ~10.3) at x < 100
    2. Validity labels (e.g. "LV 1:5 esclusi 2-3-4/3") at x < 135

    If no explicit day markers are found, we treat the entire data area
    as a single band with day_index=1.

    Returns list of DayBand sorted by y_min.
    """
    # Find day index numbers
    day_markers = []
    for w in words:
        if (w["text"].isdigit()
                and 1 <= int(w["text"]) <= 30
                and w["size"] >= DAY_INDEX_SIZE_MIN
                and w["size"] <= DAY_INDEX_SIZE_MAX
                and w["x0"] < DAY_INDEX_MAX_X
                and w["top"] > DATA_AREA_TOP_Y):
            day_markers.append({
                "day_index": int(w["text"]),
                "y": w["top"],
            })

    # Find validity labels
    validity_labels = []
    for w in words:
        if (w["x0"] < VALIDITY_MAX_X
                and w["top"] > DATA_AREA_TOP_Y
                and VALIDITY_SIZE_MIN <= w["size"] <= VALIDITY_SIZE_MAX):
            text = w["text"].strip()
            if len(text) > 1 and any(ch.isalpha() for ch in text):
                validity_labels.append({
                    "text": text,
                    "y": w["top"],
                })

    if not day_markers:
        # No explicit day markers: single band covering whole page
        return [DayBand(
            y_min=DATA_AREA_TOP_Y,
            y_max=page_height,
            day_index=1,
            validity_text=_merge_validity_near_y(
                validity_labels, DATA_AREA_TOP_Y, page_height
            ),
        )]

    # Sort markers by y
    day_markers.sort(key=lambda m: m["y"])

    bands = []
    for i, marker in enumerate(day_markers):
        # Use midpoints between consecutive markers as band boundaries.
        # This ensures all data (digits, stations, minutes) around each
        # marker is captured, even if it extends above or below the marker.
        if i == 0:
            # First band: extend generously above the first marker
            y_min = max(DATA_AREA_TOP_Y, marker["y"] - 40.0)
        else:
            y_min = (day_markers[i - 1]["y"] + marker["y"]) / 2.0

        if i + 1 < len(day_markers):
            y_max = (marker["y"] + day_markers[i + 1]["y"]) / 2.0
        else:
            y_max = page_height

        validity = _merge_validity_near_y(validity_labels, y_min, y_max)

        bands.append(DayBand(
            y_min=y_min,
            y_max=y_max,
            day_index=marker["day_index"],
            validity_text=validity,
        ))

    return bands


def _merge_validity_near_y(
    labels: list[dict],
    y_min: float,
    y_max: float,
) -> str:
    """Concatenate validity label texts within a y range."""
    parts = []
    for lbl in labels:
        if y_min <= lbl["y"] <= y_max:
            parts.append(lbl["text"])
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Station matching
# ---------------------------------------------------------------------------

def match_station_for_train(
    train_x: float,
    horizontal_stations: list[dict],
    direction: str = "from",
) -> str:
    """
    Determine the from/to station for a train based on x-position.

    Horizontal stations are placed at x positions along the route line.
    If we sort them by x, a train at position train_x falls between two
    station labels. The station to its LEFT is where it departs FROM,
    and the station to its RIGHT is where it arrives TO.

    For direction="from": return the closest station with x <= train_x
    For direction="to": return the closest station with x > train_x

    Args:
        train_x: x-coordinate of the train ID
        horizontal_stations: list of station word dicts sorted by x0
        direction: "from" or "to"

    Returns:
        Station name string, or "???" if not found.
    """
    if not horizontal_stations:
        return "???"

    sorted_stations = sorted(horizontal_stations, key=lambda s: s["x0"])

    if direction == "from":
        # Find the rightmost station that is to the LEFT of the train
        best = None
        for s in sorted_stations:
            if s["x0"] <= train_x + 10:  # small tolerance
                best = s
            else:
                break
        if best:
            return best["text"].upper()
        # Fallback: closest station overall
        closest = min(sorted_stations, key=lambda s: abs(s["x0"] - train_x))
        return closest["text"].upper()

    else:  # direction == "to"
        # Find the leftmost station that is to the RIGHT of the train
        for s in sorted_stations:
            if s["x0"] > train_x - 10:  # small tolerance
                return s["text"].upper()
        # Fallback: closest station overall
        closest = min(sorted_stations, key=lambda s: abs(s["x0"] - train_x))
        return closest["text"].upper()


# ---------------------------------------------------------------------------
# Minute-to-train matching
# ---------------------------------------------------------------------------

def match_minutes_to_train(
    train: VerticalText,
    minutes: list[dict],
    all_trains: list[VerticalText],
) -> tuple[Optional[dict], Optional[dict]]:
    """
    Find the departure and arrival minute values for a given train.

    Strategy:
    - Departure minute: the closest minute to the LEFT of the train's x,
      but not closer to another train
    - Arrival minute: the closest minute to the RIGHT of the train's x,
      but not closer to another train

    Returns (dep_minute_word, arr_minute_word) or (None, None).
    """
    tx = train.x

    # Sort minutes by x
    sorted_mins = sorted(minutes, key=lambda m: m["x0"])

    # Find dep: closest minute with x < tx
    dep_candidates = [m for m in sorted_mins if m["x0"] < tx + 5]
    arr_candidates = [m for m in sorted_mins if m["x0"] > tx - 5]

    dep_w = None
    arr_w = None

    if dep_candidates:
        # Sort by distance to train (ascending), pick closest
        dep_candidates.sort(key=lambda m: abs(m["x0"] - tx))
        for candidate in dep_candidates:
            if candidate["x0"] > tx + 5:
                continue
            # Check this minute isn't closer to another train
            dist_to_us = abs(candidate["x0"] - tx)
            if dist_to_us > MINUTE_TRAIN_X_PROXIMITY:
                continue
            closer_to_other = False
            for other_train in all_trains:
                if other_train is train:
                    continue
                if abs(candidate["x0"] - other_train.x) < dist_to_us - 2:
                    closer_to_other = True
                    break
            if not closer_to_other:
                dep_w = candidate
                break

    if arr_candidates:
        arr_candidates.sort(key=lambda m: abs(m["x0"] - tx))
        for candidate in arr_candidates:
            if candidate["x0"] < tx - 5:
                continue
            if candidate is dep_w:
                continue
            dist_to_us = abs(candidate["x0"] - tx)
            if dist_to_us > MINUTE_TRAIN_X_PROXIMITY:
                continue
            closer_to_other = False
            for other_train in all_trains:
                if other_train is train:
                    continue
                if abs(candidate["x0"] - other_train.x) < dist_to_us - 2:
                    closer_to_other = True
                    break
            if not closer_to_other:
                arr_w = candidate
                break

    return dep_w, arr_w


def find_dep_arr_minutes(
    train: VerticalText,
    minutes: list[dict],
) -> tuple[Optional[dict], Optional[dict]]:
    """
    Simplified minute matching: find the nearest minute to the left (dep)
    and to the right (arr) of the train's x position.

    This version does NOT filter by "closer to another train" -- it just
    picks the closest in each direction within the proximity threshold.
    Use this as a fallback when the more sophisticated matching fails.
    """
    tx = train.x
    dep_w = None
    arr_w = None
    dep_dist = float("inf")
    arr_dist = float("inf")

    for m in minutes:
        mx = m["x0"]
        if mx < tx + 5:
            d = abs(tx - mx)
            if d < dep_dist and d < MINUTE_TRAIN_X_PROXIMITY:
                dep_dist = d
                dep_w = m
        if mx > tx - 5:
            d = abs(mx - tx)
            if d < arr_dist and d < MINUTE_TRAIN_X_PROXIMITY:
                if m is not dep_w:
                    arr_dist = d
                    arr_w = m

    return dep_w, arr_w


# ---------------------------------------------------------------------------
# Core page parser
# ---------------------------------------------------------------------------

def parse_data_page(
    page,
    page_num: int,
    current_turno: str,
) -> tuple[list[ParsedSegment], str]:
    """
    Parse a single Gantt data page and extract train segments.

    Args:
        page: pdfplumber Page object
        page_num: 1-based page number
        current_turno: turno number carried from previous pages

    Returns:
        (segments, turno_number) where turno_number may be updated
    """
    page_height = float(page.height)

    # Extract words (for horizontal text, minutes, metadata)
    words = _extract_words_with_attrs(page)
    if not words:
        return [], current_turno

    # Check for turno number on this page
    turno = extract_turno_number(words) or current_turno

    # Verify this is a data page
    if not is_data_page(words):
        return [], turno

    # Extract individual characters (for vertical text reconstruction)
    chars = _extract_chars_with_attrs(page)

    # Detect day variant bands
    bands = detect_day_bands(words, page_height)

    all_segments = []

    for band in bands:
        band_segments = _parse_band(
            words=words,
            chars=chars,
            band=band,
            turno=turno,
            page_num=page_num,
        )
        all_segments.extend(band_segments)

    return all_segments, turno


def _parse_band(
    words: list[dict],
    chars: list[dict],
    band: DayBand,
    turno: str,
    page_num: int,
) -> list[ParsedSegment]:
    """
    Parse a single day variant band and extract train segments.

    Steps:
    1. Extract vertical train IDs (groups of stacked digits)
    2. Extract horizontal station names (route labels)
    3. Extract vertical station names (stacked letters, bottom-to-top)
    4. Extract minute values
    5. Match each train ID to its dep/arr minutes using x-proximity
    6. Determine from/to stations using station x-positions relative to train
    7. Extract km values

    Returns list of ParsedSegment.
    """
    y_min = band.y_min
    y_max = band.y_max

    # Step 1: Vertical train IDs
    v_trains = extract_vertical_train_ids(chars, y_min, y_max)

    if not v_trains:
        return []

    # Step 2: Horizontal station names
    h_stations = extract_horizontal_stations(words, y_min, y_max)

    # Step 3: Vertical station names (supplementary)
    v_stations = extract_vertical_station_names(chars, y_min, y_max)

    # Step 4: Minute values
    minutes = extract_minute_values(words, y_min, y_max)

    # Step 5: Km values
    km_values = extract_km_values(words, y_min, y_max)

    # Build combined station list for matching
    # Horizontal stations take priority (they are the route labels)
    # Merge in vertical stations that don't overlap with horizontal ones
    combined_stations = list(h_stations)
    for vs in v_stations:
        # Check if there is already a horizontal station near this x
        already_covered = any(
            abs(hs["x0"] - vs.x) < 15 for hs in h_stations
        )
        if not already_covered and len(vs.text) >= 3:
            # Normalize the vertical station name before adding
            normalized = normalize_station_name(vs.text)
            combined_stations.append({
                "text": normalized,
                "x0": vs.x,
                "top": vs.y_top,
            })

    # Sort combined stations by x
    combined_stations.sort(key=lambda s: s["x0"])

    # Step 6: Match trains to minutes and stations
    segments = []
    used_minutes = set()  # track minute indices to avoid reuse

    for train in sorted(v_trains, key=lambda t: t.x):
        # Try sophisticated matching first
        dep_w, arr_w = match_minutes_to_train(train, minutes, v_trains)

        # Fallback to simple nearest matching
        if dep_w is None or arr_w is None:
            dep_w_fb, arr_w_fb = find_dep_arr_minutes(train, minutes)
            if dep_w is None:
                dep_w = dep_w_fb
            if arr_w is None:
                arr_w = arr_w_fb

        if dep_w is None or arr_w is None:
            logger.debug(
                "Page %d: Train %s at x=%.1f - could not find dep/arr minutes",
                page_num, train.text, train.x,
            )
            continue

        # Ensure dep is to the left of arr
        if dep_w["x0"] > arr_w["x0"]:
            dep_w, arr_w = arr_w, dep_w

        # Convert to times
        dep_time = x_to_time(dep_w["x0"], dep_w["text"])
        arr_time = x_to_time(arr_w["x0"], arr_w["text"])

        # Validate: arrival should be after departure (or within same day)
        dep_h, dep_m = map(int, dep_time.split(":"))
        arr_h, arr_m = map(int, arr_time.split(":"))
        dep_total = dep_h * 60 + dep_m
        arr_total = arr_h * 60 + arr_m
        if arr_total < dep_total:
            # Could be overnight, allow if gap is reasonable
            arr_total += 24 * 60
        duration = arr_total - dep_total
        if duration > 720:  # more than 12 hours is suspicious
            logger.debug(
                "Page %d: Train %s duration %d min seems too long, skipping",
                page_num, train.text, duration,
            )
            continue
        if duration <= 0:
            logger.debug(
                "Page %d: Train %s has zero/negative duration, skipping",
                page_num, train.text,
            )
            continue

        # Match stations
        from_station = match_station_for_train(
            dep_w["x0"], combined_stations, direction="from"
        )
        to_station = match_station_for_train(
            arr_w["x0"], combined_stations, direction="to"
        )

        # If from and to are the same, try using the train x position
        if from_station == to_station and len(combined_stations) >= 2:
            from_station = match_station_for_train(
                train.x, combined_stations, direction="from"
            )
            to_station = match_station_for_train(
                train.x, combined_stations, direction="to"
            )

        # Normalize station names (expand abbreviations to full names)
        from_station = normalize_station_name(from_station)
        to_station = normalize_station_name(to_station)

        # Compute confidence
        confidence = _compute_confidence(
            train, dep_w, arr_w, from_station, to_station, duration,
        )

        # Find closest km value
        km_text = ""
        if km_values:
            closest_km = min(
                km_values, key=lambda k: abs(k["top"] - train.y_top)
            )
            if abs(closest_km["top"] - train.y_top) < 30:
                km_text = closest_km["text"]

        # Detect deadhead/vuoto: train IDs ending with "i" (e.g. "28384i")
        actual_train_id = train.text
        is_deadhead = False
        if re.match(r'^\d+[iv]$', actual_train_id, re.IGNORECASE):
            is_deadhead = True
            # Keep suffix in train_id for identification, strip for matching
            actual_train_id = actual_train_id  # keep as-is (e.g. "28384i")

        seg = ParsedSegment(
            train_id=actual_train_id,
            from_station=from_station,
            to_station=to_station,
            dep_time=dep_time,
            arr_time=arr_time,
            day_index=band.day_index,
            confidence=confidence,
            turno_id=turno,
            km=km_text,
            validity_text=band.validity_text,
            source_page=page_num,
            seq=len(segments),
            raw_text=f"T{actual_train_id} {from_station}->{to_station} {dep_time}-{arr_time}" + (" [VUOTO]" if is_deadhead else ""),
            is_deadhead=is_deadhead,
        )
        segments.append(seg)

    return segments


def _compute_confidence(
    train: VerticalText,
    dep_w: dict,
    arr_w: dict,
    from_station: str,
    to_station: str,
    duration_min: int,
) -> float:
    """
    Compute a confidence score (0.0 - 1.0) for a parsed segment.

    Factors:
    - Train ID digit count (5 = best)
    - Proximity of dep/arr minutes to train x
    - Whether stations were identified (vs "???")
    - Duration plausibility (10-300 minutes is typical)
    """
    score = 1.0

    # Train ID quality
    if train.char_count != 5:
        score -= 0.1

    # Minute proximity
    dep_dist = abs(dep_w["x0"] - train.x)
    arr_dist = abs(arr_w["x0"] - train.x)
    if dep_dist > 40 or arr_dist > 40:
        score -= 0.1
    if dep_dist > 60 or arr_dist > 60:
        score -= 0.2

    # Station identification
    if from_station == "???":
        score -= 0.2
    if to_station == "???":
        score -= 0.2
    if from_station == to_station and from_station != "???":
        score -= 0.15

    # Duration plausibility
    if duration_min < 5:
        score -= 0.3
    elif duration_min > 300:
        score -= 0.2
    elif duration_min > 180:
        score -= 0.1

    return max(0.0, min(1.0, round(score, 2)))


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def deduplicate_segments(segments: list[ParsedSegment]) -> list[ParsedSegment]:
    """
    Remove duplicate segments.

    A segment is considered duplicate if another segment has the same
    (train_id, dep_time, arr_time, day_index). When duplicates exist,
    keep the one with the highest confidence.
    """
    seen: dict[tuple, ParsedSegment] = {}
    for seg in segments:
        key = (seg.train_id, seg.dep_time, seg.arr_time, seg.day_index)
        if key not in seen or seg.confidence > seen[key].confidence:
            seen[key] = seg

    result = list(seen.values())
    # Re-assign sequential indices
    for i, seg in enumerate(result):
        seg.seq = i

    return result


def _time_to_min(hhmm: str) -> int:
    """Parse 'HH:MM' -> minutes from midnight, tolerant of empty input."""
    if not hhmm or ":" not in hhmm:
        return 0
    try:
        h, m = hhmm.split(":", 1)
        return int(h) * 60 + int(m)
    except ValueError:
        return 0


def mark_accessory_segments(
    segments: list[ParsedSegment],
) -> list[ParsedSegment]:
    """
    Flag the first and last segment of each (turno_id, day_index) as accessory.

    The turno materiale PDF shows these segments as the red bars that open or
    close the daily roster: they represent setup/wrap-up work that belongs
    to the macchinista as an 'accessorio' and isn't a commercial train run
    in the normal sense.
    """
    if not segments:
        return segments

    # Group indices by (turno_id, day_index) preserving the input order
    groups: dict[tuple, list[int]] = defaultdict(list)
    for i, seg in enumerate(segments):
        groups[(seg.turno_id, seg.day_index)].append(i)

    for indices in groups.values():
        # Sort indices chronologically by dep_time (fallback to original order)
        indices_sorted = sorted(
            indices,
            key=lambda idx: (_time_to_min(segments[idx].dep_time), idx),
        )
        if not indices_sorted:
            continue
        segments[indices_sorted[0]].is_accessory = True
        segments[indices_sorted[-1]].is_accessory = True

    return segments


def mark_cvl_cb_segments(
    segments: list[ParsedSegment],
    max_span_min: int = 80,
) -> list[ParsedSegment]:
    """
    Flag consecutive short red bars as CVL/CB.

    Rule: within a single (turno_id, day_index), scan chronologically and
    find the LONGEST contiguous sub-sequence of segments whose total span
    (first dep_time .. last arr_time) is <= max_span_min. If the sub-sequence
    has 2 or more segments, mark every one with segment_kind='cvl_cb'.

    This is applied greedily: once a window is closed, scanning resumes
    from the next segment. It correctly handles days with mixed CVL bursts
    and normal long runs.

    'CVL' (Cambio Veloce Locomotiva) and 'CB' (Cambio Banco) are both
    short shunting activities; we tag them with a single generic label.
    """
    if not segments:
        return segments

    groups: dict[tuple, list[int]] = defaultdict(list)
    for i, seg in enumerate(segments):
        groups[(seg.turno_id, seg.day_index)].append(i)

    for indices in groups.values():
        if len(indices) < 2:
            continue

        indices_sorted = sorted(
            indices,
            key=lambda idx: (_time_to_min(segments[idx].dep_time), idx),
        )

        i = 0
        n = len(indices_sorted)
        while i < n:
            start_dep = _time_to_min(segments[indices_sorted[i]].dep_time)
            j = i
            # Expand window while total span stays within max_span_min
            while j + 1 < n:
                next_arr = _time_to_min(
                    segments[indices_sorted[j + 1]].arr_time,
                )
                if next_arr < start_dep:
                    next_arr += 24 * 60  # wrap midnight
                if next_arr - start_dep > max_span_min:
                    break
                j += 1
            # Window [i..j] with >=2 segments -> tag as cvl_cb
            if j > i:
                for k in range(i, j + 1):
                    segments[indices_sorted[k]].segment_kind = "cvl_cb"
            i = j + 1

    return segments


def merge_multinumber_segments(
    segments: list[ParsedSegment],
) -> list[ParsedSegment]:
    """
    Merge segments that describe the same physical run with multiple train ids.

    In Trenord material turns, a single red bar on the Gantt can carry two
    consecutive train numbers (e.g. 3085 and 3086) when the same convoy
    changes number mid-route without changing crew/material. The parser
    creates one ParsedSegment per vertical number; this function collapses
    those into a single segment with `train_id = "3085/3086"`.

    Two segments are considered the same run when they share:
        (turno_id, day_index, from_station, to_station, dep_time, arr_time)
    The train_ids are concatenated with "/" in numeric order, and duplicates
    inside the combined id are dropped.
    """
    if not segments:
        return segments

    groups: dict[tuple, list[ParsedSegment]] = defaultdict(list)
    order: list[tuple] = []
    for seg in segments:
        key = (
            seg.turno_id, seg.day_index,
            seg.from_station, seg.to_station,
            seg.dep_time, seg.arr_time,
        )
        if key not in groups:
            order.append(key)
        groups[key].append(seg)

    merged: list[ParsedSegment] = []
    for key in order:
        group = groups[key]
        if len(group) == 1:
            merged.append(group[0])
            continue

        # Collect unique train_ids preserving order of first appearance
        # but sorted numerically when all ids are numeric
        ids_seen: list[str] = []
        for s in group:
            tid = s.train_id.strip()
            if tid and tid not in ids_seen:
                ids_seen.append(tid)

        if all(t.isdigit() for t in ids_seen):
            ids_seen.sort(key=int)

        # Start from the highest-confidence segment to preserve best data
        best = max(group, key=lambda s: s.confidence)
        best.train_id = "/".join(ids_seen)
        # Any id with deadhead suffix? keep deadhead true if any were
        best.is_deadhead = any(s.is_deadhead for s in group)
        merged.append(best)

    # Re-assign sequential indices
    for i, seg in enumerate(merged):
        seg.seq = i

    return merged


# ---------------------------------------------------------------------------
# Public API: parse_pdf()
# ---------------------------------------------------------------------------

def parse_pdf(filepath: str) -> tuple[list[dict], list[dict]]:
    """
    Parse a Trenord "Turno Materiale" PDF and extract all train segments.

    This is the main entry point for the PDF parser module.

    Args:
        filepath: path to the PDF file

    Returns:
        (segments, material_turns) where:
        - segments: list of dicts with keys:
            train_id, from_station, to_station, dep_time, arr_time,
            day_index, confidence, turno_id, km, validity_text,
            source_page, seq, raw_text
        - material_turns: list of dicts with keys:
            turn_number, source_file, total_segments
    """
    pdf_path = Path(filepath)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {filepath}")

    all_segments: list[ParsedSegment] = []
    turno_numbers_seen: set[str] = set()
    # Mappa turn_number -> material_type (primo valore non vuoto incontrato)
    turno_material_types: dict[str, str] = {}
    current_turno = ""
    data_page_count = 0

    logger.info("Opening PDF: %s", pdf_path.name)

    with pdfplumber.open(str(pdf_path)) as pdf:
        total_pages = len(pdf.pages)
        logger.info("Total pages: %d", total_pages)

        for page_num, page in enumerate(pdf.pages, start=1):
            # Quick word extraction for page classification
            words = _extract_words_with_attrs(page)

            # Always check for turno number
            page_turno = extract_turno_number(words)
            if page_turno:
                current_turno = page_turno
                turno_numbers_seen.add(page_turno)

            # Material type: cerchiamo la tabella "Impegno del materiale"
            # che appare nell'header page. Registriamo il primo valore trovato
            # per ogni turno (le pagine successive non ce l'hanno).
            if current_turno and current_turno not in turno_material_types:
                mat_type = extract_material_type(words)
                if mat_type:
                    turno_material_types[current_turno] = mat_type

            # Only parse data pages (those with the hour grid)
            if not is_data_page(words):
                continue

            data_page_count += 1

            # Full parse of the data page
            page_segments, updated_turno = parse_data_page(
                page, page_num, current_turno,
            )
            if updated_turno:
                current_turno = updated_turno
                turno_numbers_seen.add(updated_turno)

            all_segments.extend(page_segments)

            if data_page_count % 50 == 0:
                logger.info(
                    "  Processed %d data pages, %d segments so far",
                    data_page_count, len(all_segments),
                )

    logger.info(
        "Parsing complete: %d data pages, %d raw segments",
        data_page_count, len(all_segments),
    )

    # Deduplicate
    unique_segments = deduplicate_segments(all_segments)
    logger.info("After dedup: %d unique segments", len(unique_segments))

    # Merge segments sharing the same red bar but different train numbers
    # (e.g. 3085/3086). Collapses them into a single segment.
    before_merge = len(unique_segments)
    unique_segments = merge_multinumber_segments(unique_segments)
    if before_merge != len(unique_segments):
        logger.info(
            "After multi-number merge: %d segments (-%d merged)",
            len(unique_segments), before_merge - len(unique_segments),
        )

    # Flag first/last of each day as accessory, and short consecutive
    # sequences (<=80 min total) as CVL/CB.
    unique_segments = mark_accessory_segments(unique_segments)
    unique_segments = mark_cvl_cb_segments(unique_segments)
    acc = sum(1 for s in unique_segments if s.is_accessory)
    cvl = sum(1 for s in unique_segments if s.segment_kind == "cvl_cb")
    logger.info(
        "Tagged: %d accessory segments, %d cvl_cb segments", acc, cvl,
    )

    # Convert to dicts
    segment_dicts = []
    for seg in unique_segments:
        segment_dicts.append({
            "train_id": seg.train_id,
            "from_station": seg.from_station,
            "to_station": seg.to_station,
            "dep_time": seg.dep_time,
            "arr_time": seg.arr_time,
            "day_index": seg.day_index,
            "confidence": seg.confidence,
            "turno_id": seg.turno_id,
            "km": seg.km,
            "validity_text": seg.validity_text,
            "source_page": seg.source_page,
            "seq": seg.seq,
            "raw_text": seg.raw_text,
            "is_deadhead": seg.is_deadhead,
            "is_accessory": seg.is_accessory,
            "segment_kind": seg.segment_kind,
        })

    # Build material turn list
    if not turno_numbers_seen:
        turno_numbers_seen = {"0000"}

    material_turns = []
    for tn in sorted(turno_numbers_seen):
        count = sum(1 for s in segment_dicts if s.get("turno_id") == tn)
        material_turns.append({
            "turn_number": tn,
            "source_file": pdf_path.name,
            "total_segments": count,
            "material_type": turno_material_types.get(tn, ""),
        })

    return segment_dicts, material_turns


# ---------------------------------------------------------------------------
# PDFImporter class (backward-compatible interface)
# ---------------------------------------------------------------------------

class PDFImporter:
    """
    High-level importer that parses a Turno Materiale PDF and stores
    the results in the SQLite database.

    This class maintains backward compatibility with the CLI and other
    modules that instantiate PDFImporter(pdf_path, db) and call run_import().
    """

    def __init__(self, pdf_path: str, db: Database):
        self.pdf_path = Path(pdf_path)
        self.db = db
        self.segments: list[ParsedSegment] = []
        self.turn_numbers: list[str] = []
        self.warnings: list[str] = []

    def validate_pdf(self) -> bool:
        """Verify the PDF exists and is a digital Trenord document."""
        if not self.pdf_path.exists():
            print(f"ERRORE: File non trovato: {self.pdf_path}")
            return False
        try:
            with pdfplumber.open(str(self.pdf_path)) as pdf:
                if len(pdf.pages) == 0:
                    print("ERRORE: PDF vuoto (0 pagine).")
                    return False

                first_text = pdf.pages[0].extract_text() or ""
                if len(first_text.strip()) < 20:
                    print("PDF non digitale o struttura non riconosciuta.")
                    return False

                # Scan first pages for turno numbers
                for page in pdf.pages[:30]:
                    page_text = page.extract_text() or ""
                    matches = RE_TURNO.findall(page_text)
                    self.turn_numbers.extend(matches)

                self.turn_numbers = sorted(set(self.turn_numbers))
                if self.turn_numbers:
                    print(f"Turni identificati: {len(self.turn_numbers)}")
                else:
                    self.warnings.append(
                        "Nessun turno identificato nell'header. "
                        "Il parser tentera' comunque l'analisi."
                    )
        except Exception as e:
            print(f"ERRORE apertura PDF: {e}")
            return False
        return True

    def run_import(self) -> int:
        """
        Execute the full import pipeline: validate, parse, deduplicate,
        and store segments in the database.

        Returns the number of unique segments imported.
        """
        print(f"\n{'='*60}")
        print(f"IMPORTAZIONE PDF: {self.pdf_path.name}")
        print(f"{'='*60}\n")

        if not self.validate_pdf():
            return 0

        # Parse the PDF
        print("Avvio analisi pagine Gantt...")
        segment_dicts, material_turns = parse_pdf(str(self.pdf_path))

        print(f"\nSegmenti unici estratti: {len(segment_dicts)}")
        print(f"Turni materiale trovati: {len(material_turns)}")

        if not segment_dicts:
            print("\nNessun segmento trovato nel documento.")
            return 0

        # Convert back to ParsedSegment for internal storage
        for sd in segment_dicts:
            self.segments.append(ParsedSegment(
                train_id=sd["train_id"],
                from_station=sd["from_station"],
                to_station=sd["to_station"],
                dep_time=sd["dep_time"],
                arr_time=sd["arr_time"],
                day_index=sd["day_index"],
                confidence=sd["confidence"],
                turno_id=sd.get("turno_id", ""),
                km=sd.get("km", ""),
                validity_text=sd.get("validity_text", ""),
                source_page=sd["source_page"],
                seq=sd["seq"],
                raw_text=sd.get("raw_text", ""),
                is_deadhead=sd.get("is_deadhead", False),
                is_accessory=sd.get("is_accessory", False),
                segment_kind=sd.get("segment_kind", "train"),
            ))

        # Update turn numbers
        self.turn_numbers = sorted(set(
            list(self.turn_numbers)
            + [mt["turn_number"] for mt in material_turns]
        ))

        # Confidence statistics
        high = sum(1 for s in self.segments if s.confidence >= 0.8)
        medium = sum(1 for s in self.segments if 0.4 <= s.confidence < 0.8)
        low = sum(1 for s in self.segments if s.confidence < 0.4)
        print(f"\n  Confidence alta  (>=0.8): {high}")
        print(f"  Confidence media (0.4-0.8): {medium}")
        print(f"  Confidence bassa (<0.4): {low}")

        # Station coverage
        total = len(self.segments)
        unknown_from = sum(1 for s in self.segments if s.from_station == "???")
        unknown_to = sum(1 for s in self.segments if s.to_station == "???")
        if total > 0:
            pct_from = (total - unknown_from) / total * 100
            pct_to = (total - unknown_to) / total * 100
            print(f"\n  Stazione partenza identificata: {pct_from:.1f}%")
            print(f"  Stazione arrivo identificata:   {pct_to:.1f}%")

        # Unique trains
        unique_trains = sorted(set(s.train_id for s in self.segments))
        print(f"\n  Treni unici: {len(unique_trains)}")

        # Deadhead/vuoto segments
        deadhead_count = sum(1 for s in self.segments if s.is_deadhead)
        if deadhead_count:
            print(f"  Movimenti vuoto (deadhead): {deadhead_count}")

        # Save to database
        print("\nSalvataggio nel database...")
        turn_id_map = {}
        for mt in material_turns:
            mt_id = self.db.insert_material_turn(
                turn_number=mt["turn_number"],
                source_file=mt["source_file"],
                total_segments=mt["total_segments"],
                material_type=mt.get("material_type", ""),
            )
            turn_id_map[mt["turn_number"]] = mt_id

        if not turn_id_map:
            mt_id = self.db.insert_material_turn(
                turn_number="0000",
                source_file=str(self.pdf_path.name),
                total_segments=len(self.segments),
            )
            turn_id_map["0000"] = mt_id

        db_segments = []
        for seg in self.segments:
            mt_id = turn_id_map.get(
                seg.turno_id,
                list(turn_id_map.values())[0],
            )
            db_seg = TrainSegment(
                id=None,
                train_id=seg.train_id,
                from_station=seg.from_station,
                dep_time=seg.dep_time,
                to_station=seg.to_station,
                arr_time=seg.arr_time,
                material_turn_id=mt_id,
                day_index=seg.day_index,
                seq=seg.seq,
                confidence=seg.confidence,
                raw_text=seg.raw_text,
                source_page=seg.source_page,
                is_deadhead=seg.is_deadhead,
                is_accessory=seg.is_accessory,
                segment_kind=seg.segment_kind,
            )
            db_segments.append(db_seg)

        self.db.bulk_insert_segments(db_segments)
        total_db = self.db.segment_count()
        print(f"  Segmenti nel DB: {total_db}")

        # Save day variants (validity_text per day_index per material_turn)
        day_variants_seen = set()
        dv_count = 0
        for seg in self.segments:
            vt = getattr(seg, "validity_text", "").strip().upper()
            if not vt:
                vt = "GG"  # default: tutti i giorni
            mt_id = turn_id_map.get(
                seg.turno_id,
                list(turn_id_map.values())[0],
            )
            key = (seg.day_index, mt_id, vt)
            if key not in day_variants_seen:
                day_variants_seen.add(key)
                self.db.insert_day_variant(
                    day_index=seg.day_index,
                    material_turn_id=mt_id,
                    validity_text=vt,
                )
                dv_count += 1
        print(f"  Day variants salvate: {dv_count}")

        if self.warnings:
            print(f"\n  WARNINGS:")
            for w in self.warnings:
                print(f"    - {w}")

        print(f"\n{'='*60}")
        print(f"IMPORTAZIONE COMPLETATA: {len(self.segments)} segmenti")
        print(f"{'='*60}\n")

        return len(self.segments)
