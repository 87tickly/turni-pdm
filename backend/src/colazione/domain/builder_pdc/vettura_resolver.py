"""Vettura resolver §7.2 — Sprint 8.2 MR-PD3 (parte 1).

Implementa la priorità ordinata per il **rientro PdC al deposito** a
fine giornata (NORMATIVA-PDC §7.2):

1. **VETTURA**: treno commerciale via ``live.arturo.travel`` se NON
   sfora il cap prestazione 8h30 (510 min standard / 420 min notturno).
2. **MM** (Metropolitana): se la vettura sfora E il deposito è in una
   località servita dalla metropolitana di Milano. Tempo MM stimato
   forfettario.
3. **VOCTAXI** (vettura occasionale taxi): fallback sempre disponibile.

**Non gestisce**:

- §7.3 condotta come rientro produttivo (priorità SUPERIORE alla
  vettura passiva). Va valutato a monte dal builder: se esiste un
  treno di condotta che porta verso il deposito, NON si invoca questo
  resolver.
- Vettura di **partenza** (§3.2 15' pre-vettura ai bordi). Concettualmente
  speculare ma con vincoli temporali diversi (non c'è cap 8h30 prima
  della presa servizio). Modulo separato in MR-PD3 parte 2 se serve.

L'output è un dataclass ``SceltaRientro`` discriminated union con il
tipo (``VETTURA``/``MM``/``VOCTAXI``) e i dettagli operativi necessari
al builder per costruire il blocco corrispondente nel TurnoPdc.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import httpx

from colazione.integrations.live_arturo import (
    PartenzeCache,
    TrenoVettura,
    trova_treno_vettura,
)

logger = logging.getLogger(__name__)


# =====================================================================
# Costanti
# =====================================================================

#: Cap prestazione standard PdC (NORMATIVA-PDC §3 → 8h30 = 510 min).
PRESTAZIONE_MAX_STANDARD_MIN: int = 510

#: Cap prestazione notturno (presa 01:00-04:59 → 7h = 420 min).
PRESTAZIONE_MAX_NOTTURNO_MIN: int = 420

#: Estensione "fine servizio" dopo arrivo vettura ai bordi (NORMATIVA-PDC §3.2).
FINE_SERVIZIO_POST_VETTURA_MIN: int = 15

#: Buffer fra fine servizio operativo e partenza vettura (gap minimo
#: per uscire dal binario, raggiungere la vettura passeggero).
VETTURA_GAP_PRE_MIN: int = 5

#: Attesa massima fra fine servizio operativo e partenza vettura.
#: Sopra questo valore il PdC sta troppo "fermo" e il rientro non è
#: competitivo (= meglio MM o VOCTAXI direttamente).
VETTURA_ATTESA_MAX_MIN: int = 120

#: Codici Depot Trenord che sono in **Milano servito da MM**.
#: NORMATIVA-PDC §7.2 step 2: "MM si usa se la vettura sforerebbe 8h30
#: e il deposito si trova in una località servita dalla MM (tipico:
#: Milano)".
#: NORMATIVA-PDC §2.2: i depositi MILANO_PG sono ``GARIBALDI_*`` (3
#: gruppi → 1 deposito MI.PG); i depositi MIGP sono ``GRECO_*`` (2
#: gruppi → 1 deposito MIGP); FIORENZA è impianto materiale + deposito
#: PdC.
DEPOT_MILANO_MM: frozenset[str] = frozenset(
    {
        "GARIBALDI_ALE",
        "GARIBALDI_CADETTI",
        "GARIBALDI_TE",
        "GRECO_TE",
        "GRECO_S9",
        "FIORENZA",
    }
)

#: Tempo MM forfettario stazione → deposito Milano (stima operativa,
#: indipendente da quale linea MM). Più di 30' significa che NON è MM
#: utile e si dovrebbe ricadere su VOCTAXI.
MM_DURATA_FORFETTARIA_MIN: int = 30

#: Tempo VOCTAXI forfettario (taxi). Stima conservativa per Milano e
#: provincia immediata. Per depositi periferici (Sondrio, Cremona,
#: ecc.) il tempo reale può essere maggiore — il resolver lo stima
#: all'interno della finestra accettabile, lasciando al builder la
#: validazione del cap prestazione finale.
VOCTAXI_DURATA_DEFAULT_MIN: int = 30


# =====================================================================
# Dataclass output (discriminated union)
# =====================================================================


@dataclass(frozen=True)
class SceltaVettura:
    """Tipo VETTURA: il PdC viaggia come passeggero su un treno
    commerciale via API ``live.arturo.travel``."""

    tipo: Literal["VETTURA"]
    treno: TrenoVettura
    prestazione_finale_min: int
    """Prestazione totale del turno includendo la vettura
    (ora_presa → ora_arrivo_vettura + 15 min). Garantita ≤ cap."""


@dataclass(frozen=True)
class SceltaMM:
    """Tipo MM: il PdC rientra in metropolitana. Tempo forfettario."""

    tipo: Literal["MM"]
    durata_min: int
    """Durata MM (default ``MM_DURATA_FORFETTARIA_MIN``)."""

    motivo: str
    """Motivazione operativa (es. "vettura sfora 8h30, MM disponibile a
    Milano"). Visibile in UI."""


@dataclass(frozen=True)
class SceltaVOCTAXI:
    """Tipo VOCTAXI: il PdC rientra in taxi. Fallback finale."""

    tipo: Literal["VOCTAXI"]
    durata_min: int
    """Durata stimata (default ``VOCTAXI_DURATA_DEFAULT_MIN``)."""

    motivo: str
    """Motivazione operativa (es. "deposito periferico, niente MM",
    "vettura sfora 8h30 + deposito non Milano"). Visibile in UI."""


SceltaRientro = SceltaVettura | SceltaMM | SceltaVOCTAXI


# =====================================================================
# Resolver
# =====================================================================


async def risolvi_rientro(
    *,
    deposito_codice: str,
    deposito_stazione_codice: str,
    stazione_chiusura_codice: str,
    ora_presa_min: int,
    ora_chiusura_servizio_min: int,
    is_cap_notturno: bool,
    live_client: httpx.AsyncClient,
    cache: PartenzeCache | None = None,
) -> SceltaRientro:
    """Risolve il rientro PdC al deposito secondo NORMATIVA-PDC §7.2.

    Args:
        deposito_codice: Codice del Depot di residenza del PdC (es.
            ``"GARIBALDI_TE"``, ``"FIORENZA"``, ``"BERGAMO"``). Usato
            per il check "deposito a Milano" nello step MM.
        deposito_stazione_codice: ``Depot.stazione_principale_codice``.
            È la stazione in cui il PdC deve rientrare.
        stazione_chiusura_codice: Stazione in cui il PdC chiude il
            servizio produttivo. Se uguale a ``deposito_stazione_codice``
            il rientro è 0' (il chiamante NON dovrebbe invocare questo
            resolver in quel caso, ma per robustezza lo gestiamo:
            ritorna VOCTAXI 0' come no-op).
        ora_presa_min: Minuti dall'inizio giornata della presa servizio.
            Serve per calcolare la prestazione finale con la vettura.
        ora_chiusura_servizio_min: Minuti dall'inizio giornata della
            fine servizio operativo (= dopo ACCa o ultimo blocco
            condotta + ACCa). La vettura cerca treni dopo
            ``ora_chiusura_servizio_min + VETTURA_GAP_PRE_MIN``.
        is_cap_notturno: Sprint 8.2 SEVERO S1 fix. True se applicare
            cap prestazione 420 min (presa servizio 01:00-04:59 da
            NORMATIVA §3). Distinto dal flag UI ``is_notturno``
            superinclusivo che marca anche turni che finiscono dopo
            le 22 o cross-mezzanotte.
        live_client: Client httpx già aperto, condiviso con il builder
            per riusare la connessione TLS.
        cache: ``PartenzeCache`` opzionale per riusare le response
            ``/api/partenze/{stazione}`` fra più chiamate del builder.

    Returns:
        ``SceltaVettura`` (priorità 1), ``SceltaMM`` (priorità 2 se
        Milano), ``SceltaVOCTAXI`` (fallback finale).
    """
    # Caso degenere: il PdC è già al deposito → no-op.
    if stazione_chiusura_codice == deposito_stazione_codice:
        return SceltaVOCTAXI(
            tipo="VOCTAXI",
            durata_min=0,
            motivo="rientro nullo: chiusura coincide col deposito",
        )

    cap_prestazione = (
        PRESTAZIONE_MAX_NOTTURNO_MIN if is_cap_notturno else PRESTAZIONE_MAX_STANDARD_MIN
    )

    # Step 1: cerca vettura via API live.arturo.travel.
    treno = await trova_treno_vettura(
        stazione_partenza_codice=stazione_chiusura_codice,
        stazione_arrivo_codice=deposito_stazione_codice,
        ora_min_partenza=ora_chiusura_servizio_min + VETTURA_GAP_PRE_MIN,
        max_attesa_min=VETTURA_ATTESA_MAX_MIN,
        client=live_client,
        cache=cache,
    )

    if treno is not None:
        # Verifica che la vettura NON sfori il cap prestazione.
        # NORMATIVA-PDC §3.2: "fine servizio = arrivo vettura + 15 min".
        # Quindi prestazione_finale = ora_arrivo_vettura + 15 - ora_presa.
        ora_fine_servizio_finale = (
            treno.arrivo_min + FINE_SERVIZIO_POST_VETTURA_MIN
        ) % (24 * 60)
        prestazione_finale = (ora_fine_servizio_finale - ora_presa_min) % (24 * 60)
        if prestazione_finale == 0:
            prestazione_finale = 24 * 60

        if prestazione_finale <= cap_prestazione:
            return SceltaVettura(
                tipo="VETTURA",
                treno=treno,
                prestazione_finale_min=prestazione_finale,
            )
        # Vettura sfora cap → cade su step 2.
        logger.info(
            "vettura_resolver: vettura %s sfora cap (%d > %d min), "
            "cerco MM o VOCTAXI",
            treno.numero,
            prestazione_finale,
            cap_prestazione,
        )

    # Step 2: MM se deposito è a Milano servito.
    if deposito_codice in DEPOT_MILANO_MM:
        if treno is not None:
            motivo = (
                f"vettura {treno.numero} sfora cap prestazione "
                f"({cap_prestazione}min); fallback MM (deposito Milano)"
            )
        else:
            motivo = "nessuna vettura utile; fallback MM (deposito Milano)"
        return SceltaMM(
            tipo="MM",
            durata_min=MM_DURATA_FORFETTARIA_MIN,
            motivo=motivo,
        )

    # Step 3: VOCTAXI fallback finale.
    if treno is not None:
        motivo = (
            f"vettura {treno.numero} sfora cap prestazione "
            f"({cap_prestazione}min); deposito {deposito_codice} non in "
            f"area Milano-MM → VOCTAXI"
        )
    else:
        motivo = (
            f"nessuna vettura utile; deposito {deposito_codice} non in "
            f"area Milano-MM → VOCTAXI"
        )
    return SceltaVOCTAXI(
        tipo="VOCTAXI",
        durata_min=VOCTAXI_DURATA_DEFAULT_MIN,
        motivo=motivo,
    )


__all__ = [
    "DEPOT_MILANO_MM",
    "MM_DURATA_FORFETTARIA_MIN",
    "PRESTAZIONE_MAX_NOTTURNO_MIN",
    "PRESTAZIONE_MAX_STANDARD_MIN",
    "SceltaMM",
    "SceltaRientro",
    "SceltaVOCTAXI",
    "SceltaVettura",
    "VETTURA_ATTESA_MAX_MIN",
    "VETTURA_GAP_PRE_MIN",
    "VOCTAXI_DURATA_DEFAULT_MIN",
    "risolvi_rientro",
]
