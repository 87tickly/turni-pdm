"""
Router importazione turni personale, turni PdC, triple-check treni.
"""

import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File

from api.deps import get_db
from services.arturo_client import treno as arturo_treno, fermata_to_times

router = APIRouter()


@router.post("/upload-turno-personale")
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


@router.post("/upload-turno-pdc")
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


@router.get("/pdc-stats")
async def pdc_stats():
    """Statistiche dei turni PdC importati."""
    db = get_db()
    return db.pdc_get_stats()


@router.get("/pdc-find-train/{train_id}")
async def pdc_find_train(train_id: str):
    """Cerca un treno nei turni PdC."""
    db = get_db()
    results = db.pdc_find_train(train_id)
    return {"train_id": train_id, "found": len(results) > 0, "results": results}


@router.get("/train-check/{train_id}")
async def train_check(train_id: str):
    """Triple-check: cerca un treno in DB interno, Turno PdC e ARTURO Live."""
    db = get_db()
    result = {
        "train_id": train_id,
        "db_internal": {"found": False, "data": None},
        "pdc": {"found": False, "results": []},
        "arturo_live": {"found": False, "data": None},
    }

    # 1. DB Interno (giro materiale)
    try:
        segments = db.query_train(train_id)
        if segments:
            seg = segments[0]
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

    # 3. ARTURO Live (real-time)
    try:
        data = arturo_treno(train_id)
        if data:
            fermate = data.get("fermate", [])
            first_stop = fermate[0] if fermate else {}
            last_stop = fermate[-1] if fermate else {}

            dep_prog, _, _, _ = fermata_to_times(first_stop) if first_stop else ("", "", "", "")
            _, _, arr_prog, _ = fermata_to_times(last_stop) if last_stop else ("", "", "", "")

            result["arturo_live"] = {
                "found": True,
                "data": {
                    "operator": data.get("operatore", ""),
                    "category": data.get("categoria", ""),
                    "origin": data.get("origine", ""),
                    "destination": data.get("destinazione", ""),
                    "dep_time": dep_prog,
                    "arr_time": arr_prog,
                    "num_stops": len(fermate),
                    "delay": data.get("ritardo_corrente_min", 0),
                    "is_trenord": data.get("operatore", "").upper() == "TRENORD",
                    "status": data.get("stato", ""),
                },
            }
    except Exception:
        pass

    return result
