"""
Train Route Cache — verifica rotte treno via live.arturo.travel con cache su DB.

Strategia (richiesta utente):
- Prima chiamata su un (train_id, origine_hint): chiama API ARTURO Live,
  salva fermate nel DB, ritorna dati certi
- Chiamate successive: usa direttamente il DB
- Cosi' la prima generazione e' lenta, le successive veloci

Rate limit ARTURO Live: 30 req/min per IP. Il cache evita di sforare
in scenari ripetuti.

Errori transienti (timeout, 5xx) NON vengono cacheati (riprova al
prossimo giro). Errori 404 (treno inesistente) vengono cacheati con
api_status='not_found' per evitare query ripetute inutili.
"""
from __future__ import annotations

import asyncio
from typing import Optional

import httpx

from services import arturo_client
from src.database.db import Database

BASE_URL = "https://live.arturo.travel/api"
TIMEOUT = 10.0
USER_AGENT = "COLAZIONE-TurniPDM/2.0"
# Rate-limit live.arturo.travel: 30 req/min per IP. Con 10 connessioni
# concorrenti manteniamo ~1 burst al secondo, comodamente sotto la soglia.
MAX_CONCURRENT_FETCH = 10


def get_or_fetch_train_route(
    db: Database,
    train_id: str,
    origine_hint: str = "",
    force_refresh: bool = False,
) -> Optional[dict]:
    """
    Restituisce la rotta verificata di un treno, da cache DB se presente,
    altrimenti chiamando l'API live.arturo.travel.

    Returns:
      dict con chiavi:
        - train_id, origine, destinazione
        - fermate: lista di {stazione_nome, programmato_partenza, ...}
        - operatore, categoria
        - api_status: 'ok' | 'not_found' | 'error_transient'
      None solo se train_id e' vuoto.
    """
    tid = (train_id or "").strip()
    if not tid:
        return None

    # 1) Prova cache (a meno di force_refresh)
    if not force_refresh:
        cached = db.get_train_route_cached(tid, origine_hint)
        if cached and cached.get("api_status") in ("ok", "not_found"):
            return {
                "train_id": cached["train_id"],
                "origine": cached.get("first_station", ""),
                "destinazione": cached.get("last_station", ""),
                "fermate": cached.get("fermate", []),
                "operatore": cached.get("operatore", ""),
                "categoria": cached.get("categoria", ""),
                "api_status": cached.get("api_status", "ok"),
                "from_cache": True,
            }

    # 2) Chiama API
    try:
        data = arturo_client.treno(tid, origine=origine_hint or None)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            # Treno non esiste — cachea il fatto per evitare retry
            db.upsert_train_route(
                tid, origine_hint,
                fermate=[], operatore="", categoria="",
                api_status="not_found",
            )
            return {
                "train_id": tid, "origine": "", "destinazione": "",
                "fermate": [], "operatore": "", "categoria": "",
                "api_status": "not_found", "from_cache": False,
            }
        # Altri HTTP error: transient, NON cachea
        return {
            "train_id": tid, "origine": "", "destinazione": "",
            "fermate": [], "operatore": "", "categoria": "",
            "api_status": "error_transient", "from_cache": False,
        }
    except (httpx.RequestError, httpx.TimeoutException):
        # Network error: transient, NON cachea
        return {
            "train_id": tid, "origine": "", "destinazione": "",
            "fermate": [], "operatore": "", "categoria": "",
            "api_status": "error_transient", "from_cache": False,
        }

    if not data:
        # API ha risposto ma vuoto: come not_found
        db.upsert_train_route(
            tid, origine_hint,
            fermate=[], operatore="", categoria="",
            api_status="not_found",
        )
        return {
            "train_id": tid, "origine": "", "destinazione": "",
            "fermate": [], "operatore": "", "categoria": "",
            "api_status": "not_found", "from_cache": False,
        }

    fermate = data.get("fermate", []) or []
    operatore = data.get("operatore", "") or ""
    categoria = data.get("categoria", "") or ""

    # Salva in cache
    db.upsert_train_route(
        tid, origine_hint,
        fermate=fermate,
        operatore=operatore,
        categoria=categoria,
        api_status="ok",
    )

    return {
        "train_id": tid,
        "origine": data.get("origine", "") or "",
        "destinazione": data.get("destinazione", "") or "",
        "fermate": fermate,
        "operatore": operatore,
        "categoria": categoria,
        "api_status": "ok",
        "from_cache": False,
    }


def fetch_routes_batch(
    db: Database,
    pairs: list[tuple[str, str]],
) -> dict[tuple[str, str], dict]:
    """
    Batch fetch rotte treni. Sostituisce un loop di get_or_fetch_train_route
    con: (1) lookup cache DB per tutti, (2) fetch async concorrente dei
    missing via httpx.AsyncClient, (3) upsert cache + return dict.

    Restituisce: { (train_id, origine_hint_upper): route_dict }

    route_dict ha la stessa struttura di get_or_fetch_train_route:
      { train_id, origine, destinazione, fermate, operatore, categoria,
        api_status, from_cache }

    Benchmark atteso: 75 treni cache-miss passano da ~45s sync a ~3s
    concorrente (MAX_CONCURRENT_FETCH=10).
    """
    results: dict[tuple[str, str], dict] = {}
    # Deduplica (tid, origine_hint_upper) per evitare query duplicate
    seen: set = set()
    unique_pairs: list[tuple[str, str]] = []
    for tid, orig in pairs:
        key = ((tid or "").strip(), (orig or "").upper().strip())
        if not key[0] or key in seen:
            continue
        seen.add(key)
        unique_pairs.append(key)

    missing: list[tuple[str, str]] = []
    for tid, orig in unique_pairs:
        cached = db.get_train_route_cached(tid, orig)
        if cached and cached.get("api_status") in ("ok", "not_found"):
            results[(tid, orig)] = {
                "train_id": cached["train_id"],
                "origine": cached.get("first_station", ""),
                "destinazione": cached.get("last_station", ""),
                "fermate": cached.get("fermate", []),
                "operatore": cached.get("operatore", ""),
                "categoria": cached.get("categoria", ""),
                "api_status": cached.get("api_status", "ok"),
                "from_cache": True,
            }
        else:
            missing.append((tid, orig))

    if not missing:
        return results

    async def _fetch_all() -> list[tuple[str, str, str, Optional[dict]]]:
        sem = asyncio.Semaphore(MAX_CONCURRENT_FETCH)
        async with httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            async def _one(tid: str, orig: str):
                params = {"origine": orig} if orig else {}
                async with sem:
                    try:
                        r = await client.get(f"/treno/{tid}", params=params)
                        if r.status_code == 404:
                            return (tid, orig, "not_found", None)
                        r.raise_for_status()
                        data = r.json()
                        if not data:
                            return (tid, orig, "not_found", None)
                        return (tid, orig, "ok", data)
                    except (httpx.HTTPStatusError, httpx.RequestError,
                            httpx.TimeoutException):
                        return (tid, orig, "error_transient", None)

            tasks = [_one(tid, orig) for tid, orig in missing]
            return await asyncio.gather(*tasks, return_exceptions=False)

    try:
        fetched = asyncio.run(_fetch_all())
    except RuntimeError:
        # Caso raro: siamo gia' in un event loop (es. chiamata da async
        # context). Fallback sequenziale via client sync per sicurezza.
        fetched = []
        for tid, orig in missing:
            route = get_or_fetch_train_route(db, tid, origine_hint=orig)
            results[(tid, orig)] = route or {
                "train_id": tid, "origine": "", "destinazione": "",
                "fermate": [], "operatore": "", "categoria": "",
                "api_status": "error_transient", "from_cache": False,
            }
        return results

    for tid, orig, status, data in fetched:
        if status == "not_found":
            db.upsert_train_route(
                tid, orig,
                fermate=[], operatore="", categoria="",
                api_status="not_found",
            )
            results[(tid, orig)] = {
                "train_id": tid, "origine": "", "destinazione": "",
                "fermate": [], "operatore": "", "categoria": "",
                "api_status": "not_found", "from_cache": False,
            }
        elif status == "ok" and data is not None:
            fermate = data.get("fermate", []) or []
            operatore = data.get("operatore", "") or ""
            categoria = data.get("categoria", "") or ""
            db.upsert_train_route(
                tid, orig,
                fermate=fermate,
                operatore=operatore,
                categoria=categoria,
                api_status="ok",
            )
            results[(tid, orig)] = {
                "train_id": tid,
                "origine": data.get("origine", "") or "",
                "destinazione": data.get("destinazione", "") or "",
                "fermate": fermate,
                "operatore": operatore,
                "categoria": categoria,
                "api_status": "ok",
                "from_cache": False,
            }
        else:
            # Transient: NON cachea, ritorna placeholder
            results[(tid, orig)] = {
                "train_id": tid, "origine": "", "destinazione": "",
                "fermate": [], "operatore": "", "categoria": "",
                "api_status": "error_transient", "from_cache": False,
            }
    return results


def fermate_passes_through(fermate: list, station_name: str) -> bool:
    """True se una delle fermate corrisponde alla stazione (case-insensitive)."""
    needle = (station_name or "").upper().strip()
    if not needle:
        return False
    for f in fermate or []:
        nm = (f.get("stazione_nome") or "").upper().strip()
        if nm == needle:
            return True
    return False


def fermate_segment(fermate: list, from_station: str,
                    to_station: str) -> Optional[tuple]:
    """
    Trova nel percorso del treno i due indici corrispondenti a (from, to)
    nell'ordine corretto. Ritorna (idx_from, idx_to) o None se non
    e' un sotto-percorso valido (es. ordine inverso o non presente).
    """
    f_n = (from_station or "").upper().strip()
    t_n = (to_station or "").upper().strip()
    if not f_n or not t_n:
        return None
    idx_from = idx_to = None
    for i, f in enumerate(fermate or []):
        nm = (f.get("stazione_nome") or "").upper().strip()
        if idx_from is None and nm == f_n:
            idx_from = i
            continue
        if idx_from is not None and idx_to is None and nm == t_n:
            idx_to = i
            break
    if idx_from is None or idx_to is None or idx_to <= idx_from:
        return None
    return (idx_from, idx_to)
