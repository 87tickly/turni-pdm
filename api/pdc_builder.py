"""
Router per la creazione/modifica manuale di turni PdC + utility calendario italiano.

Permette di costruire turni nello stesso schema dei PdC importati da PDF
(tabelle pdc_turn / pdc_turn_day / pdc_block / pdc_train_periodicity).

Endpoint:
  POST   /pdc-turn                         - crea nuovo turno (turno + giornate + blocchi)
  PUT    /pdc-turn/{turn_id}                - sostituisce completamente un turno
  DELETE /pdc-turn/{turn_id}                - elimina turno e figli (cascade)
  GET    /italian-calendar/periodicity      - info weekday/festivita per una data
  GET    /pdc-turn/{turn_id}/apply-to-date  - quale variante si applica alla data
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.deps import get_db
from src.italian_holidays import (
    is_italian_holiday,
    weekday_for_periodicity,
    italian_holidays,
    LOCAL_PATRONS,
)

router = APIRouter()


# ══════════════════════════════════════════════════════════════════
# Pydantic models (input)
# ══════════════════════════════════════════════════════════════════

class PdcBlockIn(BaseModel):
    seq: int = 0
    block_type: str  # train|coach_transfer|cv_partenza|cv_arrivo|meal|scomp|available
    train_id: str = ""
    vettura_id: str = ""
    from_station: str = ""
    to_station: str = ""
    start_time: str = ""
    end_time: str = ""
    accessori_maggiorati: bool = False


class PdcDayIn(BaseModel):
    day_number: int
    periodicita: str = "LMXGVSD"
    start_time: str = ""
    end_time: str = ""
    lavoro_min: int = 0
    condotta_min: int = 0
    km: int = 0
    notturno: bool = False
    riposo_min: int = 0
    is_disponibile: bool = False
    blocks: list[PdcBlockIn] = Field(default_factory=list)


class PdcNoteIn(BaseModel):
    train_id: str
    periodicita_text: str = ""
    non_circola_dates: list[str] = Field(default_factory=list)
    circola_extra_dates: list[str] = Field(default_factory=list)


class PdcTurnIn(BaseModel):
    codice: str
    planning: str = ""
    impianto: str
    profilo: str = "Condotta"
    valid_from: str = ""
    valid_to: str = ""
    days: list[PdcDayIn] = Field(default_factory=list)
    notes: list[PdcNoteIn] = Field(default_factory=list)


# ══════════════════════════════════════════════════════════════════
# Validazione
# ══════════════════════════════════════════════════════════════════

VALID_PERIODICITA = {
    "LMXGVSD", "LMXGVS", "LMXGV", "LMXG", "LMX", "LM",
    "GV", "VSD", "SD", "S", "V", "G", "D",
}

VALID_BLOCK_TYPES = {
    "train", "coach_transfer", "cv_partenza", "cv_arrivo",
    "meal", "scomp", "available",
}

VALID_PROFILI = {"Condotta", "Scorta"}


def _validate_turn_input(data: PdcTurnIn) -> None:
    """Verifica integrita' del payload prima di salvare."""
    if not data.codice.strip():
        raise HTTPException(400, detail="Campo 'codice' obbligatorio")
    if not data.impianto.strip():
        raise HTTPException(400, detail="Campo 'impianto' obbligatorio")
    if data.profilo not in VALID_PROFILI:
        raise HTTPException(
            400, detail=f"Profilo '{data.profilo}' non valido. Attesi: {sorted(VALID_PROFILI)}",
        )

    day_keys: set[tuple[int, str]] = set()
    for i, day in enumerate(data.days):
        if day.periodicita.upper() not in VALID_PERIODICITA:
            raise HTTPException(
                400,
                detail=(
                    f"Giornata {i}: periodicita' '{day.periodicita}' non valida. "
                    f"Valori accettati: LMXGVSD, LMXGVS, LMXGV, SD, S, D, ..."
                ),
            )
        key = (day.day_number, day.periodicita.upper())
        if key in day_keys:
            raise HTTPException(
                400,
                detail=(
                    f"Duplicato: giornata {day.day_number} con periodicita' "
                    f"'{day.periodicita}' compare piu' volte."
                ),
            )
        day_keys.add(key)

        for j, block in enumerate(day.blocks):
            if block.block_type not in VALID_BLOCK_TYPES:
                raise HTTPException(
                    400,
                    detail=(
                        f"Giornata {day.day_number} blocco {j}: tipo "
                        f"'{block.block_type}' non valido."
                    ),
                )


# ══════════════════════════════════════════════════════════════════
# CRUD endpoints
# ══════════════════════════════════════════════════════════════════

def _save_turn(db, data: PdcTurnIn, source_file: str) -> int:
    """Persiste un turno (+ figli) nel DB. Ritorna l'ID del turno creato."""
    turn_id = db.insert_pdc_turn(
        codice=data.codice,
        planning=data.planning,
        impianto=data.impianto,
        profilo=data.profilo,
        valid_from=data.valid_from,
        valid_to=data.valid_to,
        source_file=source_file,
    )
    for day in data.days:
        day_id = db.insert_pdc_turn_day(
            pdc_turn_id=turn_id,
            day_number=day.day_number,
            periodicita=day.periodicita.upper(),
            start_time=day.start_time,
            end_time=day.end_time,
            lavoro_min=day.lavoro_min,
            condotta_min=day.condotta_min,
            km=day.km,
            notturno=day.notturno,
            riposo_min=day.riposo_min,
            is_disponibile=day.is_disponibile,
        )
        for block in day.blocks:
            db.insert_pdc_block(
                pdc_turn_day_id=day_id,
                seq=block.seq,
                block_type=block.block_type,
                train_id=block.train_id,
                vettura_id=block.vettura_id,
                from_station=block.from_station,
                to_station=block.to_station,
                start_time=block.start_time,
                end_time=block.end_time,
                accessori_maggiorati=block.accessori_maggiorati,
            )
    for note in data.notes:
        db.insert_pdc_train_periodicity(
            pdc_turn_id=turn_id,
            train_id=note.train_id,
            periodicita_text=note.periodicita_text,
            non_circola_dates=note.non_circola_dates,
            circola_extra_dates=note.circola_extra_dates,
        )
    db.conn.commit()
    return turn_id


@router.post("/pdc-turn")
async def create_pdc_turn(data: PdcTurnIn):
    """Crea un nuovo turno PdC costruito manualmente dall'utente."""
    _validate_turn_input(data)
    db = get_db()
    try:
        turn_id = _save_turn(db, data, source_file="manual_builder")
        return {
            "status": "created",
            "turn_id": turn_id,
            "codice": data.codice,
            "impianto": data.impianto,
        }
    finally:
        db.close()


@router.put("/pdc-turn/{turn_id}")
async def update_pdc_turn(turn_id: int, data: PdcTurnIn):
    """Sostituisce completamente un turno esistente.

    Cancella il turno e i suoi figli (CASCADE), poi reinserisce tutto
    secondo il payload. Mantiene lo stesso ID non e' garantito — restituisce
    il nuovo ID nell'output.
    """
    _validate_turn_input(data)
    db = get_db()
    try:
        existing = db.get_pdc_turn(turn_id)
        if not existing:
            raise HTTPException(404, detail="Turno PdC non trovato")
        # Delete via cascata (blocks e days sono ON DELETE CASCADE)
        cur = db._cursor()
        cur.execute(db._q("DELETE FROM pdc_turn WHERE id = ?"), (turn_id,))
        db.conn.commit()

        new_id = _save_turn(
            db, data, source_file=existing.get("source_file") or "manual_builder",
        )
        return {
            "status": "updated",
            "old_turn_id": turn_id,
            "new_turn_id": new_id,
            "codice": data.codice,
        }
    finally:
        db.close()


@router.delete("/pdc-turn/{turn_id}")
async def delete_pdc_turn(turn_id: int):
    """Elimina un turno PdC (e tutti i figli via CASCADE)."""
    db = get_db()
    try:
        existing = db.get_pdc_turn(turn_id)
        if not existing:
            raise HTTPException(404, detail="Turno PdC non trovato")
        cur = db._cursor()
        cur.execute(db._q("DELETE FROM pdc_turn WHERE id = ?"), (turn_id,))
        db.conn.commit()
        return {"status": "deleted", "turn_id": turn_id}
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════
# Calendario italiano
# ══════════════════════════════════════════════════════════════════

@router.get("/italian-calendar/periodicity")
async def calendar_periodicity(date_str: str, local: Optional[str] = None):
    """Per una data (YYYY-MM-DD), ritorna:
      - letter: L|M|X|G|V|S|D (considerando festivita')
      - weekday: nome giorno della settimana
      - is_holiday: bool
      - holiday_name: nome festivita' se applicabile
      - local: patrono locale considerato (se passato)
    """
    try:
        d = date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(400, detail="Formato data non valido, atteso YYYY-MM-DD")

    letter = weekday_for_periodicity(d, include_local=local)
    holiday = is_italian_holiday(d, include_local=local)

    # Trova il nome della festivita' se presente
    holiday_name = None
    if holiday:
        year_holidays = italian_holidays(d.year, include_local=local)
        if d in year_holidays:
            # match per nome
            from src.italian_holidays import FIXED_HOLIDAYS, easter_sunday, easter_monday
            if d == easter_sunday(d.year):
                holiday_name = "Pasqua"
            elif d == easter_monday(d.year):
                holiday_name = "Pasquetta"
            else:
                for m, day_f, name in FIXED_HOLIDAYS:
                    if d.month == m and d.day == day_f:
                        holiday_name = name
                        break
                if not holiday_name and local:
                    patron = LOCAL_PATRONS.get(local.lower())
                    if patron and d.month == patron[0] and d.day == patron[1]:
                        holiday_name = f"{patron[2]} (patrono {local})"

    weekdays_it = ("Lunedi'", "Martedi'", "Mercoledi'", "Giovedi'",
                   "Venerdi'", "Sabato", "Domenica")

    return {
        "date": date_str,
        "letter": letter,
        "weekday": weekdays_it[d.weekday()],
        "is_holiday": holiday,
        "holiday_name": holiday_name,
        "local": local,
    }


@router.get("/pdc-builder/lookup-train/{train_id}")
async def pdc_builder_lookup_train(train_id: str):
    """Dato un numero treno, cerca nel giro materiale il segmento
    corrispondente e ritorna stazioni + orari da usare come default
    in fase di creazione di un blocco `train` in un turno PdC.

    Questo crea il collegamento logico tra turno PdC e giro materiale:
    quando l'utente inserisce un train_id nel builder, il sistema
    popola automaticamente from_station, to_station, start_time,
    end_time se il treno e' conosciuto dal giro materiale.
    """
    db = get_db()
    try:
        segs = db.query_train(train_id)
        if not segs:
            return {"found": False, "train_id": train_id}
        seg = segs[0]
        return {
            "found": True,
            "train_id": train_id,
            "from_station": seg.get("from_station", ""),
            "to_station": seg.get("to_station", ""),
            "dep_time": seg.get("dep_time", ""),
            "arr_time": seg.get("arr_time", ""),
            "material_turn_id": seg.get("material_turn_id"),
            "is_deadhead": bool(seg.get("is_deadhead", 0)),
            "other_matches": len(segs) - 1,
        }
    finally:
        db.close()


@router.get("/pdc-turn/{turn_id}/apply-to-date")
async def pdc_turn_apply_to_date(turn_id: int, date_str: str,
                                  local: Optional[str] = None):
    """Dato un turno e una data, ritorna quale variante giornata si applica.

    Cerca tra le giornate del turno quella con periodicita' che contiene
    la lettera del giorno della data.
    """
    try:
        d = date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(400, detail="Formato data non valido, atteso YYYY-MM-DD")

    db = get_db()
    try:
        turn = db.get_pdc_turn(turn_id)
        if not turn:
            raise HTTPException(404, detail="Turno PdC non trovato")

        letter = weekday_for_periodicity(d, include_local=local)
        days = db.get_pdc_turn_days(turn_id)

        matches = []
        for day in days:
            if letter in day["periodicita"].upper():
                day["blocks"] = db.get_pdc_blocks(day["id"])
                matches.append(day)

        return {
            "date": date_str,
            "letter": letter,
            "is_holiday": is_italian_holiday(d, include_local=local),
            "turn_id": turn_id,
            "matches": matches,
            "match_count": len(matches),
        }
    finally:
        db.close()
