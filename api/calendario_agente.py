"""
Router Calendario Agente — espande i turni PdC su un range di giorni.

Endpoint:
  GET /calendario-agente?start=YYYY-MM-DD&days=28&deposito=MILANO

Schema di risposta (da HANDOFF-calendario-agente.md §3):
  {
    "range_start": "2026-04-06",
    "range_days": 28,
    "deposito": "MILANO",
    "rows": [
      {
        "pdc_id": 1,
        "pdc_code": "AROR_C",
        "display_name": "AROR_C",
        "matricola": "",
        "deposito": "MILANO",
        "totals": {work, rest, uncov, hours_min},
        "cells": [ {date, state, turno_code, prestazione_min?}, ... ]
      }
    ]
  }

Stato cella (state):
  "work"  — pdc_turn_day.is_disponibile=0 con variante compatibile per weekday
  "scomp" — pdc_turn_day.is_disponibile=1
  "rest"  — nessuna variante compatibile per quel giorno (riposo)
  "fr"    — NOT YET: richiede campo is_fr sul turn_day (da Step 7 backend v4)
  "uncov" — NOT YET: non-chiudibili per vincolo riposo (richiede validator cross-day)
  "leave" — NOT YET: richiede tabella assegnazioni matricole + ferie/permessi
  "locked"— NOT YET: idem

Nota: non esiste ancora un sistema di assegnazione matricola → turno → data.
Finche' non viene introdotto, il calendario espande "teoricamente" il ciclo
di ogni pdc_turn del deposito a partire dal primo giorno del range
(day_number=1 mappato al primo giorno del range). La UI puo' integrare
alias matricola quando sara' disponibile.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.deps import get_db
from src.italian_holidays import weekday_for_periodicity


router = APIRouter()


AgentCellState = Literal[
    "work", "rest", "fr", "scomp", "uncov", "leave", "locked"
]


class AgentGridCell(BaseModel):
    date: str
    state: AgentCellState
    span: int | None = None
    turno_code: str | None = None
    prestazione_min: int | None = None
    lock_reason: str | None = None


class AgentGridTotals(BaseModel):
    work: int
    rest: int
    uncov: int
    hours_min: int


class AgentGridRow(BaseModel):
    pdc_id: int
    pdc_code: str
    display_name: str
    matricola: str
    deposito: str
    totals: AgentGridTotals
    cells: list[AgentGridCell]


class AgentGridResponse(BaseModel):
    range_start: str
    range_days: int
    deposito: str | None
    rows: list[AgentGridRow]


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _periodicita_matches(periodicita: str, weekday_letter: str) -> bool:
    """True se la periodicita' (es. 'LMXGV', 'SD', 'S', 'LMXGVSD') include
    la lettera del weekday richiesto."""
    if not periodicita:
        return False
    p = periodicita.upper()
    return weekday_letter.upper() in p


def _select_day_for_weekday(
    turn_days: list[dict], weekday_letter: str,
) -> dict | None:
    """Sceglie il pdc_turn_day con periodicita' compatibile per il
    weekday dato. Preferenza: match esatto della lettera (es. 'D' da
    una row con periodicita='D'), poi match ampio ('LMXGVSD').

    Se non trova nulla, torna None (→ riposo).
    """
    # Priorita' 1: row con periodicita = solo quella lettera (es. 'S', 'D')
    exact = [d for d in turn_days
             if d.get("periodicita", "").upper() == weekday_letter]
    if exact:
        return exact[0]
    # Priorita' 2: row con periodicita che include la lettera
    matching = [d for d in turn_days
                if _periodicita_matches(d.get("periodicita", ""), weekday_letter)]
    if matching:
        # Se multiple, prendi la piu' specifica (piu' corta)
        matching.sort(key=lambda d: len(d.get("periodicita", "") or ""))
        return matching[0]
    return None


def _build_cells_for_turn(
    turn: dict,
    turn_days: list[dict],
    start: date,
    days: int,
) -> list[AgentGridCell]:
    """Genera le celle del calendario agente per un singolo turno PdC.

    Per ogni giorno del range calcola:
      - lettera periodicita' del weekday (via weekday_for_periodicity)
      - sceglie il pdc_turn_day compatibile
      - se is_disponibile=1 → state=scomp
      - altrimenti → state=work con turno_code = codice pdc_turn + day_number
      - se nessun match → state=rest
    """
    cells: list[AgentGridCell] = []
    for i in range(days):
        d = start + timedelta(days=i)
        letter = weekday_for_periodicity(d)
        day = _select_day_for_weekday(turn_days, letter)
        if day is None:
            cells.append(AgentGridCell(
                date=d.isoformat(),
                state="rest",
            ))
            continue

        is_disp = bool(day.get("is_disponibile", 0))
        lavoro_min = int(day.get("lavoro_min", 0) or 0)
        day_number = int(day.get("day_number", 0) or 0)

        if is_disp:
            cells.append(AgentGridCell(
                date=d.isoformat(),
                state="scomp",
                turno_code=f"{turn['codice']} · S.COMP",
                prestazione_min=lavoro_min or None,
            ))
        else:
            cells.append(AgentGridCell(
                date=d.isoformat(),
                state="work",
                turno_code=f"{turn['codice']} G{day_number}",
                prestazione_min=lavoro_min or None,
            ))
    return cells


def _compute_totals(cells: list[AgentGridCell]) -> AgentGridTotals:
    work = sum(1 for c in cells if c.state in ("work", "fr"))
    rest = sum(1 for c in cells if c.state == "rest")
    uncov = sum(1 for c in cells if c.state == "uncov")
    hours = sum(c.prestazione_min or 0 for c in cells)
    return AgentGridTotals(work=work, rest=rest, uncov=uncov, hours_min=hours)


@router.get("/calendario-agente", response_model=AgentGridResponse)
def get_calendario_agente(
    start: str,
    days: int = 28,
    deposito: str | None = None,
):
    """Ritorna il calendario agente per N giorni a partire da `start`.

    Args:
        start: data ISO YYYY-MM-DD
        days: numero di giorni (default 28, max 62)
        deposito: filtra per impianto (es. MILANO, ALESSANDRIA); None = tutti
    """
    try:
        start_date = _parse_date(start)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"start non valida: {e}")
    days = max(1, min(int(days), 62))

    db = get_db()
    cur = db.conn.cursor()

    # Carica pdc_turn attivi
    where = "WHERE superseded_by_import_id IS NULL"
    params: list = []
    # Se la colonna superseded_by_import_id non esiste (migrazione precedente)
    # fallback senza filtro
    try:
        cur.execute("SELECT superseded_by_import_id FROM pdc_turn LIMIT 1")
    except Exception:
        where = ""
    if deposito:
        where += (" AND " if where else "WHERE ") + "UPPER(impianto) = UPPER(?)"
        params.append(deposito)

    cur.execute(
        f"SELECT id, codice, impianto, profilo FROM pdc_turn {where} ORDER BY codice",
        params,
    )
    turns_raw = cur.fetchall()
    turns: list[dict] = [dict(r) if hasattr(r, "keys") else {
        "id": r[0], "codice": r[1], "impianto": r[2], "profilo": r[3],
    } for r in turns_raw]

    rows: list[AgentGridRow] = []
    for turn in turns:
        cur.execute(
            "SELECT day_number, periodicita, start_time, end_time, "
            "lavoro_min, condotta_min, km, notturno, riposo_min, is_disponibile "
            "FROM pdc_turn_day WHERE pdc_turn_id = ? "
            "ORDER BY day_number, periodicita",
            (turn["id"],),
        )
        days_raw = cur.fetchall()
        turn_days: list[dict] = [
            dict(r) if hasattr(r, "keys") else {
                "day_number": r[0], "periodicita": r[1],
                "start_time": r[2], "end_time": r[3],
                "lavoro_min": r[4], "condotta_min": r[5],
                "km": r[6], "notturno": r[7],
                "riposo_min": r[8], "is_disponibile": r[9],
            } for r in days_raw
        ]
        if not turn_days:
            continue   # turno senza giornate, skip

        cells = _build_cells_for_turn(turn, turn_days, start_date, days)
        totals = _compute_totals(cells)
        rows.append(AgentGridRow(
            pdc_id=turn["id"],
            pdc_code=turn["codice"],
            display_name=turn["codice"],
            matricola="",
            deposito=turn["impianto"],
            totals=totals,
            cells=cells,
        ))

    return AgentGridResponse(
        range_start=start,
        range_days=days,
        deposito=deposito,
        rows=rows,
    )
