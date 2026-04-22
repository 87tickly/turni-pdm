"""
Arricchimento DB segmenti treni via ARTURO Live + incrocio turno materiale.

Strategia robusta (sostituisce enrich_db_asti_from_arturo.py):

1. SCOPRE treni che toccano una stazione pivot (deposito) via ARTURO:
   cerca_tratta(pivot, dest) per varie destinazioni chiave.

2. Per ogni treno scoperto, chiama ARTURO /treno/{num} per ottenere
   TUTTE le fermate reali (il parser PDF ha solo tratti diretti).

3. INCROCIA col JSON turno_materiale_treni.json su TUTTI i giri per
   trovare a quale (giro, variant) appartiene il treno su quale day_index.
   Inserisce segmenti con material_turn_id e day_index corretti.

4. Idempotente: skip duplicati tramite marker raw_text='ARTURO-enriched'.

Non si fossilizza su 1 giro materiale (es. 1125): esplora il PDF intero.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from src.database.db import Database
from services import arturo_client as ac

# Mapping ARTURO -> nome canonico DB. Aggiungi qui stazioni nuove
# incontrate su ARTURO. Stazioni non mappate vengono ignorate (non
# diventano segmenti) per mantenere coerenza col resto del DB.
STATION_MAP = {
    "MILANO CENTRALE": "MILANO CENTRALE",
    "MILANO CERTOSA": "MI.CERTOSA",
    "MILANO ROGOREDO": "MILANO ROGOREDO",
    "MILANO LAMBRATE": "MI.LAMBRATE",
    "MILANO PORTA GARIBALDI": "MI.P.GARIBALDI",
    "MILANO SAN CRISTOFORO": "MI.S.CRISTOFORO",
    "ALESSANDRIA": "ALESSANDRIA",
    "ASTI": "ASTI",
    "PAVIA": "PAVIA",
    "VOGHERA": "VOGHERA",
    "TORTONA": "TORTONA",
    "NOVI LIGURE": "NOVI LIGURE",
    "TORINO PORTA NUOVA": "TO.P.NUOVA",
    "TORINO PORTA SUSA": "TO.P.SUSA",
    "NOVARA": "NOVARA",
    "GENOVA PIAZZA PRINCIPE": "GENOVA P.PRINCIPE",
    # Linea del Po (Alessandria-Mortara-Vigevano-MI.Rogoredo)
    "VALENZA": "VALENZA",
    "MORTARA": "MORTARA",
    "VIGEVANO": "VIGEVANO",
    "ABBIATEGRASSO": "ABBIATEGRASSO",
    "ALBAIRATE VERMEZZO": "ALBAIRATE",
    "ALBAIRATE": "ALBAIRATE",
    # Linea ALE-Genova
    "ARQUATA SCRIVIA": "ARQUATA SCRIVIA",
    "SERRAVALLE SCRIVIA": "SERRAVALLE SCRIVIA",
    # Linea Milano-Cremona/Mantova
    "CODOGNO": "CODOGNO",
    "CASALPUSTERLENGO": "CASALPUSTERLENGO",
    "LODI": "LODI",
    "CREMONA": "CREMONA",
    "PIACENZA": "PIACENZA",
}


def utc_to_local_hhmm(utc_str: str | None) -> str | None:
    if not utc_str:
        return None
    dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
    return (dt + timedelta(hours=2)).strftime("%H:%M")


def canonical_station(name: str) -> str | None:
    up = (name or "").upper().strip()
    return STATION_MAP.get(up)


def discover_trains(pivot_station: str, destinations: list[str],
                     intermediate_stations: list[str] = None) -> set[str]:
    """Scopre numeri treno che passano dal pivot e/o stazioni della linea.

    cerca_tratta(pivot, destination) + cerca_tratta(intermediate, destination).
    Print progress ogni 20 chiamate.
    """
    quando_list = ["oggi", "oggi_sera"]  # 2 slot orari bastano: 24h coverage
    trains = set()
    pivots = [pivot_station] + list(intermediate_stations or [])
    # Costruisci lista di chiamate uniche (origin, dest, quando)
    calls = []
    seen_pairs = set()
    for origin in pivots:
        for dest in destinations:
            if origin == dest:
                continue
            pair_fwd = (origin, dest)
            pair_rev = (dest, origin)
            for pair in [pair_fwd, pair_rev]:
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                for q in quando_list:
                    calls.append((pair[0], pair[1], q))
    print(f"  pianifico {len(calls)} chiamate cerca_tratta")
    for i, (a, b, q) in enumerate(calls, 1):
        try:
            r = ac.cerca_tratta(a, b, q)
            time.sleep(0.3)
            ris = r.get("risultati", []) if isinstance(r, dict) else []
            new_found = 0
            for item in ris:
                num = str(item.get("numero", "")).strip()
                if num and num not in trains:
                    trains.add(num)
                    new_found += 1
            if i % 25 == 0 or new_found > 0:
                print(f"  [{i}/{len(calls)}] {a}->{b} {q}: +{new_found} nuovi (tot={len(trains)})")
        except Exception as e:
            print(f"  cerca_tratta {a}->{b} {q}: {e}")
    return trains


def expand_nearby_numbers(trains: set[str], delta: int = 2) -> set[str]:
    """Per ogni numero scoperto, aggiunge i numeri +/-1..delta come probing.
    Molti treni hanno andata/ritorno con numeri consecutivi (2351/2352)."""
    expanded = set(trains)
    for n in list(trains):
        try:
            base = int(n)
        except ValueError:
            continue
        for d in range(1, delta + 1):
            expanded.add(str(base + d))
            expanded.add(str(max(0, base - d)))
    return expanded


def fetch_fermate(train_num: str, pivot: str) -> list[dict] | None:
    """Ritorna fermate canoniche del treno, solo se transita per pivot."""
    try:
        t = ac.treno(train_num)
    except Exception as e:
        print(f"  ARTURO /treno/{train_num}: {e}")
        return None
    if not t or not t.get("fermate"):
        return None
    out = []
    for f in t["fermate"]:
        canon = canonical_station(f.get("stazione_nome", ""))
        if not canon:
            continue
        dep = utc_to_local_hhmm(f.get("programmato_partenza"))
        arr = utc_to_local_hhmm(f.get("programmato_arrivo"))
        out.append({
            "station": canon,
            "arr": arr or dep,
            "dep": dep or arr,
            "progressivo": f.get("progressivo", 0),
            "tipo": f.get("tipo_fermata", "F"),
        })
    out.sort(key=lambda x: x["progressivo"])
    # Filtra solo se pivot tra le fermate
    if not any(f["station"] == pivot for f in out):
        return None
    return out


def segments_touching_pivot(fermate: list[dict], pivot: str) -> list[dict]:
    """Genera segmenti consecutivi tra coppie di key stations, almeno un capo = pivot."""
    segs = []
    for i in range(len(fermate)):
        for j in range(i + 1, len(fermate)):
            a = fermate[i]
            b = fermate[j]
            if pivot not in (a["station"], b["station"]):
                continue
            if not a.get("dep") or not b.get("arr"):
                continue
            segs.append({
                "from_station": a["station"],
                "to_station": b["station"],
                "dep_time": a["dep"],
                "arr_time": b["arr"],
            })
    return segs


def find_in_json_turns(train_num: str, turns_json: dict) -> list[tuple]:
    """Cerca train_num in TUTTI i giri del JSON.
    Ritorna lista di (turn_number, day_index, variant_idx, validity)."""
    out = []
    for tn, giro in turns_json.items():
        for v in giro.get("variants", []):
            day_idx = v.get("day_index")
            if day_idx is None:
                continue
            if train_num in v.get("treni", []):
                out.append((tn, day_idx, v.get("variant_index"),
                            v.get("validity", "")))
    return out


def insert_segment(db: Database, tid: str, day_index: int, mat_id: int,
                   seg: dict, confidence: float = 0.85) -> bool:
    cur = db._cursor()
    cur.execute(
        "SELECT 1 FROM train_segment WHERE train_id=? AND day_index=? "
        "AND from_station=? AND to_station=? AND dep_time=? AND arr_time=?",
        (tid, day_index, seg["from_station"], seg["to_station"],
         seg["dep_time"], seg["arr_time"])
    )
    if cur.fetchone():
        return False
    cur.execute(
        "INSERT INTO train_segment "
        "(train_id, from_station, dep_time, to_station, arr_time, "
        " material_turn_id, day_index, seq, confidence, raw_text, "
        " source_page, is_deadhead, is_accessory, segment_kind) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, 'ARTURO-enriched', 0, 0, 0, 'train')",
        (tid, seg["from_station"], seg["dep_time"], seg["to_station"],
         seg["arr_time"], mat_id, day_index, confidence)
    )
    db.conn.commit()
    return True


def lookup_turn_id(db: Database, turn_number: str) -> int | None:
    cur = db._cursor()
    cur.execute("SELECT id FROM material_turn WHERE turn_number=?", (turn_number,))
    r = cur.fetchone()
    if not r:
        return None
    return r[0] if not hasattr(r, "keys") else r["id"]


def find_db_tid(db: Database, train_num: str, day_index: int,
                material_turn_id: int) -> str | None:
    """Trova il train_id nel DB (formato '2351' o '2351/2352') che corrisponde
    a train_num per quel day_index + material_turn_id."""
    cur = db._cursor()
    cur.execute(
        "SELECT DISTINCT train_id FROM train_segment "
        "WHERE material_turn_id=? AND day_index=? "
        "AND (train_id=? OR train_id LIKE ? OR train_id LIKE ? OR train_id LIKE ?)",
        (material_turn_id, day_index, train_num,
         f"{train_num}/%", f"%/{train_num}", f"%/{train_num}/%")
    )
    r = cur.fetchone()
    if not r:
        return None
    return r[0] if not hasattr(r, "keys") else r["train_id"]


# Cache persistente ARTURO per evitare re-chiamate
CACHE_PATH = Path(__file__).parent / "arturo_cache.json"


def load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text())
        except Exception:
            return {}
    return {}


def save_cache(cache: dict):
    CACHE_PATH.write_text(json.dumps(cache, indent=2, ensure_ascii=False))


def enrich_deposit(pivot_canonical: str, pivot_arturo: str,
                   destinations: list[str],
                   intermediate_stations: list[str] = None,
                   expand_delta: int = 4,
                   turns_json_path: str = "turno_materiale_treni.json"):
    """Arricchisce DB per un deposito (pivot), scoprendo tutti i treni via
    ARTURO e incrociandoli su TUTTI i giri del JSON per trovare day_index.

    intermediate_stations: stazioni sulla linea del pivot. Amplia la
      scoperta a treni che non menzionano ALE nel manifest ma lo
      attraversano fisicamente.
    expand_delta: per ogni numero scoperto, probe anche +/-delta numeri
      consecutivi (spesso andate-ritorni della stessa linea).
    """
    db = Database()
    with open(turns_json_path) as f:
        data = json.load(f)
    turns_json = data["turni"]

    cache = load_cache()

    print(f"\n=== ENRICHMENT per pivot={pivot_canonical} ({pivot_arturo}) ===")
    # Step 1: Scopri treni via ARTURO
    print(f"\nStep 1: cerca_tratta su {pivot_arturo} + intermediate...")
    discovered = discover_trains(pivot_arturo, destinations, intermediate_stations)
    print(f"  {len(discovered)} numeri treno scoperti")
    if expand_delta > 0:
        discovered = expand_nearby_numbers(discovered, delta=expand_delta)
        print(f"  espanso con +/-{expand_delta}: {len(discovered)} numeri candidati")

    # Step 2: fetch fermate per ogni treno (con cache)
    print(f"\nStep 2: fetch fermate ARTURO (cache: {len(cache)} entries)")
    trains_with_pivot = {}  # num -> fermate canoniche
    new_calls = 0
    total = len(discovered)
    for i, num in enumerate(sorted(discovered), 1):
        if num in cache:
            ferm = cache[num]
        else:
            ferm_raw = fetch_fermate(num, pivot_canonical)
            cache[num] = ferm_raw
            new_calls += 1
            time.sleep(0.3)
            ferm = ferm_raw
            if new_calls % 50 == 0:
                print(f"  [{i}/{total}] chiamate ARTURO: {new_calls}, trovate con pivot: {len(trains_with_pivot)}")
                save_cache(cache)
        if ferm:
            trains_with_pivot[num] = ferm
    save_cache(cache)
    print(f"  {new_calls} nuove chiamate. {len(trains_with_pivot)} treni con fermata a {pivot_canonical}")

    # Step 3: incrocia col JSON turno materiale
    print(f"\nStep 3: incrocio con {len(turns_json)} giri del JSON...")
    added_total = 0
    crossed_total = 0
    for num, fermate in trains_with_pivot.items():
        occurrences = find_in_json_turns(num, turns_json)
        if not occurrences:
            continue
        crossed_total += 1
        # Dedup: 1 insert per (turn_number, day_index) anche se il treno appare in + variants
        seen_keys = set()
        for (turn_number, day_index, variant_idx, validity) in occurrences:
            key = (turn_number, day_index)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            mat_id = lookup_turn_id(db, turn_number)
            if mat_id is None:
                continue
            # Trova il train_id esatto nel DB
            tid = find_db_tid(db, num, day_index, mat_id)
            if not tid:
                # Il treno non ha segmenti in DB per questo (giro, day) — skip
                # Potremmo inserire con tid=num da solo (senza slash), ma rischia
                # duplicati col parser PDF futuro. Skip per sicurezza.
                continue
            segs = segments_touching_pivot(fermate, pivot_canonical)
            for seg in segs:
                if insert_segment(db, tid, day_index, mat_id, seg):
                    added_total += 1

    print(f"\n=== RISULTATO ===")
    print(f"  Treni incrociati in JSON: {crossed_total}")
    print(f"  Segmenti aggiunti: {added_total}")


def delete_direct_if_split_exists(db: Database, pivot: str) -> int:
    """Rimuove segmenti 'diretti' sostituiti dagli split ARTURO.
    Un segmento e' 'diretto' se lo stesso (tid, day) ha anche un enriched
    che lo spezza (es. MI-ASTI + MI-ALE + ALE-ASTI -> rimuovi il MI-ASTI)."""
    cur = db._cursor()
    cur.execute(
        "SELECT DISTINCT train_id, day_index FROM train_segment "
        "WHERE raw_text='ARTURO-enriched'"
    )
    enriched_keys = [(r[0] if not hasattr(r, "keys") else r["train_id"],
                      r[1] if not hasattr(r, "keys") else r["day_index"])
                     for r in cur.fetchall()]
    deleted = 0
    for tid, day in enriched_keys:
        # Per ogni coppia (from, to) ARTURO-enriched, rimuovi i NON enriched
        # che "contengono" l'enriched negli stessi orari larghi.
        # Strategia semplice: se esistono >=2 enriched per stesso tid/day e pivot
        # coinvolto, il segmento "diretto lungo" originale NON enriched va rimosso.
        cur.execute(
            "SELECT from_station, to_station, dep_time, arr_time FROM train_segment "
            "WHERE train_id=? AND day_index=? AND raw_text='ARTURO-enriched'",
            (tid, day)
        )
        enriched_segs = cur.fetchall()
        if len(enriched_segs) < 2:
            continue
        # Stazioni coperte dagli enriched
        stations = set()
        for r in enriched_segs:
            d = dict(r) if hasattr(r, "keys") else {
                "from_station": r[0], "to_station": r[1]}
            stations.add(d["from_station"])
            stations.add(d["to_station"])
        if pivot not in stations:
            continue
        # Trova candidati "diretti" non-enriched che collegano 2 stazioni nella union
        cur.execute(
            "SELECT id, from_station, to_station FROM train_segment "
            "WHERE train_id=? AND day_index=? "
            "AND (raw_text IS NULL OR raw_text != 'ARTURO-enriched')",
            (tid, day)
        )
        for r in cur.fetchall():
            d = dict(r) if hasattr(r, "keys") else {
                "id": r[0], "from_station": r[1], "to_station": r[2]}
            if (d["from_station"] in stations and d["to_station"] in stations
                and pivot not in (d["from_station"], d["to_station"])):
                # Segmento diretto "scavalcante" il pivot -> rimuovi
                cur.execute("DELETE FROM train_segment WHERE id=?", (d["id"],))
                deleted += 1
    db.conn.commit()
    return deleted


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(line_buffering=True)
    # ALESSANDRIA
    enrich_deposit(
        pivot_canonical="ALESSANDRIA",
        pivot_arturo="ALESSANDRIA",
        destinations=[
            # Linea principale
            "MILANO CENTRALE", "MILANO ROGOREDO", "MI.CERTOSA",
            "PAVIA", "ASTI",
            # Torino
            "TORINO PORTA NUOVA", "TORINO PORTA SUSA", "NOVARA",
            # Genova
            "GENOVA PIAZZA PRINCIPE", "NOVI LIGURE",
            # Linea direttissima
            "TORTONA", "VOGHERA",
            # Linea del Po (ALE-Mortara-Vigevano-MI)
            "MORTARA", "VIGEVANO", "VALENZA", "ABBIATEGRASSO",
        ],
        intermediate_stations=[
            "VOGHERA", "TORTONA", "NOVI LIGURE", "PAVIA", "ASTI",
            "MORTARA", "VIGEVANO",
        ],
        expand_delta=4,
    )

    db = Database()
    deleted = delete_direct_if_split_exists(db, "ALESSANDRIA")
    print(f"\nSegmenti 'diretti' (scavalcanti ALE) rimossi: {deleted}")
