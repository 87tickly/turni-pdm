"""
Client API per ARTURO Live (live.arturo.travel).
Sostituisce le chiamate dirette a ViaggiaTreno con le API normalizzate di ARTURO.

Endpoint pubblici, nessuna autenticazione richiesta.
Rate limit: 30 req/min per IP.
"""

from __future__ import annotations

import httpx

BASE_URL = "https://live.arturo.travel/api"
TIMEOUT = 10.0
USER_AGENT = "COLAZIONE-TurniPDM/2.0"


def _client() -> httpx.Client:
    """Client sincrono con timeout e User-Agent."""
    return httpx.Client(
        base_url=BASE_URL,
        timeout=TIMEOUT,
        headers={"User-Agent": USER_AGENT},
    )


def cerca_stazione(q: str) -> list[dict]:
    """Autocomplete stazione. Ritorna lista di {nome, id}.
    L'id può essere 'S01700' (stazione) o 'node:milano' (nodo aggregato)."""
    with _client() as c:
        r = c.get("/cerca/stazione", params={"q": q})
        r.raise_for_status()
        return r.json()


def partenze(stazione_id: str) -> list[dict]:
    """Partenze da una stazione. Ritorna lista di Treno con fermate."""
    with _client() as c:
        r = c.get(f"/partenze/{stazione_id}")
        r.raise_for_status()
        return r.json()


def arrivi(stazione_id: str) -> list[dict]:
    """Arrivi a una stazione. Ritorna lista di Treno con fermate."""
    with _client() as c:
        r = c.get(f"/arrivi/{stazione_id}")
        r.raise_for_status()
        return r.json()


def treno(numero: str, origine: str | None = None) -> dict | None:
    """Dettaglio treno con fermate e orari reali.
    Ritorna None se il treno non è trovato."""
    params = {"origine": origine} if origine else {}
    with _client() as c:
        r = c.get(f"/treno/{numero}", params=params)
        r.raise_for_status()
        data = r.json()
        return data if data else None


def cerca_tratta(da: str, a: str, quando: str | None = None) -> dict:
    """Cerca treni tra due stazioni.
    quando: 'oggi', 'domani', 'stasera', 'domani_mattina', 'domani_sera', o 'HH:MM'."""
    params = {"da": da, "a": a}
    if quando:
        params["quando"] = quando
    with _client() as c:
        r = c.get("/cerca/tratta", params=params)
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# Helpers di conversione per compatibilità con il resto di COLAZIONE
# ---------------------------------------------------------------------------

def resolve_station_id(station_name: str) -> str | None:
    """Risolvi nome stazione → id ARTURO (es. 'MILANO CENTRALE' → 'S01700').
    Usa l'autocomplete e prende il primo risultato."""
    results = cerca_stazione(station_name)
    if not results:
        return None
    # Match esatto prima, poi primo risultato
    name_upper = station_name.strip().upper()
    for r in results:
        if r["nome"].upper() == name_upper:
            return r["id"]
    return results[0]["id"]


def fermata_to_times(fermata: dict) -> tuple[str, str, str, str]:
    """Estrai orari da una fermata ARTURO.
    Ritorna (dep_prog, dep_reale, arr_prog, arr_reale) come 'HH:MM' o ''."""
    def _ts_to_hhmm(ts: str | None) -> str:
        if not ts:
            return ""
        # Format: "2026-04-14T09:01:00"
        try:
            return ts[11:16]  # "09:01"
        except (IndexError, TypeError):
            return ""

    return (
        _ts_to_hhmm(fermata.get("programmato_partenza")),
        _ts_to_hhmm(fermata.get("effettivo_partenza")),
        _ts_to_hhmm(fermata.get("programmato_arrivo")),
        _ts_to_hhmm(fermata.get("effettivo_arrivo")),
    )


def treno_to_dep_time(treno: dict) -> str:
    """Estrai orario partenza programmato dal primo fermata."""
    fermate = treno.get("fermate", [])
    if fermate:
        prog = fermate[0].get("programmato_partenza", "")
        if prog:
            try:
                return prog[11:16]
            except (IndexError, TypeError):
                pass
    return ""


def treno_to_arr_time(treno: dict) -> str:
    """Estrai orario arrivo programmato dall'ultimo fermata."""
    fermate = treno.get("fermate", [])
    if fermate:
        prog = fermate[-1].get("programmato_arrivo", "")
        if prog:
            try:
                return prog[11:16]
            except (IndexError, TypeError):
                pass
    return ""
