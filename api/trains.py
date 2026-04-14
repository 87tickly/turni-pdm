"""
Router query treni, stazioni, connessioni, rientri, giro materiale.
"""

from fastapi import APIRouter, HTTPException, Query

from api.deps import get_db

router = APIRouter()


@router.get("/train/{train_id}")
def query_train(train_id: str):
    db = get_db()
    try:
        results = db.query_train(train_id)
        if not results:
            raise HTTPException(404, f"Treno {train_id} non trovato")
        return {"train_id": train_id, "segments": results}
    finally:
        db.close()


@router.get("/giro-materiale/{train_id}")
def giro_materiale(train_id: str):
    """Restituisce il ciclo materiale completo a cui appartiene il treno."""
    db = get_db()
    try:
        result = db.get_material_cycle(train_id)
        if not result["cycle"]:
            raise HTTPException(404, f"Treno {train_id} non trovato nel giro materiale")
        return result
    finally:
        db.close()


@router.get("/material-info/{train_id}")
def material_info(train_id: str):
    """Returns material turn number and giro materiale for a train."""
    db = get_db()
    try:
        mt = db.get_material_turn_info(train_id)
        cycle = db.get_material_cycle(train_id)
        return {
            "train_id": train_id,
            "material_turn": mt,
            "turn_number": mt["turn_number"] if mt else None,
            "cycle_trains": cycle.get("cycle_trains", []),
            "cycle": cycle.get("cycle", []),
            "total_segments": cycle.get("total_segments", 0),
            "validity": cycle.get("validity", ""),
            "variants": cycle.get("variants", []),
            "all_variants": cycle.get("all_variants", []),
        }
    finally:
        db.close()


@router.get("/giro-chain/{train_id}")
def giro_chain(train_id: str):
    """Returns the position of a train in its giro materiale chain."""
    db = get_db()
    try:
        return db.get_giro_chain_context(train_id)
    finally:
        db.close()


@router.get("/station/{station_name}")
def query_station(station_name: str):
    db = get_db()
    try:
        departures = db.query_station_departures(station_name)
        arrivals = db.query_station_arrivals(station_name)
        if not departures and not arrivals:
            raise HTTPException(404, f"Stazione '{station_name}' non trovata")
        return {
            "station": station_name.upper(),
            "departures": departures,
            "arrivals": arrivals,
        }
    finally:
        db.close()


@router.get("/trains")
def list_trains():
    db = get_db()
    try:
        all_segs = db.get_all_segments()
        trains = {}
        for s in all_segs:
            tid = s["train_id"]
            if tid not in trains:
                trains[tid] = []
            trains[tid].append(s)
        return {"count": len(trains), "trains": trains}
    finally:
        db.close()


@router.get("/stations")
def list_stations():
    db = get_db()
    try:
        all_segs = db.get_all_segments()
        stations = set()
        for s in all_segs:
            stations.add(s["from_station"].upper())
            stations.add(s["to_station"].upper())
        return {"stations": sorted(stations), "count": len(stations)}
    finally:
        db.close()


@router.get("/connections")
def get_connections(
    from_station: str,
    after_time: str = "00:00",
    to_station: str = None,
    day_type: str = None,
    exclude: str = None,
):
    db = get_db()
    try:
        day_indices = None
        if day_type:
            day_indices = db.get_day_indices_for_validity(day_type)

        exclude_list = None
        if exclude:
            exclude_list = [t.strip() for t in exclude.split(",") if t.strip()]

        results = db.find_connecting_trains(
            from_station=from_station,
            after_time=after_time,
            to_station=to_station,
            day_indices=day_indices,
            exclude_trains=exclude_list,
            limit=15,
        )

        # Arricchisci ogni risultato con info giro materiale compatta
        for r in results:
            try:
                gctx = db.get_giro_chain_context(r["train_id"])
                if gctx and gctx.get("next"):
                    n = gctx["next"]
                    r["giro_next"] = f"{n['train_id']} {n.get('from_station','')}\u2192{n.get('to_station','')} {n.get('dep_time','')}"
                else:
                    r["giro_next"] = None
                r["giro_turn"] = gctx.get("turn_number") if gctx else None
            except Exception:
                r["giro_next"] = None
                r["giro_turn"] = None

        return {"connections": results, "count": len(results)}
    finally:
        db.close()


@router.get("/return-trains")
def find_return(from_station: str, to_station: str, after_time: str = "00:00",
                current_train: str = None):
    """Find trains to return to depot. If current_train is given,
    checks giro materiale FIRST for a return via the material cycle."""
    db = get_db()
    try:
        giro_return = None
        giro_chain_info = None

        # STEP 1: Check giro materiale se abbiamo il treno corrente
        if current_train:
            try:
                giro_ctx = db.get_giro_chain_context(current_train)
                if giro_ctx and giro_ctx.get("chain"):
                    pos = giro_ctx.get("position", -1)
                    chain = giro_ctx["chain"]
                    giro_chain_info = {
                        "turn_number": giro_ctx.get("turn_number"),
                        "chain": chain,
                        "position": pos,
                        "total": giro_ctx.get("total", 0),
                    }
                    # Cerca treno nel giro che riporta al deposito
                    for ci in range(pos + 1, len(chain)):
                        c = chain[ci]
                        c_from = (c.get("from") or "").upper()
                        c_to = (c.get("to") or "").upper()
                        if c_from == from_station.upper() and c_to == to_station.upper():
                            if c.get("dep", "") >= after_time:
                                giro_return = {
                                    "train_id": c["train_id"],
                                    "from_station": c.get("from", ""),
                                    "to_station": c.get("to", ""),
                                    "dep_time": c.get("dep", ""),
                                    "arr_time": c.get("arr", ""),
                                    "is_deadhead": c.get("is_deadhead", False),
                                    "via_giro": True,
                                }
                                break
            except Exception as e:
                print(f"[WARN] Giro materiale check for return: {e}")

        # STEP 2: Cerca nel DB
        results = db.find_return_trains(from_station, to_station, after_time)

        return {
            "return_trains": results,
            "giro_return": giro_return,
            "giro_chain": giro_chain_info,
            "count": len(results),
        }
    finally:
        db.close()


@router.get("/fr-return-trains")
def fr_return_trains(
    from_station: str,
    to_station: str,
    current_day_type: str = "LV",
):
    """Trova treni per il rientro al deposito il giorno successivo a una dormita FR."""
    from src.constants import FR_NEXT_DAY_MAP, VALIDITY_MAP
    db = get_db()
    try:
        next_day_types = FR_NEXT_DAY_MAP.get(current_day_type.upper(), ["LV"])
        all_results = []
        seen_trains = set()

        for ndt in next_day_types:
            day_indices = db.get_day_indices_for_validity(ndt)
            trains = db.find_connecting_trains(
                from_station=from_station,
                after_time="04:00",
                to_station=to_station,
                day_indices=day_indices,
                limit=20,
            )
            for t in trains:
                if t["train_id"] not in seen_trains:
                    t["next_day_type"] = ndt
                    all_results.append(t)
                    seen_trains.add(t["train_id"])

        # Also search without day_index filter as fallback
        fallback = db.find_return_trains(from_station, to_station, "04:00", limit=50)
        for t in fallback:
            if t["train_id"] not in seen_trains:
                t["next_day_type"] = "GG"
                all_results.append(t)
                seen_trains.add(t["train_id"])

        all_results.sort(key=lambda x: x.get("dep_time", "99:99"))

        # Cerca TUTTI i treni che passano dalla stazione (taglio treno)
        all_departures = db.find_trains_passing_through(
            station=from_station,
            after_time="04:00",
            limit=80,
        )

        # Anche i diretti al deposito con passing through
        passing_to_depot = db.find_trains_passing_through(
            station=from_station,
            after_time="04:00",
            target_station=to_station,
            limit=30,
        )
        # Merge passing_to_depot in all_results
        seen_direct = set(t["train_id"] for t in all_results)
        for t in passing_to_depot:
            if t["train_id"] not in seen_direct:
                t["next_day_type"] = "GG"
                t["passes_through"] = True
                all_results.append(t)
                seen_direct.add(t["train_id"])
        all_results.sort(key=lambda x: x.get("dep_time", "99:99"))

        return {
            "direct_to_depot": all_results[:50],
            "all_departures": all_departures[:80],
            "from_station": from_station,
            "to_station": to_station,
            "current_day_type": current_day_type,
            "next_day_types": next_day_types,
            "count_direct": len(all_results),
            "count_all": len(all_departures),
        }
    finally:
        db.close()


@router.get("/giro-next-day-trains")
def giro_next_day_trains(station: str, current_day_type: str = "LV"):
    """Trova giro materiale che iniziano dalla stazione dormita per il giorno dopo."""
    from src.constants import FR_NEXT_DAY_MAP
    db = get_db()
    try:
        next_day_types = FR_NEXT_DAY_MAP.get(current_day_type.upper(), ["LV"])
        all_giro = []
        seen_turns = set()

        for ndt in next_day_types:
            day_indices = db.get_day_indices_for_validity(ndt)
            giros = db.find_giro_starts_from_station(station, day_indices=day_indices, limit=10)
            for g in giros:
                key = (g["turn_number"], g["day_index"])
                if key not in seen_turns:
                    g["next_day_type"] = ndt
                    all_giro.append(g)
                    seen_turns.add(key)

        # Sort by first train dep_time
        all_giro.sort(key=lambda g: g.get("first_train", {}).get("dep", "99:99"))

        return {
            "giro_chains": all_giro[:15],
            "station": station,
            "current_day_type": current_day_type,
            "next_day_types": next_day_types,
            "count": len(all_giro),
        }
    finally:
        db.close()


@router.get("/day-index-groups")
def day_index_groups():
    """Returns day_index groups inferred as LV/SAB/DOM."""
    db = get_db()
    try:
        return db.get_day_index_groups()
    finally:
        db.close()


@router.get("/day-variants")
def get_day_variants():
    db = get_db()
    try:
        return {"variants": db.get_day_variants()}
    finally:
        db.close()
