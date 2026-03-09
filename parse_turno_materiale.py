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
OUTPUT_PATH = 'C:/Users/studio54/Desktop/COLAZIONE/turno_materiale_treni.json'

# ============================================================
# EXTRACT ALL ROWS (bottom-to-top per page)
# ============================================================
print(f"Apertura PDF: {PDF_PATH}")
pdf = pdfplumber.open(PDF_PATH)
print(f"Pagine: {len(pdf.pages)}")

all_rows = []
for pi in range(len(pdf.pages)):
    page = pdf.pages[pi]
    chars = page.chars
    if not chars:
        continue
    y_rows = defaultdict(list)
    for c in chars:
        y = round(float(c['y0']), 0)
        y_rows[y].append(c)
    for y in sorted(y_rows.keys(), reverse=True):
        row = sorted(y_rows[y], key=lambda c: float(c['x0']))
        text = ''.join(c['text'] for c in row).strip()
        if text:
            all_rows.append(text)

print(f"Righe totali estratte: {len(all_rows)}")

# ============================================================
# SPLIT INTO TURNO SECTIONS
# ============================================================
# Match turno headers including suffixes like "1191A"
turno_header_re = re.compile(r'Turno\s+Validit[^\s]*\s+[^)]*\)\s*(\d{4,5}[A-Z]?)')
turno_detail_re = re.compile(r'^Turno\s+(\d{4,5}[A-Z]?)$')

current_turno = None
turno_lines = OrderedDict()

for text in all_rows:
    m = turno_header_re.search(text)
    if m:
        current_turno = m.group(1)
        if current_turno not in turno_lines:
            turno_lines[current_turno] = []
        continue
    m = turno_detail_re.match(text)
    if m:
        current_turno = m.group(1)
        if current_turno not in turno_lines:
            turno_lines[current_turno] = []
        continue
    if current_turno and current_turno in turno_lines:
        turno_lines[current_turno].append(text)

print(f"Turni trovati: {len(turno_lines)}")
print(f"Lista: {list(turno_lines.keys())}")

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
