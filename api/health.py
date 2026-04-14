"""
Router health, info e redirect root.
"""

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from api.deps import get_db

router = APIRouter()


@router.get("/")
def root():
    return RedirectResponse(url="/static/index.html")


@router.get("/api/health")
def health():
    return {"status": "ok", "service": "Turni PDM API"}


@router.get("/info")
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
