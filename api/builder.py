"""
Router costruzione turni automatici, calendario, turno settimanale.
"""

from datetime import date as _date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.deps import get_db
from src.database.db import Database
from src.turn_builder.auto_builder import AutoBuilder
from src.turn_builder import accessori as accessori_mod
from src.turn_builder import cv_registry
from src.validator.rules import TurnValidator, _fmt_min
from services.segments import dedup_segments, serialize_segments
from services.timeline import build_timeline_blocks
from src.constants import DEPOSITI

router = APIRouter()


def _annotate_segments_with_accessori_cv(summary, db, day_date=None):
    """Annota accp_min/acca_min/cv_before_min/cv_after_min sui segmenti
    di un DaySummary *dopo* la generazione (path v3). Evita di dover
    abilitare use_v4 (piu' lento a causa del day_assembler full-stack).

    Safe: se il backend ha gia' annotato (path v4) o se manca
    material_turn_id, i seg vengono lasciati come sono.
    """
    if not summary or not summary.segments:
        return
    day_date = day_date or _date.today()
    # Cache giro materiale per (mtid, day_index) per evitare N query
    _material_cache: dict = {}

    def _get_mat_segs(mtid, dix):
        key = (mtid, dix)
        if key not in _material_cache:
            try:
                all_segs = db.get_all_segments(day_index=dix) or []
            except Exception:
                all_segs = []
            _material_cache[key] = [
                s for s in all_segs
                if s.get("material_turn_id") == mtid
            ]
        return _material_cache[key]

    def _is_refez(seg):
        if isinstance(seg, dict):
            return bool(seg.get("is_refezione", False))
        return bool(getattr(seg, "is_refezione", False))

    # Step 1: annota accp_min/acca_min
    for seg in summary.segments:
        if not isinstance(seg, dict):
            continue
        if _is_refez(seg):
            seg.setdefault("accp_min", 0)
            seg.setdefault("acca_min", 0)
            continue
        if "accp_min" in seg and "acca_min" in seg:
            continue  # gia' annotato
        mtid = seg.get("material_turn_id")
        dix = seg.get("day_index", 0)
        if mtid is None:
            continue  # non ho modo di risalire al giro materiale
        mat_segs = _get_mat_segs(mtid, dix) or [seg]
        try:
            res = accessori_mod.apply_accessori(mat_segs, seg, day_date)
            seg["accp_min"] = res["accp_min"]
            seg["acca_min"] = res["acca_min"]
            if res.get("gap_before") is not None:
                seg["gap_before"] = res["gap_before"]
            if res.get("gap_after") is not None:
                seg["gap_after"] = res["gap_after"]
        except Exception:
            pass

    # Step 2: CV interni (same_pdc=True)
    real_seq = [s for s in summary.segments
                if isinstance(s, dict) and not _is_refez(s)]
    for i in range(len(real_seq) - 1):
        prev_s, next_s = real_seq[i], real_seq[i + 1]
        if "cv_after_min" in prev_s or "cv_before_min" in next_s:
            continue
        try:
            cv = cv_registry.detect_cv(prev_s, next_s)
            if cv is not None:
                cva, cvp = cv_registry.compute_cv_split(
                    cv["gap_min"], same_pdc=True,
                )
                prev_s["cv_after_min"] = cva
                next_s["cv_before_min"] = cvp
        except Exception:
            pass


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
    """Serializza un DaySummary con timeline per risposte build-auto.

    Se i segmenti non sono gia' stati annotati (path v3), calcola qui
    accp_min/acca_min/cv_before_min/cv_after_min cosi' il frontend puo'
    mostrare pill ACCp/ACCa/CV nel Gantt.
    """
    _annotate_segments_with_accessori_cv(s, db)
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


@router.post("/build-auto-weekly")
def build_auto_weekly(req: BuildAutoRequest):
    """
    Versione di /build-auto che per ogni giornata del turno materiale
    produce 3 varianti (LMXGV, S, D) come nel PDF originale Trenord.
    Esempio di output per giornata:
      {
        "day_number": 5,
        "variants": [
          {"variant_type": "LMXGV", "summary": {...full...}, "is_scomp": false},
          {"variant_type": "S", "summary": {...}, "is_scomp": false},
          {"variant_type": "D", "is_scomp": true, "scomp_duration_min": 360},
        ]
      }
    """
    db = get_db()
    try:
        if req.deposito:
            try:
                db.clear_train_allocation(req.deposito)
            except Exception:
                pass
        builder = AutoBuilder(db, deposito=req.deposito,
                              use_v4_assembler=req.use_v4)
        result = builder.build_weekly_schedule(
            n_workdays=req.days,
            exclude_trains=[],
        )
        # Serializza ogni variante con full summary (segments, timeline, viol)
        out_days = []
        for day in result.get("days", []):
            out_variants = []
            for v in day.get("variants", []):
                entry = {
                    "variant_type": v.get("variant_type", ""),
                    "day_type": v.get("day_type", ""),
                    "is_scomp": v.get("is_scomp", False),
                    "scomp_duration_min": v.get("scomp_duration_min", 0),
                }
                s_obj = v.get("summary_obj")
                if s_obj and not v.get("is_scomp"):
                    entry["summary"] = _serialize_summary(s_obj, req.deposito, db)
                else:
                    entry["summary"] = None
                    entry["last_station"] = v.get("last_station", "")
                out_variants.append(entry)
            out_days.append({
                "day_number": day.get("day_number"),
                "variants": out_variants,
            })
        return {
            "workdays_requested": req.days,
            "deposito": req.deposito,
            "days": out_days,
            "weekly_stats": result.get("weekly_stats", {}),
        }
    finally:
        db.close()
