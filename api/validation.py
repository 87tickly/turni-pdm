"""
Router validazione giornata, costanti operative, check validita' treni.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.deps import get_db
from services.segments import dedup_segments, serialize_segments
from services.timeline import build_timeline_blocks
from src.validator.rules import TurnValidator, _fmt_min, _time_to_min
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

router = APIRouter()


# ── Request models ──────────────────────────────────────────────

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
    deadhead_ids: list[str] = []
    custom_segments: list[CustomSegment] = []
    is_fr: bool = False
    acc_start_override: int | None = None
    acc_end_override: int | None = None


class CheckValidityRequest(BaseModel):
    train_ids: list[str]
    target_day_type: str


# ── Helpers ─────────────────────────────────────────────────────

def _validate_day_common(req: ValidateDayRequest, force_timeline: bool = False):
    """Logica condivisa tra validate-day e validate-day-with-timeline."""
    db = get_db()
    try:
        segments = []
        custom_train_ids = {cs.train_id for cs in req.custom_segments}
        for tid in req.train_ids:
            if tid in custom_train_ids:
                continue
            segs = db.query_train(tid)
            segments.extend(segs)

        # Deduplica PRIMA di aggiungere custom segments
        if segments:
            segments = dedup_segments(segments)

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

        # Marca i treni di rientro come deadhead
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
            "segments": serialize_segments(segments),
            "violations": [
                {"rule": v.rule, "message": v.message, "severity": v.severity}
                for v in summary.violations
            ],
            "valid": len(summary.violations) == 0,
        }
        if req.include_timeline or force_timeline:
            result["timeline"] = build_timeline_blocks(
                summary, deposito=req.deposito, db=db,
                acc_start=acc_start_val, acc_end=acc_end_val,
            )
        return result
    finally:
        db.close()


# ── Endpoints ───────────────────────────────────────────────────

@router.get("/constants")
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


@router.post("/validate-day")
def validate_day(req: ValidateDayRequest):
    return _validate_day_common(req, force_timeline=False)


@router.post("/validate-day-with-timeline")
def validate_day_timeline(req: ValidateDayRequest):
    return _validate_day_common(req, force_timeline=True)


@router.post("/check-trains-validity")
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
