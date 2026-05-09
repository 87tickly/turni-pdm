"""Builder deposito-first per turno PdC — Sprint 8.2 MR-PD3b.

Implementa il modello "ciclo casa-casa": il turno PdC è ancorato per
costruzione al **deposito di residenza**. La giornata-tipo:

1. Inizia con PRESA servizio + ACCp dalla stazione di apertura.
2. Lavora N corse (CONDOTTA, PK fra le corse, eventuale REFEZ).
3. Termina con ACCa.
4. **NUOVO**: se la stazione di chiusura ≠ deposito, aggiunge un
   blocco di **rientro** scelto da `vettura_resolver.risolvi_rientro`
   (NORMATIVA-PDC §7.2 priorità VETTURA → MM → VOCTAXI).
5. Chiude con FINE servizio (15' dopo l'ultimo blocco operativo).

GARANZIE per costruzione:

- ``stazione_fine = depot.stazione_principale_codice`` SEMPRE
  (NORMATIVA-PDC §2.3 "il PdC rientra sempre al proprio deposito").
- Cap condotta 5h30 (330 min) **HARD**: giornate che lo eccedono sono
  **SCARTATE** (return ``None`` + violazione), non solo annotate come
  fa il builder monolitico.
- Cap prestazione 8h30 standard / 7h notturno **HARD post-rientro**:
  se VETTURA è valida ma MM/VOCTAXI forfettari spingono oltre, scarta.

NON gestisce ancora (scope MR successivi):

- §7.3 condotta come rientro produttivo (richiede ranking sui treni
  candidati al rientro: prima condotta produttiva, poi vettura
  passiva, poi MM/VOCTAXI). Sprint 8.3 MR-C7.
- §9 split CV intermedi → Sprint 8.3 MR-C7.
- §10.3 FR g1+g2 unica unità multi-giornata → Sprint 8.3 MR-C8.
- §3.2 vettura ai bordi DI PARTENZA (è il rientro che gestiamo qui).
- §11.2/§11.3/§11.4 ciclo settimanale → MR-PD7.
"""

from __future__ import annotations

import logging
from dataclasses import replace

import httpx

from colazione.domain.builder_pdc.builder import (
    ACCESSORI_MIN_STANDARD,
    CONDOTTA_MAX_MIN,
    FINE_SERVIZIO_MIN,
    _BloccoPdcDraft,
    _build_giornata_pdc,
    _from_min,
    _GiornataPdcDraft,
    _t,
)
from colazione.domain.builder_pdc.vettura_resolver import (
    PRESTAZIONE_MAX_NOTTURNO_MIN,
    PRESTAZIONE_MAX_STANDARD_MIN,
    ScelzaMM,
    ScelzaRientro,
    ScelzaVettura,
    ScelzaVOCTAXI,
    risolvi_rientro,
)
from colazione.integrations.live_arturo import PartenzeCache
from colazione.models.anagrafica import Depot
from colazione.models.giri import GiroBlocco

logger = logging.getLogger(__name__)


# =====================================================================
# Helper: aggiunta blocco rientro alla giornata
# =====================================================================


def _inserisci_blocco_rientro(
    *,
    blocchi: list[_BloccoPdcDraft],
    rientro: ScelzaRientro,
    deposito_stazione: str,
    stazione_chiusura: str,
    ora_fine_acca_min: int,
) -> tuple[list[_BloccoPdcDraft], int, int]:
    """Inserisce il blocco di rientro PRIMA del FINE servizio.

    Strategia:

    - Per **VETTURA**: blocco con ``ora_inizio = treno.partenza_min``,
      ``ora_fine = treno.arrivo_min``. Il blocco FINE viene riposizionato
      a ``treno.arrivo_min .. treno.arrivo_min + 15`` (NORMATIVA-PDC
      §3.2: fine servizio = arrivo vettura + 15 min).
    - Per **MM** / **VOCTAXI**: blocco con ``ora_inizio = ora_fine_acca``,
      ``ora_fine = ora_fine_acca + durata``. Il blocco FINE viene
      riposizionato a ``ora_fine_rientro .. ora_fine_rientro + 15``.

    Returns:
        Tupla ``(nuovi_blocchi, ora_inizio_rientro_min, ora_fine_rientro_min)``.
        Le ore servono per ricalcolare la prestazione.

    Note: ``rientro.durata_min == 0`` per ScelzaVOCTAXI con chiusura
    coincidente al deposito è un caso degenere che NON dovrebbe
    arrivare qui (filtrato a monte). Per robustezza, se durata=0
    ritorna i blocchi invariati.
    """
    # Trova il blocco FINE (sempre l'ultimo per costruzione builder MVP).
    fine_idx = -1
    for i, b in enumerate(blocchi):
        if b.tipo_evento == "FINE":
            fine_idx = i
            break
    if fine_idx == -1:
        # Builder MVP garantisce un blocco FINE; se manca è anomalia
        # logica del chiamante. Ritorna invariato per non rompere.
        logger.warning(
            "deposito_first: blocco FINE non trovato in giornata, skip rientro"
        )
        return blocchi, ora_fine_acca_min, ora_fine_acca_min

    # Caso degenere: rientro durata 0 (chiusura == deposito) → no-op.
    if isinstance(rientro, ScelzaVOCTAXI) and rientro.durata_min == 0:
        return blocchi, ora_fine_acca_min, ora_fine_acca_min

    if isinstance(rientro, ScelzaVettura):
        treno = rientro.treno
        ora_inizio_rientro_min = treno.partenza_min
        ora_fine_rientro_min = treno.arrivo_min
        blocco_rientro = _BloccoPdcDraft(
            seq=0,  # rinumerato dal chiamante
            tipo_evento="VETTURA",
            ora_inizio=_from_min(ora_inizio_rientro_min),
            ora_fine=_from_min(ora_fine_rientro_min),
            durata_min=treno.durata_min,
            stazione_da_codice=stazione_chiusura,
            stazione_a_codice=deposito_stazione,
            accessori_note=(
                f"Vettura rientro {treno.categoria} {treno.numero} "
                f"({treno.operatore or '—'}) → {deposito_stazione}"
            ),
        )
    else:
        # MM o VOCTAXI: durata forfettaria, parte subito dopo ACCa.
        ora_inizio_rientro_min = ora_fine_acca_min
        ora_fine_rientro_min = (ora_fine_acca_min + rientro.durata_min) % (24 * 60)
        tipo_evento = rientro.tipo  # "MM" or "VOCTAXI"
        if isinstance(rientro, ScelzaMM):
            note = f"Rientro MM → {deposito_stazione} ({rientro.motivo})"
        else:
            note = f"Rientro VOCTAXI → {deposito_stazione} ({rientro.motivo})"
        blocco_rientro = _BloccoPdcDraft(
            seq=0,
            tipo_evento=tipo_evento,
            ora_inizio=_from_min(ora_inizio_rientro_min),
            ora_fine=_from_min(ora_fine_rientro_min),
            durata_min=rientro.durata_min,
            stazione_da_codice=stazione_chiusura,
            stazione_a_codice=deposito_stazione,
            accessori_note=note,
        )

    # Riscala il blocco FINE: parte da ora_fine_rientro, dura
    # FINE_SERVIZIO_MIN (15'), e SI POSIZIONA AL DEPOSITO.
    ora_fine_servizio_nuovo_min = (ora_fine_rientro_min + FINE_SERVIZIO_MIN) % (
        24 * 60
    )
    nuovo_fine = _BloccoPdcDraft(
        seq=0,
        tipo_evento="FINE",
        ora_inizio=_from_min(ora_fine_rientro_min),
        ora_fine=_from_min(ora_fine_servizio_nuovo_min),
        durata_min=FINE_SERVIZIO_MIN,
        stazione_da_codice=deposito_stazione,
        stazione_a_codice=deposito_stazione,
    )

    # Componi: [tutti i blocchi tranne FINE] + [rientro] + [nuovo FINE]
    nuovi_blocchi = list(blocchi[:fine_idx]) + [blocco_rientro, nuovo_fine]

    # Renumera seq.
    for i, b in enumerate(nuovi_blocchi, start=1):
        b.seq = i

    return nuovi_blocchi, ora_inizio_rientro_min, ora_fine_rientro_min


# =====================================================================
# Builder principale per giornata
# =====================================================================


async def costruisci_giornata_deposito_first(
    *,
    depot: Depot,
    numero_giornata: int,
    variante_calendario: str,
    blocchi_giro: list[GiroBlocco],
    live_client: httpx.AsyncClient,
    cache: PartenzeCache | None = None,
) -> tuple[_GiornataPdcDraft | None, list[str]]:
    """Costruisce 1 giornata di turno PdC ancorata al deposito.

    Pipeline:

    1. ``_build_giornata_pdc`` standard (PRESA, ACCp, condotta, PK,
       REFEZ, ACCa, FINE).
    2. **HARD** se ``condotta_min > 330`` → scarta (return ``None``).
    3. Se ``stazione_fine == depot.stazione_principale_codice`` →
       giornata già chiusa al deposito. ``stazione_fine`` valorizzata
       a depot per coerenza.
    4. Altrimenti: ``risolvi_rientro`` § 7.2 → inserisce blocco
       VETTURA/MM/VOCTAXI prima di FINE, sposta FINE post-rientro.
    5. **HARD** se ``prestazione_finale > cap`` post-rientro → scarta.

    Args:
        depot: Depot di residenza del PdC. ``stazione_principale_codice``
            DEVE essere valorizzato (validato in step preliminare;
            ritorna violazione se None).
        numero_giornata: numero giornata-tipo (1-based).
        variante_calendario: validità della variante (es. ``"LMXGV"``).
        blocchi_giro: blocchi del giro materiale per quella giornata.
        live_client: client httpx aperto, condiviso col builder
            principale per riusare connessione TLS.
        cache: ``PartenzeCache`` opzionale per riusare le response
            ``/api/partenze/{stazione}`` fra giornate.

    Returns:
        ``(draft, [])`` se la giornata è valida e chiusa al deposito.
        ``(None, [violazione_str])`` se SCARTATA per cap o invarianti.
    """
    deposito_stazione = depot.stazione_principale_codice
    if deposito_stazione is None:
        return None, [
            f"giornata{numero_giornata}: depot {depot.codice} privo di "
            f"stazione_principale_codice"
        ]

    # 1. Build standard.
    draft = _build_giornata_pdc(
        numero_giornata=numero_giornata,
        variante_calendario=variante_calendario,
        blocchi_giro=blocchi_giro,
    )
    if draft is None:
        return None, [
            f"giornata{numero_giornata}: nessun blocco valido nel giro"
        ]

    # 2. HARD cap condotta.
    if draft.condotta_min > CONDOTTA_MAX_MIN:
        return None, [
            f"giornata{numero_giornata}: condotta_max_hard "
            f"{draft.condotta_min}>{CONDOTTA_MAX_MIN}min"
        ]

    # 3. Caso A: chiusura già al deposito.
    if draft.stazione_fine == deposito_stazione:
        # Garantisci stazione_fine valorizzata = deposito (era già).
        return draft, []

    if draft.stazione_fine is None:
        return None, [
            f"giornata{numero_giornata}: stazione_fine None "
            f"(blocchi giro privi di stazione_a_codice)"
        ]

    # 4. Caso B: chiusura ≠ deposito → risolvi rientro §7.2.
    ora_presa_min = _t(draft.inizio_prestazione)
    # ora_fine_servizio_old = ora_fine_acca + FINE_SERVIZIO_MIN
    # → ora_fine_acca = fine_prestazione - FINE_SERVIZIO_MIN
    ora_fine_acca_min = (_t(draft.fine_prestazione) - FINE_SERVIZIO_MIN) % (24 * 60)

    rientro = await risolvi_rientro(
        deposito_codice=depot.codice,
        deposito_stazione_codice=deposito_stazione,
        stazione_chiusura_codice=draft.stazione_fine,
        ora_presa_min=ora_presa_min,
        ora_chiusura_servizio_min=ora_fine_acca_min,
        is_notturno=draft.is_notturno,
        live_client=live_client,
        cache=cache,
    )

    # 5. Inserisci blocco rientro + sposta FINE.
    nuovi_blocchi, _ora_in, ora_fine_rientro = _inserisci_blocco_rientro(
        blocchi=draft.blocchi,
        rientro=rientro,
        deposito_stazione=deposito_stazione,
        stazione_chiusura=draft.stazione_fine,
        ora_fine_acca_min=ora_fine_acca_min,
    )

    # 6. Ricalcola prestazione finale.
    nuova_fine_servizio_min = (ora_fine_rientro + FINE_SERVIZIO_MIN) % (24 * 60)
    nuova_prestazione_min = (nuova_fine_servizio_min - ora_presa_min) % (24 * 60)
    if nuova_prestazione_min == 0:
        nuova_prestazione_min = 24 * 60

    # 7. HARD cap prestazione post-rientro.
    cap_prestazione = (
        PRESTAZIONE_MAX_NOTTURNO_MIN
        if draft.is_notturno
        else PRESTAZIONE_MAX_STANDARD_MIN
    )
    if nuova_prestazione_min > cap_prestazione:
        return None, [
            f"giornata{numero_giornata}: prestazione_max_hard "
            f"{nuova_prestazione_min}>{cap_prestazione}min post-rientro "
            f"(rientro={rientro.tipo})"
        ]

    # 8. Componi nuovo draft con stazione_fine = deposito.
    return (
        replace(
            draft,
            blocchi=nuovi_blocchi,
            stazione_fine=deposito_stazione,
            fine_prestazione=_from_min(nuova_fine_servizio_min),
            prestazione_min=nuova_prestazione_min,
        ),
        [],
    )


__all__ = [
    "costruisci_giornata_deposito_first",
]


# Re-export per consistenza (consumatori non devono cercare in builder.py).
_ = ACCESSORI_MIN_STANDARD  # silence unused-import warning per ruff
