#!/usr/bin/env python3
"""
Import turno materiale data with VARIANT support.
Cross-references new PDF train numbers with existing DB time/station data.

Strategy:
1. Delete old material_turn, train_segment, day_variant data
2. Create new material_turn entries from the new PDF (54 turni)
3. For each VARIANT within each turno:
   - Insert day_variant record with validity text
   - For each train in the variant:
     * If time/station data exists in old DB → use it
     * If not → create segment with train_id only (times/stations TBD)
   - All segments get day_index = variant_index (unique per turno)
4. Add deadhead (vuote) segments with is_deadhead=1
"""

import sqlite3
import json
import shutil
from datetime import datetime

DB_PATH = 'C:/Users/studio54/Desktop/COLAZIONE/turni.db'
JSON_PATH = 'C:/Users/studio54/Desktop/COLAZIONE/turno_materiale_treni.json'
BACKUP_PATH = f'C:/Users/studio54/Desktop/COLAZIONE/turni_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'

# ============================================================
# BACKUP
# ============================================================
print(f"Backup DB → {BACKUP_PATH}")
shutil.copy2(DB_PATH, BACKUP_PATH)

# ============================================================
# LOAD NEW DATA
# ============================================================
with open(JSON_PATH, 'r', encoding='utf-8') as f:
    new_data = json.load(f)

print(f"Turni nel nuovo PDF: {len(new_data['turni'])}")
total_variants = sum(len(t.get('variants', [])) for t in new_data['turni'].values())
print(f"Varianti totali: {total_variants}")

# ============================================================
# READ OLD DB - extract time/station data per train
# ============================================================
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Get all existing train segments with their details
cur.execute('''
    SELECT DISTINCT ts.train_id, ts.from_station, ts.dep_time,
           ts.to_station, ts.arr_time, ts.is_deadhead,
           ts.seq, ts.confidence, ts.raw_text, ts.source_page
    FROM train_segment ts
''')
old_segments = cur.fetchall()

# Build map: train_id -> segment details (best available, deduplicated)
train_time_data = {}
for row in old_segments:
    tid = row[0]
    seg = {
        'from_station': row[1],
        'dep_time': row[2],
        'to_station': row[3],
        'arr_time': row[4],
        'is_deadhead': row[5],
        'seq': row[6],
        'confidence': row[7],
        'raw_text': row[8],
        'source_page': row[9],
    }
    if tid not in train_time_data:
        train_time_data[tid] = []
    # Avoid exact duplicates
    key = (seg['from_station'], seg['dep_time'], seg['to_station'], seg['arr_time'])
    existing_keys = [(s['from_station'], s['dep_time'], s['to_station'], s['arr_time'])
                     for s in train_time_data[tid]]
    if key not in existing_keys:
        train_time_data[tid].append(seg)

print(f"Treni con dati orario nel vecchio DB: {len(train_time_data)}")

# ============================================================
# CLEAR OLD DATA
# ============================================================
print("\nPulizia vecchi dati...")
cur.execute('DELETE FROM day_variant')
cur.execute('DELETE FROM train_segment')
cur.execute('DELETE FROM material_turn')
cur.execute('DELETE FROM sqlite_sequence WHERE name IN ("material_turn", "train_segment", "day_variant")')
conn.commit()
print("  Tabelle pulite: material_turn, train_segment, day_variant")

# ============================================================
# INSERT NEW TURNI, VARIANTS, AND SEGMENTS
# ============================================================
source_file = new_data['source_pdf'].split('/')[-1]
stats = {
    'turni': 0,
    'variants': 0,
    'segments_with_times': 0,
    'segments_without_times': 0,
    'deadhead_with_times': 0,
    'deadhead_without_times': 0,
}


def insert_train_segments(train_ids, mt_id, variant_idx, seq_start, is_deadhead):
    """Insert train segments for a list of train IDs, cross-referencing old data."""
    seq = seq_start
    for tid in train_ids:
        if tid in train_time_data:
            # Use first available segment data (best match)
            seg = train_time_data[tid][0]
            cur.execute('''INSERT INTO train_segment
                (train_id, from_station, dep_time, to_station, arr_time,
                 material_turn_id, day_index, seq, confidence, raw_text,
                 source_page, is_deadhead)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (tid, seg['from_station'], seg['dep_time'],
                 seg['to_station'], seg['arr_time'],
                 mt_id, variant_idx, seq, seg['confidence'],
                 seg['raw_text'], seg['source_page'], 1 if is_deadhead else 0))
            seq += 1
            if is_deadhead:
                stats['deadhead_with_times'] += 1
            else:
                stats['segments_with_times'] += 1
        else:
            # No time data available - insert placeholder
            cur.execute('''INSERT INTO train_segment
                (train_id, from_station, dep_time, to_station, arr_time,
                 material_turn_id, day_index, seq, confidence, raw_text,
                 source_page, is_deadhead)
                VALUES (?, '', '', '', '', ?, ?, ?, 0.0, 'from_turno_materiale_pdf', 0, ?)''',
                (tid, mt_id, variant_idx, seq, 1 if is_deadhead else 0))
            seq += 1
            if is_deadhead:
                stats['deadhead_without_times'] += 1
            else:
                stats['segments_without_times'] += 1
    return seq


for tnum in sorted(new_data['turni'].keys(), key=lambda x: (x.rstrip('ABCDEFGHI'), x)):
    tdata = new_data['turni'][tnum]
    variants = tdata.get('variants', [])

    # Total segments = sum of all variant trains
    total_segs = sum(len(v['treni']) + len(v['vuote']) for v in variants)

    # Insert material_turn
    cur.execute('''INSERT INTO material_turn (turn_number, source_file, total_segments)
                   VALUES (?, ?, ?)''', (tnum, source_file, total_segs))
    mt_id = cur.lastrowid
    stats['turni'] += 1

    if variants:
        # New variant-aware import
        for var in variants:
            vi = var['variant_index']
            validity = var.get('validity', '') or 'GG'

            # Insert day_variant record
            cur.execute('''INSERT OR REPLACE INTO day_variant
                (day_index, material_turn_id, validity_text)
                VALUES (?, ?, ?)''',
                (vi, mt_id, validity.upper()))
            stats['variants'] += 1

            # Insert train segments for this variant
            seq = 0
            seq = insert_train_segments(var['treni'], mt_id, vi, seq, False)
            insert_train_segments(var['vuote'], mt_id, vi, seq, True)
    else:
        # Fallback: no variants, use flat train lists (backward compat)
        cur.execute('''INSERT OR REPLACE INTO day_variant
            (day_index, material_turn_id, validity_text)
            VALUES (?, ?, ?)''',
            (0, mt_id, 'GG'))
        stats['variants'] += 1
        seq = 0
        seq = insert_train_segments(tdata['treni'], mt_id, 0, seq, False)
        insert_train_segments(tdata['vuote'], mt_id, 0, seq, True)

conn.commit()

# ============================================================
# VERIFY
# ============================================================
cur.execute('SELECT COUNT(*) FROM material_turn')
mt_count = cur.fetchone()[0]
cur.execute('SELECT COUNT(*) FROM train_segment')
ts_count = cur.fetchone()[0]
cur.execute('SELECT COUNT(*) FROM train_segment WHERE is_deadhead = 1')
dh_count = cur.fetchone()[0]
cur.execute('SELECT COUNT(*) FROM train_segment WHERE dep_time != ""')
with_times = cur.fetchone()[0]
cur.execute('SELECT COUNT(*) FROM train_segment WHERE dep_time = ""')
without_times = cur.fetchone()[0]
cur.execute('SELECT COUNT(*) FROM day_variant')
dv_count = cur.fetchone()[0]

# Check no duplicates
cur.execute('SELECT turn_number, COUNT(*) FROM material_turn GROUP BY turn_number HAVING COUNT(*) > 1')
dups = cur.fetchall()

print(f"\n{'='*60}")
print(f"IMPORTAZIONE COMPLETATA")
print(f"{'='*60}")
print(f"Turni materiale: {mt_count} (nessun duplicato)" if not dups else f"ATTENZIONE: {len(dups)} duplicati!")
print(f"Varianti (day_variant): {dv_count}")
print(f"Segmenti totali: {ts_count}")
print(f"  Con orari/stazioni: {with_times}")
print(f"  Senza orari (da completare): {without_times}")
print(f"  Di cui deadhead (vuote): {dh_count}")
print(f"\nDettaglio:")
print(f"  Treni regolari con orari: {stats['segments_with_times']}")
print(f"  Treni regolari senza orari: {stats['segments_without_times']}")
print(f"  Vuote con orari: {stats['deadhead_with_times']}")
print(f"  Vuote senza orari: {stats['deadhead_without_times']}")

# Sample: show variants for turno 1101
cur.execute('''
    SELECT dv.day_index, dv.validity_text, COUNT(ts.id) as seg_count
    FROM day_variant dv
    JOIN material_turn mt ON dv.material_turn_id = mt.id
    LEFT JOIN train_segment ts ON ts.material_turn_id = mt.id AND ts.day_index = dv.day_index
    WHERE mt.turn_number = '1101'
    GROUP BY dv.day_index, dv.validity_text
    ORDER BY dv.day_index
''')
print(f"\nSample: Turno 1101 varianti:")
for row in cur.fetchall():
    print(f"  Variante {row[0]}: {row[1]} ({row[2]} segmenti)")

print(f"\nBackup: {BACKUP_PATH}")

conn.close()
