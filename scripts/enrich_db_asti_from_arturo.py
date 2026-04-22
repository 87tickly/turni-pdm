"""
Arricchisce il DB con segmenti ALE<->* derivati da ARTURO Live per i
treni IC che fermano a Alessandria (es. MI.CENTRALE-ASTI che passa ALE).

Il parser PDF turno materiale estrae solo i tratti diretti (MI-ASTI come
singolo segmento); ARTURO conosce le fermate intermedie. Questo script
interroga ARTURO per ogni treno ASTI nel DB, estrae le fermate e inserisce
segmenti aggiuntivi che collegano ALE ad altre stazioni chiave.

One-shot: eseguire manualmente dopo ogni re-import materiale che
tocca i treni 2xxx ASTI. Idempotente (skip duplicati).
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta

from src.database.db import Database
from services import arturo_client as ac

# Stazioni ARTURO -> nome canonico DB
STATION_MAP = {
    "MILANO CENTRALE": "MILANO CENTRALE",
    "MILANO CERTOSA": "MI.CERTOSA",
    "MILANO ROGOREDO": "MILANO ROGOREDO",
    "MILANO LAMBRATE": "MI.LAMBRATE",
    "ALESSANDRIA": "ALESSANDRIA",
    "ASTI": "ASTI",
    "PAVIA": "PAVIA",
    "VOGHERA": "VOGHERA",
    "TORTONA": "TORTONA",
}

# Stazioni significative: aggiungiamo segmenti SOLO tra queste
# (evita esplosione: N fermate = N*(N-1)/2 segmenti; limitiamo a pairs utili)
KEY_STATIONS = {"MILANO CENTRALE", "MI.CERTOSA", "MILANO ROGOREDO",
                "ALESSANDRIA", "ASTI"}


def utc_to_local_hhmm(utc_str: str | None) -> str | None:
    if not utc_str:
        return None
    dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
    return (dt + timedelta(hours=2)).strftime("%H:%M")


def canonical_station(name: str) -> str | None:
    up = (name or "").upper().strip()
    return STATION_MAP.get(up)


def fetch_fermate(train_num: str) -> list[dict] | None:
    try:
        t = ac.treno(train_num)
    except Exception as e:
        print(f"  ARTURO err {train_num}: {e}")
        return None
    if not t or not t.get("fermate"):
        return None
    out = []
    for f in t["fermate"]:
        canon = canonical_station(f.get("stazione_nome", ""))
        if not canon or canon not in KEY_STATIONS:
            continue
        dep = utc_to_local_hhmm(f.get("programmato_partenza"))
        arr = utc_to_local_hhmm(f.get("programmato_arrivo"))
        # Prima fermata (tipo P): solo dep. Ultima (A): solo arr. Intermedie (F): entrambi.
        out.append({
            "station": canon,
            "arr": arr or dep,
            "dep": dep or arr,
            "progressivo": f.get("progressivo", 0),
            "tipo": f.get("tipo_fermata", "F"),
        })
    out.sort(key=lambda x: x["progressivo"])
    return out


def segments_from_fermate(fermate: list[dict]) -> list[dict]:
    """Genera segmenti consecutivi tra KEY_STATIONS della stessa tratta."""
    segs = []
    for i in range(len(fermate)):
        for j in range(i + 1, len(fermate)):
            a = fermate[i]
            b = fermate[j]
            if not a.get("dep") or not b.get("arr"):
                continue
            segs.append({
                "from_station": a["station"],
                "to_station": b["station"],
                "dep_time": a["dep"],
                "arr_time": b["arr"],
            })
    return segs


def insert_segment(db: Database, tid: str, day_index: int, mat_id: int,
                   seg: dict, confidence: float = 0.85) -> bool:
    cur = db._cursor()
    # Skip se gia' presente (stesso tid/day/from/to/dep/arr)
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


def delete_direct_if_split_exists(db: Database) -> int:
    """
    Per ogni tid con segmenti split ARTURO-enriched, rimuove il segmento
    "diretto" originale (MI.CENTRALE->ASTI lunga tratta) per evitare
    doppioni temporali che confondono la DFS del builder.
    """
    cur = db._cursor()
    cur.execute("""
        SELECT DISTINCT train_id, day_index
        FROM train_segment
        WHERE raw_text='ARTURO-enriched'
    """)
    enriched = [(r[0] if not hasattr(r, "keys") else r["train_id"],
                 r[1] if not hasattr(r, "keys") else r["day_index"])
                for r in cur.fetchall()]
    deleted = 0
    for tid, day in enriched:
        # Rimuovi tutti i segmenti NON enriched per questo tid+day che
        # toccano ASTI (sono i "diretti" originali)
        cur.execute("""
            DELETE FROM train_segment
            WHERE train_id=? AND day_index=?
              AND (UPPER(from_station)='ASTI' OR UPPER(to_station)='ASTI')
              AND (raw_text IS NULL OR raw_text != 'ARTURO-enriched')
        """, (tid, day))
        deleted += cur.rowcount
    db.conn.commit()
    return deleted


def main():
    db = Database()
    cur = db._cursor()
    # Elenco (train_id, day_index, material_turn_id) dei segmenti ASTI esistenti
    cur.execute("""
        SELECT DISTINCT train_id, day_index, material_turn_id
        FROM train_segment
        WHERE UPPER(from_station)='ASTI' OR UPPER(to_station)='ASTI'
        ORDER BY train_id, day_index
    """)
    rows = [dict(r) if hasattr(r, "keys") else
            {"train_id": r[0], "day_index": r[1], "material_turn_id": r[2]}
            for r in cur.fetchall()]
    print(f"Trovati {len(rows)} (tid, day_index) distinti con ASTI")

    # Cache fermate per train_num base
    fermate_cache: dict[str, list[dict] | None] = {}
    added_total = 0
    for row in rows:
        tid = row["train_id"]
        day_index = row["day_index"]
        mat_id = row["material_turn_id"]
        # numero base (prima dello slash)
        base = tid.split("/")[0]
        if base not in fermate_cache:
            print(f"ARTURO query {base}...")
            fermate_cache[base] = fetch_fermate(base)
            time.sleep(0.3)  # rate limit soft
        fermate = fermate_cache.get(base)
        if not fermate:
            print(f"  {tid} day={day_index}: ARTURO no data, skip")
            continue
        # Verifica che ALE sia tra le fermate
        has_ale = any(f["station"] == "ALESSANDRIA" for f in fermate)
        if not has_ale:
            print(f"  {tid} day={day_index}: no ALE stop, skip")
            continue
        segs = segments_from_fermate(fermate)
        # Inserisci solo segmenti che NON sono duplicati del "tratto diretto"
        # originale. Criterio: almeno uno dei capi e' ALE.
        added_this = 0
        for seg in segs:
            if "ALESSANDRIA" not in (seg["from_station"], seg["to_station"]):
                continue
            if insert_segment(db, tid, day_index, mat_id, seg):
                added_this += 1
        print(f"  {tid} day={day_index}: +{added_this} segmenti")
        added_total += added_this

    print(f"\nTotale segmenti aggiunti: {added_total}")

    # Pulizia doppioni: rimuovi segmenti "diretti" MI-ASTI originali
    # quando esistono gli split ARTURO-enriched.
    deleted = delete_direct_if_split_exists(db)
    print(f"Segmenti diretti rimossi (rimpiazzati da split): {deleted}")


if __name__ == "__main__":
    main()
