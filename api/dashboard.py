"""
Router Dashboard: aggregati KPI, feed attività recenti, linea attiva.

Endpoints:
  - GET /api/dashboard/kpi      — contatori e ore settimana
  - GET /api/activity/recent    — feed eventi (basato su saved_shift)
  - GET /api/linea/attiva       — stato treni monitorati (ARTURO Live)

Dati derivati da saved_shift + ARTURO Live API. Per evitare rate-limit
la linea attiva campiona al massimo 5 treni e ha un cache in-memory 60s.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from typing import Any

import httpx
from fastapi import APIRouter, Depends

from api.deps import get_current_user, get_db
from services import arturo_client

router = APIRouter()


# ───────────────────────────────────────────────────────────────────
# KPI
# ───────────────────────────────────────────────────────────────────

@router.get("/api/dashboard/kpi")
def dashboard_kpi(user: dict = Depends(get_current_user)):
    """Aggrega contatori turni e ore per la dashboard.

    Output:
        {
          "totale_turni": int,
          "turni_settimana": int,
          "giorni_lavorati": int,        # distinti su settimana corrente
          "giorni_max": 7,
          "ore_settimana_min": int,      # somma prestazione_min settimana
          "ore_max_min": 2520,           # 42h * 60
          "delta_30gg_pct": int | None,  # % variazione turni ultimi 30gg vs 30gg precedenti
        }
    """
    db = get_db()
    try:
        uid = None if user["is_admin"] else user["id"]
        shifts = db.get_saved_shifts(user_id=uid)

        totale = len(shifts)

        # Settimana corrente (lun-dom basato su data odierna UTC)
        now = datetime.utcnow()
        start_week = now - timedelta(days=now.weekday())
        start_week = start_week.replace(hour=0, minute=0, second=0, microsecond=0)

        shifts_week = [s for s in shifts if _in_window(s.get("created_at"), start_week, now)]
        turni_settimana = len(shifts_week)
        giorni_lavorati = len({_date_only(s.get("created_at")) for s in shifts_week
                               if s.get("created_at")})
        ore_settimana_min = sum(int(s.get("prestazione_min") or 0) for s in shifts_week)

        # Delta 30gg: turni in [now-30d, now] vs [now-60d, now-30d]
        d30 = now - timedelta(days=30)
        d60 = now - timedelta(days=60)
        n_recent = sum(1 for s in shifts if _in_window(s.get("created_at"), d30, now))
        n_prev = sum(1 for s in shifts if _in_window(s.get("created_at"), d60, d30))
        if n_prev > 0:
            delta = round((n_recent - n_prev) / n_prev * 100)
        elif n_recent > 0:
            delta = 100
        else:
            delta = None

        return {
            "totale_turni": totale,
            "turni_settimana": turni_settimana,
            "giorni_lavorati": giorni_lavorati,
            "giorni_max": 7,
            "ore_settimana_min": ore_settimana_min,
            "ore_max_min": 42 * 60,
            "delta_30gg_pct": delta,
        }
    finally:
        db.close()


def _date_only(ts: Any) -> str:
    """Estrae YYYY-MM-DD da un timestamp ISO o datetime."""
    if not ts:
        return ""
    s = str(ts)
    return s[:10]


def _in_window(ts: Any, start: datetime, end: datetime) -> bool:
    if not ts:
        return False
    try:
        # Formati supportati: "YYYY-MM-DD HH:MM:SS" (SQLite), ISO
        s = str(ts).replace("T", " ")
        dt = datetime.fromisoformat(s[:19])
        return start <= dt <= end
    except (ValueError, TypeError):
        return False


# ───────────────────────────────────────────────────────────────────
# ACTIVITY FEED
# ───────────────────────────────────────────────────────────────────

@router.get("/api/activity/recent")
def activity_recent(limit: int = 20, user: dict = Depends(get_current_user)):
    """Feed di eventi recenti, derivato da saved_shift.

    Output: { "items": [{id, type, title, subtitle, created_at}, ...] }

    Types: "edit" | "validate" | "import" | "conflict". Per ora tutti i
    saved_shift diventano "validate" se hanno 0 violations, "conflict"
    altrimenti. Quando introdurremo l'audit log esteso (Fase 3) questo
    endpoint userà quello.
    """
    db = get_db()
    try:
        uid = None if user["is_admin"] else user["id"]
        shifts = db.get_saved_shifts(user_id=uid)
        items = []
        for s in shifts[: max(1, min(limit, 50))]:
            vlist = s.get("violations") or []
            if isinstance(vlist, str):
                try:
                    vlist = json.loads(vlist)
                except Exception:
                    vlist = []
            has_errors = any(
                (v or {}).get("severity") == "error" for v in vlist
            )
            ev_type = "conflict" if has_errors else "validate"

            train_ids = s.get("train_ids") or []
            if isinstance(train_ids, str):
                try:
                    train_ids = json.loads(train_ids)
                except Exception:
                    train_ids = []
            items.append({
                "id": s.get("id"),
                "type": ev_type,
                "title": s.get("name") or "Turno senza nome",
                "subtitle": f"{s.get('deposito') or '—'} · {s.get('day_type') or '—'} · {len(train_ids)} treni",
                "created_at": s.get("created_at"),
            })
        return {"items": items, "count": len(items)}
    finally:
        db.close()


# ───────────────────────────────────────────────────────────────────
# LINEA ATTIVA (ARTURO Live)
# ───────────────────────────────────────────────────────────────────

# Cache in-memory 60s per evitare rate-limit su ARTURO Live.
_LINEA_CACHE: dict[str, Any] = {"at": 0.0, "data": None}
_LINEA_TTL_SEC = 60.0
_LINEA_MAX_TRAINS = 5


@router.get("/api/linea/attiva")
def linea_attiva(user: dict = Depends(get_current_user)):
    """Stato dei primi N treni tra quelli salvati dall'utente.

    Interroga ARTURO Live per ciascun treno. Cache 60s in-memory per
    non saturare il rate-limit (30 req/min IP).

    Output: {
      "items": [{treno, tratta, stato, ritardo_min, origine, destinazione}, ...],
      "count": int,
      "cached_at": iso_ts | null,
      "note": str | null   # messaggio se ARTURO Live non è raggiungibile
    }
    """
    # Cache hit
    now = time.time()
    cached = _LINEA_CACHE["data"]
    if cached is not None and (now - _LINEA_CACHE["at"]) < _LINEA_TTL_SEC:
        return cached

    db = get_db()
    try:
        uid = None if user["is_admin"] else user["id"]
        shifts = db.get_saved_shifts(user_id=uid)
        # Raccogli train_ids unici dai turni piu recenti
        seen: list[str] = []
        for s in shifts[:20]:
            tids = s.get("train_ids") or []
            if isinstance(tids, str):
                try:
                    tids = json.loads(tids)
                except Exception:
                    tids = []
            for tid in tids:
                if tid not in seen:
                    seen.append(tid)
                if len(seen) >= _LINEA_MAX_TRAINS:
                    break
            if len(seen) >= _LINEA_MAX_TRAINS:
                break

        items: list[dict] = []
        note: str | None = None

        for tid in seen:
            try:
                data = arturo_client.treno(tid)
            except (httpx.HTTPError, Exception) as e:
                note = note or f"ARTURO Live non raggiungibile ({type(e).__name__})"
                continue
            if not data:
                continue
            items.append(_arturo_to_linea_row(tid, data))

        payload = {
            "items": items,
            "count": len(items),
            "cached_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "note": note,
        }
        _LINEA_CACHE["at"] = now
        _LINEA_CACHE["data"] = payload
        return payload
    finally:
        db.close()


def _arturo_to_linea_row(tid: str, treno: dict) -> dict:
    """Converte payload ARTURO Live → riga linea attiva."""
    fermate = treno.get("fermate") or []
    origine = fermate[0].get("stazione") if fermate else ""
    destinazione = fermate[-1].get("stazione") if fermate else ""
    tratta = f"{origine} → {destinazione}" if (origine and destinazione) else "—"

    # Stato: cerca `stato` top-level o deriva dal delay
    stato_raw = (treno.get("stato") or "").lower()
    ritardo_min = int(treno.get("ritardo_minuti") or 0)
    if stato_raw in ("soppresso", "cancelled"):
        stato = "soppresso"
    elif ritardo_min > 5:
        stato = "ritardo"
    else:
        stato = "ok"

    ritardo_label = ""
    if stato == "ritardo":
        ritardo_label = f"+{ritardo_min}′"
    elif stato == "ok":
        ritardo_label = "—"

    return {
        "treno": tid,
        "tratta": tratta,
        "stato": stato,
        "ritardo_min": ritardo_min,
        "ritardo_label": ritardo_label,
        "origine": origine,
        "destinazione": destinazione,
    }
