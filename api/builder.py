"""
Router costruzione turni automatici, calendario, turno settimanale.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.deps import get_db
from src.database.db import Database
from src.turn_builder.auto_builder import AutoBuilder
from src.validator.rules import TurnValidator, _fmt_min
from services.segments import dedup_segments, serialize_segments
from services.timeline import build_timeline_blocks
from src.constants import DEPOSITI

router = APIRouter()


# ── Request models ──────────────────────────────────────────────

class BuildAutoRequest(BaseModel):
    deposito: str = ""
    days: int = 5
    day_type: str = "LV"
    accessory_type: str = "standard"
    # Builder v4: architettura centrata sulla condotta (seed + posizionamento
    # in vettura + rientro). Genera turni ALOR_C-like con piu' linee diverse
    # e posizionamenti reali, ma puo' lasciare giornate vuote se il dataset
    # non e' sufficiente. Default False (usa v3 piu' tollerante).
    use_v4: bool = False


class BuildAutoAllRequest(BaseModel):
    days: int = 5
    day_type: str = "LV"
    accessory_type: str = "standard"


class BuildWeeklyRequest(BaseModel):
    deposito: str
    n_days: int = 5
    exclude_trains: list[str] = []
    accessory_type: str = "standard"


# ── Helpers ─────────────────────────────────────────────────────

def _serialize_summary(s, deposito, db):
    """Serializza un DaySummary con timeline per risposte build-auto."""
    timeline = build_timeline_blocks(s, deposito=deposito, db=db)
    return {
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
        "segments": serialize_segments(s.segments),
        "timeline": timeline,
        "violations": [
            {"rule": v.rule, "message": v.message, "severity": v.severity}
            for v in s.violations
        ],
    }


# ── Endpoints ───────────────────────────────────────────────────

@router.post("/build-auto")
def build_auto(req: BuildAutoRequest):
    db = get_db()
    try:
        # ── Unicita' cross-deposito: pulisci allocazioni stale del deposito ──
        # cosi' alla rigenerazione il builder vede solo i treni bloccati da ALTRI.
        if req.deposito:
            try:
                db.clear_train_allocation(req.deposito)
            except Exception:
                pass
        builder = AutoBuilder(db, deposito=req.deposito,
                              use_v4_assembler=req.use_v4)
        used = db.get_used_train_ids(day_type=req.day_type)
        calendar = builder.build_schedule(
            n_workdays=req.days,
            day_type=req.day_type,
            exclude_trains=used,
        )
        # Registra i treni usati nel turno come "allocati" a questo deposito
        try:
            builder.commit_allocations(calendar)
        except Exception:
            pass

        result = []
        for entry in calendar:
            item = {
                "type": entry["type"],
                "day": entry.get("day"),
                "week_day_type": entry.get("week_day_type", ""),
            }
            if entry.get("summary") and entry["summary"].segments:
                item["summary"] = _serialize_summary(entry["summary"], req.deposito, db)
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
            "weekly": {
                "hours_total": meta.get("weekly_hours_total", 0),
                "hours_min": meta.get("weekly_hours_min", 33),
                "hours_target": meta.get("weekly_hours_target", 35.5),
                "hours_max": meta.get("weekly_hours_max", 38),
                "under_target": meta.get("weekly_under_target", False),
                "over_max": meta.get("weekly_over_max", False),
                "warning": meta.get("weekly_warning", ""),
            },
        }
    finally:
        db.close()


@router.post("/build-auto-all")
def build_auto_all(req: BuildAutoAllRequest):
    """Genera turni automatici per TUTTI i 19 impianti.

    Nota unicita' cross-deposito: genera IN SEQUENZA (non in parallelo).
    Ogni deposito rispetta i treni gia' allocati dai precedenti. All'avvio
    la tabella train_allocation viene pulita totalmente per ripartire da zero.
    """
    db = get_db()
    try:
        # Pulizia globale: al prossimo build_auto_all si riparte da zero
        try:
            db.clear_train_allocation()
        except Exception:
            pass
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
                # Blocca i treni usati prima di passare al prossimo deposito
                try:
                    builder.commit_allocations(calendar)
                except Exception:
                    pass

                cal_items = []
                total_days_ok = 0
                total_violations = 0
                for entry in calendar:
                    item = {"type": entry["type"], "day": entry.get("day")}
                    if entry.get("summary") and entry["summary"].segments:
                        s = entry["summary"]
                        item["summary"] = _serialize_summary(s, deposito, db)
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


@router.get("/calendar/{n_days}")
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


@router.post("/build-weekly")
def build_weekly(req: BuildWeeklyRequest):
    """Genera un turno settimanale unificato (LMXGV + S + D per ogni giornata)."""
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
