"""Client per l'API live di ARTURO — Sprint 7.10 MR α.5.

Trova treni commerciali reali da usare come "vettura passiva" (=
deadhead) per riportare il PdC al deposito a fine turno. URL base
in `Settings.live_arturo_api_url`.

Endpoint usati (verificati il 2026-05-05 via Railway CLI):

- ``GET /api/cerca/stazione?q={query}`` →
  ``[{"nome": "LECCO", "id": "S01520"}, ...]``
- ``GET /api/partenze/{stazione_id}`` →
  ``[{"numero", "categoria", "operatore", "destinazione",
       "fermate": [{"stazione_id", "stazione_nome",
                    "programmato_partenza" (ISO),
                    "programmato_arrivo" (ISO|None), ...}]}, ...]``

Il `stazione_id` di live.arturo coincide con il `stazione.codice`
di COLAZIONE (entrambi RFI), quindi non serve un mapping
intermedio: passare direttamente lo stazione_codice al client.

**Robustezza**: in caso di errore di rete, timeout, o response
malformata, le funzioni ritornano ``None``. Mai propagare eccezioni
verso il chiamante (= il builder PdC). Loggare un warning con
contesto utile.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from colazione.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TrenoVettura:
    """Treno commerciale candidato come vettura passiva per il PdC.

    Tutti gli orari in minuti dall'inizio della giornata (00:00-24:00,
    senza data assoluta — il chiamante li interpreta nel calendario
    del turno). Se il treno cross-mezzanotte, ``arrivo_min`` può
    essere < ``partenza_min``: il chiamante deve gestire il wrap.
    """

    numero: str
    categoria: str
    operatore: str | None
    stazione_partenza_codice: str
    stazione_arrivo_codice: str
    partenza_min: int
    arrivo_min: int
    durata_min: int


def _hhmm_to_min(iso_or_hhmm: str | None) -> int | None:
    """Estrae minuti dall'inizio giornata da un timestamp ISO.

    Accetta sia formato ISO completo (``2026-05-05T11:48:00Z``) sia
    HH:MM. Ritorna None se input None o malformato.
    """
    if not iso_or_hhmm:
        return None
    try:
        if "T" in iso_or_hhmm:
            dt = datetime.fromisoformat(iso_or_hhmm.replace("Z", "+00:00"))
            return dt.hour * 60 + dt.minute
        # HH:MM o HH:MM:SS
        parts = iso_or_hhmm.split(":")
        if len(parts) >= 2:
            return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError):
        pass
    return None


async def cerca_stazione(
    nome: str, *, client: httpx.AsyncClient | None = None
) -> str | None:
    """Cerca una stazione per nome e ritorna il primo `id` matchato.

    Usato come fallback quando il chiamante ha solo il nome
    descrittivo (es. "LECCO") e non il codice RFI.

    Returns ``None`` su errore o nessun match.
    """
    settings = get_settings()
    url = f"{settings.live_arturo_api_url}/api/cerca/stazione"
    own_client = client is None
    try:
        if client is None:
            client = httpx.AsyncClient(timeout=settings.live_arturo_timeout_sec)
        try:
            resp = await client.get(url, params={"q": nome})
            resp.raise_for_status()
            data = resp.json()
        finally:
            if own_client:
                await client.aclose()
        if not isinstance(data, list) or not data:
            return None
        first = data[0]
        if not isinstance(first, dict) or "id" not in first:
            return None
        sid = first["id"]
        return str(sid) if sid else None
    except (httpx.HTTPError, ValueError, KeyError) as e:
        logger.warning("live_arturo.cerca_stazione fallita per '%s': %s", nome, e)
        return None


async def trova_treno_vettura(
    *,
    stazione_partenza_codice: str,
    stazione_arrivo_codice: str,
    ora_min_partenza: int,
    max_attesa_min: int = 120,
    client: httpx.AsyncClient | None = None,
) -> TrenoVettura | None:
    """Cerca il primo treno passante per (partenza, arrivo) dopo
    ``ora_min_partenza``.

    Strategia:
    1. ``GET /api/partenze/{stazione_partenza_codice}``
    2. Filtra i treni che:
       - hanno una fermata con ``stazione_id == stazione_arrivo_codice``
         (= il treno passa per il deposito di rientro)
       - partono da ``stazione_partenza_codice`` dopo ``ora_min_partenza``
       - l'attesa (gap fra ``ora_min_partenza`` e partenza treno) ≤
         ``max_attesa_min``
    3. Tra i candidati, sceglie quello con ``partenza_min`` minimo
       (= attesa più breve).

    Returns ``None`` se nessun treno trovato (può capitare:
    nessun passante in finestra, API down, stazione errata, ecc.).
    Il builder usa ``None`` come segnale di "vettura non disponibile"
    e flagga la cosa nei metadata, senza bloccare la generazione.
    """
    settings = get_settings()
    url = f"{settings.live_arturo_api_url}/api/partenze/{stazione_partenza_codice}"
    own_client = client is None
    try:
        if client is None:
            client = httpx.AsyncClient(timeout=settings.live_arturo_timeout_sec)
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
        finally:
            if own_client:
                await client.aclose()
    except httpx.HTTPError as e:
        logger.warning(
            "live_arturo.trova_treno_vettura GET %s fallita: %s", url, e
        )
        return None
    except ValueError as e:
        logger.warning(
            "live_arturo.trova_treno_vettura JSON malformato per %s: %s", url, e
        )
        return None

    if not isinstance(data, list):
        return None

    candidati: list[TrenoVettura] = []
    for treno in data:
        if not isinstance(treno, dict):
            continue
        try:
            cand = _estrai_candidato(
                treno,
                stazione_partenza_codice=stazione_partenza_codice,
                stazione_arrivo_codice=stazione_arrivo_codice,
                ora_min_partenza=ora_min_partenza,
                max_attesa_min=max_attesa_min,
            )
            if cand is not None:
                candidati.append(cand)
        except (KeyError, TypeError, ValueError) as e:
            logger.debug("Treno scartato (parsing): %s", e)
            continue

    if not candidati:
        return None

    # Sceglie il treno con partenza più imminente (= minor attesa).
    candidati.sort(key=lambda t: t.partenza_min)
    return candidati[0]


def _estrai_candidato(
    treno: dict[str, Any],
    *,
    stazione_partenza_codice: str,
    stazione_arrivo_codice: str,
    ora_min_partenza: int,
    max_attesa_min: int,
) -> TrenoVettura | None:
    """Estrae un ``TrenoVettura`` da una entry di /api/partenze, se
    soddisfa i vincoli. Ritorna None altrimenti.
    """
    fermate = treno.get("fermate")
    if not isinstance(fermate, list) or not fermate:
        return None

    # 1. Trova l'INDICE della fermata di PARTENZA (= dove il PdC sale).
    # Sprint 7.10 MR α.5.fix: nella response live arturo la fermata di
    # partenza ha spesso `stazione_id=""` (l'API mette il codice solo
    # sulle fermate intermedie/finali, non su quella di origine).
    # Match esplicito su codice O fallback alla fermata 0.
    fp_idx: int | None = None
    for i, f in enumerate(fermate):
        if isinstance(f, dict) and f.get("stazione_id") == stazione_partenza_codice:
            fp_idx = i
            break
    if fp_idx is None:
        # Fallback: assume `fermate[0]` come partenza.
        fp_idx = 0
    fermata_partenza = fermate[fp_idx]
    if not isinstance(fermata_partenza, dict):
        return None

    partenza_min = _hhmm_to_min(fermata_partenza.get("programmato_partenza"))
    if partenza_min is None:
        return None

    # Vincoli temporali: deve partire DOPO ora_min_partenza e l'attesa
    # NON deve eccedere max_attesa_min.
    attesa = (partenza_min - ora_min_partenza) % (24 * 60)
    if attesa < 0 or attesa > max_attesa_min:
        return None

    # 2. Trova la fermata di ARRIVO nelle fermate SUCCESSIVE all'indice
    # di partenza (così evitiamo direzioni opposte).
    fermata_arrivo: dict[str, Any] | None = None
    for f in fermate[fp_idx + 1 :]:
        if isinstance(f, dict) and f.get("stazione_id") == stazione_arrivo_codice:
            fermata_arrivo = f
            break
    if fermata_arrivo is None:
        return None

    arrivo_min = _hhmm_to_min(fermata_arrivo.get("programmato_arrivo")) or _hhmm_to_min(
        fermata_arrivo.get("programmato_partenza")
    )
    if arrivo_min is None:
        return None

    durata = (arrivo_min - partenza_min) % (24 * 60)
    if durata <= 0:
        return None

    return TrenoVettura(
        numero=str(treno.get("numero", "")),
        categoria=str(treno.get("categoria", "")),
        operatore=treno.get("operatore"),
        stazione_partenza_codice=stazione_partenza_codice,
        stazione_arrivo_codice=stazione_arrivo_codice,
        partenza_min=partenza_min,
        arrivo_min=arrivo_min,
        durata_min=durata,
    )


__all__ = [
    "TrenoVettura",
    "cerca_stazione",
    "trova_treno_vettura",
]
