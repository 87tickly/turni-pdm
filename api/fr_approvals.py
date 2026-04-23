"""
Router per gestione FR approvate per PdC — Step 7 / Step 9 / Step 10.

Endpoints:
  GET    /api/pdc/{pdc_id}/fr-approved           lista stazioni FR approvate
  POST   /api/pdc/{pdc_id}/fr-approved           approva stazione
  DELETE /api/pdc/{pdc_id}/fr-approved/{station} revoca approvazione
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.deps import get_db
from src.turn_builder import fr_registry

router = APIRouter()


class FRApproveRequest(BaseModel):
    station: str
    notes: str = ""


class FRApproveBatchRequest(BaseModel):
    stations: list[str]


@router.get("/pdc/{pdc_id}/fr-approved")
def list_fr_approved(pdc_id: str):
    """Lista le stazioni FR approvate per il PdC."""
    db = get_db()
    conn = db.conn
    try:
        stations = sorted(fr_registry.list_approved(conn, pdc_id))
        return {"pdc_id": pdc_id, "stations": stations, "count": len(stations)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pdc/{pdc_id}/fr-approved")
def approve_fr(pdc_id: str, req: FRApproveRequest):
    """Approva una stazione FR per il PdC."""
    if not req.station or not req.station.strip():
        raise HTTPException(status_code=400, detail="station richiesta")
    db = get_db()
    conn = db.conn
    try:
        fr_registry.approve(conn, pdc_id, req.station, req.notes)
        stations = sorted(fr_registry.list_approved(conn, pdc_id))
        return {"ok": True, "stations": stations}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pdc/{pdc_id}/fr-approved/batch")
def approve_fr_batch(pdc_id: str, req: FRApproveBatchRequest):
    """Approva N stazioni in batch. Ritorna il numero di nuove."""
    db = get_db()
    conn = db.conn
    try:
        added = fr_registry.approve_batch(conn, pdc_id, req.stations)
        stations = sorted(fr_registry.list_approved(conn, pdc_id))
        return {"ok": True, "added": added, "stations": stations}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/pdc/{pdc_id}/fr-approved/{station}")
def revoke_fr(pdc_id: str, station: str):
    """Revoca l'approvazione di una stazione FR per il PdC."""
    db = get_db()
    conn = db.conn
    try:
        fr_registry.revoke(conn, pdc_id, station)
        stations = sorted(fr_registry.list_approved(conn, pdc_id))
        return {"ok": True, "stations": stations}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
