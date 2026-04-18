#!/usr/bin/env python3
"""
Parser per il PDF Turno Materiale Trenord.
Estrae tutti i numeri treno (regolari e vuote) per ogni turno materiale,
separati per variante di validità.

Gestisce:
- Turni con suffisso (es. 1191A, 1192A)
- Coppie di treni TILO/FNM: "24 25410 25411 COMO"
- Treni S-line: "37 47 25559 920319 Stabio"
- Vuote (deadhead) con suffisso "i": "28096i"
- Concatenazioni da estrazione PDF
- Valori km concatenati: "10609424,04"
- Varianti di validità (LV, SAB, DOM, etc.) per turno
"""

import pdfplumber
import re
import json
import sys
from collections import defaultdict, OrderedDict

PDF_PATH = sys.argv[1] if len(sys.argv) > 1 else 'C:/Users/studio54/Downloads/Vuoto 50 (1).pdf'
# OUTPUT_PATH: secondo argomento CLI, oppure fallback a turno_materiale_treni.json
# nella working directory corrente (cross-platform).
OUTPUT_PATH = sys.argv[2] if len(sys.argv) > 2 else 'turno_materiale_treni.json'


# ============================================================
# VERTICAL EXTRACTOR (new PDF format 2026+)
# ============================================================
# Nel PDF Trenord post-2026 i numeri treno sono scritti VERTICALMENTE
# (upright=False) sopra le barre del Gantt: una cifra per riga Y, da
# leggere BOTTOM-TO-TOP (prima cifra al fondo).
#
# Varianti dello stesso turno (es. LV + esclusioni) appaiono come
# row-band Gantt separate, quindi lo stesso treno puo' comparire piu'
# volte nella stessa colonna X a bande Y diverse.
def _find_y_bands(chars, band_gap=20.0):
    """Trova bande Y globali della pagina usando i salti > band_gap.

    Ritorna lista di (y_min, y_max) per ogni banda.
    """
    if not chars:
        return []
    ys = sorted(set(round(float(c['y0']), 1) for c in chars))
    bands = []
    band_start = ys[0]
    prev = ys[0]
    for y in ys[1:]:
        if y - prev > band_gap:
            bands.append((band_start, prev))
            band_start = y
        prev = y
    bands.append((band_start, prev))
    return bands


def extract_vertical_trains(page, x_tol=2.0, band_gap=20.0, intra_char_gap=8.0):
    """Estrae ID treni da colonne verticali di char rotated (upright=False).

    Algoritmo:
    1. Filtra char con upright=False
    2. Trova bande Y globali (gap verticali > band_gap pt)
    3. Dentro ogni banda, cluster char per X (tolleranza x_tol)
    4. Sort by Y ASCENDING (bottom-to-top = ordine lettura)
    5. Split intra-banda se intra_char_gap superato (riduce falsi positivi
       quando una banda contiene numero+stazione adiacenti)
    6. Match pattern numero treno: \\d{4,6} con 'i' opzionale finale

    Args:
        page: pdfplumber.Page
        x_tol: tolleranza clustering X in pt (default 2).
        band_gap: gap Y minimo per separare bande Gantt (default 20pt).
        intra_char_gap: gap max tra char consecutivi di uno stesso numero (default 8pt).

    Returns:
        lista di (train_id:str, is_deadhead:bool)
    """
    rot_chars = [c for c in page.chars if not c.get('upright', True)]
    if not rot_chars:
        return []

    # 1. Bande Y globali
    bands = _find_y_bands(rot_chars, band_gap=band_gap)

    results = []
    for band_lo, band_hi in bands:
        # 2. Char appartenenti alla banda
        band_chars = [c for c in rot_chars if band_lo - 0.5 <= float(c['y0']) <= band_hi + 0.5]

        # 3. Cluster per X
        cols = defaultdict(list)
        for c in band_chars:
            x_key = round(float(c['x0']) / x_tol) * x_tol
            cols[x_key].append(c)

        for x_key, chars in cols.items():
            # Sort per Y crescente (bottom-to-top)
            chars.sort(key=lambda c: float(c['y0']))

            # 5. Split per gap intra-char (evita concatenazioni spurie)
            subgroups = []
            current = [chars[0]]
            for c in chars[1:]:
                if float(c['y0']) - float(current[-1]['y0']) > intra_char_gap:
                    subgroups.append(current)
                    current = [c]
                else:
                    current.append(c)
            subgroups.append(current)

            for group in subgroups:
                text = ''.join(c['text'] for c in group)
                # Caso 1: colonna pulita = un solo numero
                m = re.fullmatch(r'(\d{4,6})(i?)', text)
                if m:
                    results.append((m.group(1), m.group(2) == 'i'))
                    continue
                # Caso 2: colonna mista digit+letter (es. "28220iMICE")
                # Estrai tutti i pattern \d{4,6}i? concatenati
                for sub in re.finditer(r'(\d{4,6})(i?)(?=\D|$|\d{4,6})', text):
                    tid = sub.group(1)
                    # Evita falsi positivi: minuti a 2-3 cifre non vengono matchati
                    # (pattern e' \d{4,6})
                    results.append((tid, sub.group(2) == 'i'))

    return results


# ============================================================
# EXTRACT ALL ROWS (bottom-to-top per page)
# ============================================================
print(f"Apertura PDF: {PDF_PATH}")
pdf = pdfplumber.open(PDF_PATH)
print(f"Pagine: {len(pdf.pages)}")

all_rows = []
# Per ogni pagina: raccogli i numeri treno verticali (nuovo formato 2026+).
# Li annotiamo con un marker speciale sulla pagina corrente per poterli
# associare al turno rilevato dalle righe orizzontali.
vertical_trains_by_page = {}
for pi in range(len(pdf.pages)):
    page = pdf.pages[pi]
    chars = page.chars
    if not chars:
        continue
    # Estrazione verticale (nuovo formato)
    v_trains = extract_vertical_trains(page)
    if v_trains:
        vertical_trains_by_page[pi] = v_trains

    # Estrazione orizzontale (formato storico + header/metadati)
    y_rows = defaultdict(list)
    for c in chars:
        y = round(float(c['y0']), 0)
        y_rows[y].append(c)
    # Marca inizio pagina per tracciare associazione vertical-trains -> turno
    all_rows.append(f"__PAGE_START__{pi}")
    for y in sorted(y_rows.keys(), reverse=True):
        row = sorted(y_rows[y], key=lambda c: float(c['x0']))
        text = ''.join(c['text'] for c in row).strip()
        if text:
            all_rows.append(text)

print(f"Righe totali estratte: {len(all_rows)}")
print(f"Pagine con treni verticali: {len(vertical_trains_by_page)}")
total_v = sum(len(v) for v in vertical_trains_by_page.values())
print(f"Totale occorrenze treni verticali: {total_v}")

# ============================================================
# SPLIT INTO TURNO SECTIONS
# ============================================================
# Match turno headers (include suffissi tipo "1191A").
# Il PDF Trenord ha due formati distinti:
#   A) Header pagina indice:  "Turno 1100 Validità P)"        (num PRIMA di Validita)
#   B) Header legacy/altro:   "Turno Validit... ) 1100"       (num DOPO la parentesi)
# Supportiamo entrambi con alternanze regex.
#
# Il dettaglio interno della pagina (estratto char-by-char) puo' essere
# concatenato senza spazi (es. "Turno1100"); per questo usiamo \s* (0..n spazi).
turno_header_re = re.compile(
    r'(?:Turno\s+(\d{4,5}[A-Z]?)\s+Validit'                 # formato A
    r'|Turno\s+Validit[^\s]*\s+[^)]*\)\s*(\d{4,5}[A-Z]?))', # formato B
    re.IGNORECASE,
)
turno_detail_re = re.compile(r'^Turno\s*(\d{4,5}[A-Z]?)$', re.IGNORECASE)

current_turno = None
current_page = None
turno_lines = OrderedDict()
# Mappa pagina -> turno attivo (per associare treni verticali)
page_to_turno = {}

for text in all_rows:
    # Marker di inizio pagina iniettato in fase di estrazione
    if text.startswith('__PAGE_START__'):
        current_page = int(text.split('__PAGE_START__')[1])
        continue
    m = turno_header_re.search(text)
    if m:
        # Il regex ha due alternative; prendi il primo gruppo non-None
        current_turno = m.group(1) or m.group(2)
        if current_turno not in turno_lines:
            turno_lines[current_turno] = []
        if current_page is not None:
            page_to_turno[current_page] = current_turno
        continue
    m = turno_detail_re.match(text)
    if m:
        current_turno = m.group(1)
        if current_turno not in turno_lines:
            turno_lines[current_turno] = []
        if current_page is not None:
            page_to_turno[current_page] = current_turno
        continue
    if current_turno and current_turno in turno_lines:
        turno_lines[current_turno].append(text)

print(f"Turni trovati: {len(turno_lines)}")
print(f"Lista: {list(turno_lines.keys())}")

# Associa treni verticali -> turno via page_to_turno
# vertical_trains_by_turno: {turno_code: [(tid, is_dh), ...]}
vertical_trains_by_turno = defaultdict(list)
for pi, v_trains in vertical_trains_by_page.items():
    turno = page_to_turno.get(pi)
    if turno:
        vertical_trains_by_turno[turno].extend(v_trains)
print(f"Turni con treni verticali associati: {len(vertical_trains_by_turno)}")

# ============================================================
# METADATA PATTERNS TO SKIP
# ============================================================
METADATA_PATTERNS = [
    r'^Turni',
    r'^Stampato',
    r'^Note\s',
    r'^Composizione',
    r'^OMV/OML',
    r'^Posti\s',
    r'^Pezzo',
    r'^Impegno',
    r'^Media\s',
    r'^Totale\s',
    r'^Numero\s+Giornate',
    r'^PR\s+\d',
    r'^Tipo\s+Materiale',
    r'^Valid',
    r'^\d{1,3}/\d{2,}$',  # page numbers X/YY+ (not date fragments like 30/3)
    r'^1\s+2\s+3\s+4\s+5',
    r'^P$',
    r'^TILO\s',
    r'^Non\s+assegnato',
    # Material type lines
    r'^nBBW?\s',
    r'^npBB',
    r'^npBD',
    r'^nBC',
    r'^E464',
    r'^nAA',
    r'^TAF',
    r'^TSR',
    r'^ETR',
    r'^ATR',
    r'^ALe',
    r'^ALn',
    r'^Le\d',
    r'^Ale\d',
]
META_RE = [re.compile(p) for p in METADATA_PATTERNS]

# ============================================================
# VALIDITY TEXT DETECTION
# ============================================================
VALIDITY_KEYWORDS = re.compile(
    r'(LV|Lv|SAB|DOM|Domenica|Sabato|Venerd|Circola|Si\s+e[f\ufb00]|E[f\ufb00]ettuato|'
    r'esclus[io]|dal\s+\d|al\s+\d|^F\s|^F$|SF|FsF|FES|PF|Sab_|Infr|Luned|Marte|Gioved|'
    r'\d{1,2}/\d{1,2}|\d{1,2}-\d{1,2}/)',
    re.IGNORECASE
)

def is_validity_text(text):
    """Check if text is a validity description (day types, dates, etc.)."""
    if not text:
        return False
    if re.search(r'\d{4}', text):  # Contains 4+ digit number (train ID)
        return False
    if re.match(r'^\d{1,3},\d{1,2}$', text):  # km value
        return False
    return bool(VALIDITY_KEYWORDS.search(text))


# ============================================================
# TRAIN ENTRY PARSER
# ============================================================
def parse_train_entries(line):
    """Extract (train_id, is_deadhead) from a text line.

    Handles multiple formats:
    - Standard: "35 24 10606 CREMONA"
    - Deadhead: "38 3 93058i" or "18 28220i"
    - KM concat: "36 22 10609424,04"
    - Station concat: "BERG7 37 22671 MICL"
    - Single minute prefix: "722617 TREV"
    - Minute merge: "16 5093019i"
    - Double train (TILO): "24 25410 25411 COMO"
    - Double with S-line: "37 47 25559 920319 Stabio"
    - Bare minute + train pair: "2425453 VARE" -> 24 25453
    """
    trains = []
    original = line

    # Pre-clean: separate km values concatenated at end
    line = re.sub(r'(\d{4,5})(\d{1,3},\d{1,2})\s*$', r'\1 KM\2', line)

    # Pre-clean: separate concatenated station+digits
    # "BERG7 37 22671" -> "BERG 7 37 22671"
    line = re.sub(r'([A-Za-z.]{2,})(\d{1,2}\s+\d{1,2}\s+\d{4,6})', r'\1 \2', line)
    # "MICL0\n50 2248" pattern
    line = re.sub(r'([A-Za-z.]{2,})(\d)(\d{4,5})', r'\1 \2 \3', line)

    # Pre-clean: handle merged minutes + deadhead train
    # "16 5093019i" -> "16 50 93019i"
    # "354828085i" -> "35 48 28085i"
    line = re.sub(r'(\d{1,2})\s+(\d{2})(\d{4,6}i)', r'\1 \2 \3', line)
    # Handle fully merged: "354828085i" with no space
    line = re.sub(r'^(\d{2})(\d{2})(\d{4,6}i)', r'\1 \2 \3', line)

    # Pre-clean: merged minute + S-line train (900xxx/90xxxx)
    # "7900865 MI.N.CAD" -> "7 900865 MI.N.CAD"
    line = re.sub(r'(?:^|\s)(\d)(9\d{5})(?=\s+[A-Z])', r' \1 \2', line)
    # "7900780SARO" -> "7 900780 SARO" (station concatenated)
    line = re.sub(r'(?:^|\s)(\d)(9\d{5})([A-Z][A-Za-z.]{2,})', r' \1 \2 \3', line)
    # Pre-clean: merged 2-digit minute + 5/6-digit train before station
    # "2425453 VARE" -> "24 25453 VARE"
    line = re.sub(r'(?:^|\s)(\d{2})(\d{5,6})(?=\s+[A-Z])', r' \1 \2', line)


    # Pattern 1: Double train entry (TILO format)
    # "24 25410 25411 COMO" or "37 47 25559 920319 Stabio"
    for m in re.finditer(
        r'(?:^|\s)(\d{1,2})\s+(\d{1,2})\s+(\d{4,6})\s+(\d{4,6})(i?)\s+([A-Za-z])',
        line
    ):
        dep_m = int(m.group(1))
        arr_m = int(m.group(2))
        tid1 = m.group(3)
        tid2 = m.group(4)
        is_dh = m.group(5) == 'i'

        if dep_m <= 59 and arr_m <= 59:
            trains.append((tid1, is_dh))
            trains.append((tid2, is_dh))

    # Pattern 1b: "MM TRAIN1 TRAIN2 STATION" (single minute, double train - TILO)
    # "24 25410 25411 COMO" where 24 is arr_min only
    for m in re.finditer(
        r'(?:^|\s)(\d{1,2})\s+(\d{5,6})\s+(\d{5,6})\s+([A-Za-z])',
        line
    ):
        mm = int(m.group(1))
        tid1 = m.group(2)
        tid2 = m.group(3)
        if mm <= 59:
            if (tid1, False) not in trains and (tid1, True) not in trains:
                trains.append((tid1, False))
            if (tid2, False) not in trains and (tid2, True) not in trains:
                trains.append((tid2, False))

    # Pattern 2: Standard "MM MM TRAINID[i] STATION"
    for m in re.finditer(
        r'(?:^|\s)(\d{1,2})\s+(\d{1,2})\s+(\d{4,6})(i?)(?:\s+[A-Za-z]|\s*$)',
        line
    ):
        dep_m = int(m.group(1))
        arr_m = int(m.group(2))
        tid = m.group(3)
        is_dh = m.group(4) == 'i'

        if dep_m <= 59 and arr_m <= 59:
            if (tid, is_dh) not in trains and (tid, not is_dh) not in trains:
                trains.append((tid, is_dh))

    # Pattern 2b: "MM TRAINID[i] STATION" (single minute + train)
    # Handles: "10 900303 MI.N.CAD", "25 10427 COMO S.G"
    for m in re.finditer(
        r'(?:^|\s)(\d{1,2})\s+(\d{4,6})(i?)(?:\s+[A-Za-z]|\s*$)',
        line
    ):
        mm = int(m.group(1))
        tid = m.group(2)
        is_dh = m.group(3) == 'i'

        if mm <= 59:
            if (tid, is_dh) not in trains and (tid, not is_dh) not in trains:
                trains.append((tid, is_dh))

    # Pattern 3: "MM TRAINIDi" (single minute + deadhead)
    for m in re.finditer(r'(?:^|\s)(\d{1,2})\s+(\d{4,6})i(?:\s|$)', line):
        mm = int(m.group(1))
        tid = m.group(2)
        if mm <= 59 and (tid, True) not in trains:
            trains.append((tid, True))

    # Pattern 4: standalone "TRAINIDi"
    for m in re.finditer(r'(?:^|\s)(\d{4,6})i(?:\s|$)', line):
        tid = m.group(1)
        if (tid, True) not in trains and (tid, False) not in trains:
            trains.append((tid, True))

    # Pattern 5: single-digit minute + train: "722617 TREV" -> train 22617
    # Only matches truly concatenated minute+train (no space between them)
    for m in re.finditer(r'(?:^|\s)(\d)(\d{4,5})\s+[A-Za-z]', line):
        minute = int(m.group(1))
        tid = m.group(2)
        if minute <= 9 and (tid, False) not in trains and (tid, True) not in trains:
            trains.append((tid, False))

    return trains


# ============================================================
# VARIANT BLOCK SPLITTER
# ============================================================
def split_into_variants(lines):
    """Split a turno's lines into variant blocks.

    Each variant block has trains + validity text + day_index.
    In the PDF, the structure for each variant is:
      [route header]
      [train entries]
      [km value at end of last line]
      [day_index (standalone small number)]
      [validity text (1+ lines)]
      [next route header or metadata block]

    So validity text is a POSTFIX label for the trains above it.
    """
    variants = []
    current_trains = []  # list of (train_id, is_deadhead)
    current_day_idx = None
    current_validity = []
    collecting_validity = False  # True after trains end, collecting postfix info

    for line in lines:
        # Skip metadata
        is_meta = any(pat.search(line) for pat in META_RE)
        if is_meta:
            if current_trains:
                # Save current variant at metadata boundary
                variants.append({
                    'entries': list(current_trains),
                    'day_index': current_day_idx,
                    'validity': ' '.join(current_validity).strip(),
                })
                current_trains = []
                current_day_idx = None
                current_validity = []
                collecting_validity = False
            continue

        # DISPONIBILE lines = variant boundary (material parked, no trains)
        if 'DISPONIBILE' in line.upper():
            if current_trains:
                variants.append({
                    'entries': list(current_trains),
                    'day_index': current_day_idx,
                    'validity': ' '.join(current_validity).strip(),
                })
                current_trains = []
            current_day_idx = None
            current_validity = []
            collecting_validity = False
            continue

        # Try parsing as train data
        entries = parse_train_entries(line)

        if entries:
            if collecting_validity and current_trains:
                # We had trains + validity, now found new trains = new variant
                variants.append({
                    'entries': list(current_trains),
                    'day_index': current_day_idx,
                    'validity': ' '.join(current_validity).strip(),
                })
                current_trains = []
                current_day_idx = None
                current_validity = []
                collecting_validity = False

            current_trains.extend(entries)
        else:
            # Non-train line
            stripped = line.strip()

            if current_trains and not collecting_validity:
                # Transition from train data to post-train info
                collecting_validity = True

            if collecting_validity:
                if current_day_idx is None and re.match(r'^\d{1,2}$', stripped):
                    current_day_idx = int(stripped)
                elif is_validity_text(stripped):
                    current_validity.append(stripped)
            # else: before any trains (route headers, etc.) - skip

    # Save last variant
    if current_trains:
        variants.append({
            'entries': list(current_trains),
            'day_index': current_day_idx,
            'validity': ' '.join(current_validity).strip(),
        })

    return variants


# ============================================================
# PARSE ROUTE HEADERS
# ============================================================
def extract_route_info(lines):
    """Extract route/line info from the variant lines."""
    routes = set()
    for line in lines:
        if re.match(r'^[A-Z][A-Z .()]+$', line):
            if any(x in line for x in ['DISPONIBILE', 'MCPTC', 'IMPMAN']):
                continue
            routes.add(line.strip())
    return sorted(routes)


# ============================================================
# PARSE ALL TURNI (with variant support)
# ============================================================
turno_results = {}

for tnum in sorted(turno_lines.keys(), key=lambda x: (x.rstrip('ABCDEFG'), x)):
    lines = turno_lines[tnum]

    # Split into variant blocks
    raw_variants = split_into_variants(lines)

    # Estrazione verticale: treni raccolti dalle colonne rotated del PDF
    # nuovo formato. Non hanno variant info, li aggiungiamo come pool globale.
    v_trains = vertical_trains_by_turno.get(tnum, [])

    # Collect ALL train IDs globally for fragment filtering
    all_trains_global = {}
    for var in raw_variants:
        for tid, is_dh in var['entries']:
            tid_clean = str(int(tid))
            tid_int = int(tid_clean)
            if tid_int < 100:
                continue
            if tid_clean in ('2026', '2025', '2024'):
                continue
            if tid_clean not in all_trains_global:
                all_trains_global[tid_clean] = {'deadhead': is_dh}
            if is_dh:
                all_trains_global[tid_clean]['deadhead'] = True

    # Aggiungi treni verticali al pool globale (deduplica via dict)
    for tid, is_dh in v_trains:
        tid_clean = str(int(tid))
        tid_int = int(tid_clean)
        if tid_int < 100:
            continue
        if tid_clean in ('2026', '2025', '2024'):
            continue
        if tid_clean not in all_trains_global:
            all_trains_global[tid_clean] = {'deadhead': is_dh}
        if is_dh:
            all_trains_global[tid_clean]['deadhead'] = True

    # Fragment filtering (global across all variants)
    train_set = set(all_trains_global.keys())
    fragments = set()
    for t in list(train_set):
        t_int = int(t)
        if t_int < 10000:
            for other in train_set:
                if other == t:
                    continue
                if len(other) > len(t) and other.endswith(t):
                    fragments.add(t)
                    break
        elif len(t) == 6 and t_int >= 100000:
            suffix5 = str(int(t[1:]))
            if suffix5 in train_set and suffix5 != t and int(suffix5) >= 10000:
                fragments.add(t)

    # Process each variant: clean trains, apply fragment filter
    processed_variants = []
    for vi, var in enumerate(raw_variants):
        var_trains = {}
        for tid, is_dh in var['entries']:
            tid_clean = str(int(tid))
            tid_int = int(tid_clean)
            if tid_int < 100:
                continue
            if tid_clean in ('2026', '2025', '2024'):
                continue
            if tid_clean in fragments:
                continue
            if tid_clean not in var_trains:
                var_trains[tid_clean] = is_dh
            if is_dh:
                var_trains[tid_clean] = True

        regular = sorted(
            [t for t, dh in var_trains.items() if not dh],
            key=lambda x: int(x)
        )
        deadhead = sorted(
            [t for t, dh in var_trains.items() if dh],
            key=lambda x: int(x)
        )

        if regular or deadhead:  # Only include variants with actual trains
            processed_variants.append({
                'variant_index': len(processed_variants),
                'day_index': var['day_index'],
                'validity': var['validity'],
                'treni': regular,
                'vuote': deadhead,
            })

    # Se esistono treni dall'estrazione verticale ma non sono comparsi in
    # nessuna variante orizzontale, aggiungi una variante "vertical" che li
    # espone nell'output. Questa logica e' additiva: non altera i variant
    # classici se il formato era orizzontale (PDF storico).
    if v_trains:
        v_train_map = {}
        for tid, is_dh in v_trains:
            tid_clean = str(int(tid))
            tid_int = int(tid_clean)
            if tid_int < 100 or tid_clean in ('2026', '2025', '2024'):
                continue
            if tid_clean in fragments:
                continue
            if tid_clean not in v_train_map:
                v_train_map[tid_clean] = is_dh
            if is_dh:
                v_train_map[tid_clean] = True
        v_regular = sorted(
            [t for t, dh in v_train_map.items() if not dh],
            key=lambda x: int(x)
        )
        v_deadhead = sorted(
            [t for t, dh in v_train_map.items() if dh],
            key=lambda x: int(x)
        )
        # Check se c'e' gia' una variante che contiene tutti questi treni
        already_covered = False
        for pv in processed_variants:
            if set(v_regular).issubset(set(pv['treni'])) and \
               set(v_deadhead).issubset(set(pv['vuote'])):
                already_covered = True
                break
        if not already_covered and (v_regular or v_deadhead):
            processed_variants.append({
                'variant_index': len(processed_variants),
                'day_index': None,
                'validity': '(vertical-extraction)',
                'treni': v_regular,
                'vuote': v_deadhead,
            })

    # Combined lists (backward compat)
    all_regular = sorted(
        [t for t in all_trains_global
         if not all_trains_global[t]['deadhead'] and t not in fragments],
        key=lambda x: int(x)
    )
    all_deadhead = sorted(
        [t for t in all_trains_global
         if all_trains_global[t]['deadhead'] and t not in fragments],
        key=lambda x: int(x)
    )
    routes = extract_route_info(lines)

    turno_results[tnum] = {
        'variants': processed_variants,
        'treni': all_regular,
        'vuote': all_deadhead,
        'percorsi': routes,
        'fragments_removed': len(fragments),
    }

# ============================================================
# OUTPUT
# ============================================================
all_regular = set()
all_deadhead = set()

for tnum in sorted(turno_results.keys(), key=lambda x: (x.rstrip('ABCDEFG'), x)):
    r = turno_results[tnum]
    all_regular.update(r['treni'])
    all_deadhead.update(r['vuote'])

    n_vars = len(r['variants'])
    print(f"\nTURNO {tnum}: {len(r['treni'])} treni, {len(r['vuote'])} vuote, {n_vars} varianti")
    if n_vars > 1:
        for v in r['variants']:
            validity = v['validity'] or '(base)'
            print(f"  VAR {v['variant_index']} [day{v['day_index'] or '?'}] "
                  f"{validity}: {len(v['treni'])} treni + {len(v['vuote'])} vuote")
            print(f"    TRENI: {v['treni']}")
            if v['vuote']:
                print(f"    VUOTE: {v['vuote']}")
    else:
        print(f"  TRENI: {r['treni']}")
        if r['vuote']:
            print(f"  VUOTE: {r['vuote']}")
    if r['percorsi']:
        print(f"  PERCORSI: {r['percorsi']}")

print(f"\n{'='*70}")
print(f"RIEPILOGO")
print(f"{'='*70}")
print(f"Turni materiale: {len(turno_results)}")
print(f"Treni regolari distinti (tutti i turni): {len(all_regular)}")
print(f"Vuote distinte (tutti i turni): {len(all_deadhead)}")
print(f"Totale treni unici: {len(all_regular | all_deadhead)}")

total_variants = sum(len(r['variants']) for r in turno_results.values())
multi_variant = sum(1 for r in turno_results.values() if len(r['variants']) > 1)
print(f"Varianti totali: {total_variants}")
print(f"Turni con varianti multiple: {multi_variant}")

# Save JSON
output = {
    'source_pdf': PDF_PATH,
    'turni': turno_results,
    'summary': {
        'total_turni': len(turno_results),
        'all_regular_trains': sorted(all_regular, key=lambda x: int(x)),
        'all_deadhead_trains': sorted(all_deadhead, key=lambda x: int(x)),
        'total_regular': len(all_regular),
        'total_deadhead': len(all_deadhead),
        'total_variants': total_variants,
        'multi_variant_turni': multi_variant,
    }
}

with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"\nSalvato: {OUTPUT_PATH}")
