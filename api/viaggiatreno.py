"""
Router dati treni real-time via ARTURO Live (live.arturo.travel).
Sostituisce il vecchio proxy ViaggiaTreno diretto con API normalizzate.

Mantiene gli stessi URL /vt/* per retrocompatibilità col frontend legacy.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from services.arturo_client import (
    cerca_stazione, partenze, arrivi, treno,
    cerca_tratta, resolve_station_id, fermata_to_times,
)
from src.validator.rules import _time_to_min

router = APIRouter()

# Mapping depositi interni → nomi stazione reali
_DEPOSITO_TO_STATION = {
    "GARIBALDI_ALE": "MILANO PORTA GARIBALDI",
    "GARIBALDI_CADETTI": "MILANO PORTA GARIBALDI",
    "GARIBALDI_TE": "MILANO PORTA GARIBALDI",
    "GRECO_TE": "MILANO GRECO PIRELLI",
    "GRECO_S9": "MILANO GRECO PIRELLI",
    "FIORENZA": "MILANO CADORNA",
    "COMO": "COMO SAN GIOVANNI",
}


def _resolve_deposito(name: str) -> str:
    """Mappa nome deposito interno a nome stazione reale."""
    return _DEPOSITO_TO_STATION.get(name.strip().upper(), name)


# ── Endpoints ───────────────────────────────────────────────────

@router.get("/vt/autocomplete-station")
def vt_autocomplete_station(q: str):
    """Autocomplete stazione via ARTURO Live."""
    try:
        results = cerca_stazione(q)
        return {
            "stations": [
                {"name": r["nome"], "code": r["id"]}
                for r in results
            ]
        }
    except Exception as e:
        raise HTTPException(502, detail=f"ARTURO Live non raggiungibile: {e}")


@router.get("/vt/departures")
def vt_departures(
    station_code: str,
    date: str | None = None,
    time: str | None = None,
    only_trenord: bool = True,
):
    """Partenze da una stazione via ARTURO Live."""
    try:
        data = partenze(station_code)
    except Exception as e:
        raise HTTPException(502, detail=f"ARTURO Live errore: {e}")

    results = []
    for t in data:
        if only_trenord and t.get("operatore", "").upper() != "TRENORD":
            continue
        fermate = t.get("fermate", [])
        dep_time = ""
        if fermate:
            prog = fermate[0].get("programmato_partenza", "")
            if prog:
                dep_time = prog[11:16]  # "HH:MM"

        results.append({
            "train_number": t.get("numero"),
            "category": t.get("categoria", ""),
            "origin": t.get("codice_origine"),
            "destination": t.get("destinazione"),
            "dep_time": dep_time,
            "delay": t.get("ritardo_corrente_min", 0),
            "platform_scheduled": fermate[0].get("binario_programmato_partenza") if fermate else None,
            "platform_actual": fermate[0].get("binario_effettivo_partenza") if fermate else None,
            "running": t.get("circolante", False),
            "operator": t.get("operatore", ""),
        })
    return {"station_code": station_code, "departures": results, "count": len(results)}


@router.get("/vt/arrivals")
def vt_arrivals(
    station_code: str,
    date: str | None = None,
    time: str | None = None,
    only_trenord: bool = True,
):
    """Arrivi a una stazione via ARTURO Live."""
    try:
        data = arrivi(station_code)
    except Exception as e:
        raise HTTPException(502, detail=f"ARTURO Live errore: {e}")

    results = []
    for t in data:
        if only_trenord and t.get("operatore", "").upper() != "TRENORD":
            continue
        fermate = t.get("fermate", [])
        arr_time = ""
        if fermate:
            prog = fermate[-1].get("programmato_arrivo", "")
            if prog:
                arr_time = prog[11:16]

        results.append({
            "train_number": t.get("numero"),
            "category": t.get("categoria", ""),
            "origin": t.get("origine"),
            "destination": t.get("destinazione"),
            "arr_time": arr_time,
            "delay": t.get("ritardo_corrente_min", 0),
            "platform_scheduled": fermate[-1].get("binario_programmato_arrivo") if fermate else None,
            "platform_actual": fermate[-1].get("binario_effettivo_arrivo") if fermate else None,
            "running": t.get("circolante", False),
            "operator": t.get("operatore", ""),
        })
    return {"station_code": station_code, "arrivals": results, "count": len(results)}


@router.get("/vt/train-info")
def vt_train_info(train_number: int, date: str | None = None):
    """Dettaglio treno con fermate e ritardi in tempo reale."""
    try:
        data = treno(str(train_number))
    except Exception as e:
        raise HTTPException(502, detail=f"ARTURO Live errore: {e}")

    if not data:
        raise HTTPException(404, detail=f"Treno {train_number} non trovato")

    # Map stato ARTURO → status leggibile
    status_map = {
        "IN_ORARIO": "regolare",
        "RITARDO": "ritardo",
        "SOPPRESSO": "soppresso",
        "NON_PARTITO": "non_partito",
    }

    stops = []
    for f in data.get("fermate", []):
        dep_prog, dep_real, arr_prog, arr_real = fermata_to_times(f)
        stops.append({
            "station": f.get("stazione_nome"),
            "station_code": f.get("stazione_id"),
            "scheduled_dep": dep_prog or None,
            "scheduled_arr": arr_prog or None,
            "actual_dep": dep_real or None,
            "actual_arr": arr_real or None,
            "delay_dep": f.get("ritardo_partenza_min", 0),
            "delay_arr": f.get("ritardo_arrivo_min", 0),
            "platform_scheduled": f.get("binario_programmato_partenza"),
            "platform_actual": f.get("binario_effettivo_partenza"),
            "stop_type": f.get("tipo_fermata"),
            "cancelled": f.get("soppressa", False),
        })

    return {
        "train_number": train_number,
        "origin_code": data.get("codice_origine"),
        "operator": data.get("operatore"),
        "is_trenord": data.get("operatore", "").upper() == "TRENORD",
        "status": status_map.get(data.get("stato", ""), data.get("stato", "")),
        "last_update": data.get("timestamp_aggiornamento"),
        "delay": data.get("ritardo_corrente_min", 0),
        "stops": stops,
        "cancelled_stops": [
            f.get("stazione_nome") for f in data.get("fermate", [])
            if f.get("soppressa")
        ],
    }


@router.get("/vt/real-passage")
def vt_real_passage(train_number: int, station: str):
    """Orario REALE di passaggio di un treno a una stazione specifica."""
    try:
        data = treno(str(train_number))
    except Exception:
        return {"error": f"Treno {train_number} non trovato", "real_time": None}

    if not data:
        return {"error": f"Treno {train_number} non trovato", "real_time": None}

    fermate = data.get("fermate", [])
    station_upper = station.strip().upper()

    # Trova la fermata richiesta (per nome o id)
    target = None
    for f in fermate:
        if (f.get("stazione_nome", "").upper() == station_upper
                or f.get("stazione_id", "").upper() == station_upper):
            target = f
            break

    # Treno arrivato a destinazione?
    train_finished = data.get("arrivato_destinazione", False)

    # Staleness check
    stale = data.get("is_stale", False)
    last_detected_station = data.get("ultima_stazione")
    last_detected_time = ""
    if data.get("ora_ultimo_rilevamento_vt"):
        ts = data["ora_ultimo_rilevamento_vt"]
        if isinstance(ts, str) and len(ts) >= 16:
            last_detected_time = ts[11:16]

    real_time = None
    scheduled_time = None
    if target:
        dep_prog, dep_real, arr_prog, arr_real = fermata_to_times(target)
        real_time = dep_real or arr_real or None
        scheduled_time = dep_prog or arr_prog or None

    return {
        "train_number": train_number,
        "station": station,
        "real_time": real_time,
        "scheduled_time": scheduled_time,
        "train_finished": train_finished,
        "stale": stale,
        "last_detected_station": last_detected_station,
        "last_detected_time": last_detected_time,
    }


@router.get("/vt/solutions")
def vt_solutions(
    from_station: str,
    to_station: str,
    date: str | None = None,
    time: str | None = None,
):
    """Cerca soluzioni di viaggio tra due stazioni via ARTURO Live."""
    quando = None
    if time:
        quando = time  # ARTURO accetta HH:MM
    try:
        data = cerca_tratta(from_station, to_station, quando=quando)
    except Exception as e:
        raise HTTPException(502, detail=f"ARTURO Live errore: {e}")

    results = []
    for r in data.get("risultati", []):
        results.append({
            "train_number": r.get("numero"),
            "category": r.get("categoria", ""),
            "destination": r.get("destinazione"),
            "dep_time": r.get("orario_programmato", ""),
            "arr_time": r.get("orario_arrivo", ""),
            "delay": r.get("ritardo", 0),
            "running": not r.get("non_partito", False),
            "operator": r.get("operatore", ""),
            "is_trenord": r.get("operatore", "").upper() == "TRENORD",
            "durata": r.get("durata"),
            "consigliato": r.get("consigliato", False),
            "affidabilita": r.get("affidabilita"),
        })

    return {"from": from_station, "to": to_station, "departures": results, "count": len(results)}


@router.get("/vt/find-return")
def vt_find_return(
    from_station: str,
    to_station: str,
    after_time: str = "00:00",
    max_check: int = 20,
):
    """Cerca treni REALI per rientrare al deposito via ARTURO Live.

    Strategia DOPPIA:
      A) Cerca ARRIVI al deposito → verifica se il treno passa dalla stazione corrente
      B) Cerca PARTENZE dalla stazione corrente → verifica se arriva al deposito
    """
    from_name = _resolve_deposito(from_station)
    to_name = _resolve_deposito(to_station)

    from_id = resolve_station_id(from_name)
    to_id = resolve_station_id(to_name)

    if not from_id:
        return {"return_trains": [], "error": f"Stazione '{from_station}' non trovata"}
    if not to_id:
        return {"return_trains": [], "error": f"Stazione '{to_station}' non trovata"}

    from_upper = from_name.strip().upper()
    to_upper = to_name.strip().upper()
    after_min = _time_to_min(after_time)

    return_trains = []
    seen = set()
    total_checked = 0

    # ━━━ STRATEGIA A: ARRIVI al deposito ━━━
    try:
        arr_data = arrivi(to_id)
        for t in arr_data[:max_check]:
            total_checked += 1
            num = t.get("numero")
            if not num or num in seen:
                continue

            fermate = t.get("fermate", [])
            # Verifica che il treno passi dalla nostra stazione PRIMA del deposito
            from_fermata = None
            to_fermata = None
            found_from = False
            for f in fermate:
                f_name = (f.get("stazione_nome") or "").upper()
                f_id = (f.get("stazione_id") or "").upper()
                if not found_from:
                    if f_name == from_upper or f_id == from_id.upper():
                        from_fermata = f
                        found_from = True
                else:
                    if f_name == to_upper or f_id == to_id.upper():
                        to_fermata = f
                        break

            if not from_fermata or not to_fermata:
                continue

            dep_prog, dep_real, _, _ = fermata_to_times(from_fermata)
            _, _, arr_prog, arr_real = fermata_to_times(to_fermata)

            if dep_prog:
                if _time_to_min(dep_prog) < after_min:
                    continue

            seen.add(num)
            return_trains.append({
                "train_number": num,
                "category": t.get("categoria", ""),
                "from_station": from_upper,
                "to_station": to_upper,
                "dep_time": dep_prog,
                "arr_time": arr_prog,
                "arr_time_real": arr_real,
                "delay": t.get("ritardo_corrente_min", 0),
                "delay_arr": to_fermata.get("ritardo_arrivo_min", 0),
                "platform": to_fermata.get("binario_effettivo_arrivo")
                    or to_fermata.get("binario_programmato_arrivo") or "",
                "destination_finale": (t.get("destinazione") or "").upper(),
                "origin_treno": (t.get("origine") or "").upper(),
                "running": t.get("circolante", False),
                "operator": t.get("operatore", ""),
                "source": "arrivi",
            })
    except Exception as e:
        print(f"[ARTURO] Errore arrivi al deposito: {e}")

    # ━━━ STRATEGIA B: PARTENZE dalla stazione corrente ━━━
    try:
        dep_data = partenze(from_id)
        for t in dep_data[:max_check]:
            total_checked += 1
            num = t.get("numero")
            if not num or num in seen:
                continue

            fermate = t.get("fermate", [])
            # Verifica che il treno arrivi al deposito
            found_from = False
            to_fermata = None
            for f in fermate:
                f_name = (f.get("stazione_nome") or "").upper()
                f_id = (f.get("stazione_id") or "").upper()
                if not found_from:
                    if f_name == from_upper or f_id == from_id.upper():
                        found_from = True
                    continue
                if f_name == to_upper or f_id == to_id.upper():
                    to_fermata = f
                    break

            if not to_fermata:
                continue

            # Orario partenza dalla nostra stazione
            dep_prog = ""
            for f in fermate:
                f_name = (f.get("stazione_nome") or "").upper()
                f_id = (f.get("stazione_id") or "").upper()
                if f_name == from_upper or f_id == from_id.upper():
                    p = f.get("programmato_partenza", "")
                    if p:
                        dep_prog = p[11:16]
                    break

            _, _, arr_prog, arr_real = fermata_to_times(to_fermata)

            seen.add(num)
            return_trains.append({
                "train_number": num,
                "category": t.get("categoria", ""),
                "from_station": from_upper,
                "to_station": to_upper,
                "dep_time": dep_prog,
                "arr_time": arr_prog,
                "arr_time_real": arr_real,
                "delay": t.get("ritardo_corrente_min", 0),
                "delay_arr": to_fermata.get("ritardo_arrivo_min", 0),
                "platform": to_fermata.get("binario_effettivo_partenza")
                    or to_fermata.get("binario_programmato_partenza") or "",
                "destination_finale": (t.get("destinazione") or "").upper(),
                "running": t.get("circolante", False),
                "operator": t.get("operatore", ""),
                "source": "partenze",
            })
    except Exception as e:
        print(f"[ARTURO] Errore partenze: {e}")

    return_trains.sort(key=lambda x: x.get("dep_time", "99:99"))

    return {
        "return_trains": return_trains,
        "from_id": from_id,
        "to_id": to_id,
        "checked": total_checked,
    }


@router.get("/vt/all-departures")
def vt_all_departures(station: str, after_time: str = "00:00"):
    """Tutte le partenze da una stazione (senza filtro operatore)."""
    station_name = _resolve_deposito(station)
    station_id = resolve_station_id(station_name)
    if not station_id:
        return {"departures": [], "error": f"Stazione '{station}' non trovata"}

    after_min = _time_to_min(after_time)
    results = []

    try:
        data = partenze(station_id)
        for t in data:
            fermate = t.get("fermate", [])
            dep_time = ""
            if fermate:
                prog = fermate[0].get("programmato_partenza", "")
                if prog:
                    dep_time = prog[11:16]

            if dep_time and _time_to_min(dep_time) < after_min:
                continue

            results.append({
                "train_number": t.get("numero"),
                "from_station": station_name.strip().upper(),
                "to_station": (t.get("destinazione") or "").upper(),
                "dep_time": dep_time,
                "delay": t.get("ritardo_corrente_min", 0),
                "running": t.get("circolante", False),
                "operator": t.get("operatore", ""),
            })
    except Exception as e:
        return {"departures": [], "error": str(e)}

    results.sort(key=lambda x: x.get("dep_time", "99:99"))
    return {"departures": results, "station_code": station_id}
