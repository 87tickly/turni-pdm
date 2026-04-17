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
async def upload_turno_pdc(file: UploadFile = File(...),
                            dry_run: bool = False):
    """Importa il PDF Turni PdC rete RFI nel database (schema v2.1, versionato).

    Comportamento:
      - dry_run=true : parsa il PDF, calcola il diff rispetto ai turni attivi
                        ma NON scrive nulla nel DB. Utile per anteprima UI
                        "nuovi / aggiornati / non piu' presenti".
      - dry_run=false (default): parsa, crea pdc_import nuovo, inserisce
                        i turni con import_id = nuovo, marca superseded
                        i turni attivi con stesso (codice, impianto).
                        Lo storico NON viene cancellato.

    Risposta dry_run:
      {
        "status": "preview",
        "filename": "...",
        "diff": {"new":[...], "updated":[...], "only_in_old":[...], "counts":{...}},
        "summary": [{codice, impianto, planning, days, notes, valid_from, valid_to}, ...]
      }

    Risposta import reale:
      {
        "status": "ok",
        "filename": "...",
        "import_id": 5,
        "turni_imported": 28,
        "turni_superseded": 26,
        "days_imported": 1315,
        "blocks_imported": 6054,
        "notes_imported": 2901,
        "stats": {...},          # statistiche sui turni ATTIVI
        "summary": [...],
        "diff": {...}            # diff del cambio
      }
    """
    from src.importer.turno_pdc_parser import (
        parse_pdc_pdf, save_parsed_turns_as_import,
    )

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, detail="Il file deve essere un PDF")

    content = await file.read()
    if not content:
        raise HTTPException(400, detail="File vuoto")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        turns = parse_pdc_pdf(tmp_path)
        if not turns:
            raise HTTPException(
                422,
                detail=(
                    "Nessun turno PdC trovato nel PDF. "
                    "Formato atteso: Modello SGI Turni del Personale Mobile "
                    "(MDL-PdC v1.0)."
                ),
            )

        # Parsing pagine per meta import (richiede pdfplumber; best-effort)
        n_pagine_pdf = 0
        try:
            import pdfplumber
            with pdfplumber.open(tmp_path) as pdf:
                n_pagine_pdf = len(pdf.pages)
        except Exception:
            pass

        summary = [
            {
                "codice": t.codice,
                "impianto": t.impianto,
                "planning": t.planning,
                "days": len(t.days),
                "notes": len(t.notes),
                "valid_from": t.valid_from,
                "valid_to": t.valid_to,
            }
            for t in turns
        ]

        db = get_db()
        try:
            diff = db.diff_import_candidates(turns)

            if dry_run:
                return {
                    "status": "preview",
                    "filename": file.filename,
                    "n_pagine_pdf": n_pagine_pdf,
                    "turni_parsed": len(turns),
                    "diff": diff,
                    "summary": summary,
                }

            result = save_parsed_turns_as_import(
                turns, db,
                filename=file.filename or "turno_pdc.pdf",
                n_pagine_pdf=n_pagine_pdf,
            )
            return {
                "status": "ok",
                "filename": file.filename,
                "import_id": result["import_id"],
                "turni_imported": result["turni_imported"],
                "turni_superseded": result["turni_superseded"],
                "days_imported": result["days_imported"],
                "blocks_imported": result["blocks_imported"],
                "notes_imported": result["notes_imported"],
                "stats": result["stats_active"],
                "summary": summary,
                "diff": diff,
            }
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, detail=f"Errore parsing turno PdC: {e}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@router.get("/pdc-imports")
async def pdc_imports_list():
    """Storico degli import PdC, dal piu' recente al piu' vecchio.

    Ogni record indica filename, data stampa/pubblicazione del PDF,
    range di validita' coperto, numero turni, quando e' stato caricato.
    """
    db = get_db()
    try:
        imports = db.list_pdc_imports()
        # Arricchisce con conteggio turni attualmente attivi per questo import
        cur = db.conn.cursor()
        for imp in imports:
            cur.execute(
                db._q(
                    "SELECT COUNT(*) AS n FROM pdc_turn "
                    "WHERE import_id = ? AND superseded_by_import_id IS NULL"
                ),
                (imp["id"],),
            )
            imp["turni_attivi"] = db._dict(cur.fetchone())["n"]
        return {"count": len(imports), "imports": imports}
    finally:
        db.close()


@router.get("/pdc-imports/{import_id}")
async def pdc_import_detail(import_id: int):
    """Dettaglio di un import: meta + turni generati da questo import
    (attivi e superseded)."""
    db = get_db()
    try:
        imp = db.get_pdc_import(import_id)
        if not imp:
            raise HTTPException(404, detail="Import non trovato")
        cur = db.conn.cursor()
        cur.execute(
            db._q(
                "SELECT id, codice, impianto, planning, profilo, "
                "valid_from, valid_to, superseded_by_import_id "
                "FROM pdc_turn WHERE import_id = ? "
                "ORDER BY impianto, codice"
            ),
            (import_id,),
        )
        turns = [db._dict(r) for r in cur.fetchall()]
        return {
            "import": imp,
            "turns": turns,
            "active_count": sum(
                1 for t in turns if t["superseded_by_import_id"] is None
            ),
            "superseded_count": sum(
                1 for t in turns if t["superseded_by_import_id"] is not None
            ),
        }
    finally:
        db.close()


@router.get("/pdc-stats")
async def pdc_stats():
    """Statistiche dei turni PdC importati (schema v2)."""
    db = get_db()
    try:
        return db.get_pdc_stats()
    finally:
        db.close()


@router.get("/pdc-turns")
async def pdc_turns(impianto: str = None, profilo: str = None):
    """Lista turni PdC caricati, filtrabili per impianto/profilo."""
    db = get_db()
    try:
        turns = db.list_pdc_turns(impianto=impianto, profilo=profilo)
        return {"count": len(turns), "turns": turns}
    finally:
        db.close()


@router.get("/pdc-turn/{turn_id}")
async def pdc_turn_detail(turn_id: int):
    """Dettaglio turno PdC: header + giornate + blocchi per giornata + note."""
    db = get_db()
    try:
        turn = db.get_pdc_turn(turn_id)
        if not turn:
            raise HTTPException(404, detail="Turno PdC non trovato")
        days = db.get_pdc_turn_days(turn_id)
        for d in days:
            d["blocks"] = db.get_pdc_blocks(d["id"])
        notes = db.get_pdc_train_periodicity(turn_id)
        return {"turn": turn, "days": days, "notes": notes}
    finally:
        db.close()


@router.get("/pdc-find-train/{train_id}")
async def pdc_find_train(train_id: str):
    """Cerca un treno nei turni PdC (schema v2)."""
    db = get_db()
    try:
        results = db.find_pdc_train(train_id)
        return {"train_id": train_id, "found": len(results) > 0, "results": results}
    finally:
        db.close()


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

    # 2. Turno PdC (schema v2)
    try:
        pdc_results = db.find_pdc_train(train_id)
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
