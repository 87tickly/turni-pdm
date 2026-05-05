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

**Sprint 7.10 MR α.8.2**: cache per (azienda, stazione) + retry
backoff su 429. Per un giro tipico (8 segmenti × 25 depositi
candidati × 3 lookup) avrei 600 chiamate; con cache + retry
diventano ~30 chiamate (= 1 per ogni stazione distinta toccata).
La cache è scope-funzione: l'utente la inizializza all'inizio
della generazione di un giro e la passa al client per tutta la
durata.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx

from colazione.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class PartenzeCache:
    """Sprint 7.10 MR α.8.2: cache in-memory delle response
    ``/api/partenze/{stazione_id}``. Una entry per stazione, riusata
    per tutti i lookup dentro la stessa generazione di giro.

    NB: la cache assume che lo stato dell'API live sia "fermo" per la
    durata della generazione (in pratica pochi secondi). Se più di
    qualche minuto passa, le partenze potrebbero essere variate ma
    per i nostri lookup (orari programmati) è ininfluente.
    """

    by_stazione: dict[str, list[dict[str, Any]] | None] = field(default_factory=dict)
    """``stazione_id → response (lista treni)`` se trovata; ``None``
    se l'API ha definitivamente fallito (429 dopo retry, 500, ecc.)
    e non vogliamo riprovare nello stesso giro."""

    hits: int = 0
    misses: int = 0
    errori: int = 0


_RETRY_429_DELAYS_SEC: tuple[float, ...] = (0.2, 0.5, 1.0)
"""Sprint 7.10 MR α.8.2: backoff per retry su 429 Too Many Requests.
3 retry totali con delay crescente. Se anche dopo il terzo fallisce,
arrendersi e cachare None."""


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


async def _fetch_partenze(
    stazione_codice: str,
    *,
    client: httpx.AsyncClient,
    cache: PartenzeCache | None,
) -> list[dict[str, Any]] | None:
    """Fetch /api/partenze/{stazione} con cache + retry 429.

    Se ``cache`` è valorizzata e contiene già un'entry per la
    stazione, riusa quella senza fare la chiamata. Altrimenti fa la
    chiamata e cacha il risultato (anche se è ``None`` per evitare
    di ripetere errori).

    Retry su 429: backoff 200ms → 500ms → 1s. Se dopo il terzo
    retry ancora 429 → ritorna None.
    """
    if cache is not None and stazione_codice in cache.by_stazione:
        cache.hits += 1
        return cache.by_stazione[stazione_codice]

    settings = get_settings()
    url = f"{settings.live_arturo_api_url}/api/partenze/{stazione_codice}"

    last_exc: Exception | None = None
    data: list[dict[str, Any]] | None = None

    for tentativo, delay_pre in enumerate([0.0, *_RETRY_429_DELAYS_SEC]):
        if delay_pre > 0:
            await asyncio.sleep(delay_pre)
        try:
            resp = await client.get(url)
            if resp.status_code == 429:
                logger.info(
                    "live_arturo: 429 su %s (tentativo %d/%d), retry in %.1fs",
                    stazione_codice,
                    tentativo + 1,
                    len(_RETRY_429_DELAYS_SEC) + 1,
                    _RETRY_429_DELAYS_SEC[tentativo]
                    if tentativo < len(_RETRY_429_DELAYS_SEC)
                    else 0.0,
                )
                continue
            resp.raise_for_status()
            payload = resp.json()
            if isinstance(payload, list):
                data = payload
            else:
                data = None
            break
        except httpx.HTTPError as e:
            last_exc = e
            break  # errore non-429: non riprovare
        except ValueError as e:
            last_exc = e
            data = None
            break

    if last_exc is not None:
        logger.warning(
            "live_arturo._fetch_partenze GET %s fallita: %s", url, last_exc
        )
        if cache is not None:
            cache.errori += 1
            cache.by_stazione[stazione_codice] = None
        return None

    if cache is not None:
        cache.misses += 1
        cache.by_stazione[stazione_codice] = data
    return data


async def trova_treno_vettura(
    *,
    stazione_partenza_codice: str,
    stazione_arrivo_codice: str,
    ora_min_partenza: int,
    max_attesa_min: int = 120,
    client: httpx.AsyncClient | None = None,
    cache: PartenzeCache | None = None,
) -> TrenoVettura | None:
    """Cerca il primo treno passante per (partenza, arrivo) dopo
    ``ora_min_partenza``.

    Sprint 7.10 MR α.8.2: la chiamata API ``/api/partenze/{stazione}``
    è cachata per la durata della generazione del giro tramite
    ``cache``. Una sola chiamata HTTP per stazione, indipendentemente
    da quante coppie (partenza, arrivo, finestra) la usano.

    Strategia:
    1. Recupera (o cacha) la lista treni passanti per
       ``stazione_partenza_codice`` da ``/api/partenze/{stazione}``.
    2. Filtra in-memory i treni che:
       - hanno una fermata con ``stazione_id == stazione_arrivo_codice``
       - partono da ``stazione_partenza_codice`` dopo
         ``ora_min_partenza`` (con attesa ≤ ``max_attesa_min``).
    3. Tra i candidati, sceglie quello con ``partenza_min`` minimo.

    Returns ``None`` se nessun treno trovato (nessun passante in
    finestra, API down dopo retry, stazione errata, ecc.).
    """
    own_client = client is None
    try:
        if client is None:
            settings = get_settings()
            client = httpx.AsyncClient(timeout=settings.live_arturo_timeout_sec)
        try:
            data = await _fetch_partenze(
                stazione_partenza_codice, client=client, cache=cache
            )
        finally:
            if own_client:
                await client.aclose()
    except httpx.HTTPError as e:
        logger.warning(
            "live_arturo.trova_treno_vettura wrapper failure for %s: %s",
            stazione_partenza_codice,
            e,
        )
        return None

    if data is None:
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
    "PartenzeCache",
    "TrenoVettura",
    "cerca_stazione",
    "trova_treno_vettura",
]
