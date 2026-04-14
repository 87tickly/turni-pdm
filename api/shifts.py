"""
Router turni salvati: salvataggio, lista, eliminazione, timeline, turni settimanali.
"""

import json

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from api.deps import get_db, get_current_user
from services.segments import dedup_segments, serialize_segments
from services.timeline import build_timeline_blocks
from src.validator.rules import TurnValidator
from src.constants import ACCESSORY_OPTIONS

router = APIRouter()


# ── Request models ──────────────────────────────────────────────

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


class SaveWeeklyRequest(BaseModel):
    name: str
    deposito: str
    days: list[dict]
    accessory_type: str = "standard"
    notes: str = ""


# ── Endpoints ───────────────────────────────────────────────────

@router.post("/save-shift")
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


@router.get("/saved-shifts")
def list_saved_shifts(day_type: str = None, user: dict = Depends(get_current_user)):
    db = get_db()
    try:
        uid = None if user["is_admin"] else user["id"]
        shifts = db.get_saved_shifts(day_type=day_type, user_id=uid)
        return {"shifts": shifts, "count": len(shifts)}
    finally:
        db.close()


@router.delete("/saved-shift/{shift_id}")
def delete_saved_shift(shift_id: int, user: dict = Depends(get_current_user)):
    db = get_db()
    try:
        uid = None if user["is_admin"] else user["id"]
        db.delete_saved_shift(shift_id, user_id=uid)
        return {"status": "deleted"}
    finally:
        db.close()


@router.delete("/saved-shifts")
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


@router.get("/saved-shift/{shift_id}/timeline")
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
            train_ids = json.loads(train_ids)

        deposito = shift.get("deposito", "")
        accessory_type = shift.get("accessory_type", "standard")

        # Recupera deadhead_ids se salvati
        deadhead_ids = shift.get("deadhead_ids", [])
        if isinstance(deadhead_ids, str):
            try:
                deadhead_ids = json.loads(deadhead_ids)
            except Exception:
                deadhead_ids = []

        segments = []
        for tid in train_ids:
            segs = db.query_train(tid)
            segments.extend(segs)

        if not segments:
            return {"timeline": [], "error": "Nessun segmento trovato"}

        segments = dedup_segments(segments)

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
        timeline = build_timeline_blocks(summary, deposito=deposito, db=db,
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
            "segments": serialize_segments(segments),
            "violations": [
                {"rule": v.rule, "message": v.message, "severity": v.severity}
                for v in summary.violations
            ],
        }
    finally:
        db.close()


@router.get("/used-trains")
def get_used_trains(day_type: str = None, user: dict = Depends(get_current_user)):
    db = get_db()
    try:
        uid = None if user["is_admin"] else user["id"]
        used = db.get_used_train_ids(day_type=day_type, user_id=uid)
        return {"train_ids": used, "count": len(used)}
    finally:
        db.close()


@router.post("/save-weekly-shift")
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


@router.get("/weekly-shifts")
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


@router.delete("/weekly-shift/{weekly_id}")
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
