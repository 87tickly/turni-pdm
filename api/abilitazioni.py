"""
Router abilitazioni deposito (linee + materiale rotabile).

Le abilitazioni filtrano quali segmenti l'auto-builder puo' usare per
i PdC di un deposito. Linea = coppia stazioni estremi del giro materiale
(normalizzata alfabeticamente). Materiale = codice locomotiva/automotrice
estratto dal PDF turno materiale (es. E464N).
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_db, get_current_user

router = APIRouter()


# ── Request models ──────────────────────────────────────────────

class LinePair(BaseModel):
    station_a: str
    station_b: str


class MaterialItem(BaseModel):
    material_type: str


# ── Endpoints ───────────────────────────────────────────────────

@router.get("/abilitazioni/{deposito}")
def get_abilitazioni(deposito: str):
    """Stato completo abilitazioni di un deposito + lista candidati."""
    db = get_db()
    try:
        return {
            "deposito": deposito.upper().strip(),
            "enabled_lines": [
                {"station_a": a, "station_b": b}
                for a, b in db.get_enabled_lines(deposito)
            ],
            "enabled_materials": db.get_enabled_materials(deposito),
            "available_lines": db.get_available_lines_for_depot(deposito),
            "available_materials": db.get_available_materials_for_depot(deposito),
        }
    finally:
        db.close()


@router.post("/abilitazioni/{deposito}/linee")
def add_linea(deposito: str, body: LinePair, user=Depends(get_current_user)):
    db = get_db()
    try:
        ok = db.add_enabled_line(deposito, body.station_a, body.station_b)
        return {"added": ok}
    finally:
        db.close()


@router.delete("/abilitazioni/{deposito}/linee")
def remove_linea(deposito: str, body: LinePair, user=Depends(get_current_user)):
    db = get_db()
    try:
        n = db.remove_enabled_line(deposito, body.station_a, body.station_b)
        return {"removed": n}
    finally:
        db.close()


@router.post("/abilitazioni/{deposito}/materiali")
def add_materiale(deposito: str, body: MaterialItem, user=Depends(get_current_user)):
    db = get_db()
    try:
        ok = db.add_enabled_material(deposito, body.material_type)
        return {"added": ok}
    finally:
        db.close()


@router.delete("/abilitazioni/{deposito}/materiali")
def remove_materiale(deposito: str, body: MaterialItem, user=Depends(get_current_user)):
    db = get_db()
    try:
        n = db.remove_enabled_material(deposito, body.material_type)
        return {"removed": n}
    finally:
        db.close()
