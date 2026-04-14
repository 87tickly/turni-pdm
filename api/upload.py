"""
Router upload PDF turni e gestione database.
"""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File

from src.importer.pdf_parser import PDFImporter
from api.deps import get_db

router = APIRouter()

UPLOAD_DIR = Path(__file__).parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


@router.post("/upload")
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
        old_count = db.segment_count()
        old_saved = db.get_saved_shifts()
        if old_count > 0:
            print(f"\n[IMPORT] Pulizia dati precedenti: {old_count} segmenti rimossi")
            db.clear_all()

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


@router.delete("/database")
def clear_database():
    db = get_db()
    try:
        db.clear_all()
        return {"status": "ok", "message": "Database svuotato"}
    finally:
        db.close()
