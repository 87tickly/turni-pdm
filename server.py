"""
Web server FastAPI per il sistema Turni PDM.
Espone query treni, stazioni, turn builder e upload PDF via HTTP.
"""

import json
import os
import shutil
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

import bcrypt
from jose import jwt, JWTError
from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional

from src.database.db import Database
from src.importer.pdf_parser import PDFImporter
from src.validator.rules import TurnValidator, _fmt_min, _time_to_min, _min_to_time
from src.turn_builder.auto_builder import AutoBuilder
from src.constants import (
    MAX_PRESTAZIONE_MIN,
    MAX_CONDOTTA_MIN,
    MEAL_MIN,
    ACCESSORY_RULES,
    ACCESSORY_OPTIONS,
    TEMPI_MEDI_RULES,
    EXTRA_START_MIN,
    EXTRA_END_MIN,
    TARGET_CONDOTTA_MIN,
    FR_MAX_PRESTAZIONE_RIENTRO_MIN,
    FR_MIN_RIPOSO_H,
    FR_MAX_PER_WEEK,
    FR_MAX_PER_28_DAYS,
    VALIDITY_MAP,
    DEPOSITI,
    FIXED_TRAVEL_TIMES,
    load_fr_stations,
    WEEKLY_REST_MIN_H,
    WEEKLY_HOURS_MIN,
    WEEKLY_HOURS_MAX,
    WEEKLY_HOURS_TARGET,
)

app = FastAPI(
    title="Turni PDM API",
    description="API per interrogazione treni e costruzione turni personale di macchina",
    version="1.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "turni.db"
UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Serve static files (frontend)
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


def get_db() -> Database:
    return Database(db_path=DB_PATH)


# ---------------------------------------------------------------
# AUTH (JWT)
# ---------------------------------------------------------------
SECRET_KEY = os.environ.get("JWT_SECRET", "dev-secret-turni-pdm-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 72
security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(user_id: int, username: str, is_admin: bool) -> str:
    payload = {
        "sub": str(user_id),
        "username": username,
        "is_admin": is_admin,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    if not credentials:
        raise HTTPException(401, "Token mancante")
    try:
        payload = jwt.decode(
            credentials.credentials, SECRET_KEY, algorithms=[JWT_ALGORITHM]
        )
        return {
            "id": int(payload["sub"]),
            "username": payload["username"],
            "is_admin": payload.get("is_admin", False),
        }
    except JWTError:
        raise HTTPException(401, "Token non valido o scaduto")


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/api/register")
def register(req: RegisterRequest):
    if len(req.username.strip()) < 3:
        raise HTTPException(400, "Username deve avere almeno 3 caratteri")
    if len(req.password) < 6:
        raise HTTPException(400, "Password deve avere almeno 6 caratteri")
    db = get_db()
    try:
        if db.get_user_by_username(req.username.strip()):
            raise HTTPException(400, "Username gia' in uso")
        pw_hash = hash_password(req.password)
        user_id = db.create_user(req.username.strip(), pw_hash, is_admin=False)
        token = create_token(user_id, req.username.strip(), False)
        return {
            "token": token,
            "user": {"id": user_id, "username": req.username.strip(), "is_admin": False},
        }
    finally:
        db.close()


@app.post("/api/login")
def login(req: LoginRequest):
    db = get_db()
    try:
        user = db.get_user_by_username(req.username.strip())
        if not user or not verify_password(req.password, user["password_hash"]):
            raise HTTPException(401, "Credenziali non valide")
        db.update_last_login(user["id"])
        token = create_token(user["id"], user["username"], bool(user["is_admin"]))
        return {
            "token": token,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "is_admin": bool(user["is_admin"]),
            },
        }
    finally:
        db.close()


@app.get("/api/me")
def get_me(user: dict = Depends(get_current_user)):
    return user


@app.get("/api/admin/users")
def admin_list_users(user: dict = Depends(get_current_user)):
    if not user["is_admin"]:
        raise HTTPException(403, "Solo admin")
    db = get_db()
    try:
        return {"users": db.get_all_users()}
    finally:
        db.close()


@app.get("/api/admin/saved-shifts")
def admin_all_saved_shifts(user: dict = Depends(get_current_user)):
    if not user["is_admin"]:
        raise HTTPException(403, "Solo admin")
    db = get_db()
    try:
        shifts = db.get_saved_shifts(user_id=None)
        users = {u["id"]: u["username"] for u in db.get_all_users()}
        for s in shifts:
            s["owner"] = users.get(s.get("user_id"), "—")
        return {"shifts": shifts, "count": len(shifts)}
    finally:
        db.close()


@app.get("/api/admin/weekly-shifts")
def admin_all_weekly_shifts(user: dict = Depends(get_current_user)):
    if not user["is_admin"]:
        raise HTTPException(403, "Solo admin")
    db = get_db()
    try:
        shifts = db.get_weekly_shifts(user_id=None)
        users = {u["id"]: u["username"] for u in db.get_all_users()}
        for s in shifts:
            s["owner"] = users.get(s.get("user_id"), "—")
        return {"shifts": shifts}
    finally:
        db.close()


# ---------------------------------------------------------------
# INFO & HEALTH
# ---------------------------------------------------------------
@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "Turni PDM API"}


@app.get("/info")
def info():
    db = get_db()
    try:
        count = db.segment_count()
        turns = db.get_material_turns()
        days = db.get_distinct_day_indices()
        all_segs = db.get_all_segments()
        unique_trains = sorted(set(s["train_id"] for s in all_segs))
        return {
            "total_segments": count,
            "material_turns": turns,
            "day_indices": days,
            "unique_trains": unique_trains,
            "unique_trains_count": len(unique_trains),
        }
    finally:
        db.close()


# ---------------------------------------------------------------
# UPLOAD PDF
# ---------------------------------------------------------------
@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Il file deve essere un PDF")

    # Save uploaded file
    dest = UPLOAD_DIR / file.filename
    with open(dest, "wb") as f:
        content = await file.read()
        f.write(content)

    # Import into database
    db = get_db()
    try:
        importer = PDFImporter(str(dest), db)

        if not importer.validate_pdf():
            raise HTTPException(
                422,
                "PDF non valido o non riconosciuto. Richiesto PDF nativo Trenord."
            )

        # --- PULIZIA DATI VECCHI PRIMA DI IMPORTARE ---
        # Conta segmenti esistenti per avvisare l'utente
        old_count = db.segment_count()
        old_saved = db.get_saved_shifts()
        if old_count > 0:
            print(f"\n[IMPORT] Pulizia dati precedenti: {old_count} segmenti rimossi")
            db.clear_all()  # cancella material_turn, train_segment, day_variant (NON saved_shift)

        count = importer.run_import()

        # Gather stats
        all_segs = db.get_all_segments()
        unique_trains = sorted(set(s["train_id"] for s in all_segs))

        high_conf = sum(1 for s in importer.segments if s.confidence >= 0.8)
        med_conf = sum(1 for s in importer.segments if 0.4 <= s.confidence < 0.8)
        low_conf = sum(1 for s in importer.segments if s.confidence < 0.4)

        # Verifica integrità turni salvati dopo re-import
        saved_warnings = []
        if old_saved:
            new_train_set = set(unique_trains)
            for shift in old_saved:
                shift_trains = json.loads(shift["train_ids"]) if isinstance(shift["train_ids"], str) else shift["train_ids"]
                missing = [t for t in shift_trains if t not in new_train_set]
                if missing:
                    saved_warnings.append(
                        f"Turno salvato \"{shift['name']}\" contiene treni non presenti nel nuovo PDF: {', '.join(missing)}"
                    )

        all_warnings = list(importer.warnings) + saved_warnings

        return {
            "filename": file.filename,
            "segments_imported": count,
            "total_segments_db": db.segment_count(),
            "unique_trains": unique_trains,
            "unique_trains_count": len(unique_trains),
            "turn_numbers": sorted(importer.turn_numbers) if importer.turn_numbers else [],
            "confidence": {
                "high": high_conf,
                "medium": med_conf,
                "low": low_conf,
            },
            "warnings": all_warnings,
            "previous_data_cleared": old_count > 0,
            "previous_segments_cleared": old_count,
            "saved_shift_warnings": saved_warnings,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Errore durante l'importazione: {str(e)}")
    finally:
        db.close()


@app.delete("/database")
def clear_database():
    db = get_db()
    try:
        db.clear_all()
        return {"status": "ok", "message": "Database svuotato"}
    finally:
        db.close()


# ---------------------------------------------------------------
# QUERY TRENO
# ---------------------------------------------------------------
@app.get("/train/{train_id}")
def query_train(train_id: str):
    db = get_db()
    try:
        results = db.query_train(train_id)
        if not results:
            raise HTTPException(404, f"Treno {train_id} non trovato")
        return {"train_id": train_id, "segments": results}
    finally:
        db.close()


# ---------------------------------------------------------------
# GIRO MATERIALE (ciclo completo del treno)
# ---------------------------------------------------------------
@app.get("/giro-materiale/{train_id}")
def giro_materiale(train_id: str):
    """
    Restituisce il ciclo materiale completo a cui appartiene il treno.
    Mostra tutti i treni che il materiale rotabile fa nel corso della giornata.
    """
    db = get_db()
    try:
        result = db.get_material_cycle(train_id)
        if not result["cycle"]:
            raise HTTPException(404, f"Treno {train_id} non trovato nel giro materiale")
        return result
    finally:
        db.close()


# ---------------------------------------------------------------
# MATERIAL INFO (turno materiale + giro)
# ---------------------------------------------------------------
@app.get("/material-info/{train_id}")
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


@app.get("/giro-chain/{train_id}")
def giro_chain(train_id: str):
    """Returns the position of a train in its giro materiale chain:
    prev train, next train, full chain. This is the KEY endpoint
    for understanding what the material does before/after a train."""
    db = get_db()
    try:
        return db.get_giro_chain_context(train_id)
    finally:
        db.close()


# ---------------------------------------------------------------
# QUERY STAZIONE
# ---------------------------------------------------------------
@app.get("/station/{station_name}")
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


# ---------------------------------------------------------------
# LISTA TRENI
# ---------------------------------------------------------------
@app.get("/trains")
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


# ---------------------------------------------------------------
# LISTA STAZIONI UNICHE (per autocomplete frontend)
# ---------------------------------------------------------------
@app.get("/stations")
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


# ---------------------------------------------------------------
# COSTANTI OPERATIVE
# ---------------------------------------------------------------
@app.get("/constants")
def get_constants():
    return {
        "MAX_PRESTAZIONE_MIN": MAX_PRESTAZIONE_MIN,
        "MAX_PRESTAZIONE": _fmt_min(MAX_PRESTAZIONE_MIN),
        "MAX_CONDOTTA_MIN": MAX_CONDOTTA_MIN,
        "MAX_CONDOTTA": _fmt_min(MAX_CONDOTTA_MIN),
        "TARGET_CONDOTTA_MIN": TARGET_CONDOTTA_MIN,
        "TARGET_CONDOTTA": _fmt_min(TARGET_CONDOTTA_MIN),
        "MEAL_MIN": MEAL_MIN,
        "EXTRA_START_MIN": EXTRA_START_MIN,
        "EXTRA_END_MIN": EXTRA_END_MIN,
        "ACCESSORY_RULES": ACCESSORY_RULES,
        "ACCESSORY_OPTIONS": ACCESSORY_OPTIONS,
        "TEMPI_MEDI_RULES": TEMPI_MEDI_RULES,
        "FR_STATIONS": load_fr_stations(),
        "FR_MAX_PRESTAZIONE_RIENTRO_MIN": FR_MAX_PRESTAZIONE_RIENTRO_MIN,
        "FR_MIN_RIPOSO_H": FR_MIN_RIPOSO_H,
        "FR_MAX_PER_WEEK": FR_MAX_PER_WEEK,
        "FR_MAX_PER_28_DAYS": FR_MAX_PER_28_DAYS,
        "VALIDITY_MAP": VALIDITY_MAP,
        "DEPOSITI": DEPOSITI,
        "FIXED_TRAVEL_TIMES": {f"{k[0]}|{k[1]}": v for k, v in FIXED_TRAVEL_TIMES.items()},
        "WEEKLY_REST_MIN_H": WEEKLY_REST_MIN_H,
        "WEEKLY_HOURS_MIN": WEEKLY_HOURS_MIN,
        "WEEKLY_HOURS_MAX": WEEKLY_HOURS_MAX,
        "WEEKLY_HOURS_TARGET": WEEKLY_HOURS_TARGET,
    }


# ---------------------------------------------------------------
# VALIDATE DAY
# ---------------------------------------------------------------
class CustomSegment(BaseModel):
    train_id: str
    from_station: str
    to_station: str
    dep_time: str
    arr_time: str
    is_deadhead: bool = False


class ValidateDayRequest(BaseModel):
    train_ids: list[str]
    deposito: str = ""
    accessory_type: str = "standard"
    include_timeline: bool = False
    deadhead_ids: list[str] = []  # treni di rientro (vettura, non condotta)
    custom_segments: list[CustomSegment] = []  # segmenti VT non nel DB
    is_fr: bool = False  # se True, utente ha marcato esplicitamente come FR
    acc_start_override: int | None = None  # override manuale accessori inizio (minuti)
    acc_end_override: int | None = None    # override manuale accessori fine (minuti)


@app.post("/validate-day")
def validate_day(req: ValidateDayRequest):
    db = get_db()
    try:
        segments = []
        custom_train_ids = {cs.train_id for cs in req.custom_segments}
        for tid in req.train_ids:
            if tid in custom_train_ids:
                continue  # skip DB lookup for custom segments
            segs = db.query_train(tid)
            segments.extend(segs)

        # Deduplica PRIMA di aggiungere custom segments
        if segments:
            segments = _dedup_segments(segments)

        # Aggiungi segmenti custom (VT trains non nel DB) DOPO la dedup
        for cs in req.custom_segments:
            segments.append({
                "train_id": cs.train_id,
                "from_station": cs.from_station,
                "to_station": cs.to_station,
                "dep_time": cs.dep_time,
                "arr_time": cs.arr_time,
                "is_deadhead": cs.is_deadhead,
            })

        if not segments:
            raise HTTPException(400, "Nessun segmento trovato per i treni indicati")

        # Marca i treni di rientro come deadhead (vettura, non condotta)
        dh_set = set(req.deadhead_ids)
        if dh_set:
            for seg in segments:
                if seg.get("train_id") in dh_set:
                    seg["is_deadhead"] = True

        segments.sort(key=lambda s: s["dep_time"])

        # Risolvi accessory_type in valori start/end reali
        acc_opt = ACCESSORY_OPTIONS.get(req.accessory_type, ACCESSORY_OPTIONS["standard"])
        acc_start_val = req.acc_start_override if req.acc_start_override is not None else acc_opt["start"]
        acc_end_val = req.acc_end_override if req.acc_end_override is not None else acc_opt["end"]

        validator = TurnValidator(deposito=req.deposito)
        summary = validator.validate_day(segments, deposito=req.deposito,
                                          is_fr_override=req.is_fr,
                                          acc_start=acc_start_val, acc_end=acc_end_val)

        result = {
            "prestazione_min": summary.prestazione_min,
            "prestazione": _fmt_min(summary.prestazione_min),
            "limite_prestazione": _fmt_min(MAX_PRESTAZIONE_MIN),
            "condotta_min": summary.condotta_min,
            "condotta": _fmt_min(summary.condotta_min),
            "limite_condotta": _fmt_min(MAX_CONDOTTA_MIN),
            "meal_min": summary.meal_min,
            "accessori_min": summary.accessori_min,
            "tempi_medi_min": summary.tempi_medi_min,
            "extra_min": summary.extra_min,
            "night_minutes": summary.night_minutes,
            "day_type": summary.day_type,
            "presentation_time": summary.presentation_time,
            "end_time": summary.end_time,
            "is_fr": summary.is_fr,
            "last_station": summary.last_station,
            "meal_start": summary.meal_start,
            "meal_end": summary.meal_end,
            "segments": _serialize_segments(segments),
            "violations": [
                {"rule": v.rule, "message": v.message, "severity": v.severity}
                for v in summary.violations
            ],
            "valid": len(summary.violations) == 0,
        }
        if req.include_timeline:
            result["timeline"] = _build_timeline_blocks(summary, deposito=req.deposito, db=db)
        return result
    finally:
        db.close()


# ---------------------------------------------------------------
# BUILD AUTO
# ---------------------------------------------------------------
class BuildAutoRequest(BaseModel):
    deposito: str = ""
    days: int = 5
    day_type: str = "LV"
    accessory_type: str = "standard"


def _seg_get(seg, key, default=""):
    """Helper: get field from segment (dict or object)."""
    if isinstance(seg, dict):
        return seg.get(key, default)
    return getattr(seg, key, default)


def _dedup_segments(segments: list[dict]) -> list[dict]:
    """Deduplica segmenti: per ogni train_id, prende solo quelli del day_index
    piu' frequente (= LV, tipicamente). Rimuove anche segmenti identici."""
    from collections import Counter
    if not segments:
        return segments

    # Conta quale day_index è più frequente tra tutti i segmenti
    day_idx_counts = Counter(s.get("day_index", 0) for s in segments)
    best_day_idx = day_idx_counts.most_common(1)[0][0]

    # Per ogni train_id, prendi solo i segmenti del best day_index
    # Se un treno non ha quel day_index, prendi il suo primo day_index
    by_train: dict[str, dict[int, list]] = {}
    for s in segments:
        tid = s.get("train_id", "")
        di = s.get("day_index", 0)
        by_train.setdefault(tid, {}).setdefault(di, []).append(s)

    result = []
    seen = set()
    for tid, di_map in by_train.items():
        # Preferisci best_day_idx, altrimenti il primo disponibile
        chosen_di = best_day_idx if best_day_idx in di_map else min(di_map.keys())
        for s in di_map[chosen_di]:
            # Dedup per (train_id, dep_time, arr_time, from_station, to_station)
            key = (s.get("train_id"), s.get("dep_time"), s.get("arr_time"),
                   s.get("from_station"), s.get("to_station"))
            if key not in seen:
                seen.add(key)
                result.append(s)

    return result


def _build_timeline_blocks(summary, deposito: str = "", db: Database = None,
                           acc_start: int = None, acc_end: int = None) -> list[dict]:
    """
    Genera i blocchi timeline per una giornata di turno.
    Ogni blocco ha: type, label, detail, start (min), end (min),
    start_time (HH:MM), end_time (HH:MM), from_station, to_station, duration.

    Se deposito e db sono forniti, aggiunge:
    - blocco 'spostamento' (cyan) se il turno finisce fuori deposito
    - blocco 'dormita_fr' (indaco) se la stazione finale è FR
    """
    blocks = []
    segs = summary.segments
    if not segs or not summary.presentation_time or not summary.end_time:
        return blocks

    # Valori accessori effettivi (custom o default)
    eff_acc_start = acc_start if acc_start is not None else ACCESSORY_RULES["default_start"]
    eff_acc_end = acc_end if acc_end is not None else ACCESSORY_RULES["default_end"]

    pres_m = _time_to_min(summary.presentation_time)
    end_m = _time_to_min(summary.end_time)
    if end_m <= pres_m:
        end_m += 24 * 60

    first_dep_str = _seg_get(segs[0], "dep_time")
    last_arr_str = _seg_get(segs[-1], "arr_time")
    first_from_st = _seg_get(segs[0], "from_station", "")
    last_to_st = _seg_get(segs[-1], "to_station", "")
    first_dep_m = _time_to_min(first_dep_str)
    last_arr_m = _time_to_min(last_arr_str)
    if first_dep_m < pres_m:
        first_dep_m += 24 * 60
    if last_arr_m < first_dep_m:
        last_arr_m += 24 * 60

    # 1. Extra Inizio
    extra_s_end = pres_m + EXTRA_START_MIN
    blocks.append({
        "type": "extra", "label": "Extra Inizio",
        "start": pres_m, "end": extra_s_end,
        "start_time": _min_to_time(pres_m), "end_time": _min_to_time(extra_s_end),
        "duration": EXTRA_START_MIN,
        "from_station": first_from_st, "to_station": first_from_st,
    })

    # 2. Accessori Inizio (usa valore effettivo)
    acc_start_dur = first_dep_m - extra_s_end
    blocks.append({
        "type": "accessori", "label": "Acc. Inizio" + (" (CVL)" if eff_acc_start == 5 else ""),
        "start": extra_s_end, "end": first_dep_m,
        "start_time": _min_to_time(extra_s_end), "end_time": first_dep_str,
        "duration": acc_start_dur,
        "from_station": first_from_st, "to_station": first_from_st,
    })

    # 3. Segmenti treno + gap + refezione
    meal_s_m = _time_to_min(summary.meal_start) if summary.meal_start else None
    meal_e_m = _time_to_min(summary.meal_end) if summary.meal_end else None
    if meal_s_m is not None and meal_s_m < pres_m:
        meal_s_m += 24 * 60
    if meal_e_m is not None and meal_e_m < pres_m:
        meal_e_m += 24 * 60

    meal_placed = False

    for i, seg in enumerate(segs):
        dep_m = _time_to_min(_seg_get(seg, "dep_time"))
        arr_m = _time_to_min(_seg_get(seg, "arr_time"))
        if dep_m < pres_m:
            dep_m += 24 * 60
        if arr_m <= dep_m:
            arr_m += 24 * 60

        train_id = _seg_get(seg, "train_id", "?")
        from_st = _seg_get(seg, "from_station", "")
        to_st = _seg_get(seg, "to_station", "")
        seg_dur = arr_m - dep_m
        is_dh = _seg_get(seg, "is_deadhead", False)

        blocks.append({
            "type": "deadhead" if is_dh else "train",
            "label": str(train_id) + (" [V]" if is_dh else ""),
            "detail": from_st + " \u2192 " + to_st,
            "train_id": str(train_id),
            "start": dep_m, "end": arr_m,
            "start_time": _seg_get(seg, "dep_time"),
            "end_time": _seg_get(seg, "arr_time"),
            "duration": seg_dur,
            "from_station": from_st,
            "to_station": to_st,
            "is_deadhead": bool(is_dh),
        })

        # Gap dopo questo segmento
        if i < len(segs) - 1:
            next_dep_str = _seg_get(segs[i + 1], "dep_time")
            next_from_st = _seg_get(segs[i + 1], "from_station", "")
            next_dep_m = _time_to_min(next_dep_str)
            if next_dep_m < pres_m:
                next_dep_m += 24 * 60

            if next_dep_m > arr_m:
                # Verifica se la refezione cade in questo gap
                if (not meal_placed and meal_s_m is not None
                        and meal_s_m >= arr_m and meal_e_m <= next_dep_m):
                    # Attesa prima della refezione
                    if meal_s_m > arr_m:
                        blocks.append({
                            "type": "attesa", "label": "Attesa",
                            "start": arr_m, "end": meal_s_m,
                            "start_time": _min_to_time(arr_m),
                            "end_time": _min_to_time(meal_s_m),
                            "duration": meal_s_m - arr_m,
                            "from_station": to_st, "to_station": to_st,
                        })
                    # Refezione
                    blocks.append({
                        "type": "meal", "label": "Refezione",
                        "start": meal_s_m, "end": meal_e_m,
                        "start_time": summary.meal_start,
                        "end_time": summary.meal_end,
                        "duration": meal_e_m - meal_s_m,
                        "from_station": to_st, "to_station": to_st,
                    })
                    meal_placed = True
                    # Attesa dopo la refezione
                    if meal_e_m < next_dep_m:
                        blocks.append({
                            "type": "attesa", "label": "Attesa",
                            "start": meal_e_m, "end": next_dep_m,
                            "start_time": _min_to_time(meal_e_m),
                            "end_time": next_dep_str,
                            "duration": next_dep_m - meal_e_m,
                            "from_station": to_st, "to_station": next_from_st,
                        })
                else:
                    blocks.append({
                        "type": "attesa", "label": "Attesa",
                        "start": arr_m, "end": next_dep_m,
                        "start_time": _min_to_time(arr_m),
                        "end_time": next_dep_str,
                        "duration": next_dep_m - arr_m,
                        "from_station": to_st, "to_station": next_from_st,
                    })

    # Se la refezione non è stata piazzata in un gap, cercare il gap migliore
    if not meal_placed and meal_s_m is not None:
        # Cercare il gap più ampio tra i treni dove piazzare la refezione
        best_gap = None
        best_gap_station = ""
        for i in range(len(segs) - 1):
            arr_str = _seg_get(segs[i], "arr_time")
            dep_str = _seg_get(segs[i + 1], "dep_time")
            arr_m_gap = _time_to_min(arr_str)
            dep_m_gap = _time_to_min(dep_str)
            if arr_m_gap < pres_m:
                arr_m_gap += 24 * 60
            if dep_m_gap < pres_m:
                dep_m_gap += 24 * 60
            gap_dur = dep_m_gap - arr_m_gap
            if gap_dur >= MEAL_MIN and (best_gap is None or gap_dur > best_gap[2]):
                best_gap = (arr_m_gap, dep_m_gap, gap_dur)
                best_gap_station = _seg_get(segs[i], "to_station", "")
        if best_gap:
            # Piazza la refezione all'inizio del gap migliore
            meal_s_adj = best_gap[0]
            meal_e_adj = meal_s_adj + MEAL_MIN
            blocks.append({
                "type": "meal", "label": "Refezione",
                "start": meal_s_adj, "end": meal_e_adj,
                "start_time": _min_to_time(meal_s_adj),
                "end_time": _min_to_time(meal_e_adj),
                "duration": MEAL_MIN,
                "from_station": best_gap_station, "to_station": best_gap_station,
            })
        # Se nessun gap trovato: NON inserire la refezione (violazione segnalata)

    # 4. Accessori Fine (usa valore effettivo)
    acc_end_start = last_arr_m
    acc_end_end = last_arr_m + eff_acc_end
    blocks.append({
        "type": "accessori", "label": "Acc. Fine" + (" (CVL)" if eff_acc_end == 5 else ""),
        "start": acc_end_start, "end": acc_end_end,
        "start_time": last_arr_str,
        "end_time": _min_to_time(acc_end_end),
        "duration": eff_acc_end,
        "from_station": last_to_st, "to_station": last_to_st,
    })

    # 5. Extra Fine
    blocks.append({
        "type": "extra", "label": "Extra Fine",
        "start": acc_end_end, "end": end_m,
        "start_time": _min_to_time(acc_end_end),
        "end_time": _min_to_time(end_m),
        "duration": end_m - acc_end_end,
        "from_station": last_to_st, "to_station": last_to_st,
    })

    # 6. Rientro al deposito — Waterfall a 3 step:
    #    Step 1: Giro materiale → next train arriva a deposito?
    #    Step 2: Cerca nel DB treno di collegamento
    #    Step 3: Niente → violation NO_RIENTRO_BASE
    if deposito and last_to_st.upper() != deposito.upper():
        if db:
            rientro_found = False
            last_train_id = _seg_get(segs[-1], "train_id", "")

            # ── STEP 1: Controlla giro materiale ──
            # Cerca SOLO il treno immediatamente successivo nel giro che:
            #   - parta dalla stessa stazione dove siamo rimasti
            #   - arrivi al deposito
            #   - parta DOPO il nostro ultimo arrivo
            # Se non c'è match esatto, skip (no allucinazioni)
            if last_train_id:
                try:
                    giro_ctx = db.get_giro_chain_context(last_train_id)
                    if giro_ctx and giro_ctx.get("chain") and len(giro_ctx["chain"]) > 1:
                        pos = giro_ctx.get("position", -1)
                        chain = giro_ctx["chain"]
                        dep_upper = deposito.upper()
                        last_upper = last_to_st.upper()

                        for ci in range(pos + 1, len(chain)):
                            c = chain[ci]
                            c_from = (c.get("from") or "").upper().strip()
                            c_to = (c.get("to") or "").upper().strip()

                            # Match flessibile: confronta anche senza spazi
                            from_match = c_from == last_upper or c_from.replace(" ", "") == last_upper.replace(" ", "")
                            to_match = c_to == dep_upper or c_to.replace(" ", "") == dep_upper.replace(" ", "")

                            if from_match and to_match:
                                n_dep_m = _time_to_min(c["dep"])
                                n_arr_m = _time_to_min(c["arr"])
                                if n_dep_m < last_arr_m:
                                    n_dep_m += 24 * 60
                                if n_arr_m < n_dep_m:
                                    n_arr_m += 24 * 60

                                # Sanity check: la partenza deve essere dopo l'arrivo
                                if n_dep_m < last_arr_m:
                                    continue

                                # Attesa prima del rientro giro
                                if n_dep_m > end_m:
                                    blocks.append({
                                        "type": "attesa", "label": "Attesa rientro",
                                        "start": end_m, "end": n_dep_m,
                                        "start_time": _min_to_time(end_m),
                                        "end_time": c["dep"],
                                        "duration": n_dep_m - end_m,
                                        "from_station": last_to_st, "to_station": last_to_st,
                                    })

                                blocks.append({
                                    "type": "giro_return",
                                    "label": f"Giro {c['train_id']}",
                                    "detail": f"{last_to_st} \u2192 {deposito} (giro mat.)",
                                    "start": n_dep_m, "end": n_arr_m,
                                    "start_time": c["dep"],
                                    "end_time": c["arr"],
                                    "duration": n_arr_m - n_dep_m,
                                    "from_station": last_to_st,
                                    "to_station": deposito,
                                    "train_id": c["train_id"],
                                    "is_deadhead": c.get("is_deadhead", False),
                                })
                                rientro_found = True
                                break
                except Exception as e:
                    import traceback
                    print(f"[WARN] Giro materiale check failed for {last_train_id}: {e}")
                    traceback.print_exc()

            # ── STEP 2: Cerca nel DB treni di collegamento ──
            if not rientro_found:
                try:
                    connections = db.find_connecting_trains(
                        from_station=last_to_st,
                        after_time=_min_to_time(last_arr_m),
                        to_station=deposito,
                        limit=3,
                    )
                    if connections:
                        conn = connections[0]
                        c_dep_m = _time_to_min(conn["dep_time"])
                        c_arr_m = _time_to_min(conn["arr_time"])
                        if c_dep_m < last_arr_m:
                            c_dep_m += 24 * 60
                        if c_arr_m < c_dep_m:
                            c_arr_m += 24 * 60

                        # Attesa prima dello spostamento
                        if c_dep_m > end_m:
                            blocks.append({
                                "type": "attesa", "label": "Attesa spostamento",
                                "start": end_m, "end": c_dep_m,
                                "start_time": _min_to_time(end_m),
                                "end_time": conn["dep_time"],
                                "duration": c_dep_m - end_m,
                                "from_station": last_to_st, "to_station": last_to_st,
                            })

                        # Blocco spostamento (cyan)
                        blocks.append({
                            "type": "spostamento",
                            "label": f"Spost. {conn.get('train_id', '?')}",
                            "detail": f"{last_to_st} \u2192 {deposito}",
                            "start": c_dep_m, "end": c_arr_m,
                            "start_time": conn["dep_time"],
                            "end_time": conn["arr_time"],
                            "duration": c_arr_m - c_dep_m,
                            "from_station": last_to_st,
                            "to_station": deposito,
                            "train_id": conn.get("train_id", ""),
                        })
                        rientro_found = True
                except Exception as e:
                    print(f"[WARN] find_connecting_trains failed: {e}")

            # ── STEP 3: Nessun rientro trovato ──
            if not rientro_found:
                blocks.append({
                    "type": "spostamento",
                    "label": "\u26a0 No rientro",
                    "detail": f"Nessun treno da {last_to_st} a {deposito}",
                    "start": end_m, "end": end_m + 15,
                    "start_time": _min_to_time(end_m),
                    "end_time": _min_to_time(end_m + 15),
                    "duration": 0,
                    "from_station": last_to_st, "to_station": last_to_st,
                })

    return blocks


def _serialize_segments(segments) -> list[dict]:
    """Serializza segmenti in formato JSON-safe."""
    result = []
    for seg in segments:
        result.append({
            "train_id": _seg_get(seg, "train_id", "?"),
            "from_station": _seg_get(seg, "from_station", ""),
            "to_station": _seg_get(seg, "to_station", ""),
            "dep_time": _seg_get(seg, "dep_time", ""),
            "arr_time": _seg_get(seg, "arr_time", ""),
            "is_deadhead": _seg_get(seg, "is_deadhead", False),
        })
    return result


@app.post("/build-auto")
def build_auto(req: BuildAutoRequest):
    db = get_db()
    try:
        builder = AutoBuilder(db, deposito=req.deposito)
        # Escludi treni gia salvati per questo tipo giorno
        used = db.get_used_train_ids(day_type=req.day_type)
        calendar = builder.build_schedule(
            n_workdays=req.days,
            day_type=req.day_type,
            exclude_trains=used,
        )

        result = []
        for entry in calendar:
            item = {"type": entry["type"], "day": entry.get("day")}
            if entry.get("summary") and entry["summary"].segments:
                s = entry["summary"]
                timeline = _build_timeline_blocks(s, deposito=req.deposito, db=db)
                item["summary"] = {
                    "prestazione": _fmt_min(s.prestazione_min),
                    "prestazione_min": s.prestazione_min,
                    "condotta": _fmt_min(s.condotta_min),
                    "condotta_min": s.condotta_min,
                    "accessori_min": s.accessori_min,
                    "tempi_medi_min": s.tempi_medi_min,
                    "extra_min": s.extra_min,
                    "meal_min": s.meal_min,
                    "meal_start": s.meal_start,
                    "meal_end": s.meal_end,
                    "presentation_time": s.presentation_time,
                    "end_time": s.end_time,
                    "day_type": s.day_type,
                    "night_minutes": s.night_minutes,
                    "is_fr": s.is_fr,
                    "last_station": s.last_station,
                    "segments_count": len(s.segments),
                    "segments": _serialize_segments(s.segments),
                    "timeline": timeline,
                    "violations": [
                        {"rule": v.rule, "message": v.message,
                         "severity": v.severity}
                        for v in s.violations
                    ],
                }
            result.append(item)

        # ── VERIFICA TRENI DUPLICATI ──
        all_train_ids = []
        for entry in calendar:
            if entry.get("summary") and entry["summary"].segments:
                for seg in entry["summary"].segments:
                    tid = seg.get("train_id", "") if isinstance(seg, dict) else seg.train_id
                    all_train_ids.append(tid)
        duplicates = db.validate_no_duplicate_trains(all_train_ids)
        if duplicates:
            # Rimuovi duplicati automaticamente (tieni solo la prima occorrenza)
            used_in_result = set()
            for entry in calendar:
                if entry.get("summary") and entry["summary"].segments:
                    clean_segs = []
                    for seg in entry["summary"].segments:
                        tid = seg.get("train_id", "") if isinstance(seg, dict) else seg.train_id
                        if tid not in used_in_result:
                            used_in_result.add(tid)
                            clean_segs.append(seg)
                    if clean_segs != entry["summary"].segments:
                        entry["summary"].segments = clean_segs
                        # Ricalcola summary con segmenti puliti
                        validator = TurnValidator(deposito=req.deposito)
                        entry["summary"] = validator.validate_day(
                            clean_segs, deposito=req.deposito
                        )

        # Estrai metadati zona raggiungibile
        meta = {}
        if calendar and calendar[0].get("_meta"):
            meta = calendar[0]["_meta"]

        # Ricalcola lista treni per risposta
        all_train_ids_final = []
        for entry in calendar:
            if entry.get("summary") and entry["summary"].segments:
                for seg in entry["summary"].segments:
                    tid = seg.get("train_id", "") if isinstance(seg, dict) else seg.train_id
                    all_train_ids_final.append(tid)
        final_duplicates = db.validate_no_duplicate_trains(all_train_ids_final)

        return {
            "workdays_requested": req.days,
            "calendar": result,
            "deposito": meta.get("deposito", req.deposito),
            "reachable_stations": meta.get("reachable_stations", []),
            "total_violations": meta.get("total_violations", 0),
            "train_dedup": {
                "total_trains": len(all_train_ids_final),
                "unique_trains": len(set(all_train_ids_final)),
                "duplicates": final_duplicates,
                "clean": len(final_duplicates) == 0,
            },
        }
    finally:
        db.close()


# ---------------------------------------------------------------
# BUILD AUTO - TUTTI GLI IMPIANTI
# ---------------------------------------------------------------
class BuildAutoAllRequest(BaseModel):
    days: int = 5
    day_type: str = "LV"
    accessory_type: str = "standard"


@app.post("/build-auto-all")
def build_auto_all(req: BuildAutoAllRequest):
    """Genera turni automatici per TUTTI i 19 impianti."""
    db = get_db()
    try:
        results = {}
        for deposito in DEPOSITI:
            try:
                builder = AutoBuilder(db, deposito=deposito)
                used = db.get_used_train_ids(day_type=req.day_type)
                calendar = builder.build_schedule(
                    n_workdays=req.days,
                    day_type=req.day_type,
                    exclude_trains=used,
                )

                cal_items = []
                total_days_ok = 0
                total_violations = 0
                for entry in calendar:
                    item = {"type": entry["type"], "day": entry.get("day")}
                    if entry.get("summary") and entry["summary"].segments:
                        s = entry["summary"]
                        timeline = _build_timeline_blocks(s, deposito=deposito, db=db)
                        item["summary"] = {
                            "prestazione": _fmt_min(s.prestazione_min),
                            "prestazione_min": s.prestazione_min,
                            "condotta": _fmt_min(s.condotta_min),
                            "condotta_min": s.condotta_min,
                            "accessori_min": s.accessori_min,
                            "tempi_medi_min": s.tempi_medi_min,
                            "extra_min": s.extra_min,
                            "meal_min": s.meal_min,
                            "meal_start": s.meal_start,
                            "meal_end": s.meal_end,
                            "presentation_time": s.presentation_time,
                            "end_time": s.end_time,
                            "day_type": s.day_type,
                            "night_minutes": s.night_minutes,
                            "is_fr": s.is_fr,
                            "last_station": s.last_station,
                            "segments_count": len(s.segments),
                            "segments": _serialize_segments(s.segments),
                            "timeline": timeline,
                            "violations": [
                                {"rule": v.rule, "message": v.message,
                                 "severity": v.severity}
                                for v in s.violations
                            ],
                        }
                        total_days_ok += 1
                        total_violations += len(s.violations)
                    cal_items.append(item)

                meta = {}
                if calendar and calendar[0].get("_meta"):
                    meta = calendar[0]["_meta"]

                results[deposito] = {
                    "calendar": cal_items,
                    "deposito": deposito,
                    "reachable_stations": meta.get("reachable_stations", []),
                    "total_days_ok": total_days_ok,
                    "total_violations": total_violations,
                    "status": "ok",
                }
            except Exception as e:
                results[deposito] = {
                    "calendar": [],
                    "deposito": deposito,
                    "reachable_stations": [],
                    "total_days_ok": 0,
                    "total_violations": 0,
                    "status": "error",
                    "error": str(e),
                }

        return {
            "depositi_count": len(DEPOSITI),
            "depositi": DEPOSITI,
            "results": results,
        }
    finally:
        db.close()


# ---------------------------------------------------------------
# CALENDAR 5+2
# ---------------------------------------------------------------
@app.get("/calendar/{n_days}")
def generate_calendar(n_days: int):
    validator = TurnValidator()
    calendar = validator.build_calendar(n_days)
    weekly_v = validator.validate_weekly_rest(calendar)
    return {
        "workdays": n_days,
        "calendar": [e["type"] for e in calendar],
        "total_days": len(calendar),
        "violations": [
            {"rule": v.rule, "message": v.message} for v in weekly_v
        ],
    }


# ---------------------------------------------------------------
# CONNECTIONS (treni in partenza da una stazione)
# ---------------------------------------------------------------
@app.get("/connections")
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
                    r["giro_next"] = f"{n['train_id']} {n.get('from_station','')}→{n.get('to_station','')} {n.get('dep_time','')}"
                else:
                    r["giro_next"] = None
                r["giro_turn"] = gctx.get("turn_number") if gctx else None
            except Exception:
                r["giro_next"] = None
                r["giro_turn"] = None

        return {"connections": results, "count": len(results)}
    finally:
        db.close()


# ---------------------------------------------------------------
# RETURN TRAINS (rientro al deposito) - con giro materiale
# ---------------------------------------------------------------
@app.get("/return-trains")
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


# ---------------------------------------------------------------
# FR RETURN TRAINS (treni giorno dopo per dormita fuori residenza)
# ---------------------------------------------------------------
@app.get("/fr-return-trains")
def fr_return_trains(
    from_station: str,
    to_station: str,
    current_day_type: str = "LV",
):
    """Trova treni per il rientro al deposito il giorno successivo a una dormita FR.
    Cerca in tutti i day_type possibili del giorno successivo."""
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

        # Cerchiamo TUTTI i treni che passano dalla stazione (taglio treno)
        # Usa find_trains_passing_through per includere anche treni che
        # arrivano alla stazione e poi ripartono (non solo from_station)
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


# ---------------------------------------------------------------
# GIRO NEXT DAY TRAINS (per dormita FR → continuazione giro)
# ---------------------------------------------------------------
@app.get("/giro-next-day-trains")
def giro_next_day_trains(station: str, current_day_type: str = "LV"):
    """Trova giro materiale che iniziano dalla stazione dormita per il giorno dopo.
    Utile per proporre la continuazione giro dopo dormita fuori residenza."""
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


# ---------------------------------------------------------------
# DAY INDEX GROUPS (LV/SAB/DOM inference)
# ---------------------------------------------------------------
@app.get("/day-index-groups")
def day_index_groups():
    """Returns day_index groups inferred as LV/SAB/DOM."""
    db = get_db()
    try:
        return db.get_day_index_groups()
    finally:
        db.close()


# ---------------------------------------------------------------
# DAY VARIANTS
# ---------------------------------------------------------------
@app.get("/day-variants")
def get_day_variants():
    db = get_db()
    try:
        return {"variants": db.get_day_variants()}
    finally:
        db.close()


# ---------------------------------------------------------------
# TRAIN VALIDITY CHECK
# ---------------------------------------------------------------
class CheckValidityRequest(BaseModel):
    train_ids: list[str]
    target_day_type: str  # "SAB" o "DOM"


@app.post("/check-trains-validity")
def check_trains_validity(req: CheckValidityRequest):
    """Verifica se i treni esistono per un dato tipo giorno (SAB/DOM)."""
    db = get_db()
    try:
        result = db.check_trains_for_day_type(req.train_ids, req.target_day_type)
        missing = [tid for tid, info in result.items() if not info["found"]]
        return {
            "results": result,
            "all_valid": len(missing) == 0,
            "missing_trains": missing,
            "target_day_type": req.target_day_type,
        }
    finally:
        db.close()


# ---------------------------------------------------------------
# SAVED SHIFTS
# ---------------------------------------------------------------
class SaveShiftRequest(BaseModel):
    name: str
    deposito: str = ""
    day_type: str = "LV"
    train_ids: list[str]
    deadhead_ids: list[str] = []
    prestazione_min: int = 0
    condotta_min: int = 0
    meal_min: int = 0
    accessori_min: int = 0
    extra_min: int = 0
    is_fr: bool = False
    last_station: str = ""
    violations: list = []
    accessory_type: str = "standard"
    presentation_time: str = ""
    end_time: str = ""


@app.post("/save-shift")
def save_shift(req: SaveShiftRequest, user: dict = Depends(get_current_user)):
    db = get_db()
    try:
        shift_id = db.save_shift(
            name=req.name,
            deposito=req.deposito,
            day_type=req.day_type,
            train_ids=req.train_ids,
            prestazione_min=req.prestazione_min,
            condotta_min=req.condotta_min,
            meal_min=req.meal_min,
            accessori_min=req.accessori_min,
            extra_min=req.extra_min,
            is_fr=req.is_fr,
            last_station=req.last_station,
            violations=req.violations,
            accessory_type=req.accessory_type,
            deadhead_ids=req.deadhead_ids,
            presentation_time=req.presentation_time,
            end_time=req.end_time,
            user_id=user["id"],
        )
        return {"id": shift_id, "status": "saved"}
    finally:
        db.close()


@app.get("/saved-shifts")
def list_saved_shifts(day_type: str = None, user: dict = Depends(get_current_user)):
    db = get_db()
    try:
        uid = None if user["is_admin"] else user["id"]
        shifts = db.get_saved_shifts(day_type=day_type, user_id=uid)
        return {"shifts": shifts, "count": len(shifts)}
    finally:
        db.close()


@app.delete("/saved-shift/{shift_id}")
def delete_saved_shift(shift_id: int, user: dict = Depends(get_current_user)):
    db = get_db()
    try:
        uid = None if user["is_admin"] else user["id"]
        db.delete_saved_shift(shift_id, user_id=uid)
        return {"status": "deleted"}
    finally:
        db.close()


@app.delete("/saved-shifts")
def delete_all_saved_shifts(user: dict = Depends(get_current_user)):
    db = get_db()
    try:
        uid = None if user["is_admin"] else user["id"]
        cur = db._cursor()
        if uid is not None:
            cur.execute(db._q("DELETE FROM saved_shift WHERE user_id = ?"), (uid,))
        else:
            cur.execute("DELETE FROM saved_shift")
        db.conn.commit()
        return {"status": "deleted", "count": cur.rowcount}
    finally:
        db.close()


@app.get("/saved-shift/{shift_id}/timeline")
def saved_shift_timeline(shift_id: int, user: dict = Depends(get_current_user)):
    """Ricalcola timeline completa per un turno salvato."""
    db = get_db()
    try:
        uid = None if user["is_admin"] else user["id"]
        shifts = db.get_saved_shifts(user_id=uid)
        shift = None
        for s in shifts:
            if s.get("id") == shift_id:
                shift = s
                break
        if not shift:
            raise HTTPException(404, "Turno non trovato")

        train_ids = shift.get("train_ids", [])
        if isinstance(train_ids, str):
            import json as _json
            train_ids = _json.loads(train_ids)

        deposito = shift.get("deposito", "")
        accessory_type = shift.get("accessory_type", "standard")

        # Recupera deadhead_ids se salvati
        deadhead_ids = shift.get("deadhead_ids", [])
        if isinstance(deadhead_ids, str):
            import json as _json
            try:
                deadhead_ids = _json.loads(deadhead_ids)
            except Exception:
                deadhead_ids = []

        segments = []
        for tid in train_ids:
            segs = db.query_train(tid)
            segments.extend(segs)

        if not segments:
            return {"timeline": [], "error": "Nessun segmento trovato"}

        segments = _dedup_segments(segments)

        # Marca deadhead
        dh_set = set(deadhead_ids)
        if dh_set:
            for seg in segments:
                if seg.get("train_id") in dh_set:
                    seg["is_deadhead"] = True

        segments.sort(key=lambda s: s["dep_time"])

        # Risolvi accessory_type in valori start/end reali
        acc_opt = ACCESSORY_OPTIONS.get(accessory_type, ACCESSORY_OPTIONS["standard"])
        acc_start_val = acc_opt["start"]
        acc_end_val = acc_opt["end"]

        validator = TurnValidator(deposito=deposito)
        summary = validator.validate_day(segments, deposito=deposito,
                                          acc_start=acc_start_val, acc_end=acc_end_val)
        timeline = _build_timeline_blocks(summary, deposito=deposito, db=db,
                                           acc_start=acc_start_val, acc_end=acc_end_val)

        return {
            "shift_id": shift_id,
            "name": shift.get("name", ""),
            "deposito": deposito,
            "prestazione_min": summary.prestazione_min,
            "condotta_min": summary.condotta_min,
            "meal_min": summary.meal_min,
            "accessori_min": summary.accessori_min,
            "extra_min": summary.extra_min,
            "presentation_time": summary.presentation_time,
            "end_time": summary.end_time,
            "is_fr": summary.is_fr,
            "last_station": summary.last_station,
            "timeline": timeline,
            "segments": _serialize_segments(segments),
            "violations": [
                {"rule": v.rule, "message": v.message, "severity": v.severity}
                for v in summary.violations
            ],
        }
    finally:
        db.close()


@app.get("/used-trains")
def get_used_trains(day_type: str = None, user: dict = Depends(get_current_user)):
    db = get_db()
    try:
        uid = None if user["is_admin"] else user["id"]
        used = db.get_used_train_ids(day_type=day_type, user_id=uid)
        return {"train_ids": used, "count": len(used)}
    finally:
        db.close()


# ---------------------------------------------------------------
# VALIDATE DAY WITH TIMELINE (per builder manuale)
# ---------------------------------------------------------------
@app.post("/validate-day-with-timeline")
def validate_day_timeline(req: ValidateDayRequest):
    db = get_db()
    try:
        segments = []
        custom_train_ids = {cs.train_id for cs in req.custom_segments}
        for tid in req.train_ids:
            if tid in custom_train_ids:
                continue  # skip DB lookup for custom segments
            segs = db.query_train(tid)
            segments.extend(segs)

        # Deduplica PRIMA di aggiungere custom segments (evita che vengano filtrati)
        if segments:
            segments = _dedup_segments(segments)

        # Aggiungi segmenti custom (VT trains non nel DB) DOPO la dedup
        for cs in req.custom_segments:
            segments.append({
                "train_id": cs.train_id,
                "from_station": cs.from_station,
                "to_station": cs.to_station,
                "dep_time": cs.dep_time,
                "arr_time": cs.arr_time,
                "is_deadhead": cs.is_deadhead,
            })

        if not segments:
            raise HTTPException(400, "Nessun segmento trovato per i treni indicati")

        # Marca i treni di rientro come deadhead (vettura, non condotta)
        dh_set = set(req.deadhead_ids)
        if dh_set:
            for seg in segments:
                if seg.get("train_id") in dh_set:
                    seg["is_deadhead"] = True
        segments.sort(key=lambda s: s["dep_time"])

        # Risolvi accessory_type in valori start/end reali
        acc_opt = ACCESSORY_OPTIONS.get(req.accessory_type, ACCESSORY_OPTIONS["standard"])
        acc_start_val = req.acc_start_override if req.acc_start_override is not None else acc_opt["start"]
        acc_end_val = req.acc_end_override if req.acc_end_override is not None else acc_opt["end"]

        validator = TurnValidator(deposito=req.deposito)
        summary = validator.validate_day(segments, deposito=req.deposito,
                                          is_fr_override=req.is_fr,
                                          acc_start=acc_start_val, acc_end=acc_end_val)
        timeline = _build_timeline_blocks(summary, deposito=req.deposito, db=db,
                                           acc_start=acc_start_val, acc_end=acc_end_val)

        return {
            "prestazione_min": summary.prestazione_min,
            "prestazione": _fmt_min(summary.prestazione_min),
            "limite_prestazione": _fmt_min(MAX_PRESTAZIONE_MIN),
            "condotta_min": summary.condotta_min,
            "condotta": _fmt_min(summary.condotta_min),
            "limite_condotta": _fmt_min(MAX_CONDOTTA_MIN),
            "meal_min": summary.meal_min,
            "accessori_min": summary.accessori_min,
            "tempi_medi_min": summary.tempi_medi_min,
            "extra_min": summary.extra_min,
            "night_minutes": summary.night_minutes,
            "day_type": summary.day_type,
            "presentation_time": summary.presentation_time,
            "end_time": summary.end_time,
            "is_fr": summary.is_fr,
            "last_station": summary.last_station,
            "meal_start": summary.meal_start,
            "meal_end": summary.meal_end,
            "segments": _serialize_segments(segments),
            "timeline": timeline,
            "violations": [
                {"rule": v.rule, "message": v.message, "severity": v.severity}
                for v in summary.violations
            ],
            "valid": len(summary.violations) == 0,
        }
    finally:
        db.close()


# =====================================================================
# WEEKLY SHIFT ENDPOINTS
# =====================================================================

class BuildWeeklyRequest(BaseModel):
    deposito: str
    n_days: int = 5
    exclude_trains: list[str] = []
    accessory_type: str = "standard"


@app.post("/build-weekly")
def build_weekly(req: BuildWeeklyRequest):
    """Genera un turno settimanale unificato (LMXGV + S + D per ogni giornata)."""
    from src.turn_builder.auto_builder import AutoBuilder
    db = Database()
    try:
        builder = AutoBuilder(db, deposito=req.deposito)
        result = builder.build_weekly_schedule(
            n_workdays=req.n_days,
            exclude_trains=req.exclude_trains,
        )
        return result
    except Exception as e:
        raise HTTPException(500, detail=str(e))
    finally:
        db.close()


class SaveWeeklyRequest(BaseModel):
    name: str
    deposito: str
    days: list[dict]
    accessory_type: str = "standard"
    notes: str = ""


@app.post("/save-weekly-shift")
def save_weekly_shift(req: SaveWeeklyRequest, user: dict = Depends(get_current_user)):
    """Salva un turno settimanale nel database."""
    db = get_db()
    try:
        weekly_id = db.save_weekly_shift(
            name=req.name,
            deposito=req.deposito,
            days=req.days,
            accessory_type=req.accessory_type,
            notes=req.notes,
            user_id=user["id"],
        )
        return {"id": weekly_id, "message": "Turno settimanale salvato"}
    except Exception as e:
        raise HTTPException(500, detail=str(e))
    finally:
        db.close()


@app.get("/weekly-shifts")
def get_weekly_shifts_endpoint(user: dict = Depends(get_current_user)):
    """Restituisce i turni settimanali dell'utente (admin vede tutti)."""
    db = get_db()
    try:
        uid = None if user["is_admin"] else user["id"]
        shifts = db.get_weekly_shifts(user_id=uid)
        return {"shifts": shifts}
    except Exception as e:
        raise HTTPException(500, detail=str(e))
    finally:
        db.close()


@app.delete("/weekly-shift/{weekly_id}")
def delete_weekly_shift(weekly_id: int, user: dict = Depends(get_current_user)):
    """Elimina un turno settimanale."""
    db = get_db()
    try:
        uid = None if user["is_admin"] else user["id"]
        db.delete_weekly_shift(weekly_id, user_id=uid)
        return {"message": "Turno settimanale eliminato"}
    except Exception as e:
        raise HTTPException(500, detail=str(e))
    finally:
        db.close()


@app.post("/upload-turno-personale")
async def upload_turno_personale(file: UploadFile = File(...)):
    """Importa un PDF di Turno Personale per confronto/modifica."""
    from src.importer.turno_personale_parser import (
        parse_turno_personale_pdf, personal_shift_to_dict,
    )

    content = await file.read()
    if not content:
        raise HTTPException(400, detail="File vuoto")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        shift = parse_turno_personale_pdf(tmp_path)
        result = personal_shift_to_dict(shift)
        result["source_file"] = file.filename
        result["pages_parsed"] = (shift.raw_text or "").count("--- PAGE ---") + 1

        # Se il parser non ha trovato giornate, prova a restituire almeno il testo
        if not result.get("days"):
            raw_preview = (shift.raw_text or "")[:500]
            result["parse_warning"] = (
                f"Nessuna giornata trovata nel PDF. "
                f"Potrebbe essere un formato non supportato. "
                f"Prime righe: {raw_preview}"
            )
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, detail=f"Errore parsing turno personale: {str(e)}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# ---------------------------------------------------------------
# TURNO PDC - Import e ricerca
# ---------------------------------------------------------------

@app.post("/upload-turno-pdc")
async def upload_turno_pdc(file: UploadFile = File(...)):
    """Importa il PDF Turni PdC rete RFI nel database."""
    from src.importer.turno_pdc_parser import parse_pdc_pdf

    content = await file.read()
    if not content:
        raise HTTPException(400, detail="File vuoto")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        turni = parse_pdc_pdf(tmp_path)
        if not turni:
            raise HTTPException(400, detail="Nessun turno PdC trovato nel PDF")

        db = get_db()
        count = db.import_pdc_turni(turni, source_file=file.filename or "turno_pdc.pdf")
        stats = db.pdc_get_stats()

        return {
            "status": "ok",
            "turni_imported": count,
            "stats": stats,
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, detail=f"Errore parsing turno PdC: {str(e)}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@app.get("/pdc-stats")
async def pdc_stats():
    """Statistiche dei turni PdC importati."""
    db = get_db()
    return db.pdc_get_stats()


@app.get("/pdc-find-train/{train_id}")
async def pdc_find_train(train_id: str):
    """Cerca un treno nei turni PdC."""
    db = get_db()
    results = db.pdc_find_train(train_id)
    return {"train_id": train_id, "found": len(results) > 0, "results": results}


@app.get("/train-check/{train_id}")
async def train_check(train_id: str):
    """Triple-check: cerca un treno in DB interno, Turno PdC e ViaggiaTreno."""
    db = get_db()
    result = {
        "train_id": train_id,
        "db_internal": {"found": False, "data": None},
        "pdc": {"found": False, "results": []},
        "viaggiatreno": {"found": False, "data": None},
    }

    # 1. DB Interno (giro materiale)
    try:
        segments = db.query_train(train_id)
        if segments:
            seg = segments[0]
            # Cerca il giro completo
            giro = db.get_giro_chain_context(train_id)
            result["db_internal"] = {
                "found": True,
                "data": {
                    "from_station": seg["from_station"],
                    "dep_time": seg["dep_time"],
                    "to_station": seg["to_station"],
                    "arr_time": seg["arr_time"],
                    "material_turn_id": seg.get("material_turn_id"),
                    "day_index": seg.get("day_index", 0),
                    "is_deadhead": bool(seg.get("is_deadhead", 0)),
                    "giro_chain_len": len(giro.get("chain", [])) if giro else 0,
                },
            }
    except Exception:
        pass

    # 2. Turno PdC
    try:
        pdc_results = db.pdc_find_train(train_id)
        if pdc_results:
            result["pdc"] = {"found": True, "results": pdc_results}
    except Exception:
        pass

    # 3. ViaggiaTreno (real-time)
    try:
        async with httpx.AsyncClient(timeout=_VT_TIMEOUT) as client:
            # Cerca il treno
            search_url = f"{_VT_BASE}/cercaNumeroTrenoTrenoAutocomplete/{train_id}"
            resp = await client.get(search_url)
            if resp.status_code == 200 and resp.text.strip():
                lines = resp.text.strip().split("\n")
                if lines and lines[0].strip():
                    first_line = lines[0].strip()
                    # Format: "10045 - MILANO CADORNA - 08/03/26|10045-S01066-1772924400000"
                    parts = first_line.split("|")
                    if len(parts) >= 2:
                        # Parse codice: "10045-S01066-1772924400000"
                        code_parts = parts[-1].strip().split("-")
                        origin_code = ""
                        for cp in code_parts:
                            if cp.startswith("S") and len(cp) >= 4 and cp[1:].isdigit():
                                origin_code = cp
                                break
                        # Prova andamentoTreno
                        if origin_code:
                            ts = _vt_midnight_ms()
                            anda_url = f"{_VT_BASE}/andamentoTreno/{origin_code}/{train_id}/{ts}"
                            resp2 = await client.get(anda_url)
                            if resp2.status_code == 200:
                                try:
                                    data = resp2.json()
                                    if data:
                                        # Estrai info essenziali
                                        fermate = data.get("fermate", [])
                                        first_stop = fermate[0] if fermate else {}
                                        last_stop = fermate[-1] if fermate else {}
                                        dep_t = _vt_ts_to_str(first_stop.get("partenza_teorica"))
                                        arr_t = _vt_ts_to_str(last_stop.get("arrivo_teorico"))
                                        # Operatore
                                        operator = (data.get("compTipologiaTreno")
                                                    or data.get("compRifwordsLingua")
                                                    or data.get("compNumeroTreno", "")
                                                    or "")
                                        is_trenord = "TRENORD" in operator.upper() if operator else False
                                        result["viaggiatreno"] = {
                                            "found": True,
                                            "data": {
                                                "operator": operator,
                                                "category": data.get("categoriaDescrizione", data.get("categoria", "")) or "",
                                                "origin": data.get("origine", "") or "",
                                                "destination": data.get("destinazione", "") or "",
                                                "dep_time": dep_t,
                                                "arr_time": arr_t,
                                                "num_stops": len(fermate),
                                                "delay": data.get("ritardo", 0),
                                                "is_trenord": is_trenord,
                                                "status": "circolante" if data.get("oraUltimoRilevamento") else "non partito",
                                            },
                                        }
                                except Exception:
                                    pass
    except Exception:
        pass

    return result


# ---------------------------------------------------------------
# VIAGGIATRENO API PROXY  (no auth, no CORS issues)
# ---------------------------------------------------------------
import httpx
from datetime import datetime as _dt, timedelta as _td
from zoneinfo import ZoneInfo
import time as _time
from urllib.parse import quote as _url_quote

_VT_BASE = "http://www.viaggiatreno.it/infomobilita/resteasy/viaggiatreno"
_VT_TIMEOUT = 12.0  # seconds
_ROME_TZ = ZoneInfo("Europe/Rome")

# Locale-independent day/month names (VT expects English)
_DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _now_rome() -> _dt:
    """Current datetime in Europe/Rome (handles CET/CEST automatically)."""
    return _dt.now(_ROME_TZ)


def _vt_datetime_param(date_str: str | None = None, time_str: str | None = None) -> str:
    """Build JS‑style datetime string accepted by ViaggiaTreno.
    e.g. 'Sun Mar 08 2026 14:30:00 GMT+0100' (URL-encoded).

    If the requested time is more than 1h in the past (today), automatically
    uses tomorrow's date so VT returns data instead of an empty list.
    """
    now = _now_rome()
    if date_str:
        try:
            d = _dt.strptime(date_str, "%Y-%m-%d").replace(tzinfo=_ROME_TZ)
        except ValueError:
            d = now
    else:
        d = now
    if time_str:
        parts = time_str.split(":")
        h = int(parts[0]) if len(parts) > 0 else now.hour
        m = int(parts[1]) if len(parts) > 1 else 0
    else:
        h, m = now.hour, now.minute
    target = d.replace(hour=h, minute=m, second=0, microsecond=0)

    # If no explicit date was provided and the target time is >1h in the past,
    # use tomorrow instead (VT only returns data for a ~2h window around now)
    if not date_str and (now - target).total_seconds() > 3600:
        target += _td(days=1)

    # Compute the UTC offset for the target date (handles CET/CEST)
    utc_off = target.strftime("%z")  # e.g. '+0100' or '+0200'
    if not utc_off:
        utc_off = "+0100"
    gmt_str = f"GMT{utc_off}"

    # Use locale-independent day/month names
    day_name = _DAY_NAMES[target.weekday()]
    month_name = _MONTH_NAMES[target.month - 1]
    formatted = f"{day_name} {month_name} {target.day:02d} {target.year} {target.hour:02d}:{target.minute:02d}:{target.second:02d} {gmt_str}"

    # URL-encode for safe use in URL path segments
    return _url_quote(formatted, safe="")


def _vt_midnight_ms(date_str: str | None = None) -> int:
    """Return midnight timestamp in ms for ViaggiaTreno (Rome timezone)."""
    if date_str:
        try:
            d = _dt.strptime(date_str, "%Y-%m-%d")
            d = d.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=_ROME_TZ)
        except ValueError:
            d = _now_rome().replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        d = _now_rome().replace(hour=0, minute=0, second=0, microsecond=0)
    return int(d.timestamp()) * 1000


def _vt_ts_to_str(ms) -> str:
    """Convert VT millisecond timestamp to HH:MM string in Rome timezone."""
    if not ms:
        return ""
    try:
        return _dt.fromtimestamp(ms / 1000, tz=_ROME_TZ).strftime("%H:%M")
    except Exception:
        return ""


@app.get("/vt/autocomplete-station")
def vt_autocomplete_station(q: str):
    """Autocomplete stazione ViaggiaTreno."""
    try:
        r = httpx.get(f"{_VT_BASE}/autocompletaStazione/{q}", timeout=_VT_TIMEOUT)
        r.raise_for_status()
        lines = r.text.strip().split("\n")
        results = []
        for line in lines:
            if "|" in line:
                name, code = line.rsplit("|", 1)
                results.append({"name": name.strip(), "code": code.strip()})
        return {"stations": results}
    except Exception as e:
        raise HTTPException(502, detail=f"ViaggiaTreno non raggiungibile: {e}")


@app.get("/vt/departures")
def vt_departures(
    station_code: str,
    date: str | None = None,
    time: str | None = None,
    only_trenord: bool = True,
):
    """Partenze da una stazione. station_code = es. S01700 (Milano C.le)."""
    dt_param = _vt_datetime_param(date, time)
    url = f"{_VT_BASE}/partenze/{station_code}/{dt_param}"
    try:
        r = httpx.get(url, timeout=_VT_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        raise HTTPException(502, detail=f"ViaggiaTreno errore: {e}")

    results = []
    for t in data:
        if only_trenord and t.get("codiceCliente") != 63:
            continue
        dep_ms = t.get("orarioPartenza")
        dep_time = ""
        if dep_ms:
            dep_time = _vt_ts_to_str(dep_ms)
        results.append({
            "train_number": t.get("numeroTreno"),
            "category": (t.get("categoriaDescrizione") or "").strip(),
            "origin": t.get("codOrigine"),
            "destination": t.get("destinazione"),
            "dep_time": t.get("compOrarioPartenza") or dep_time,
            "delay": t.get("ritardo", 0),
            "platform_scheduled": t.get("binarioProgrammatoPartenzaDescrizione"),
            "platform_actual": t.get("binarioEffettivoPartenzaDescrizione"),
            "running": t.get("circolante", False),
            "operator_code": t.get("codiceCliente"),
        })
    return {"station_code": station_code, "departures": results, "count": len(results)}


@app.get("/vt/arrivals")
def vt_arrivals(
    station_code: str,
    date: str | None = None,
    time: str | None = None,
    only_trenord: bool = True,
):
    """Arrivi a una stazione."""
    dt_param = _vt_datetime_param(date, time)
    url = f"{_VT_BASE}/arrivi/{station_code}/{dt_param}"
    try:
        r = httpx.get(url, timeout=_VT_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        raise HTTPException(502, detail=f"ViaggiaTreno errore: {e}")

    results = []
    for t in data:
        if only_trenord and t.get("codiceCliente") != 63:
            continue
        arr_ms = t.get("orarioArrivo")
        arr_time = ""
        if arr_ms:
            arr_time = _vt_ts_to_str(arr_ms)
        results.append({
            "train_number": t.get("numeroTreno"),
            "category": (t.get("categoriaDescrizione") or "").strip(),
            "origin": t.get("origine"),
            "destination": t.get("destinazione"),
            "arr_time": t.get("compOrarioArrivo") or arr_time,
            "delay": t.get("ritardo", 0),
            "platform_scheduled": t.get("binarioProgrammatoArrivoDescrizione"),
            "platform_actual": t.get("binarioEffettivoArrivoDescrizione"),
            "running": t.get("circolante", False),
            "operator_code": t.get("codiceCliente"),
        })
    return {"station_code": station_code, "arrivals": results, "count": len(results)}


@app.get("/vt/train-info")
def vt_train_info(train_number: int, date: str | None = None):
    """Dettaglio treno con fermate e ritardi in tempo reale."""
    # Step 1: lookup origin station + midnight timestamp
    try:
        r = httpx.get(
            f"{_VT_BASE}/cercaNumeroTrenoTrenoAutocomplete/{train_number}",
            timeout=_VT_TIMEOUT,
        )
        r.raise_for_status()
        text = r.text.strip()
    except Exception as e:
        raise HTTPException(502, detail=f"ViaggiaTreno lookup errore: {e}")

    if not text or "|" not in text:
        raise HTTPException(404, detail=f"Treno {train_number} non trovato su ViaggiaTreno")

    # Parse: "10801 - BRESCIA - 08/03/26|10801-S01717-1772924400000"
    right = text.split("|")[-1]  # 10801-S01717-1772924400000
    parts = right.split("-")
    if len(parts) < 3:
        raise HTTPException(500, detail=f"Formato risposta inatteso: {text}")
    origin_code = parts[1]
    midnight_ts = parts[2]

    # Se l'utente ha specificato una data diversa, ricalcola il midnight
    if date:
        midnight_ts = str(_vt_midnight_ms(date))

    # Step 2: get andamentoTreno
    try:
        r2 = httpx.get(
            f"{_VT_BASE}/andamentoTreno/{origin_code}/{train_number}/{midnight_ts}",
            timeout=_VT_TIMEOUT,
        )
        r2.raise_for_status()
        data = r2.json()
    except Exception as e:
        raise HTTPException(502, detail=f"ViaggiaTreno andamento errore: {e}")

    # Build clean response
    stops = []
    for f in data.get("fermate", []):
        prog_dep = f.get("partenza_teorica") or f.get("programmata")
        prog_arr = f.get("arrivo_teorico") or f.get("programmata")
        eff_dep = f.get("partenzaReale")
        eff_arr = f.get("arrivoReale")

        dep_str = _vt_ts_to_str(prog_dep) or None
        arr_str = _vt_ts_to_str(prog_arr) or None
        eff_dep_str = _vt_ts_to_str(eff_dep) or None
        eff_arr_str = _vt_ts_to_str(eff_arr) or None

        stops.append({
            "station": f.get("stazione"),
            "station_code": f.get("id"),
            "scheduled_dep": dep_str,
            "scheduled_arr": arr_str,
            "actual_dep": eff_dep_str,
            "actual_arr": eff_arr_str,
            "delay_dep": f.get("ritardoPartenza", 0),
            "delay_arr": f.get("ritardoArrivo", 0),
            "platform_scheduled": f.get("binarioProgrammatoPartenzaDescrizione"),
            "platform_actual": f.get("binarioEffettivoPartenzaDescrizione"),
            "stop_type": f.get("tipoFermata"),  # P=partenza, F=fermata, A=arrivo
            "cancelled": f.get("actualFermataType") == 3,
        })

    status_map = {
        "PG": "regolare",
        "ST": "soppresso",
        "DV": "deviato",
        "SI": "parzialmente_soppresso",
        "SF": "parzialmente_soppresso",
    }

    return {
        "train_number": train_number,
        "origin_code": origin_code,
        "operator_code": data.get("codiceCliente"),
        "is_trenord": data.get("codiceCliente") == 63,
        "status": status_map.get(data.get("tipoTreno", ""), data.get("tipoTreno", "")),
        "last_update": data.get("oraUltimoRilevamento"),
        "delay": data.get("ritardo", 0),
        "stops": stops,
        "cancelled_stops": [s.get("stazione") for s in data.get("fermateSoppresse", [])],
    }


@app.get("/vt/solutions")
def vt_solutions(
    from_station: str,
    to_station: str,
    date: str | None = None,
    time: str | None = None,
):
    """Cerca soluzioni di viaggio tra due stazioni (partenze/arrivi filtrati)."""
    # Prima cerca partenze dalla stazione di origine
    dt_param = _vt_datetime_param(date, time)
    url = f"{_VT_BASE}/partenze/{from_station}/{dt_param}"
    try:
        r = httpx.get(url, timeout=_VT_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        raise HTTPException(502, detail=f"ViaggiaTreno errore: {e}")

    # Filtra treni che hanno come destinazione la stazione richiesta
    to_upper = to_station.upper().replace("S", "").strip()
    results = []
    for t in data:
        dest = (t.get("destinazione") or "").upper()
        dep_ms = t.get("orarioPartenza")
        dep_time = ""
        if dep_ms:
            dep_time = _vt_ts_to_str(dep_ms)
        results.append({
            "train_number": t.get("numeroTreno"),
            "category": (t.get("categoriaDescrizione") or "").strip(),
            "destination": t.get("destinazione"),
            "dep_time": t.get("compOrarioPartenza") or dep_time,
            "delay": t.get("ritardo", 0),
            "running": t.get("circolante", False),
            "operator_code": t.get("codiceCliente"),
            "is_trenord": t.get("codiceCliente") == 63,
        })

    return {"from": from_station, "departures": results, "count": len(results)}


# --- Cache codici stazione ---
_station_code_cache: dict[str, str] = {}


def _resolve_station_code(station_name: str) -> str | None:
    """Risolvi nome stazione -> codice ViaggiaTreno (es. 'MILANO ROGOREDO' -> 'S01820')."""
    name_upper = station_name.strip().upper()
    if name_upper in _station_code_cache:
        return _station_code_cache[name_upper]
    try:
        r = httpx.get(
            f"{_VT_BASE}/autocompletaStazione/{name_upper}",
            timeout=_VT_TIMEOUT,
        )
        if r.status_code == 200 and r.text.strip():
            for line in r.text.strip().split("\n"):
                if "|" in line:
                    n, code = line.rsplit("|", 1)
                    n_upper = n.strip().upper()
                    _station_code_cache[n_upper] = code.strip()
                    if n_upper == name_upper:
                        return code.strip()
            # Se non c'è match esatto, prendi il primo
            first_line = r.text.strip().split("\n")[0]
            if "|" in first_line:
                _, code = first_line.rsplit("|", 1)
                _station_code_cache[name_upper] = code.strip()
                return code.strip()
    except Exception:
        pass
    return None


def _vt_get_train_detail(train_num):
    """Cerca dettaglio treno VT: lookup autocomplete → andamentoTreno. Restituisce (detail_json, origin_code) o (None, None)."""
    try:
        lookup_r = httpx.get(
            f"{_VT_BASE}/cercaNumeroTrenoTrenoAutocomplete/{train_num}",
            timeout=8,
        )
        if lookup_r.status_code != 200 or not lookup_r.text.strip() or "|" not in lookup_r.text:
            return None, None
        right = lookup_r.text.strip().split("|")[-1]
        parts = right.split("-")
        if len(parts) < 3:
            return None, None
        origin_code = parts[1]
        midnight_ts = parts[2]

        detail_r = httpx.get(
            f"{_VT_BASE}/andamentoTreno/{origin_code}/{train_num}/{midnight_ts}",
            timeout=8,
        )
        if detail_r.status_code != 200:
            return None, None
        return detail_r.json(), origin_code
    except Exception:
        return None, None


def _vt_extract_stop_info(fermate, station_code, station_name_upper):
    """Cerca una fermata nel percorso di un treno. Restituisce il dict fermata o None."""
    for fermata in fermate:
        fermata_name = (fermata.get("stazione") or "").upper()
        fermata_id = (fermata.get("id") or "").upper()
        if fermata_id == station_code.upper() or fermata_name == station_name_upper:
            return fermata
    return None


def _vt_fermata_to_times(fermata):
    """Estrae orari dep/arr da una fermata VT. Restituisce (dep_str, dep_real, arr_str, arr_real)."""
    dep_prog = fermata.get("partenza_teorica") or fermata.get("programmata")
    dep_real = fermata.get("partenzaReale")
    arr_prog = fermata.get("arrivo_teorico") or fermata.get("programmata")
    arr_real = fermata.get("arrivoReale")

    return _vt_ts_to_str(dep_prog), _vt_ts_to_str(dep_real), _vt_ts_to_str(arr_prog), _vt_ts_to_str(arr_real)


@app.get("/vt/find-return")
def vt_find_return(
    from_station: str,
    to_station: str,
    after_time: str = "00:00",
    max_check: int = 20,
):
    """Cerca treni REALI (ViaggiaTreno) per rientrare al deposito.

    Strategia DOPPIA:
      A) Cerca ARRIVI al deposito → per ogni treno verifica se passa dalla stazione corrente
      B) Cerca PARTENZE dalla stazione corrente → per ogni treno verifica se arriva al deposito

    La strategia A trova molti piu treni perche cerca direttamente chi arriva al deposito,
    inclusi treni che non partono dalla nostra stazione ma ci passano.
    """
    # Step 1: map station names to codes
    from_code = _resolve_station_code(from_station)
    to_code = _resolve_station_code(to_station)

    if not from_code:
        return {"return_trains": [], "error": f"Stazione '{from_station}' non trovata su ViaggiaTreno"}
    if not to_code:
        return {"return_trains": [], "error": f"Stazione '{to_station}' non trovata su ViaggiaTreno"}

    from_name_upper = from_station.strip().upper()
    to_name_upper = to_station.strip().upper()
    after_min = _time_to_min(after_time)

    return_trains = []
    seen_trains = set()  # evita duplicati
    total_checked = 0

    # ━━━ STRATEGIA A: Cerca ARRIVI al deposito ━━━
    dt_param = _vt_datetime_param(None, after_time)
    try:
        r = httpx.get(f"{_VT_BASE}/arrivi/{to_code}/{dt_param}", timeout=_VT_TIMEOUT)
        if r.status_code == 200:
            arrivals = r.json()
            trenord_arrivals = [t for t in arrivals if t.get("codiceCliente") == 63][:max_check]
            total_checked += len(trenord_arrivals)

            for t in trenord_arrivals:
                train_num = t.get("numeroTreno")
                if not train_num or train_num in seen_trains:
                    continue

                # Orario arrivo al deposito
                arr_ms = t.get("orarioArrivo")
                arr_time_str = t.get("compOrarioArrivo") or ""
                if not arr_time_str and arr_ms:
                    arr_time_str = _vt_ts_to_str(arr_ms)

                # Verifica che il treno passi dalla nostra stazione corrente
                # Serve andamentoTreno per controllare le fermate
                try:
                    detail, _ = _vt_get_train_detail(train_num)
                    if not detail:
                        continue
                    fermate = detail.get("fermate", [])

                    # Cerca la fermata di partenza (from_station) E la fermata di arrivo (to_station)
                    from_fermata = None
                    to_fermata = None
                    found_from = False
                    for fermata in fermate:
                        fermata_name = (fermata.get("stazione") or "").upper()
                        fermata_id = (fermata.get("id") or "").upper()

                        if not found_from:
                            if fermata_id == from_code.upper() or fermata_name == from_name_upper:
                                from_fermata = fermata
                                found_from = True
                        else:
                            if fermata_id == to_code.upper() or fermata_name == to_name_upper:
                                to_fermata = fermata
                                break

                    if not from_fermata or not to_fermata:
                        continue  # Non passa dalla nostra stazione

                    # Estrai orari
                    dep_str, dep_real, _, _ = _vt_fermata_to_times(from_fermata)
                    _, _, arr_str, arr_real = _vt_fermata_to_times(to_fermata)

                    # Filtra: partenza dopo after_time
                    if dep_str:
                        dep_min = _time_to_min(dep_str)
                        if dep_min < after_min and dep_min + 1440 >= after_min:
                            dep_min += 1440
                        if dep_min < after_min:
                            continue

                    seen_trains.add(train_num)
                    origin_upper = (detail.get("origine") or "").upper()
                    dest_upper = (detail.get("destinazione") or "").upper()

                    return_trains.append({
                        "train_number": train_num,
                        "category": (detail.get("categoriaDescrizione") or detail.get("categoria") or "").strip(),
                        "from_station": from_name_upper,
                        "to_station": to_name_upper,
                        "dep_time": dep_str,
                        "arr_time": arr_str,
                        "arr_time_real": arr_real,
                        "delay": t.get("ritardo", 0),
                        "delay_arr": to_fermata.get("ritardoArrivo", 0),
                        "platform": t.get("binarioEffettivoArrivoDescrizione")
                            or t.get("binarioProgrammatoArrivoDescrizione")
                            or "",
                        "destination_finale": dest_upper,
                        "origin_treno": origin_upper,
                        "running": t.get("circolante", False),
                        "via_viaggiatreno": True,
                        "source": "arrivi",
                    })
                except Exception as e:
                    print(f"[VT-arrivi] Errore check treno {train_num}: {e}")
                    continue
    except Exception as e:
        print(f"[VT] Errore arrivi al deposito: {e}")

    # ━━━ STRATEGIA B: Cerca PARTENZE dalla stazione corrente (fallback/complementare) ━━━
    try:
        r = httpx.get(f"{_VT_BASE}/partenze/{from_code}/{dt_param}", timeout=_VT_TIMEOUT)
        if r.status_code == 200:
            departures = r.json()
            trenord_deps = [t for t in departures if t.get("codiceCliente") == 63][:max_check]
            total_checked += len(trenord_deps)

            for t in trenord_deps:
                train_num = t.get("numeroTreno")
                if not train_num or train_num in seen_trains:
                    continue

                dep_ms = t.get("orarioPartenza")
                dep_time_str = t.get("compOrarioPartenza") or ""
                if not dep_time_str and dep_ms:
                    dep_time_str = _vt_ts_to_str(dep_ms)
                dest_upper = (t.get("destinazione") or "").upper()

                try:
                    detail, _ = _vt_get_train_detail(train_num)
                    if not detail:
                        continue
                    fermate = detail.get("fermate", [])

                    # Cerca from_station PRIMA di to_station
                    found_from = False
                    found_dep_stop = None
                    for fermata in fermate:
                        fermata_name = (fermata.get("stazione") or "").upper()
                        fermata_id = (fermata.get("id") or "").upper()
                        if not found_from:
                            if fermata_id == from_code.upper() or fermata_name == from_name_upper:
                                found_from = True
                            continue
                        if fermata_name == to_name_upper or fermata_id == to_code.upper():
                            found_dep_stop = fermata
                            break

                    if found_dep_stop:
                        arr_prog = found_dep_stop.get("arrivo_teorico") or found_dep_stop.get("programmata")
                        arr_real = found_dep_stop.get("arrivoReale")
                        arr_time_str = _vt_ts_to_str(arr_prog)
                        arr_real_str = _vt_ts_to_str(arr_real)

                        seen_trains.add(train_num)
                        return_trains.append({
                            "train_number": train_num,
                            "category": (t.get("categoriaDescrizione") or "").strip(),
                            "from_station": from_name_upper,
                            "to_station": to_name_upper,
                            "dep_time": dep_time_str,
                            "arr_time": arr_time_str,
                            "arr_time_real": arr_real_str,
                            "delay": t.get("ritardo", 0),
                            "delay_arr": found_dep_stop.get("ritardoArrivo", 0),
                            "platform": t.get("binarioEffettivoPartenzaDescrizione")
                                or t.get("binarioProgrammatoPartenzaDescrizione"),
                            "destination_finale": dest_upper,
                            "running": t.get("circolante", False),
                            "via_viaggiatreno": True,
                            "source": "partenze",
                        })
                except Exception as e:
                    print(f"[VT-partenze] Errore check treno {train_num}: {e}")
                    continue
    except Exception as e:
        print(f"[VT] Errore partenze: {e}")

    # Ordina per orario partenza
    return_trains.sort(key=lambda x: x.get("dep_time", "99:99"))

    return {
        "return_trains": return_trains,
        "from_code": from_code,
        "to_code": to_code,
        "checked": total_checked,
    }


# ---------------------------------------------------------------
# VT ALL DEPARTURES (tutte le partenze da una stazione, senza filtro dest)
# ---------------------------------------------------------------
@app.get("/vt/all-departures")
def vt_all_departures(station: str, after_time: str = "00:00"):
    """Restituisce TUTTE le partenze Trenord da una stazione (ViaggiaTreno).

    Utile per la dormita: trova treni che PASSANO da una stazione,
    anche quelli non nel DB locale. Non filtra per destinazione.
    """
    code = _resolve_station_code(station)
    if not code:
        return {"departures": [], "error": f"Stazione '{station}' non trovata su ViaggiaTreno"}

    dt_param = _vt_datetime_param(None, after_time)
    after_min = _time_to_min(after_time)
    results = []

    try:
        vt_url = f"{_VT_BASE}/partenze/{code}/{dt_param}"
        print(f"[VT all-deps] GET {vt_url}")
        r = httpx.get(vt_url, timeout=_VT_TIMEOUT)
        print(f"[VT all-deps] status={r.status_code}, len={len(r.text)}")
        if r.status_code == 200:
            deps = r.json()
            print(f"[VT all-deps] total trains: {len(deps)}")
            # Solo Trenord (codiceCliente 63)
            trenord = [t for t in deps if t.get("codiceCliente") == 63]
            print(f"[VT all-deps] Trenord trains: {len(trenord)}")
            for t in trenord:
                train_num = t.get("numeroTreno")
                if not train_num:
                    continue
                dep_time = t.get("compOrarioPartenza") or ""
                dep_ms = t.get("orarioPartenza")
                if not dep_time and dep_ms:
                    dep_time = _vt_ts_to_str(dep_ms)
                # Filtra per after_time
                if dep_time:
                    dep_min = _time_to_min(dep_time)
                    if dep_min < after_min:
                        continue

                results.append({
                    "train_number": train_num,
                    "from_station": station.strip().upper(),
                    "to_station": (t.get("destinazione") or "").upper(),
                    "dep_time": dep_time,
                    "delay": t.get("ritardo", 0),
                    "running": t.get("circolante", False),
                })
    except Exception as e:
        return {"departures": [], "error": str(e)}

    results.sort(key=lambda x: x.get("dep_time", "99:99"))
    return {"departures": results, "station_code": code}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)
