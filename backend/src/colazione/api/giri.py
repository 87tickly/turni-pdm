"""Route HTTP per generazione giri materiali — Sprint 4.4.5b.

Endpoint:

- ``POST /api/programmi/{id}/genera-giri`` — esegue il builder
  end-to-end e persiste i giri.

Multi-tenant: ``azienda_id`` dal JWT, niente input client.
Auth: ruolo ``PIANIFICATORE_GIRO`` (admin bypassa).

Strategia di rigenerazione (decisione utente, vedi
``docs/PROGRAMMA-MATERIALE.md``): se il programma ha già giri
persistiti, l'endpoint ritorna **409 Conflict** salvo
``?force=true`` esplicito (cancella tutti i giri e rigenera).

Modalità di generazione (decisione utente):
- **Istanze 1:1**: ogni giro è generato per date concrete dal
  parametro ``data_inizio + n_giornate``. Pattern ricorrenza
  (un giro vale tutti i lunedì) è scope futuro.
- **Una località per chiamata**: parametro ``localita_codice``
  obbligatorio. Per N località il pianificatore lancia N chiamate.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.auth import require_any_role, require_role
from colazione.db import get_session
from colazione.domain.builder_giro.builder import (
    BuilderResult,
    BuilderVersionNonSupportata,
    GiriEsistentiError,
    PdcDipendentiError,
    PeriodoFuoriProgrammaError,
    ProgrammaNonAttivoError,
    ProgrammaNonTrovatoError,
    StrictModeViolation,
    carica_festivita_periodo,
    genera_giri,
)
from colazione.domain.builder_giro.etichetta import genera_etichetta_parlante
from colazione.domain.builder_giro.persister import LocalitaNonTrovataError
from colazione.domain.builder_giro.risolvi_corsa import (
    ComposizioneNonAmmessaError,
    RegolaAmbiguaError,
    determina_giorno_tipo,
    matches_all,
)
from colazione.domain.pipeline import (
    materiale_freezato,
    programma_visibile_per_ruoli,
    soglia_pipeline_per_ruoli,
    stati_pdc_da,
)
from colazione.models.anagrafica import (
    MaterialeThread,
    MaterialeThreadEvento,
    Stazione,
)
from colazione.models.corse import (
    CorsaCommerciale,
    CorsaMaterialeVuoto,
    corse_attive_clause,
)
from colazione.models.giri import GiroBlocco, GiroGiornata, GiroMateriale, GiroVariante
from colazione.models.programmi import ProgrammaMateriale, ProgrammaRegolaAssegnazione
from colazione.schemas.security import CurrentUser

router = APIRouter(prefix="/api/programmi", tags=["giri"])

_authz = Depends(require_role("PIANIFICATORE_GIRO"))
# Sprint 8.0 MR 0 (entry 164): lettura giri ammessa ai 4 ruoli pipeline.
# La visibilità per ``stato_pipeline_pdc`` del programma proprietario è
# applicata nel body via ``soglia_pipeline_per_ruoli``. Le scritture
# (POST genera-giri) restano protette da `_authz`.
_authz_read = Depends(
    require_any_role(
        "PIANIFICATORE_GIRO",
        "PIANIFICATORE_PDC",
        "GESTIONE_PERSONALE",
        "MANUTENZIONE",
    )
)


# =====================================================================
# Response schema
# =====================================================================


class BuilderResultResponse(BaseModel):
    """Risposta di ``POST /genera-giri``: stats + warning."""

    giri_ids: list[int] = Field(description="ID dei GiroMateriale creati.")
    n_giri_creati: int
    n_corse_processate: int = Field(description="Totale blocchi corsa assegnati nei giri.")
    n_corse_residue: int = Field(description="Corse senza regola applicabile (warning).")
    n_giri_chiusi: int
    n_giri_non_chiusi: int = Field(description="Giri con motivo_chiusura != 'naturale' (warning).")
    n_eventi_composizione: int = Field(
        description="Blocchi aggancio/sgancio inseriti (da validare in editor)."
    )
    n_incompatibilita_materiale: int
    n_giri_scartati: int = Field(
        default=0,
        description=(
            "Sprint 8.2 MR-D5f S1: giri prodotti dalla pipeline ma non "
            "persistiti. Cause tipiche (ramo linea_centrica): regola_id=None, "
            "oppure giro per sede diversa dalla `localita_codice` del run "
            "(modello cumulativo). Se >0 frontend mostra toast warning."
        ),
    )
    modalita_sede: str | None = Field(
        default=None,
        description=(
            "Sprint 8.2 MR-D5h-bis S4: stato modalità sede del run. "
            "`null` per ramo legacy (rigido/esplorativo). Per ramo "
            "linea-centrica: `'normale'` (pool azienda attivo) o "
            "`'degradata_single_sede'` (sede del run NON nel pool azienda, "
            "pipeline ridotta a single-sede). Frontend mostra warning "
            "se `'degradata_single_sede'`."
        ),
    )
    warnings: list[str]


def _to_response(result: BuilderResult) -> BuilderResultResponse:
    return BuilderResultResponse(
        giri_ids=result.giri_ids,
        n_giri_creati=result.n_giri_creati,
        n_corse_processate=result.n_corse_processate,
        n_corse_residue=result.n_corse_residue,
        n_giri_chiusi=result.n_giri_chiusi,
        n_giri_non_chiusi=result.n_giri_non_chiusi,
        n_eventi_composizione=result.n_eventi_composizione,
        n_incompatibilita_materiale=result.n_incompatibilita_materiale,
        n_giri_scartati=result.n_giri_scartati,
        modalita_sede=result.modalita_sede,
        warnings=result.warnings,
    )


# =====================================================================
# Endpoint
# =====================================================================


@router.post(
    "/{programma_id}/genera-giri",
    response_model=BuilderResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Genera giri materiali per un programma in una finestra di date",
)
async def genera_giri_endpoint(
    programma_id: int,
    data_inizio: date | None = Query(
        None,
        description=(
            "Prima data del range (YYYY-MM-DD). Default: programma.valido_da. "
            "Sprint 7.5 MR 4: parametro opzionale (decisione utente C3)."
        ),
    ),
    n_giornate: int | None = Query(
        None,
        ge=1,
        le=400,
        description=(
            "Numero giornate (1-400). Default: dalla data_inizio fino a "
            "programma.valido_a inclusa (periodo intero). Specificare "
            "esplicitamente solo per limitare il range a una sotto-finestra."
        ),
    ),
    localita_codice: str = Query(
        ..., description="Codice località manutenzione (es. IMPMAN_MILANO_FIORENZA)."
    ),
    force: bool = Query(
        False,
        description="Se true, cancella i giri esistenti del programma e rigenera.",
    ),
    confirm_delete_pdc: bool = Query(
        False,
        description=(
            "Sprint 7.9 strategy A: se true, conferma la cancellazione "
            "a cascata dei turni PdC dipendenti dai giri rigenerati. "
            "Senza questa conferma, una rigenerazione che cancellerebbe "
            "PdC esistenti restituisce 409 con il count nei dettagli."
        ),
    ),
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> BuilderResultResponse:
    """Lancia il builder end-to-end (pipeline 4.4.1→4.4.5a) per il
    programma + finestra + località indicati.

    Sprint 7.5 MR 4 (decisione utente C3): ``data_inizio`` e
    ``n_giornate`` sono opzionali. Se omessi, il default è il periodo
    intero del programma — è la scelta che attiva il clustering A1
    sul calendario completo (vedi `multi_giornata.py` Sprint 7.5 MR 1).

    Errori HTTP:

    - **404**: programma o località non trovati per l'azienda corrente.
    - **400**: programma non in stato 'attivo', o ``n_giornate`` invalido,
      o regole ambigue, o strict mode violato, o composizione regola
      con coppia non in ``materiale_accoppiamento_ammesso``.
    - **409**: il programma ha già giri persistiti — passa
      ``?force=true`` per cancellare e rigenerare.
    - **422**: ``data_inizio`` fuori dal periodo del programma.

    Risposta 200: ``BuilderResultResponse`` con ``giri_ids`` (id dei
    `GiroMateriale` creati) + statistiche per il pianificatore.

    Sprint 8.0 MR 1: 409 se ``stato_pipeline_pdc >= MATERIALE_CONFERMATO``
    (giri freezati al handoff Materiale → PdC). Per rigenerare, l'admin
    deve prima sbloccare via ``POST /api/programmi/{id}/sblocca``.
    """
    # Freeze read-only post MATERIALE_CONFERMATO (Sprint 8.0 MR 1).
    stato_pipeline = (
        await session.execute(
            select(ProgrammaMateriale.stato_pipeline_pdc).where(
                ProgrammaMateriale.id == programma_id,
                ProgrammaMateriale.azienda_id == user.azienda_id,
            )
        )
    ).scalar_one_or_none()
    if stato_pipeline is not None and materiale_freezato(stato_pipeline):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"programma in stato pipeline {stato_pipeline!r} "
                "(>= MATERIALE_CONFERMATO): giri read-only. Per rigenerare "
                "richiedi a un admin POST /api/programmi/{id}/sblocca."
            ),
        )

    try:
        result = await genera_giri(
            programma_id=programma_id,
            data_inizio=data_inizio,
            n_giornate=n_giornate,
            localita_codice=localita_codice,
            session=session,
            azienda_id=user.azienda_id,
            force=force,
            confirm_delete_pdc=confirm_delete_pdc,
            eseguito_da_user_id=user.user_id,
        )
    except ProgrammaNonTrovatoError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LocalitaNonTrovataError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ProgrammaNonAttivoError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except BuilderVersionNonSupportata as exc:
        # MR-1110 sotto-MR 10 (entry 206): 501 NOT IMPLEMENTED quando il
        # programma chiede builder_version='v2' ma il wiring al persister
        # non è ancora pronto. Il pianificatore deve riportarlo a 'v1'.
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={
                "code": "builder_version_non_supportata",
                "messaggio": str(exc),
                "programma_id": exc.programma_id,
                "version": exc.version,
            },
        ) from exc
    except PeriodoFuoriProgrammaError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except PdcDipendentiError as exc:
        # Sprint 7.9 strategy A: 409 STRUTTURATO con n_pdc + codici per UI.
        # Il frontend usa questi dati per la seconda dialog di conferma.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "pdc_dipendenti",
                "messaggio": str(exc),
                "n_pdc_dipendenti": exc.n_pdc,
                "pdc_codici": exc.pdc_codici,
                "programma_id": exc.programma_id,
                "localita_codice": exc.localita_codice,
            },
        ) from exc
    except GiriEsistentiError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except StrictModeViolation as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RegolaAmbiguaError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ComposizioneNonAmmessaError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return _to_response(result)


# =====================================================================
# Read-side endpoints (Sprint 5.6 R1) — alimentano il frontend Pianificatore
# =====================================================================


class GiroMaterialeListItem(BaseModel):
    """Item della lista giri di un programma (compatto, per tabella UI).

    Sprint 7.7 MR 5: rimossi ``etichetta_tipo``/``etichetta_dettaglio``
    (concetto MR 3 superseded — ora le etichette vivono per variante).
    Nuovo campo ``n_varianti_totale`` come hint UI per "questo giro ha
    varianti calendariali per giornata".
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    numero_turno: str
    tipo_materiale: str
    materiale_tipo_codice: str | None
    numero_giornate: int
    km_media_giornaliera: float | None
    km_media_annua: float | None
    motivo_chiusura: str | None
    chiuso: bool
    stato: str
    # Sprint 7.7 MR 5: somma di tutte le varianti del giro
    # (= sum(len(varianti) for giornata in giornate)).
    n_varianti_totale: int
    created_at: datetime


class GiroBloccoRead(BaseModel):
    """Singolo blocco di un giro (corsa, vuoto, evento).

    Include i nomi stazione e il numero treno risolti via lookup
    anagrafico, così il frontend non deve mappare codici a mano.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    seq: int
    tipo_blocco: str
    corsa_commerciale_id: int | None
    corsa_materiale_vuoto_id: int | None
    stazione_da_codice: str | None
    stazione_a_codice: str | None
    stazione_da_nome: str | None
    stazione_a_nome: str | None
    numero_treno: str | None
    ora_inizio: time | None
    ora_fine: time | None
    descrizione: str | None
    is_validato_utente: bool
    metadata_json: dict[str, Any]


class GiroVarianteRead(BaseModel):
    """Sprint 7.7 MR 5+6: una variante calendariale di una giornata-tipo.

    Più varianti per la stessa giornata significano "in periodi diversi
    il convoglio fa percorsi diversi" (modello PDF Trenord 1134).
    L'``etichetta_parlante`` è calcolata server-side da
    ``calcola_etichetta_variante`` (MR 6), categorizzazione semantica
    delle date di applicazione: ``"Lavorativo · 12 date"``,
    ``"Festivo · 8 date"``, ``"Prefestivo · 4 date"``,
    ``"Solo 04/05/2026"``, ``"Misto: Lavorativo+Festivo · 7 date"``.
    Il ``validita_testo`` PdE grezzo resta esposto per riferimento
    ma non è più mostrato come etichetta principale in UI.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    variant_index: int
    validita_testo: str | None
    dates_apply_json: list[Any]
    dates_skip_json: list[Any]
    etichetta_parlante: str
    blocchi: list[GiroBloccoRead]
    # Sprint 7.9 MR 8A (decisione utente 2026-05-03): lista dei
    # `variant_index` originari (PRE-aggregazione MR6) dei cluster A1
    # confluiti in questa variante. Permette al frontend di propagare
    # la selezione tra giornate basandosi sull'identità del cluster
    # A1 sottostante (intersezione non vuota = stessa traiettoria
    # del convoglio attraverso il ciclo).
    cluster_a1_ids: list[int] = []


class GiroGiornataRead(BaseModel):
    """Giornata di un giro (1..numero_giornate).

    Sprint 7.7 MR 5: ``varianti`` torna come lista ordinata per
    ``variant_index`` (canonica = index 0).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    numero_giornata: int
    # Sprint 7.6 MR 3.2 / 7.7 MR 5: somma km_tratta della VARIANTE
    # CANONICA (= variant_index=0) della giornata. None se nessuna
    # corsa con km.
    km_giornata: float | None = None
    varianti: list[GiroVarianteRead]


class GiroMaterialeDettaglioRead(BaseModel):
    """Dettaglio completo di un giro per visualizzatore Gantt."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    numero_turno: str
    tipo_materiale: str
    materiale_tipo_codice: str | None
    numero_giornate: int
    km_media_giornaliera: float | None
    km_media_annua: float | None
    localita_manutenzione_partenza_id: int | None
    localita_manutenzione_arrivo_id: int | None
    stato: str
    generation_metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    giornate: list[GiroGiornataRead]


@router.get(
    "/{programma_id}/giri",
    response_model=list[GiroMaterialeListItem],
    summary="Lista giri persistiti del programma",
)
async def list_giri_programma(
    programma_id: int,
    user: CurrentUser = _authz_read,
    session: AsyncSession = Depends(get_session),
) -> list[GiroMaterialeListItem]:
    """Ritorna i giri persistiti per il programma. Filtro per la colonna
    FK ``programma_id`` (introdotta dalla migration 0010, sfrutta
    l'indice ``idx_giro_materiale_programma_id``).

    Sprint 8.0 MR 0 (entry 164): controllo di visibilità per ruolo del
    programma proprietario. 404 (privacy multi-tenant) se l'utente
    non ha la soglia pipeline per vederlo.
    """
    # Check visibilità programma proprietario.
    stato_pipeline = (
        await session.execute(
            select(ProgrammaMateriale.stato_pipeline_pdc).where(
                ProgrammaMateriale.id == programma_id,
                ProgrammaMateriale.azienda_id == user.azienda_id,
            )
        )
    ).scalar_one_or_none()
    if stato_pipeline is None or not programma_visibile_per_ruoli(
        stato_pipeline, user.roles, user.is_admin
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="programma non trovato",
        )

    # Sprint 7.3 fix: usa la colonna esplicita programma_id (migration
    # 0010) invece del cast da generation_metadata_json. Più veloce
    # (indicizzato) e più leggibile.
    stmt = (
        select(GiroMateriale)
        .where(
            GiroMateriale.azienda_id == user.azienda_id,
            GiroMateriale.programma_id == programma_id,
        )
        .order_by(GiroMateriale.numero_turno)
    )
    rows = (await session.execute(stmt)).scalars().all()
    out: list[GiroMaterialeListItem] = []
    for g in rows:
        meta = g.generation_metadata_json or {}
        # Sprint 7.7 MR 5: leggo il count delle varianti dal metadata
        # tracciato dal persister; fallback 0 se assente.
        n_varianti_per_giornata = meta.get("n_varianti_per_giornata") or []
        n_varianti_totale = (
            sum(int(x) for x in n_varianti_per_giornata)
            if isinstance(n_varianti_per_giornata, list)
            else 0
        )
        out.append(
            GiroMaterialeListItem(
                id=g.id,
                numero_turno=g.numero_turno,
                tipo_materiale=g.tipo_materiale,
                materiale_tipo_codice=g.materiale_tipo_codice,
                numero_giornate=g.numero_giornate,
                km_media_giornaliera=float(g.km_media_giornaliera) if g.km_media_giornaliera is not None else None,
                km_media_annua=float(g.km_media_annua) if g.km_media_annua is not None else None,
                motivo_chiusura=meta.get("motivo_chiusura"),
                chiuso=bool(meta.get("chiuso", False)),
                stato=g.stato,
                n_varianti_totale=n_varianti_totale,
                created_at=g.created_at,
            )
        )
    return out


# =====================================================================
# Cerca treno — entry 214 (MR-1)
# =====================================================================


class CercaTrenoBloccoRef(BaseModel):
    """Riferimento a un blocco giro che usa il treno cercato.

    Permette al frontend di navigare al Gantt del giro corretto e
    scrollare/evidenziare il blocco specifico (giornata + variante +
    seq).
    """

    blocco_id: int
    giro_id: int
    numero_turno: str
    giornata: int
    variante_index: int
    variante_etichetta: str | None = Field(
        description="``GiroVariante.validita_testo`` (es. 'LV 1:5')."
    )
    seq: int


class CercaTrenoItem(BaseModel):
    """Risultato cerca-treno raggruppato per corsa/vuoto.

    Una corsa (commerciale o vuoto) può apparire in più ``GiroBlocco``
    perché il builder la replica per giornate/varianti del ciclo.
    Tutti i blocchi confluiscono nella lista ``blocchi``.
    """

    corsa_id: int
    tipo: Literal["commerciale", "vuoto"]
    numero_treno: str
    stazione_da_codice: str
    stazione_a_codice: str
    ora_partenza: time
    ora_arrivo: time
    blocchi: list[CercaTrenoBloccoRef]


@router.get(
    "/{programma_id}/cerca-treno",
    response_model=list[CercaTrenoItem],
    summary="Cerca treno (commerciale o vuoto) tra i giri del programma",
)
async def cerca_treno(
    programma_id: int,
    q: str = Query(
        ...,
        min_length=1,
        max_length=20,
        description="Numero treno o sottostringa (case-insensitive). "
        "Es. ``28`` matcha ``28335``, ``28301``, ``92811`` ecc.",
    ),
    limit: int = Query(
        50,
        ge=1,
        le=200,
        description="Max corse distinte ritornate. Ogni corsa può "
        "avere N blocchi.",
    ),
    user: CurrentUser = _authz_read,
    session: AsyncSession = Depends(get_session),
) -> list[CercaTrenoItem]:
    """Cerca treni per ``numero_treno`` tra i giri persistiti del
    programma. Match partial case-insensitive (``ILIKE %q%``).

    Include sia treni commerciali (``CorsaCommerciale.numero_treno``)
    sia vuoti (``CorsaMaterialeVuoto.numero_treno_vuoto``, formato
    ``9{commerciale}`` per i rientri sede — memoria
    ``project_rientro_sede_9XXXX``).

    Output raggruppato per ``(corsa_id, tipo)``: ogni corsa appare
    una volta sola, con la lista dei blocchi giro che la usano
    (giornata + variante + seq + giro). Il frontend usa
    ``blocchi[0]`` per navigazione di default + tutti i blocchi
    per highlight multi.

    Sprint 8.0 (entry 214): MR-1 nuova feature ricerca treno
    richiesta dall'utente. Per ora solo treni *assegnati* a un
    giro; i treni del PdE non assegnati a nessun giro saranno una
    iterazione 2 (decisione utente "iniziamo con la tua proposta
    poi vediamo").
    """
    # Check visibilità programma (404 multi-tenant + ruolo).
    stato_pipeline = (
        await session.execute(
            select(ProgrammaMateriale.stato_pipeline_pdc).where(
                ProgrammaMateriale.id == programma_id,
                ProgrammaMateriale.azienda_id == user.azienda_id,
            )
        )
    ).scalar_one_or_none()
    if stato_pipeline is None or not programma_visibile_per_ruoli(
        stato_pipeline, user.roles, user.is_admin
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="programma non trovato",
        )

    pattern = f"%{q.strip()}%"

    # Query 1 — treni commerciali. Niente filtro ``corse_attive_clause``:
    # qui è un lookup di numero treno per blocchi esistenti (audit
    # storico ammesso, vedi docstring di ``corse_attive_clause``).
    stmt_comm = (
        select(
            CorsaCommerciale.id.label("corsa_id"),
            CorsaCommerciale.numero_treno,
            CorsaCommerciale.codice_origine,
            CorsaCommerciale.codice_destinazione,
            CorsaCommerciale.ora_partenza,
            CorsaCommerciale.ora_arrivo,
            GiroBlocco.id.label("blocco_id"),
            GiroBlocco.seq,
            GiroVariante.variant_index,
            GiroVariante.validita_testo,
            GiroGiornata.numero_giornata,
            GiroMateriale.id.label("giro_id"),
            GiroMateriale.numero_turno,
        )
        .join(GiroBlocco, GiroBlocco.corsa_commerciale_id == CorsaCommerciale.id)
        .join(GiroVariante, GiroBlocco.giro_variante_id == GiroVariante.id)
        .join(GiroGiornata, GiroVariante.giro_giornata_id == GiroGiornata.id)
        .join(GiroMateriale, GiroGiornata.giro_materiale_id == GiroMateriale.id)
        .where(GiroMateriale.programma_id == programma_id)
        .where(GiroMateriale.azienda_id == user.azienda_id)
        .where(CorsaCommerciale.numero_treno.ilike(pattern))
        .order_by(
            CorsaCommerciale.numero_treno,
            GiroMateriale.numero_turno,
            GiroGiornata.numero_giornata,
            GiroVariante.variant_index,
            GiroBlocco.seq,
        )
    )

    # Query 2 — treni vuoti.
    stmt_vuo = (
        select(
            CorsaMaterialeVuoto.id.label("corsa_id"),
            CorsaMaterialeVuoto.numero_treno_vuoto.label("numero_treno"),
            CorsaMaterialeVuoto.codice_origine,
            CorsaMaterialeVuoto.codice_destinazione,
            CorsaMaterialeVuoto.ora_partenza,
            CorsaMaterialeVuoto.ora_arrivo,
            GiroBlocco.id.label("blocco_id"),
            GiroBlocco.seq,
            GiroVariante.variant_index,
            GiroVariante.validita_testo,
            GiroGiornata.numero_giornata,
            GiroMateriale.id.label("giro_id"),
            GiroMateriale.numero_turno,
        )
        .join(
            GiroBlocco,
            GiroBlocco.corsa_materiale_vuoto_id == CorsaMaterialeVuoto.id,
        )
        .join(GiroVariante, GiroBlocco.giro_variante_id == GiroVariante.id)
        .join(GiroGiornata, GiroVariante.giro_giornata_id == GiroGiornata.id)
        .join(GiroMateriale, GiroGiornata.giro_materiale_id == GiroMateriale.id)
        .where(GiroMateriale.programma_id == programma_id)
        .where(GiroMateriale.azienda_id == user.azienda_id)
        .where(CorsaMaterialeVuoto.numero_treno_vuoto.ilike(pattern))
        .order_by(
            CorsaMaterialeVuoto.numero_treno_vuoto,
            GiroMateriale.numero_turno,
            GiroGiornata.numero_giornata,
            GiroVariante.variant_index,
            GiroBlocco.seq,
        )
    )

    rows_comm = (await session.execute(stmt_comm)).all()
    rows_vuo = (await session.execute(stmt_vuo)).all()

    # Raggruppa per (tipo, corsa_id). Ordine inserimento = ordine
    # SQL → numero_treno asc, prima commerciali poi vuoti.
    items: dict[tuple[str, int], CercaTrenoItem] = {}

    def _add_rows(rows: Any, tipo: Literal["commerciale", "vuoto"]) -> None:
        for r in rows:
            key = (tipo, int(r.corsa_id))
            blocco = CercaTrenoBloccoRef(
                blocco_id=int(r.blocco_id),
                giro_id=int(r.giro_id),
                numero_turno=str(r.numero_turno),
                giornata=int(r.numero_giornata),
                variante_index=int(r.variant_index),
                variante_etichetta=r.validita_testo,
                seq=int(r.seq),
            )
            if key in items:
                items[key].blocchi.append(blocco)
            else:
                items[key] = CercaTrenoItem(
                    corsa_id=int(r.corsa_id),
                    tipo=tipo,
                    numero_treno=str(r.numero_treno),
                    stazione_da_codice=str(r.codice_origine),
                    stazione_a_codice=str(r.codice_destinazione),
                    ora_partenza=r.ora_partenza,
                    ora_arrivo=r.ora_arrivo,
                    blocchi=[blocco],
                )
                # Limit precoce: smetto quando ho ``limit`` corse
                # distinte. Il taglio definitivo è dopo il merge sotto.

    _add_rows(rows_comm, "commerciale")
    _add_rows(rows_vuo, "vuoto")

    # Limit applicato sulle corse distinte (commerciali prima, poi vuoti).
    return list(items.values())[:limit]


# =====================================================================
# Corse non coperte vs PdE (B3) — entry 218 (MR-2)
# =====================================================================


class RegolaMatchRef(BaseModel):
    """Riferimento a una regola del programma che includerebbe la corsa."""

    regola_id: int
    priorita: int


class CorsaNonCopertaItem(BaseModel):
    """Una corsa del PdE che entra nel perimetro del programma (matching
    regole + periodo) ma non è stata coperta da nessun giro generato.

    Iterazione 1 (entry 218): solo corse con **0 istanze coperte**.
    Copertura parziale per data (es. coperta in 10/15 date) → iterazione 2.
    """

    corsa_id: int
    numero_treno: str
    stazione_da_codice: str
    stazione_a_codice: str
    ora_partenza: time
    ora_arrivo: time
    n_date_perimetro: int = Field(
        description="Numero di date di ``valido_in_date_json`` che cadono "
        "nel periodo del programma (``valido_da → valido_a``)."
    )
    regole_match: list[RegolaMatchRef] = Field(
        description="Regole del programma che includerebbero la corsa "
        "(matching ``filtri_json`` su almeno un giorno_tipo)."
    )
    motivo_presunto: Literal[
        "linea_disgiunta",
        "sovrapposizione_stazioni",
        "indeterminato",
    ] = Field(
        description="Diagnostica MR-2.5-bis (entry 220):\n"
        "- ``linea_disgiunta``: né origine né destinazione della corsa "
        "compaiono nelle stazioni toccate dai giri del programma → il "
        "convoglio non passa mai da queste stazioni → fill smart non è "
        "fattibile, serve nuovo giro con materiale libero (MR-2.7).\n"
        "- ``sovrapposizione_stazioni``: almeno una delle 2 stazioni "
        "compare nei giri esistenti → potrebbe essere fillabile durante "
        "una sosta del giro (MR-2.6 smart fill).\n"
        "- ``indeterminato``: caso default."
    )


@router.get(
    "/{programma_id}/corse-non-coperte",
    response_model=list[CorsaNonCopertaItem],
    summary="Corse del PdE che cadono nel perimetro del programma ma non "
    "sono coperte da nessun giro",
)
async def corse_non_coperte(
    programma_id: int,
    user: CurrentUser = _authz_read,
    session: AsyncSession = Depends(get_session),
) -> list[CorsaNonCopertaItem]:
    """Diagnostica delle corse non coperte (B3 perimetro programma).

    Logica:

    1. **Carica programma**: prende ``valido_da`` e ``valido_a``.
    2. **Carica regole del programma**: ``filtri_json`` per il matching.
    3. **Carica corse commerciali attive dell'azienda**: filtro
       ``corse_attive_clause()`` (escludi cancellate da
       VARIAZIONE_CANCELLAZIONE).
    4. **Carica corse coperte**: ID delle corse referenziate da almeno
       un ``giro_blocco`` di un giro di questo programma.
    5. **Filtro perimetro per ogni corsa non coperta**:
       a. Le sue date in ``valido_in_date_json`` ∩ periodo programma
          → ``n_date_perimetro``. Se 0 → fuori periodo, skip.
       b. Matching almeno una regola del programma in almeno un
          ``giorno_tipo`` (``feriale``, ``sabato``, ``festivo``) → se
          nessuna matcha, skip (corsa non è del perimetro programma).
    6. Ritorna la lista ordinata per ``numero_treno``.

    Multi-tenant: ``azienda_id`` dal JWT. Visibilità programma per ruolo
    via ``programma_visibile_per_ruoli`` (404 se non vede).

    Sprint 8.0 MR-2 (entry 218): nuova feature richiesta dall'utente
    "una sezione persistente cosi non lo dimentichiamo". Decisione
    utente "B3" (perimetro programma, non tutto il PdE).
    """
    # 1. Visibilità + load programma.
    programma = (
        await session.execute(
            select(ProgrammaMateriale).where(
                ProgrammaMateriale.id == programma_id,
                ProgrammaMateriale.azienda_id == user.azienda_id,
            )
        )
    ).scalar_one_or_none()
    if programma is None or not programma_visibile_per_ruoli(
        programma.stato_pipeline_pdc, user.roles, user.is_admin
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="programma non trovato",
        )

    # 2. Regole del programma.
    regole = list(
        (
            await session.execute(
                select(ProgrammaRegolaAssegnazione)
                .where(ProgrammaRegolaAssegnazione.programma_id == programma_id)
                .order_by(ProgrammaRegolaAssegnazione.priorita.desc())
            )
        )
        .scalars()
        .all()
    )
    if not regole:
        # Programma senza regole → niente perimetro, niente "non coperte".
        return []

    # 3. Corse commerciali attive dell'azienda (no filtro periodo qui:
    # filtro temporale è applicato dopo via valido_in_date_json).
    corse = list(
        (
            await session.execute(
                select(CorsaCommerciale)
                .where(CorsaCommerciale.azienda_id == user.azienda_id)
                .where(corse_attive_clause())
            )
        )
        .scalars()
        .all()
    )

    # 4. ID corse già coperte da almeno un blocco di un giro di questo programma.
    coperte_rows = (
        await session.execute(
            select(GiroBlocco.corsa_commerciale_id)
            .join(GiroVariante, GiroVariante.id == GiroBlocco.giro_variante_id)
            .join(GiroGiornata, GiroGiornata.id == GiroVariante.giro_giornata_id)
            .join(GiroMateriale, GiroMateriale.id == GiroGiornata.giro_materiale_id)
            .where(GiroMateriale.programma_id == programma_id)
            .where(GiroBlocco.corsa_commerciale_id.is_not(None))
            .distinct()
        )
    ).all()
    coperte_set: set[int] = {int(r[0]) for r in coperte_rows if r[0] is not None}

    # MR-2.5-bis (entry 220): set delle stazioni toccate dai giri del
    # programma per la diagnostica ``motivo_presunto`` di ogni corsa
    # scoperta. Una stazione è "toccata" se compare come ``stazione_da``
    # o ``stazione_a`` di un blocco di un giro.
    stazioni_giri_rows = (
        await session.execute(
            select(GiroBlocco.stazione_da_codice, GiroBlocco.stazione_a_codice)
            .join(GiroVariante, GiroVariante.id == GiroBlocco.giro_variante_id)
            .join(GiroGiornata, GiroGiornata.id == GiroVariante.giro_giornata_id)
            .join(GiroMateriale, GiroMateriale.id == GiroGiornata.giro_materiale_id)
            .where(GiroMateriale.programma_id == programma_id)
        )
    ).all()
    stazioni_giri: set[str] = set()
    for sg_row in stazioni_giri_rows:
        if sg_row[0] is not None:
            stazioni_giri.add(str(sg_row[0]))
        if sg_row[1] is not None:
            stazioni_giri.add(str(sg_row[1]))

    # 5. Per ogni corsa: filtro perimetro + non coperta.
    out: list[CorsaNonCopertaItem] = []
    giorni_tipo = ("feriale", "sabato", "festivo")
    for corsa in corse:
        if corsa.id in coperte_set:
            continue
        # Periodo: date della corsa che cadono nel range del programma.
        n_date_perimetro = 0
        for d_str in corsa.valido_in_date_json or []:
            try:
                d = date.fromisoformat(str(d_str))
            except ValueError:
                continue
            if programma.valido_da <= d <= programma.valido_a:
                n_date_perimetro += 1
        if n_date_perimetro == 0:
            continue
        # Matching regole: la corsa è "del programma" se almeno una
        # regola la include in almeno un giorno_tipo. ``determina_giorno_tipo``
        # è qui ridondante (uso le 3 stringhe direttamente) ma resta
        # importato per coerenza con il builder.
        _ = determina_giorno_tipo  # silence "unused" del linter
        regole_match: list[RegolaMatchRef] = []
        for r in regole:
            for gt in giorni_tipo:
                if matches_all(r.filtri_json, corsa, gt):
                    regole_match.append(
                        RegolaMatchRef(regola_id=r.id, priorita=r.priorita)
                    )
                    break
        if not regole_match:
            continue
        # MR-2.5-bis: motivo presunto. Se né origine né destinazione
        # compaiono nelle stazioni toccate dai giri → linea totalmente
        # disgiunta dai giri esistenti (serve nuovo giro/materiale,
        # MR-2.7). Altrimenti almeno un endpoint coincide → la corsa
        # potrebbe essere fillabile durante una sosta (MR-2.6 smart
        # fill su soste). Niente check sulla dotazione qui — iterazione
        # successiva.
        motivo: Literal[
            "linea_disgiunta",
            "sovrapposizione_stazioni",
            "indeterminato",
        ]
        origine_in_giri = corsa.codice_origine in stazioni_giri
        destinazione_in_giri = corsa.codice_destinazione in stazioni_giri
        if not origine_in_giri and not destinazione_in_giri:
            motivo = "linea_disgiunta"
        elif origine_in_giri or destinazione_in_giri:
            motivo = "sovrapposizione_stazioni"
        else:
            motivo = "indeterminato"
        out.append(
            CorsaNonCopertaItem(
                corsa_id=corsa.id,
                numero_treno=corsa.numero_treno,
                stazione_da_codice=corsa.codice_origine,
                stazione_a_codice=corsa.codice_destinazione,
                ora_partenza=corsa.ora_partenza,
                ora_arrivo=corsa.ora_arrivo,
                n_date_perimetro=n_date_perimetro,
                regole_match=regole_match,
                motivo_presunto=motivo,
            )
        )

    out.sort(key=lambda x: x.numero_treno)
    return out


# =====================================================================
# Riempi gap — entry 219 (MR-2.5)
# =====================================================================


class FillGapInsert(BaseModel):
    """Anteprima/log di un singolo inserimento corsa → gap."""

    corsa_id: int
    numero_treno: str
    giro_id: int
    numero_turno: str
    giornata: int
    variante_index: int
    seq_inserito: int
    """Posizione in cui la corsa viene inserita (i blocchi successivi
    shiftano di +1)."""


class FillGapResult(BaseModel):
    """Risposta di ``POST /riempi-gap``: anteprima (dry_run=true) o
    apply (dry_run=false)."""

    applied: bool
    n_corse_inserite: int
    n_corse_ancora_scoperte: int
    inserimenti: list[FillGapInsert]


def _minuti(t: time) -> int:
    return t.hour * 60 + t.minute


def _date_set_from_json(j: list[Any]) -> set[date]:
    out: set[date] = set()
    for s in j:
        try:
            out.add(date.fromisoformat(str(s)))
        except ValueError:
            continue
    return out


@router.post(
    "/{programma_id}/riempi-gap",
    response_model=FillGapResult,
    summary="Riprende le corse non coperte e prova a inserirle nei gap "
    "intra-giornata dei giri esistenti del programma",
)
async def riempi_gap(
    programma_id: int,
    dry_run: bool = Query(
        True,
        description="Se True (default): anteprima senza modifiche al DB. "
        "Se False: applica gli inserimenti.",
    ),
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> FillGapResult:
    """Sprint 8.0 MR-2.5 (entry 219): "Fill gap" delle corse non
    coperte sui giri esistenti.

    Logica (livello A — "match esatto stazioni"):

    1. Carica programma + regole + corse non coperte (riuso logica di
       ``corse-non-coperte`` ma inline per autonomia).
    2. Carica i giri del programma con giornate, varianti, blocchi.
    3. **Indicizza i gap intra-giornata** per ogni variante: per ogni
       coppia di blocchi consecutivi (ordinati per ``seq``) calcola
       ``(stazione_a_blocco_prec, stazione_da_blocco_succ,
       minuti_liberi)``. Skip se uno dei due blocchi non ha stazione
       o orario (es. blocchi di tipo ``aggancio``/``sgancio`` senza
       orari espliciti).
    4. Per ogni corsa non coperta:
       - Determina materiale (regola dominante che la matcha → primo
         elemento di ``composizione_json``).
       - Skip giri con materiale diverso.
       - Per ogni variante con ``valido_in_date_json ⊆ dates_apply_json``:
         cerca un gap ``(c.codice_origine, c.codice_destinazione,
         tempo_libero >= durata_corsa)``.
       - Primo match → inserimento candidato.

    5. **dry_run=true** (default): ritorna l'anteprima senza modificare.
    6. **dry_run=false**: per ogni inserimento:
       - Shifta seq dei blocchi successivi (``UPDATE giro_blocco SET
         seq=seq+1 WHERE giro_variante_id=? AND seq>=?``).
       - INSERT del nuovo ``GiroBlocco`` con ``tipo_blocco="corsa_commerciale"``.

    **PdC**: l'operazione è non distruttiva (solo INSERT), quindi i
    PdC esistenti restano coerenti (FK ``giro_blocco_id`` SET NULL).
    L'utente eventualmente rigenererà i PdC per coprire le nuove
    corse aggiunte (decisione utente entry 219).
    """
    # 1. Visibilità + load programma.
    programma = (
        await session.execute(
            select(ProgrammaMateriale).where(
                ProgrammaMateriale.id == programma_id,
                ProgrammaMateriale.azienda_id == user.azienda_id,
            )
        )
    ).scalar_one_or_none()
    if programma is None or not programma_visibile_per_ruoli(
        programma.stato_pipeline_pdc, user.roles, user.is_admin
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="programma non trovato",
        )

    # 2. Regole + corse non coperte (riproduzione locale della logica di
    # corse_non_coperte).
    regole = list(
        (
            await session.execute(
                select(ProgrammaRegolaAssegnazione)
                .where(ProgrammaRegolaAssegnazione.programma_id == programma_id)
                .order_by(ProgrammaRegolaAssegnazione.priorita.desc())
            )
        )
        .scalars()
        .all()
    )
    if not regole:
        return FillGapResult(
            applied=False,
            n_corse_inserite=0,
            n_corse_ancora_scoperte=0,
            inserimenti=[],
        )

    corse = list(
        (
            await session.execute(
                select(CorsaCommerciale)
                .where(CorsaCommerciale.azienda_id == user.azienda_id)
                .where(corse_attive_clause())
            )
        )
        .scalars()
        .all()
    )

    coperte_rows = (
        await session.execute(
            select(GiroBlocco.corsa_commerciale_id)
            .join(GiroVariante, GiroVariante.id == GiroBlocco.giro_variante_id)
            .join(GiroGiornata, GiroGiornata.id == GiroVariante.giro_giornata_id)
            .join(GiroMateriale, GiroMateriale.id == GiroGiornata.giro_materiale_id)
            .where(GiroMateriale.programma_id == programma_id)
            .where(GiroBlocco.corsa_commerciale_id.is_not(None))
            .distinct()
        )
    ).all()
    coperte_set: set[int] = {int(r[0]) for r in coperte_rows if r[0] is not None}

    giorni_tipo = ("feriale", "sabato", "festivo")

    @dataclass(frozen=True)
    class _CorsaCandidata:
        corsa: CorsaCommerciale
        materiale: str  # codice materiale primo della regola

    candidate: list[_CorsaCandidata] = []
    for c in corse:
        if c.id in coperte_set:
            continue
        # Periodo
        date_in_periodo = _date_set_from_json(c.valido_in_date_json or [])
        date_in_periodo = {
            d for d in date_in_periodo if programma.valido_da <= d <= programma.valido_a
        }
        if not date_in_periodo:
            continue
        # Matching regola → materiale
        materiale: str | None = None
        for r in regole:
            for gt in giorni_tipo:
                if matches_all(r.filtri_json, c, gt):
                    if r.composizione_json:
                        try:
                            materiale = str(r.composizione_json[0]["materiale_tipo_codice"])
                        except (KeyError, IndexError, TypeError):
                            materiale = None
                    break
            if materiale is not None:
                break
        if materiale is None:
            continue
        candidate.append(_CorsaCandidata(corsa=c, materiale=materiale))

    # 3. Carica giri completi per il programma + tutti i blocchi (single
    # wide-join query, raggruppata in Python). ``wide_rows`` annotato
    # come ``list[Any]`` per disambiguare mypy nel narrowing dei tipi
    # SQLAlchemy Row con multi-column select (vs ``corse`` che è
    # ``list[CorsaCommerciale]``).
    wide_rows: list[Any] = list(
        (
            await session.execute(
                select(
                    GiroMateriale.id.label("giro_id"),
                    GiroMateriale.numero_turno,
                    GiroMateriale.materiale_tipo_codice,
                    GiroGiornata.id.label("giornata_id"),
                    GiroGiornata.numero_giornata,
                    GiroVariante.id.label("variante_id"),
                    GiroVariante.variant_index,
                    GiroVariante.dates_apply_json,
                    GiroBlocco.id.label("blocco_id"),
                    GiroBlocco.seq,
                    GiroBlocco.tipo_blocco,
                    GiroBlocco.stazione_da_codice,
                    GiroBlocco.stazione_a_codice,
                    GiroBlocco.ora_inizio,
                    GiroBlocco.ora_fine,
                )
                .join(GiroGiornata, GiroGiornata.giro_materiale_id == GiroMateriale.id)
                .join(GiroVariante, GiroVariante.giro_giornata_id == GiroGiornata.id)
                .outerjoin(
                    GiroBlocco, GiroBlocco.giro_variante_id == GiroVariante.id
                )
                .where(GiroMateriale.programma_id == programma_id)
                .where(GiroMateriale.azienda_id == user.azienda_id)
                .order_by(
                    GiroMateriale.id,
                    GiroGiornata.numero_giornata,
                    GiroVariante.variant_index,
                    GiroBlocco.seq,
                )
            )
        ).all()
    )

    @dataclass
    class _Variante:
        variante_id: int
        giro_id: int
        numero_turno: str
        materiale: str | None
        giornata_numero: int
        variant_index: int
        dates_set: set[date]
        # blocchi ordinati per seq, con orari validi (esclusi blocchi
        # senza ora_inizio/ora_fine come aggancio/sgancio "puri").
        blocchi: list[tuple[int, int, str | None, str | None, time, time]]
        # (blocco_id, seq, stazione_da, stazione_a, ora_inizio, ora_fine)

    varianti: dict[int, _Variante] = {}
    for r in wide_rows:
        v_id = int(r.variante_id)
        v = varianti.get(v_id)
        if v is None:
            v = _Variante(
                variante_id=v_id,
                giro_id=int(r.giro_id),
                numero_turno=str(r.numero_turno),
                materiale=r.materiale_tipo_codice,
                giornata_numero=int(r.numero_giornata),
                variant_index=int(r.variant_index),
                dates_set=_date_set_from_json(list(r.dates_apply_json or [])),
                blocchi=[],
            )
            varianti[v_id] = v
        if r.blocco_id is None or r.ora_inizio is None or r.ora_fine is None:
            continue
        v.blocchi.append(
            (
                int(r.blocco_id),
                int(r.seq),
                r.stazione_da_codice,
                r.stazione_a_codice,
                r.ora_inizio,
                r.ora_fine,
            )
        )

    # 4. Per ogni corsa candidata: cerca gap compatibile (primo match).
    inserimenti: list[FillGapInsert] = []
    # Trackiamo gli inserimenti pendenti per variante, così se 2 corse
    # vogliono lo stesso gap la seconda si adatta correttamente
    # (semplificazione iterazione 1: ogni gap riempito al massimo da
    # 1 corsa per chiamata).
    gap_consumati: set[tuple[int, int]] = set()  # (variante_id, seq_target)

    for cand in candidate:
        c = cand.corsa
        durata = _minuti(c.ora_arrivo) - _minuti(c.ora_partenza)
        if durata <= 0:
            # Cross-mezzanotte: per iterazione 1 skip.
            continue
        match: FillGapInsert | None = None
        for v in varianti.values():
            if v.materiale != cand.materiale:
                continue
            # Date subset: tutte le date_corsa devono essere in dates_apply
            date_corsa = _date_set_from_json(c.valido_in_date_json or [])
            date_corsa = {
                d for d in date_corsa if programma.valido_da <= d <= programma.valido_a
            }
            if not date_corsa.issubset(v.dates_set):
                continue
            if not v.blocchi:
                continue
            # Cerca gap intra-giornata tra blocchi consecutivi.
            blocchi_sorted = sorted(v.blocchi, key=lambda b: b[1])  # by seq
            for i in range(len(blocchi_sorted) - 1):
                a = blocchi_sorted[i]
                b = blocchi_sorted[i + 1]
                a_staz_arr = a[3]
                b_staz_par = b[2]
                a_ora_fine = a[5]
                b_ora_inizio = b[4]
                if a_staz_arr is None or b_staz_par is None:
                    continue
                # Match esatto livello A.
                if a_staz_arr != c.codice_origine:
                    continue
                if b_staz_par != c.codice_destinazione:
                    continue
                # Tempo: usa ora_inizio del blocco successivo come fine
                # del gap (più safe: vincolo che la corsa entri prima
                # dell'inizio del prossimo blocco).
                gap_min_disponibili = _minuti(b_ora_inizio) - _minuti(a_ora_fine)
                if gap_min_disponibili < durata:
                    continue
                # Tempo: la corsa deve poter partire dopo a.ora_fine
                # con ``ora_partenza == a.ora_fine`` ammesso o successivo.
                if _minuti(c.ora_partenza) < _minuti(a_ora_fine):
                    continue
                if _minuti(c.ora_arrivo) > _minuti(b_ora_inizio):
                    continue
                # Gap già consumato in questa chiamata?
                seq_target = int(b[1])
                key = (v.variante_id, seq_target)
                if key in gap_consumati:
                    continue
                # MATCH!
                gap_consumati.add(key)
                match = FillGapInsert(
                    corsa_id=int(c.id),
                    numero_treno=str(c.numero_treno),
                    giro_id=v.giro_id,
                    numero_turno=v.numero_turno,
                    giornata=v.giornata_numero,
                    variante_index=v.variant_index,
                    seq_inserito=seq_target,
                )
                break
            if match is not None:
                break
        if match is not None:
            inserimenti.append(match)

    n_inseriti = len(inserimenti)
    n_ancora = len(candidate) - n_inseriti

    if dry_run:
        return FillGapResult(
            applied=False,
            n_corse_inserite=n_inseriti,
            n_corse_ancora_scoperte=n_ancora,
            inserimenti=inserimenti,
        )

    # 5. Apply: per ogni inserimento → SHIFT seq + INSERT giro_blocco.
    # Raggruppa per (variante_id, seq_target) per shiftare correttamente:
    # se inserisco in seq=3 e seq=5 della stessa variante, devo shiftare
    # seq>=5 prima (di +1), poi seq>=3 (di +1, che però NON deve toccare
    # il blocco appena inserito a seq=3). Per semplicità faccio gli
    # inserimenti in ordine seq desc, così ogni shift non conflitta.
    inserimenti_sorted = sorted(
        inserimenti, key=lambda i: (i.giro_id, -i.seq_inserito)
    )
    # Mappa rapida corsa_id → CorsaCommerciale per leggere stazioni/orari.
    corsa_by_id = {c.id: c for c in corse}

    for ins in inserimenti_sorted:
        # Shift seq+=1 dei blocchi successivi.
        await session.execute(
            update(GiroBlocco)
            .where(GiroBlocco.giro_variante_id == _variante_id_from_ins(ins, varianti))
            .where(GiroBlocco.seq >= ins.seq_inserito)
            .values(seq=GiroBlocco.seq + 1)
        )
        c = corsa_by_id[ins.corsa_id]
        nuovo = GiroBlocco(
            giro_variante_id=_variante_id_from_ins(ins, varianti),
            seq=ins.seq_inserito,
            tipo_blocco="corsa_commerciale",
            corsa_commerciale_id=c.id,
            stazione_da_codice=c.codice_origine,
            stazione_a_codice=c.codice_destinazione,
            ora_inizio=c.ora_partenza,
            ora_fine=c.ora_arrivo,
            is_validato_utente=False,
            metadata_json={"origine": "fill_gap_mr_2_5"},
        )
        session.add(nuovo)

    await session.flush()

    return FillGapResult(
        applied=True,
        n_corse_inserite=n_inseriti,
        n_corse_ancora_scoperte=n_ancora,
        inserimenti=inserimenti,
    )


# =====================================================================
# Genera-da-residue — entry 221 (MR-2.7)
# =====================================================================


class GeneraDaResidueLocResult(BaseModel):
    """Risultato per singola località."""

    localita_codice: str
    n_giri_creati: int
    giri_ids: list[int]
    n_corse_processate: int
    n_corse_residue: int
    warnings: list[str]
    errore: str | None = Field(
        default=None,
        description="Se non None, l'esecuzione per questa sede è fallita.",
    )


class GeneraDaResidueResponse(BaseModel):
    """Risposta aggregata multi-località."""

    n_giri_totali_creati: int
    n_corse_inserite_totali: int
    risultati_per_localita: list[GeneraDaResidueLocResult]


@router.post(
    "/{programma_id}/genera-da-residue",
    response_model=GeneraDaResidueResponse,
    summary="Secondo run del builder sulle corse non coperte. Genera "
    "giri AGGIUNTIVI usando i materiali ancora liberi della dotazione, "
    "senza wipe degli esistenti.",
)
async def genera_da_residue(
    programma_id: int,
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> GeneraDaResidueResponse:
    """Sprint 8.0 MR-2.7 (entry 221): "Genera-da-residue".

    Il builder viene eseguito una seconda volta con:

    - **Pool corse** = corse del PdE che NON sono già coperte dai giri
      esistenti del programma (il primo run le ha lasciate fuori).
    - **Multi-località**: itera su tutte le sedi distinte delle regole
      del programma + sedi dei giri esistenti. Per ogni sede, lancia
      ``genera_giri(solo_residue=True)``.
    - **Niente wipe**: i giri esistenti del programma restano intatti.
      I nuovi giri vengono numerati con offset
      ``n_esistenti_sede + 1`` per non collidere sull'unique
      ``(azienda_id, programma_id, numero_turno)``.

    **Limitazione iterazione 1**: il check capacity del builder usa
    la dotazione **totale** dell'azienda, non sottrae i pezzi già
    usati nei giri esistenti del programma. Significa che il second
    run può generare più giri di quanti la dotazione libera consenta.
    Il warning del builder lo segnala. Iterazione 2: override
    dotazione con ``totale - già_usati``.

    **PdC**: l'operazione è non distruttiva (solo INSERT di nuovi
    giri), i PdC esistenti restano coerenti.

    Decisione utente entry 220: "io farei 2.7 e poi prendere in
    considerazione di aggiungere altri materiali".
    """
    # 1. Visibilità + load programma.
    programma = (
        await session.execute(
            select(ProgrammaMateriale).where(
                ProgrammaMateriale.id == programma_id,
                ProgrammaMateriale.azienda_id == user.azienda_id,
            )
        )
    ).scalar_one_or_none()
    if programma is None or not programma_visibile_per_ruoli(
        programma.stato_pipeline_pdc, user.roles, user.is_admin
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="programma non trovato",
        )
    if programma.stato != "attivo":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="programma non attivo",
        )

    # 2. Set delle località da processare:
    #    a) sedi distinte delle regole del programma (con sede esplicita)
    #    b) sedi dei giri esistenti (potrebbero essere state generate da
    #       regole con sede successivamente cambiata)
    sedi_regole_rows = (
        await session.execute(
            select(ProgrammaRegolaAssegnazione.localita_codice)
            .where(ProgrammaRegolaAssegnazione.programma_id == programma_id)
            .where(ProgrammaRegolaAssegnazione.localita_codice.is_not(None))
            .distinct()
        )
    ).all()
    sedi_codici: set[str] = {str(r[0]) for r in sedi_regole_rows if r[0] is not None}

    sedi_giri_rows = (
        await session.execute(
            select(GiroMateriale.localita_manutenzione_partenza_id)
            .where(GiroMateriale.programma_id == programma_id)
            .distinct()
        )
    ).all()
    if sedi_giri_rows:
        from colazione.models.anagrafica import LocalitaManutenzione

        loc_ids = [int(r[0]) for r in sedi_giri_rows if r[0] is not None]
        if loc_ids:
            loc_codici_rows = (
                await session.execute(
                    select(LocalitaManutenzione.codice).where(
                        LocalitaManutenzione.id.in_(loc_ids)
                    )
                )
            ).all()
            for lr in loc_codici_rows:
                if lr[0] is not None:
                    sedi_codici.add(str(lr[0]))

    if not sedi_codici:
        return GeneraDaResidueResponse(
            n_giri_totali_creati=0,
            n_corse_inserite_totali=0,
            risultati_per_localita=[],
        )

    # 3. Calcola escludi_corse_ids (corse già coperte da blocchi dei giri
    # del programma) — passato al builder per filtrare il pool.
    coperte_rows = (
        await session.execute(
            select(GiroBlocco.corsa_commerciale_id)
            .join(GiroVariante, GiroVariante.id == GiroBlocco.giro_variante_id)
            .join(GiroGiornata, GiroGiornata.id == GiroVariante.giro_giornata_id)
            .join(GiroMateriale, GiroMateriale.id == GiroGiornata.giro_materiale_id)
            .where(GiroMateriale.programma_id == programma_id)
            .where(GiroBlocco.corsa_commerciale_id.is_not(None))
            .distinct()
        )
    ).all()
    escludi_ids: set[int] = {
        int(r[0]) for r in coperte_rows if r[0] is not None
    }

    # 4. Itera per sede e lancia il builder con solo_residue=True.
    from colazione.domain.builder_giro.builder import (
        BuilderResult,
        genera_giri,
    )

    risultati: list[GeneraDaResidueLocResult] = []
    n_giri_totali = 0
    for sede in sorted(sedi_codici):
        try:
            res: BuilderResult = await genera_giri(
                programma_id=programma_id,
                localita_codice=sede,
                session=session,
                azienda_id=user.azienda_id,
                force=False,
                solo_residue=True,
                escludi_corse_ids=escludi_ids,
                eseguito_da_user_id=user.user_id,
            )
            risultati.append(
                GeneraDaResidueLocResult(
                    localita_codice=sede,
                    n_giri_creati=res.n_giri_creati,
                    giri_ids=res.giri_ids,
                    n_corse_processate=res.n_corse_processate,
                    n_corse_residue=res.n_corse_residue,
                    warnings=res.warnings,
                )
            )
            n_giri_totali += res.n_giri_creati
        except (
            ProgrammaNonTrovatoError,
            ProgrammaNonAttivoError,
            LocalitaNonTrovataError,
            BuilderVersionNonSupportata,
            ComposizioneNonAmmessaError,
            RegolaAmbiguaError,
            StrictModeViolation,
            ValueError,
        ) as exc:
            risultati.append(
                GeneraDaResidueLocResult(
                    localita_codice=sede,
                    n_giri_creati=0,
                    giri_ids=[],
                    n_corse_processate=0,
                    n_corse_residue=0,
                    warnings=[],
                    errore=f"{type(exc).__name__}: {exc}",
                )
            )

    n_corse_inserite_totali = sum(r.n_corse_processate for r in risultati)

    return GeneraDaResidueResponse(
        n_giri_totali_creati=n_giri_totali,
        n_corse_inserite_totali=n_corse_inserite_totali,
        risultati_per_localita=risultati,
    )


# =====================================================================
# Sprint 8.0 MR-5 (entry 228): aggrega-modifica giri per gruppo
# (materiale, sede). Chirurgico: modifica regole + rigenera force.
# =====================================================================


class AggregaModificaRequest(BaseModel):
    """Payload MR-5: identifica un gruppo `(materiale_tipo_codice_old,
    localita_codice_old)` e specifica i nuovi valori (uno o entrambi).

    Decisione utente entry 224: edit batch chirurgico = aggiorna le
    regole `programma_regola_assegnazione` del gruppo + rigenera
    `force=True` per le sedi toccate. NON modifica direttamente i giri.
    """

    materiale_tipo_codice_old: str = Field(
        ...,
        min_length=1,
        description="Materiale del gruppo da modificare (es. 'ATR803').",
    )
    localita_codice_old: str = Field(
        ...,
        min_length=1,
        description=(
            "Codice località manutentiva del gruppo "
            "(es. 'IMPMAN_MILANO_FIORENZA')."
        ),
    )
    materiale_tipo_codice_new: str | None = Field(
        default=None,
        description="Nuovo materiale. None = invariato.",
    )
    localita_codice_new: str | None = Field(
        default=None,
        description="Nuova località. None = invariata.",
    )
    confirm_delete_pdc: bool = Field(
        default=False,
        description=(
            "Conferma cancellazione PdC dipendenti dei giri rigenerati. "
            "Senza questa conferma, il rigenera force restituisce 409 "
            "se ci sono PdC dipendenti."
        ),
    )


class AggregaModificaSedeResult(BaseModel):
    """Risultato per singola sede rigenerata."""

    localita_codice: str
    n_giri_creati: int
    giri_ids: list[int]
    n_corse_processate: int
    n_corse_residue: int
    warnings: list[str]
    errore: str | None = Field(
        default=None,
        description=(
            "Se non None, la rigenerazione per questa sede è fallita. "
            "L'aggiornamento delle regole è comunque stato applicato."
        ),
    )


class AggregaModificaResponse(BaseModel):
    """Risposta MR-5."""

    n_regole_aggiornate: int
    n_giri_totali_creati: int
    risultati_per_sede: list[AggregaModificaSedeResult]


@router.post(
    "/{programma_id}/giri/aggrega-modifica",
    response_model=AggregaModificaResponse,
    summary=(
        "Sprint 8.0 MR-5: modifica chirurgica di un gruppo "
        "(materiale + sede). Aggiorna le regole "
        "programma_regola_assegnazione e rigenera (force=True) i giri "
        "delle sedi toccate."
    ),
)
async def aggrega_modifica(
    programma_id: int,
    payload: AggregaModificaRequest,
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> AggregaModificaResponse:
    """Sprint 8.0 MR-5 (entry 228).

    Flusso chirurgico:

    1. Trova le regole con `localita_codice == OLD` e `composizione_json`
       che contiene voce `materiale_tipo_codice == mat_old`.
    2. Aggiorna `composizione_json` (sostituisce voce mat_old → mat_new
       se diverso) e/o `localita_codice` (se diverso). Tiene in sync il
       campo legacy `materiale_tipo_codice` quando è single-material.
    3. Rigenera i giri (force=True) per OLD e per NEW (se diverse).

    Errori HTTP:

    - **404**: programma non visibile / inesistente.
    - **400**: programma non attivo, nessuna modifica specificata, o
      nessuna regola corrisponde al gruppo `(mat_old, loc_old)`.
    - **409**: pipeline freezata (`stato_pipeline_pdc >=
      MATERIALE_CONFERMATO`) — chiedi a un admin di sbloccare.
    - **409**: PdC dipendenti senza `confirm_delete_pdc=true`.

    Errori del builder per singola sede (es. `LocalitaNonTrovataError`,
    `RegolaAmbiguaError`) vengono catturati e tornati nel campo
    `errore` della sede corrispondente — l'aggiornamento delle regole
    resta comunque applicato (rollback completo non semantico per
    edit cross-sede).
    """
    # 1. Visibilità + load programma.
    programma = (
        await session.execute(
            select(ProgrammaMateriale).where(
                ProgrammaMateriale.id == programma_id,
                ProgrammaMateriale.azienda_id == user.azienda_id,
            )
        )
    ).scalar_one_or_none()
    if programma is None or not programma_visibile_per_ruoli(
        programma.stato_pipeline_pdc, user.roles, user.is_admin
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="programma non trovato",
        )
    if programma.stato != "attivo":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="programma non attivo",
        )
    if materiale_freezato(programma.stato_pipeline_pdc):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"programma in stato pipeline "
                f"{programma.stato_pipeline_pdc!r} "
                "(>= MATERIALE_CONFERMATO): giri read-only. Per "
                "modificare richiedi a un admin "
                "POST /api/programmi/{id}/sblocca."
            ),
        )

    # 2. Validazione: deve esserci almeno un cambio reale.
    cambia_mat = (
        payload.materiale_tipo_codice_new is not None
        and payload.materiale_tipo_codice_new
        != payload.materiale_tipo_codice_old
    )
    cambia_loc = (
        payload.localita_codice_new is not None
        and payload.localita_codice_new != payload.localita_codice_old
    )
    if not cambia_mat and not cambia_loc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "nessuna modifica richiesta: specifica "
                "materiale_tipo_codice_new e/o localita_codice_new "
                "diversi dai _old"
            ),
        )

    # 3. Trova le regole del gruppo (loc_old + comp contiene mat_old).
    regole_loc = (
        (
            await session.execute(
                select(ProgrammaRegolaAssegnazione).where(
                    ProgrammaRegolaAssegnazione.programma_id == programma_id,
                    ProgrammaRegolaAssegnazione.localita_codice
                    == payload.localita_codice_old,
                )
            )
        )
        .scalars()
        .all()
    )
    regole_aggiornabili: list[ProgrammaRegolaAssegnazione] = []
    for r in regole_loc:
        comp = r.composizione_json or []
        for item in comp:
            if (
                isinstance(item, dict)
                and item.get("materiale_tipo_codice")
                == payload.materiale_tipo_codice_old
            ):
                regole_aggiornabili.append(r)
                break

    if not regole_aggiornabili:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"nessuna regola trovata per gruppo "
                f"({payload.materiale_tipo_codice_old}, "
                f"{payload.localita_codice_old})"
            ),
        )

    # 4. Aggiorna le regole. Il SET su mapped attribute basta —
    # il flush avviene quando genera_giri fa il proprio commit/flush.
    new_mat = payload.materiale_tipo_codice_new
    new_loc = payload.localita_codice_new
    n_aggiornate = 0
    for r in regole_aggiornabili:
        if cambia_mat and new_mat is not None:
            new_comp: list[Any] = []
            for item in r.composizione_json or []:
                if (
                    isinstance(item, dict)
                    and item.get("materiale_tipo_codice")
                    == payload.materiale_tipo_codice_old
                ):
                    new_comp.append(
                        {**item, "materiale_tipo_codice": new_mat}
                    )
                else:
                    new_comp.append(item)
            r.composizione_json = new_comp
            # Sync legacy field se single-material.
            if (
                r.materiale_tipo_codice
                == payload.materiale_tipo_codice_old
            ):
                r.materiale_tipo_codice = new_mat
        if cambia_loc and new_loc is not None:
            r.localita_codice = new_loc
        n_aggiornate += 1

    await session.flush()

    # 5. Sedi da rigenerare = {old} se sede invariata, altrimenti {old, new}.
    sedi_da_rigenerare: set[str] = {payload.localita_codice_old}
    if cambia_loc and new_loc is not None:
        sedi_da_rigenerare.add(new_loc)

    # 6. Rigenera per ciascuna sede.
    risultati: list[AggregaModificaSedeResult] = []
    n_giri_totali = 0
    for sede in sorted(sedi_da_rigenerare):
        try:
            res: BuilderResult = await genera_giri(
                programma_id=programma_id,
                localita_codice=sede,
                session=session,
                azienda_id=user.azienda_id,
                force=True,
                confirm_delete_pdc=payload.confirm_delete_pdc,
                eseguito_da_user_id=user.user_id,
            )
            risultati.append(
                AggregaModificaSedeResult(
                    localita_codice=sede,
                    n_giri_creati=res.n_giri_creati,
                    giri_ids=res.giri_ids,
                    n_corse_processate=res.n_corse_processate,
                    n_corse_residue=res.n_corse_residue,
                    warnings=res.warnings,
                )
            )
            n_giri_totali += res.n_giri_creati
        except PdcDipendentiError as exc:
            # 409 per PdC dipendenti — l'utente deve passare
            # confirm_delete_pdc=true. Le regole sono GIA' aggiornate
            # ma nessun giro è stato cancellato/rigenerato (il check
            # PdC è prima del wipe).
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "pdc_dipendenti",
                    "sede": sede,
                    "message": str(exc),
                    "n_regole_aggiornate": n_aggiornate,
                },
            ) from exc
        except GiriEsistentiError as exc:
            # Difensivo: non dovrebbe mai capitare con force=True.
            risultati.append(
                AggregaModificaSedeResult(
                    localita_codice=sede,
                    n_giri_creati=0,
                    giri_ids=[],
                    n_corse_processate=0,
                    n_corse_residue=0,
                    warnings=[],
                    errore=f"{type(exc).__name__}: {exc}",
                )
            )
        except (
            ProgrammaNonTrovatoError,
            ProgrammaNonAttivoError,
            LocalitaNonTrovataError,
            BuilderVersionNonSupportata,
            ComposizioneNonAmmessaError,
            RegolaAmbiguaError,
            StrictModeViolation,
            PeriodoFuoriProgrammaError,
            ValueError,
        ) as exc:
            risultati.append(
                AggregaModificaSedeResult(
                    localita_codice=sede,
                    n_giri_creati=0,
                    giri_ids=[],
                    n_corse_processate=0,
                    n_corse_residue=0,
                    warnings=[],
                    errore=f"{type(exc).__name__}: {exc}",
                )
            )

    return AggregaModificaResponse(
        n_regole_aggiornate=n_aggiornate,
        n_giri_totali_creati=n_giri_totali,
        risultati_per_sede=risultati,
    )


# =====================================================================
# Sprint 8.0 MR-C (entry 229): wizard "materiale + linee → giri"
# =====================================================================
# Decisione utente entry 228+: il problema vero non è solo cosmetico —
# il builder produce turni mono-giornata mono-corsa quando non riesce
# a concatenare. Il wizard rovescia il paradigma: l'utente sceglie un
# materiale + le linee da coprire, il builder pesca tutte le corse di
# quelle linee e prova ad aggregarle in giri lunghi prima di rinunciare.
# Niente vuoti di posizionamento (regola utente).
#
# Implementazione "chirurgica": il wizard CREA regole
# `programma_regola_assegnazione` (priorità 90, una per linea) e poi
# rigenera (force=True) la sede target. Resta nel modello attuale, le
# regole sono modificabili dalla UI.


class LineaDistinct(BaseModel):
    """Linea del PdE con conteggio corse nel periodo del programma."""

    codice_linea: str
    n_corse: int


@router.get(
    "/{programma_id}/linee-distinct",
    response_model=list[LineaDistinct],
    summary=(
        "Linee distinte (codice_linea) delle corse PdE che cadono nel "
        "periodo del programma, con conteggio corse per linea. Usato "
        "dal wizard 'materiale + linee → giri'."
    ),
)
async def list_linee_distinct(
    programma_id: int,
    user: CurrentUser = _authz_read,
    session: AsyncSession = Depends(get_session),
) -> list[LineaDistinct]:
    """Sprint 8.0 MR-C (entry 229).

    Filtro periodo: intersezione tra `[corsa.valido_da, corsa.valido_a]`
    e `[programma.valido_da, programma.valido_a]`. Esclude corse
    cancellate (`corse_attive_clause`).

    Solo `codice_linea is not null` (le corse senza linea non sono
    selezionabili dal wizard — restano gestibili dalle regole standard).
    """
    programma = (
        await session.execute(
            select(ProgrammaMateriale).where(
                ProgrammaMateriale.id == programma_id,
                ProgrammaMateriale.azienda_id == user.azienda_id,
            )
        )
    ).scalar_one_or_none()
    if programma is None or not programma_visibile_per_ruoli(
        programma.stato_pipeline_pdc, user.roles, user.is_admin
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="programma non trovato",
        )

    rows = (
        await session.execute(
            select(
                CorsaCommerciale.codice_linea,
                func.count(CorsaCommerciale.id).label("n"),
            )
            .where(CorsaCommerciale.azienda_id == user.azienda_id)
            .where(corse_attive_clause())
            .where(CorsaCommerciale.codice_linea.is_not(None))
            .where(CorsaCommerciale.valido_da <= programma.valido_a)
            .where(CorsaCommerciale.valido_a >= programma.valido_da)
            .group_by(CorsaCommerciale.codice_linea)
            .order_by(CorsaCommerciale.codice_linea)
        )
    ).all()

    return [
        LineaDistinct(codice_linea=str(r[0]), n_corse=int(r[1]))
        for r in rows
    ]


class WizardDaLineeRequest(BaseModel):
    """Payload del wizard: materiale + sede + linee."""

    materiale_tipo_codice: str = Field(
        ...,
        min_length=1,
        description="Codice materiale (es. 'ETR522').",
    )
    localita_codice: str = Field(
        ...,
        min_length=1,
        description=(
            "Codice della località manutentiva sede del materiale "
            "(es. 'IMPMAN_MILANO_FIORENZA')."
        ),
    )
    linee: list[str] = Field(
        ...,
        min_length=1,
        description="Lista di `codice_linea` da coprire con il materiale.",
    )
    confirm_delete_pdc: bool = Field(
        default=False,
        description=(
            "Conferma cancellazione PdC dipendenti dei giri rigenerati."
        ),
    )


class WizardDaLineeResponse(BaseModel):
    """Risposta del wizard."""

    n_regole_create: int
    n_regole_aggiornate: int
    n_giri_creati: int
    giri_ids: list[int]
    n_corse_processate: int
    n_corse_residue: int
    warnings: list[str]
    errore: str | None = Field(
        default=None,
        description=(
            "Se non None, la rigenerazione è fallita. Le regole sono "
            "comunque state create/aggiornate e l'utente può ritentare "
            "il rigenera dalla UI standard."
        ),
    )


@router.post(
    "/{programma_id}/giri/wizard-da-linee",
    response_model=WizardDaLineeResponse,
    summary=(
        "Sprint 8.0 MR-C (entry 229): wizard 'materiale + linee → giri'. "
        "Crea regole programma_regola_assegnazione (1 per linea, "
        "priorità 90) e rigenera force=True i giri della sede."
    ),
)
async def wizard_da_linee(
    programma_id: int,
    payload: WizardDaLineeRequest,
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> WizardDaLineeResponse:
    """Sprint 8.0 MR-C (entry 229).

    Decisione utente: "imposto un materiale, scrivo uno per scriverne
    100, e gli do le linee, lui prende tutti i treni presenti sul PdE
    per quelle linee e crea tutti i giri materiali per quelle linee
    con il treno che ho impostato".

    Flusso:

    1. Validazione: programma visibile + attivo + non freezato; almeno
       1 linea richiesta.
    2. Per ogni linea: cerca regola esistente match (filtri =
       `[{campo: "codice_linea", op: "eq", valore: linea}]`,
       localita_codice = sede). Se trovata, aggiorna composizione +
       priorità a 90; altrimenti crea nuova regola.
    3. Rigenera (`force=True`) per la sede.

    Errori HTTP:

    - **404**: programma non visibile / inesistente.
    - **400**: programma non attivo, lista linee vuota.
    - **409**: pipeline freezata (>= MATERIALE_CONFERMATO).
    - **409**: PdC dipendenti senza `confirm_delete_pdc=true`.
    """
    # 1. Visibilità + load programma con LOCK pessimistico
    # (`SELECT ... FOR UPDATE`) per serializzare 2+ wizard concorrenti
    # sullo stesso programma. Il lock viene rilasciato a fine request
    # (commit/rollback). Senza, 2 utenti potrebbero creare regole
    # duplicate o causare race sul rigenera force=True.
    programma = (
        await session.execute(
            select(ProgrammaMateriale)
            .where(
                ProgrammaMateriale.id == programma_id,
                ProgrammaMateriale.azienda_id == user.azienda_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if programma is None or not programma_visibile_per_ruoli(
        programma.stato_pipeline_pdc, user.roles, user.is_admin
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="programma non trovato",
        )
    if programma.stato != "attivo":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="programma non attivo",
        )
    if materiale_freezato(programma.stato_pipeline_pdc):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"programma in stato pipeline "
                f"{programma.stato_pipeline_pdc!r} "
                "(>= MATERIALE_CONFERMATO): giri read-only. Per "
                "rigenerare richiedi a un admin "
                "POST /api/programmi/{id}/sblocca."
            ),
        )

    # 2. Dedupe + normalizza linee (no stringhe vuote, no duplicati).
    linee_norm = sorted({lin.strip() for lin in payload.linee if lin.strip()})
    if not linee_norm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="lista linee vuota dopo normalizzazione",
        )

    # 3. Carica regole esistenti del programma per match incrementale.
    regole_esistenti = (
        (
            await session.execute(
                select(ProgrammaRegolaAssegnazione).where(
                    ProgrammaRegolaAssegnazione.programma_id == programma_id,
                )
            )
        )
        .scalars()
        .all()
    )

    def _trova_regola_per_linea(
        linea: str,
    ) -> ProgrammaRegolaAssegnazione | None:
        """Match conservativo (Fausto review #4 + #5 entry 229):

        - Match SOLO se `filtri_json` è ESATTAMENTE una singola clausola
          `[{"campo":"codice_linea","op":"eq","valore":<linea>}]`, niente
          filtri AND extra (fascia_oraria, giorno_tipo). Se la regola ha
          filtri compositi, è considerata "non match" → il wizard crea
          una NUOVA regola affiancata, lasciando intatta quella manuale.
        - Salta anche regole multi-material (composizione_json con > 1
          voce): non vogliamo distruggere info di composizioni miste
          (es. ETR526+ETR425). Anche qui, "non match" → crea nuova.
        - `localita_codice == sede passed` resta requisito.
        """
        for r in regole_esistenti:
            if r.localita_codice != payload.localita_codice:
                continue
            filtri = r.filtri_json or []
            if len(filtri) != 1:
                continue
            f = filtri[0]
            if not isinstance(f, dict):
                continue
            if (
                f.get("campo") != "codice_linea"
                or f.get("op") != "eq"
                or f.get("valore") != linea
            ):
                continue
            comp = r.composizione_json or []
            if len(comp) > 1:
                # Multi-material: non sovrascriviamo, creiamo nuova.
                continue
            return r
        return None

    composizione_singola: list[Any] = [
        {
            "materiale_tipo_codice": payload.materiale_tipo_codice,
            "n_pezzi": 1,
        }
    ]

    n_create = 0
    n_aggiornate = 0
    for linea in linee_norm:
        match = _trova_regola_per_linea(linea)
        if match is None:
            nuova = ProgrammaRegolaAssegnazione(
                programma_id=programma_id,
                filtri_json=[
                    {"campo": "codice_linea", "op": "eq", "valore": linea}
                ],
                composizione_json=composizione_singola,
                materiale_tipo_codice=payload.materiale_tipo_codice,
                numero_pezzi=1,
                priorita=90,
                localita_codice=payload.localita_codice,
                note=(
                    "Creata da wizard 'materiale + linee → giri' "
                    "(MR-C entry 229)."
                ),
            )
            session.add(nuova)
            n_create += 1
        else:
            match.composizione_json = composizione_singola
            match.materiale_tipo_codice = payload.materiale_tipo_codice
            match.numero_pezzi = 1
            match.priorita = 90
            n_aggiornate += 1

    await session.flush()

    # 4. Rigenera giri (force=True) per la sede.
    try:
        res: BuilderResult = await genera_giri(
            programma_id=programma_id,
            localita_codice=payload.localita_codice,
            session=session,
            azienda_id=user.azienda_id,
            force=True,
            confirm_delete_pdc=payload.confirm_delete_pdc,
            eseguito_da_user_id=user.user_id,
        )
        return WizardDaLineeResponse(
            n_regole_create=n_create,
            n_regole_aggiornate=n_aggiornate,
            n_giri_creati=res.n_giri_creati,
            giri_ids=res.giri_ids,
            n_corse_processate=res.n_corse_processate,
            n_corse_residue=res.n_corse_residue,
            warnings=res.warnings,
        )
    except PdcDipendentiError as exc:
        # Le regole sono già state create — il rollback completo non è
        # semantico (l'utente vuole le regole comunque). Ritorna 409
        # con conteggio regole create per UX informata.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "pdc_dipendenti",
                "message": str(exc),
                "n_regole_create": n_create,
                "n_regole_aggiornate": n_aggiornate,
            },
        ) from exc
    except (
        ProgrammaNonTrovatoError,
        ProgrammaNonAttivoError,
        LocalitaNonTrovataError,
        BuilderVersionNonSupportata,
        ComposizioneNonAmmessaError,
        RegolaAmbiguaError,
        StrictModeViolation,
        PeriodoFuoriProgrammaError,
        GiriEsistentiError,
        ValueError,
    ) as exc:
        return WizardDaLineeResponse(
            n_regole_create=n_create,
            n_regole_aggiornate=n_aggiornate,
            n_giri_creati=0,
            giri_ids=[],
            n_corse_processate=0,
            n_corse_residue=0,
            warnings=[],
            errore=f"{type(exc).__name__}: {exc}",
        )


def _variante_id_from_ins(
    ins: FillGapInsert, varianti: "dict[int, Any]"
) -> int:
    """Lookup variante_id partendo da (giro_id, giornata, variant_index)
    nel dict ``varianti`` indicizzato per ``variante_id``.
    """
    for v in varianti.values():
        if (
            v.giro_id == ins.giro_id
            and v.giornata_numero == ins.giornata
            and v.variant_index == ins.variante_index
        ):
            return int(v.variante_id)
    raise RuntimeError(
        f"variante non trovata per inserimento {ins.giro_id}/"
        f"{ins.giornata}/{ins.variante_index}"
    )


# Router separato (radice /api) per il dettaglio singolo: il prefix
# `/api/programmi/{id}/giri` è del router principale, ma il dettaglio
# di un giro si lookup-pa via `/api/giri/{id}` indipendentemente dal
# programma.
giri_dettaglio_router = APIRouter(prefix="/api/giri", tags=["giri"])


@giri_dettaglio_router.get(
    "",
    response_model=list[GiroMaterialeListItem],
    summary="Lista giri materiali dell'azienda (cross-programma)",
)
async def list_giri_azienda(
    programma_id: int | None = Query(
        None, description="Filtra per programma. Se omesso, ritorna i giri di tutti i programmi dell'azienda."
    ),
    stato: str | None = Query(None, description="Filtra per stato (es. 'bozza', 'pubblicato')."),
    tipo_materiale: str | None = Query(
        None, description="Filtra per descrizione tipo materiale (match esatto)."
    ),
    q: str | None = Query(
        None,
        description="Ricerca testuale su numero_turno (case-insensitive contiene).",
        min_length=1,
        max_length=50,
    ),
    limit: int = Query(100, ge=1, le=500, description="Max righe ritornate."),
    offset: int = Query(0, ge=0, description="Offset paginazione."),
    user: CurrentUser = _authz_read,
    session: AsyncSession = Depends(get_session),
) -> list[GiroMaterialeListItem]:
    """Lista giri materiali dell'azienda, ordinata per ``numero_turno``.

    Sprint 7.3 MR 2: alimenta la schermata 4.2
    `/pianificatore-pdc/giri` (vista readonly del 2° ruolo) e può
    essere riusata dal 1° ruolo per drilldown cross-programma.
    Sprint 8.0 MR 0 (entry 164): aperta a tutti i 4 ruoli pipeline,
    con filtraggio per ``stato_pipeline_pdc`` del programma
    proprietario in base al ruolo dell'utente.
    """
    stmt = select(GiroMateriale).where(GiroMateriale.azienda_id == user.azienda_id)
    if programma_id is not None:
        stmt = stmt.where(GiroMateriale.programma_id == programma_id)
    if stato is not None:
        stmt = stmt.where(GiroMateriale.stato == stato)
    if tipo_materiale is not None:
        stmt = stmt.where(GiroMateriale.tipo_materiale == tipo_materiale)
    if q is not None:
        stmt = stmt.where(GiroMateriale.numero_turno.ilike(f"%{q}%"))

    # Sprint 8.0 MR 0: filtro visibilità per ruolo via JOIN sul
    # programma proprietario.
    soglia = soglia_pipeline_per_ruoli(user.roles, user.is_admin)
    if soglia is not None:
        stmt = stmt.join(
            ProgrammaMateriale,
            ProgrammaMateriale.id == GiroMateriale.programma_id,
        ).where(
            ProgrammaMateriale.stato_pipeline_pdc.in_(stati_pdc_da(soglia))
        )

    stmt = stmt.order_by(GiroMateriale.numero_turno).limit(limit).offset(offset)
    rows = (await session.execute(stmt)).scalars().all()
    out: list[GiroMaterialeListItem] = []
    for g in rows:
        meta = g.generation_metadata_json or {}
        n_varianti_per_giornata = meta.get("n_varianti_per_giornata") or []
        n_varianti_totale = (
            sum(int(x) for x in n_varianti_per_giornata)
            if isinstance(n_varianti_per_giornata, list)
            else 0
        )
        out.append(
            GiroMaterialeListItem(
                id=g.id,
                numero_turno=g.numero_turno,
                tipo_materiale=g.tipo_materiale,
                materiale_tipo_codice=g.materiale_tipo_codice,
                numero_giornate=g.numero_giornate,
                km_media_giornaliera=float(g.km_media_giornaliera)
                if g.km_media_giornaliera is not None
                else None,
                km_media_annua=float(g.km_media_annua) if g.km_media_annua is not None else None,
                motivo_chiusura=meta.get("motivo_chiusura"),
                chiuso=bool(meta.get("chiuso", False)),
                stato=g.stato,
                n_varianti_totale=n_varianti_totale,
                created_at=g.created_at,
            )
        )
    return out


class PatchGiroMaterialeRequest(BaseModel):
    """MR η — payload PATCH ``/api/giri/{id}``.

    Permette di modificare il materiale assegnato a un giro generato.
    Spec utente 2026-05-06:

    > "Una volta generato il turno io posso interagire sul turno
    > generato, potendo inserire se il materiale è in doppia, se
    > sgancia oppure no."

    Scope MR η MVP: solo il materiale del giro (header). Le azioni
    "doppia composizione" e "sgancio" agiscono su singoli ``GiroBlocco``
    e sono scope di MR η-bis (non ancora implementate).
    """

    model_config = ConfigDict(extra="forbid")

    materiale_tipo_codice: str | None = Field(
        default=None,
        description="Nuovo codice MaterialeTipo. None = non toccare il valore.",
    )
    descrizione_materiale: str | None = Field(
        default=None, description="Descrizione testuale (denormalizzata)."
    )
    tipo_materiale: str | None = Field(
        default=None,
        description="Nome del tipo (denormalizzato, es. 'ETR526').",
    )


@giri_dettaglio_router.patch(
    "/{giro_id}",
    response_model=GiroMaterialeListItem,
    summary="Modifica materiale del giro generato (MR η)",
)
async def update_giro(
    giro_id: int,
    payload: PatchGiroMaterialeRequest,
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> GiroMateriale:
    """MR η — modifica i campi del giro generato (oggi: materiale).

    Vincoli:

    - Giro deve esistere e appartenere all'azienda corrente (404).
    - Giro non deve essere in stato pipeline freezato (409). Per ora
      il check è morbido: il programma può essere freezato ma il giro
      stesso non ha pipeline propria.
    - Il PATCH è idempotente. Solo i campi forniti vengono aggiornati
      (Pydantic ``exclude_unset``).
    """
    stmt = select(GiroMateriale).where(
        GiroMateriale.id == giro_id,
        GiroMateriale.azienda_id == user.azienda_id,
    )
    g = (await session.execute(stmt)).scalar_one_or_none()
    if g is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Giro non trovato")

    # Check freeze pipeline (coerente con i PATCH di altri endpoint).
    prog_stmt = select(ProgrammaMateriale.stato_pipeline_pdc).where(
        ProgrammaMateriale.id == g.programma_id
    )
    stato_pipeline = (await session.execute(prog_stmt)).scalar_one_or_none()
    if stato_pipeline is not None and materiale_freezato(stato_pipeline):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"giro nel programma con pipeline {stato_pipeline!r}: read-only. "
                "L'admin deve sbloccare il programma per modificare il giro."
            ),
        )

    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(g, k, v)
    g.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(g)
    return g


class PatchBloccoRequest(BaseModel):
    """MR η-bis — payload PATCH ``/api/giri/{giro_id}/blocchi/{blocco_id}``.

    Permette di marcare un blocco come "doppia composizione" (n_pezzi=2)
    o come punto di "sgancio" (è il blocco DOPO il quale il materiale
    si separa). Salvato in ``metadata_json`` per evitare migration —
    è semantica UI/operativa, non vincolo del builder.
    """

    model_config = ConfigDict(extra="forbid")

    n_pezzi: int | None = Field(default=None, ge=1, le=4)
    is_sgancio: bool | None = None
    is_validato_utente: bool | None = None


class DuplicaGiroResponse(BaseModel):
    """MR η-bis — response del ``POST /api/giri/{giro_id}/duplica``.

    Ritorna l'``id`` del nuovo giro creato + il ``numero_turno``
    generato col suffisso ``-DUP-{N}``.
    """

    model_config = ConfigDict(extra="forbid")

    nuovo_giro_id: int
    nuovo_numero_turno: str
    n_giornate_copiate: int
    n_varianti_copiate: int
    n_blocchi_copiati: int


@giri_dettaglio_router.patch(
    "/{giro_id}/blocchi/{blocco_id}",
    response_model=GiroBloccoRead,
    summary="Modifica un singolo GiroBlocco (MR η-bis: doppia/sgancio)",
)
async def patch_blocco(
    giro_id: int,
    blocco_id: int,
    payload: PatchBloccoRequest,
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> GiroBloccoRead:
    """MR η-bis — aggiorna metadata di un blocco.

    Attualmente supporta:

    - ``n_pezzi`` (1..4): doppia/multi composizione su questo blocco.
    - ``is_sgancio`` (bool): marker "il materiale si sgancia dopo questo
      blocco" (semantica UI per la visualizzazione).
    - ``is_validato_utente`` (bool): conferma manuale del pianificatore.

    I primi due sono salvati in ``metadata_json`` per evitare migration:
    sono semantica operativa, il builder non li usa per costruire la
    sequenza.
    """
    # Verifica ownership: giro appartiene all'azienda + blocco
    # appartiene a quel giro.
    g_stmt = select(GiroMateriale).where(
        GiroMateriale.id == giro_id,
        GiroMateriale.azienda_id == user.azienda_id,
    )
    giro = (await session.execute(g_stmt)).scalar_one_or_none()
    if giro is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Giro non trovato")

    # Pipeline freeze.
    prog_stmt = select(ProgrammaMateriale.stato_pipeline_pdc).where(
        ProgrammaMateriale.id == giro.programma_id
    )
    stato_pipeline = (await session.execute(prog_stmt)).scalar_one_or_none()
    if stato_pipeline is not None and materiale_freezato(stato_pipeline):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"programma freezato (pipeline {stato_pipeline!r}): blocco read-only.",
        )

    # Carica blocco e verifica che appartenga al giro (via variante →
    # giornata → giro).
    b_stmt = (
        select(GiroBlocco)
        .join(GiroVariante, GiroVariante.id == GiroBlocco.giro_variante_id)
        .join(GiroGiornata, GiroGiornata.id == GiroVariante.giro_giornata_id)
        .where(
            GiroBlocco.id == blocco_id,
            GiroGiornata.giro_materiale_id == giro_id,
        )
    )
    blocco = (await session.execute(b_stmt)).scalar_one_or_none()
    if blocco is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="blocco non trovato per questo giro",
        )

    metadata = dict(blocco.metadata_json) if blocco.metadata_json else {}
    if payload.n_pezzi is not None:
        metadata["n_pezzi"] = payload.n_pezzi
    if payload.is_sgancio is not None:
        metadata["is_sgancio"] = payload.is_sgancio
    blocco.metadata_json = metadata
    if payload.is_validato_utente is not None:
        blocco.is_validato_utente = payload.is_validato_utente

    await session.commit()
    await session.refresh(blocco)

    # Lookup nomi stazione + numero treno per la response (riusiamo lo
    # stesso pattern di get_giro_dettaglio).
    nome_stazione: dict[str, str] = {}
    codici = [
        c for c in (blocco.stazione_da_codice, blocco.stazione_a_codice) if c is not None
    ]
    if codici:
        st_stmt = select(Stazione.codice, Stazione.nome).where(
            Stazione.codice.in_(codici), Stazione.azienda_id == user.azienda_id
        )
        nome_stazione = dict((await session.execute(st_stmt)).tuples().all())
    num: str | None = None
    if blocco.corsa_commerciale_id is not None:
        n_stmt = select(CorsaCommerciale.numero_treno).where(
            CorsaCommerciale.id == blocco.corsa_commerciale_id
        )
        num = (await session.execute(n_stmt)).scalar_one_or_none()
    elif blocco.corsa_materiale_vuoto_id is not None:
        n_stmt2 = select(CorsaMaterialeVuoto.numero_treno_vuoto).where(
            CorsaMaterialeVuoto.id == blocco.corsa_materiale_vuoto_id
        )
        num = (await session.execute(n_stmt2)).scalar_one_or_none()

    return GiroBloccoRead(
        id=blocco.id,
        seq=blocco.seq,
        tipo_blocco=blocco.tipo_blocco,
        corsa_commerciale_id=blocco.corsa_commerciale_id,
        corsa_materiale_vuoto_id=blocco.corsa_materiale_vuoto_id,
        stazione_da_codice=blocco.stazione_da_codice,
        stazione_a_codice=blocco.stazione_a_codice,
        stazione_da_nome=(
            nome_stazione.get(blocco.stazione_da_codice)
            if blocco.stazione_da_codice
            else None
        ),
        stazione_a_nome=(
            nome_stazione.get(blocco.stazione_a_codice)
            if blocco.stazione_a_codice
            else None
        ),
        ora_inizio=blocco.ora_inizio,
        ora_fine=blocco.ora_fine,
        descrizione=blocco.descrizione,
        is_validato_utente=blocco.is_validato_utente,
        metadata_json=blocco.metadata_json,
        numero_treno=num,
    )


# =====================================================================
# Sprint 8.0 MR-B.1 (entry 230): sposta blocco tra giornate/varianti
# =====================================================================
# Decisione utente entry 229: "drag&drop deve essere fluido come un
# desktop Mac". Backend: endpoint che sposta un blocco tra giornate/
# varianti dello stesso giro, calcolando le violazioni di fattibilità
# (continuità stazioni + tempi) e ritornandole. Se l'utente forza
# l'operazione (force=True), la mossa viene applicata anche con
# violazioni.


class ViolazioneFattibilita(BaseModel):
    """Singola violazione di fattibilità trovata dal check post-sposta."""

    severity: Literal["error", "warning"]
    codice: str  # "discontinuita_stazione" | "gap_negativo" | "gap_eccessivo"
    variante_id: int
    variante_label: str  # "G2 V0" per UI
    seq_blocco_a: int
    seq_blocco_b: int
    descrizione: str


class SpostaBloccoRequest(BaseModel):
    """Payload per spostare un blocco tra giornate/varianti.

    Sprint 8.0 MR-A (entry 231): supporto cross-turno via
    `giro_target_id` opzionale. Quando passato, il blocco viene
    spostato in un altro `GiroMateriale` dello stesso programma e
    azienda. Default `None` = stesso giro (comportamento MR-B.1).
    """

    model_config = ConfigDict(extra="forbid")

    giornata_target: int = Field(
        ..., ge=1, description="Numero giornata destinazione."
    )
    variant_index_target: int = Field(
        ...,
        ge=0,
        description="Indice variante destinazione (0 = canonica).",
    )
    seq_target: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Posizione seq nella variante destinazione (1-based). "
            "Se None, append in coda."
        ),
    )
    giro_target_id: int | None = Field(
        default=None,
        description=(
            "Sprint 8.0 MR-A entry 231 — id del giro destinazione "
            "per spostamento cross-turno. Default None = stesso giro "
            "del blocco (intra-turno, comportamento MR-B.1). Il giro "
            "target deve appartenere stesso programma + stessa azienda."
        ),
    )
    dry_run: bool = Field(
        default=False,
        description=(
            "Se true, calcola le violazioni ma NON applica lo "
            "spostamento."
        ),
    )
    force: bool = Field(
        default=False,
        description=(
            "Se true, applica anche se ci sono violazioni "
            "(severity=error)."
        ),
    )


class SpostaBloccoResponse(BaseModel):
    """Esito dello spostamento."""

    applied: bool
    blocco_id: int
    nuovo_giro_variante_id: int | None
    nuovo_seq: int | None
    violazioni: list[ViolazioneFattibilita]


def _check_fattibilita_variante(
    blocchi_ordinati: list[GiroBlocco],
    variante_id: int,
    variante_label: str,
) -> list[ViolazioneFattibilita]:
    """Calcola le violazioni di fattibilità di una sequenza di blocchi.

    Regole:
    - **Continuità stazione** (severity=error): per blocchi consecutivi
      con stazione_a/da definita, deve essere `block[i].stazione_a ==
      block[i+1].stazione_da`. Salta i blocchi senza stazioni (es. soste
      pure, alcuni accessori).
    - **Gap negativo** (severity=error): `block[i].ora_fine` deve essere
      ≤ `block[i+1].ora_inizio`. Cross-mezzanotte consentito (l'ora di
      fine può essere "minore" se il blocco successivo è il giorno
      dopo); modello semplificato: consideriamo violazione solo se gap
      ≤ -360 min (6h indietro = quasi certo bug).
    - **Gap eccessivo** (severity=warning): gap > 5h diurni
      intra-giornata (allineato con MR-3 entry 222). Solo warning, non
      error.
    """
    violazioni: list[ViolazioneFattibilita] = []
    for i in range(len(blocchi_ordinati) - 1):
        a = blocchi_ordinati[i]
        b = blocchi_ordinati[i + 1]
        # Continuità stazione.
        if (
            a.stazione_a_codice is not None
            and b.stazione_da_codice is not None
            and a.stazione_a_codice != b.stazione_da_codice
        ):
            violazioni.append(
                ViolazioneFattibilita(
                    severity="error",
                    codice="discontinuita_stazione",
                    variante_id=variante_id,
                    variante_label=variante_label,
                    seq_blocco_a=a.seq,
                    seq_blocco_b=b.seq,
                    descrizione=(
                        f"Discontinuità: blocco seq={a.seq} arriva a "
                        f"{a.stazione_a_codice}, blocco seq={b.seq} "
                        f"parte da {b.stazione_da_codice}."
                    ),
                )
            )
        # Gap orari.
        if a.ora_fine is not None and b.ora_inizio is not None:
            min_a = a.ora_fine.hour * 60 + a.ora_fine.minute
            min_b = b.ora_inizio.hour * 60 + b.ora_inizio.minute
            gap = min_b - min_a  # may be negative (cross-mezzanotte)
            # Cross-mezzanotte: se gap < 0, normalizziamo +1440.
            if gap < -360:
                violazioni.append(
                    ViolazioneFattibilita(
                        severity="error",
                        codice="gap_negativo",
                        variante_id=variante_id,
                        variante_label=variante_label,
                        seq_blocco_a=a.seq,
                        seq_blocco_b=b.seq,
                        descrizione=(
                            f"Gap negativo eccessivo tra seq={a.seq} "
                            f"(fine {a.ora_fine}) e seq={b.seq} "
                            f"(inizio {b.ora_inizio}): {gap} min."
                        ),
                    )
                )
            elif gap > 300:  # > 5h diurni
                # Warning soft (intra-giornata > 5h è atipico).
                violazioni.append(
                    ViolazioneFattibilita(
                        severity="warning",
                        codice="gap_eccessivo",
                        variante_id=variante_id,
                        variante_label=variante_label,
                        seq_blocco_a=a.seq,
                        seq_blocco_b=b.seq,
                        descrizione=(
                            f"Gap > 5h tra seq={a.seq} (fine "
                            f"{a.ora_fine}) e seq={b.seq} (inizio "
                            f"{b.ora_inizio}): {gap} min."
                        ),
                    )
                )
    return violazioni


@giri_dettaglio_router.post(
    "/{giro_id}/blocchi/{blocco_id}/sposta",
    response_model=SpostaBloccoResponse,
    summary=(
        "Sprint 8.0 MR-B.1 (entry 230): sposta un blocco tra "
        "giornate/varianti dello stesso giro. Calcola le violazioni "
        "di fattibilità (continuità stazioni + gap orari)."
    ),
)
async def sposta_blocco(
    giro_id: int,
    blocco_id: int,
    payload: SpostaBloccoRequest,
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> SpostaBloccoResponse:
    """Sprint 8.0 MR-B.1 (entry 230).

    Flusso:

    1. Valida ownership: giro+blocco appartengono all'azienda corrente.
    2. Pipeline freeze check.
    3. Trova variante destinazione (nello stesso giro: `numero_giornata
       == giornata_target`, `variant_index == variant_index_target`).
       404 se non esiste.
    4. Calcola la sequenza variante origine (post-rimozione del blocco)
       e variante destinazione (post-inserimento in `seq_target`).
    5. `_check_fattibilita_variante` su entrambe le sequenze.
    6. Se violazioni con `severity=="error"` e `not force` → ritorna
       `applied=False` con la lista violazioni (no commit).
    7. Altrimenti applica:
       - Aggiorna FK `giro_variante_id` del blocco al target.
       - Re-numera seq nella variante origine (compattazione).
       - Re-numera seq nella variante destinazione (shift in mezzo).
       - Commit.

    Errori HTTP:
    - 404: giro/blocco/giornata-variante target non trovati.
    - 409: pipeline freezata.
    """
    # 1. Ownership giro + LOCK pessimistico (Fausto review #3+#5
    # CRITICAL entry 230): serializza drag&drop concorrenti sullo
    # stesso giro evitando corruzione di `seq` (unique
    # `(giro_variante_id, seq)`). Il lock è rilasciato a fine request.
    #
    # Sprint 8.0 MR-A entry 231: lock anche giro_target_id per
    # cross-turno. Per evitare deadlock se 2 utenti spostano in
    # direzioni opposte (A→B e B→A), lock i due giri in ordine di id
    # crescente (deterministico).
    target_giro_id = payload.giro_target_id
    if target_giro_id is not None and target_giro_id != giro_id:
        lock_ids = sorted([giro_id, target_giro_id])
    else:
        lock_ids = [giro_id]

    giri_locked = list(
        (
            await session.execute(
                select(GiroMateriale)
                .where(
                    GiroMateriale.id.in_(lock_ids),
                    GiroMateriale.azienda_id == user.azienda_id,
                )
                .order_by(GiroMateriale.id)
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    if len(giri_locked) != len(lock_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="giro o giro_target non trovato",
        )
    giri_by_id = {g.id: g for g in giri_locked}
    giro = giri_by_id[giro_id]

    # MR-A entry 231: cross-turno richiede stesso programma_id (i giri
    # devono appartenere allo stesso programma per garantire coerenza
    # PdE, regole, dotazione).
    # MR-G2 (Fausto F6 LOW): defensive check — la select è già filtrata
    # per `azienda_id == user.azienda_id`, ma esplicitare l'assert
    # documenta l'invariante e protegge da future modifiche della query
    # che dimentichino il filtro.
    if target_giro_id is not None and target_giro_id != giro_id:
        target_giro = giri_by_id.get(target_giro_id)
        if target_giro is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="giro_target non trovato",
            )
        assert target_giro.azienda_id == user.azienda_id, (
            "invariante violata: target_giro.azienda_id != user.azienda_id "
            "(la select pessimistica avrebbe dovuto filtrarlo)"
        )
        if target_giro.programma_id != giro.programma_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "giro_target appartiene a un programma diverso: "
                    "lo spostamento cross-programma non è ammesso."
                ),
            )

    # 2. Pipeline freeze.
    stato_pipeline = (
        await session.execute(
            select(ProgrammaMateriale.stato_pipeline_pdc).where(
                ProgrammaMateriale.id == giro.programma_id
            )
        )
    ).scalar_one_or_none()
    if stato_pipeline is not None and materiale_freezato(stato_pipeline):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"programma freezato (pipeline {stato_pipeline!r}): "
                "blocco read-only."
            ),
        )

    # 3. Carica blocco con variante origine.
    blocco = (
        await session.execute(
            select(GiroBlocco)
            .join(GiroVariante, GiroVariante.id == GiroBlocco.giro_variante_id)
            .join(GiroGiornata, GiroGiornata.id == GiroVariante.giro_giornata_id)
            .where(
                GiroBlocco.id == blocco_id,
                GiroGiornata.giro_materiale_id == giro_id,
            )
        )
    ).scalar_one_or_none()
    if blocco is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="blocco non trovato per questo giro",
        )

    variante_origine_id = blocco.giro_variante_id

    # 4. Trova variante destinazione (intra o cross-turno MR-A).
    target_giro_id_effective = (
        payload.giro_target_id
        if payload.giro_target_id is not None
        else giro_id
    )
    variante_target = (
        await session.execute(
            select(GiroVariante)
            .join(GiroGiornata, GiroGiornata.id == GiroVariante.giro_giornata_id)
            .where(
                GiroGiornata.giro_materiale_id == target_giro_id_effective,
                GiroGiornata.numero_giornata == payload.giornata_target,
                GiroVariante.variant_index == payload.variant_index_target,
            )
        )
    ).scalar_one_or_none()
    if variante_target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"variante target non trovata: giro="
                f"{target_giro_id_effective}, giornata="
                f"{payload.giornata_target}, variant_index="
                f"{payload.variant_index_target}"
            ),
        )

    # 5. Carica blocchi della variante origine + destinazione (escludi
    # il blocco da spostare nelle simulazioni).
    async def _blocchi_variante(var_id: int) -> list[GiroBlocco]:
        return list(
            (
                await session.execute(
                    select(GiroBlocco)
                    .where(GiroBlocco.giro_variante_id == var_id)
                    .order_by(GiroBlocco.seq)
                )
            )
            .scalars()
            .all()
        )

    origine_blocchi = await _blocchi_variante(variante_origine_id)
    target_blocchi = (
        origine_blocchi
        if variante_target.id == variante_origine_id
        else await _blocchi_variante(variante_target.id)
    )

    # Sequenza simulata variante origine (post rimozione del blocco).
    sim_origine = [b for b in origine_blocchi if b.id != blocco.id]

    # Sequenza simulata variante target (post inserimento del blocco).
    # MR-G2 (Fausto F7): chiarimento semantica seq_target.
    # - Payload `seq_target` è 1-based (`Field(..., ge=1)` su request).
    # - `pos_inserimento` è 0-based (indice dentro `target_senza`).
    # - Conversione: `seq_target - 1`. Clamp a [0, len(target_senza)]
    #   per accettare append in coda (`seq_target == len + 1`) e
    #   inserimento in testa (`seq_target == 1` → pos 0).
    # - Se `seq_target is None` → append in coda.
    target_senza = [b for b in target_blocchi if b.id != blocco.id]
    pos_inserimento = (
        len(target_senza)
        if payload.seq_target is None
        else max(0, min(payload.seq_target - 1, len(target_senza)))
    )
    sim_target = (
        target_senza[:pos_inserimento]
        + [blocco]
        + target_senza[pos_inserimento:]
    )

    # 6. Calcola violazioni.
    label_origine = f"V{0}"  # placeholder; potremmo lookup la giornata
    label_target = f"G{payload.giornata_target} V{payload.variant_index_target}"

    violazioni: list[ViolazioneFattibilita] = []
    if variante_target.id != variante_origine_id:
        violazioni.extend(
            _check_fattibilita_variante(
                sim_origine, variante_origine_id, label_origine
            )
        )
    violazioni.extend(
        _check_fattibilita_variante(sim_target, variante_target.id, label_target)
    )

    # Fausto review #7 WARNING entry 230: PdC dipendenti dal blocco.
    # Lo spostamento non rompe FK (giro_blocco_id resta valido), ma il
    # PdC pianificato per il blocco nella giornata X ora è in giornata Y
    # → la pianificazione PdC è "stale". Warning, non error: l'utente
    # decide se procedere e poi rigenera i PdC.
    if variante_target.id != variante_origine_id:
        from colazione.models.turni_pdc import TurnoPdcBlocco

        n_pdc_dipendenti = int(
            (
                await session.execute(
                    select(func.count(TurnoPdcBlocco.id)).where(
                        TurnoPdcBlocco.giro_blocco_id == blocco.id
                    )
                )
            ).scalar_one()
        )
        if n_pdc_dipendenti > 0:
            violazioni.append(
                ViolazioneFattibilita(
                    severity="warning",
                    codice="pdc_stale",
                    variante_id=variante_target.id,
                    variante_label=label_target,
                    seq_blocco_a=blocco.seq,
                    seq_blocco_b=blocco.seq,
                    descrizione=(
                        f"{n_pdc_dipendenti} blocchi PdC dipendono da "
                        "questo blocco: lo spostamento li rende "
                        "pianificazionalmente stale. Considera di "
                        "rigenerare i turni PdC dopo l'operazione."
                    ),
                )
            )

    has_errors = any(v.severity == "error" for v in violazioni)

    # 7. Dry run o errori senza force → no commit.
    if payload.dry_run or (has_errors and not payload.force):
        return SpostaBloccoResponse(
            applied=False,
            blocco_id=blocco.id,
            nuovo_giro_variante_id=None,
            nuovo_seq=None,
            violazioni=violazioni,
        )

    # 8. Applica lo spostamento.
    # Sprint 8.0 MR-B.4 entry 233 (Fausto review #3): l'unique
    # constraint `(giro_variante_id, seq)` può violarsi durante il
    # flush se SQLAlchemy invia gli UPDATE in ordine non-favorevole
    # (es. UPDATE b3.seq=2 prima di spostare via b2 al nuovo
    # giro_variante_id). Pattern: 2-passate con seq negativi
    # temporanei (intero signed, niente collisione coi positivi),
    # flush in mezzo, poi assegnazione finale positiva.

    # 8a. Sposta via il blocco PRIMA di rinumerare la variante origine.
    blocco.giro_variante_id = variante_target.id
    # Seq temporaneo negativo per il blocco trasferito così non
    # collide con i seq esistenti nella variante target.
    blocco.seq = -1_000_000
    await session.flush()

    # 8b. Re-numera origine (sim_origine = blocchi che restano).
    if variante_target.id != variante_origine_id:
        # Step 1: seq negativi temporanei
        for idx, b in enumerate(sim_origine, start=1):
            b.seq = -idx
        await session.flush()
        # Step 2: seq finali positivi
        for idx, b in enumerate(sim_origine, start=1):
            b.seq = idx
        await session.flush()

    # 8c. Re-numera target (sim_target include il blocco appena spostato).
    # Step 1: seq negativi temporanei
    for idx, b in enumerate(sim_target, start=1):
        b.seq = -idx
    await session.flush()
    # Step 2: seq finali positivi
    for idx, b in enumerate(sim_target, start=1):
        b.seq = idx

    await session.commit()
    await session.refresh(blocco)

    return SpostaBloccoResponse(
        applied=True,
        blocco_id=blocco.id,
        nuovo_giro_variante_id=variante_target.id,
        nuovo_seq=blocco.seq,
        violazioni=violazioni,
    )


# =====================================================================
# Sprint 8.0 MR-B.2.2 (entry 235): aggiungi blocco vuoto manuale
# =====================================================================
# Decisione utente entry 230 + 234: "io posso decidere di aggiungere
# un vuoto". L'aggiunta crea un `giro_blocco` con
# `tipo_blocco='materiale_vuoto'` e `corsa_materiale_vuoto_id=null`
# (vuoto MANUALE, distinto dai vuoti generati dal builder).
# Validazione fattibilità + re-numerazione seq + lock pessimistico
# riusano i pattern di MR-B.1/B.2.


class AggiungiVuotoRequest(BaseModel):
    """Payload per aggiungere un vuoto manuale a una variante."""

    model_config = ConfigDict(extra="forbid")

    giornata_target: int = Field(..., ge=1)
    variant_index_target: int = Field(..., ge=0)
    seq_target: int | None = Field(
        default=None,
        ge=1,
        description="1-based. Se None, append in coda alla variante.",
    )
    stazione_da_codice: str = Field(..., min_length=1, max_length=20)
    stazione_a_codice: str = Field(..., min_length=1, max_length=20)
    ora_inizio: str = Field(
        ..., description="Formato HH:MM o HH:MM:SS."
    )
    ora_fine: str = Field(..., description="Formato HH:MM o HH:MM:SS.")
    descrizione: str | None = Field(default=None, max_length=200)
    dry_run: bool = Field(default=False)
    force: bool = Field(default=False)


class AggiungiVuotoResponse(BaseModel):
    applied: bool
    blocco_id: int | None
    nuovo_seq: int | None
    violazioni: list[ViolazioneFattibilita]


def _parse_time_input(s: str) -> time:
    """Parsa 'HH:MM' o 'HH:MM:SS' in `time`. Lancia ValueError altrimenti."""
    parts = s.split(":")
    if len(parts) < 2 or len(parts) > 3:
        raise ValueError(f"orario non valido: {s!r}")
    h = int(parts[0])
    m = int(parts[1])
    sec = int(parts[2]) if len(parts) == 3 else 0
    if not (0 <= h < 24 and 0 <= m < 60 and 0 <= sec < 60):
        raise ValueError(f"orario fuori range: {s!r}")
    return time(h, m, sec)


@giri_dettaglio_router.post(
    "/{giro_id}/blocchi/aggiungi-vuoto",
    response_model=AggiungiVuotoResponse,
    status_code=status.HTTP_200_OK,
    summary=(
        "Sprint 8.0 MR-B.2.2 (entry 235): aggiungi un vuoto manuale "
        "a una variante. corsa_materiale_vuoto_id=null lo distingue "
        "dai vuoti generati dal builder."
    ),
)
async def aggiungi_vuoto(
    giro_id: int,
    payload: AggiungiVuotoRequest,
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> AggiungiVuotoResponse:
    """Sprint 8.0 MR-B.2.2 (entry 235).

    Flusso:
    1. Lock pessimistico giro.
    2. Pipeline freeze check.
    3. Validazione orari + esistenza stazioni (FK implicita).
    4. Lookup variante target (404 se non trovata).
    5. Carica blocchi variante e simula post-inserimento.
    6. Check fattibilità (continuità stazioni + gap orari).
    7. Se dry_run o errors-no-force → no commit.
    8. Else: INSERT blocco + re-numera seq con pattern offset negativo
       (MR-B.4 entry 234) per evitare unique violation.
    """
    giro = (
        await session.execute(
            select(GiroMateriale)
            .where(
                GiroMateriale.id == giro_id,
                GiroMateriale.azienda_id == user.azienda_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if giro is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="giro non trovato",
        )

    stato_pipeline = (
        await session.execute(
            select(ProgrammaMateriale.stato_pipeline_pdc).where(
                ProgrammaMateriale.id == giro.programma_id
            )
        )
    ).scalar_one_or_none()
    if stato_pipeline is not None and materiale_freezato(stato_pipeline):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"programma freezato (pipeline {stato_pipeline!r}): "
                "blocco read-only."
            ),
        )

    # Parse orari
    try:
        ora_inizio_t = _parse_time_input(payload.ora_inizio)
        ora_fine_t = _parse_time_input(payload.ora_fine)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"orario invalido: {exc}",
        ) from exc

    # Verifica esistenza stazioni (FK implicita su giro_blocco).
    staz_codici = (
        (
            await session.execute(
                select(Stazione.codice).where(
                    Stazione.codice.in_(
                        [
                            payload.stazione_da_codice,
                            payload.stazione_a_codice,
                        ]
                    ),
                    Stazione.azienda_id == user.azienda_id,
                )
            )
        )
        .scalars()
        .all()
    )
    staz_set = set(staz_codici)
    if payload.stazione_da_codice not in staz_set:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"stazione_da_codice {payload.stazione_da_codice!r} non trovata",
        )
    if payload.stazione_a_codice not in staz_set:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"stazione_a_codice {payload.stazione_a_codice!r} non trovata",
        )

    # Lookup variante target.
    variante_target = (
        await session.execute(
            select(GiroVariante)
            .join(GiroGiornata, GiroGiornata.id == GiroVariante.giro_giornata_id)
            .where(
                GiroGiornata.giro_materiale_id == giro_id,
                GiroGiornata.numero_giornata == payload.giornata_target,
                GiroVariante.variant_index == payload.variant_index_target,
            )
        )
    ).scalar_one_or_none()
    if variante_target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"variante non trovata: giornata={payload.giornata_target}, "
                f"variant_index={payload.variant_index_target}"
            ),
        )

    # Carica blocchi esistenti.
    blocchi_esistenti = list(
        (
            await session.execute(
                select(GiroBlocco)
                .where(GiroBlocco.giro_variante_id == variante_target.id)
                .order_by(GiroBlocco.seq)
            )
        )
        .scalars()
        .all()
    )
    pos_inserimento = (
        len(blocchi_esistenti)
        if payload.seq_target is None
        else max(0, min(payload.seq_target - 1, len(blocchi_esistenti)))
    )

    # Crea il nuovo blocco vuoto manuale (in memoria, no flush ancora).
    nuovo = GiroBlocco(
        giro_variante_id=variante_target.id,
        seq=-1_000_000,  # placeholder, riassegnato dopo
        tipo_blocco="materiale_vuoto",
        corsa_commerciale_id=None,
        corsa_materiale_vuoto_id=None,
        stazione_da_codice=payload.stazione_da_codice,
        stazione_a_codice=payload.stazione_a_codice,
        ora_inizio=ora_inizio_t,
        ora_fine=ora_fine_t,
        descrizione=payload.descrizione,
        is_validato_utente=True,
        metadata_json={
            "is_manuale": True,
            "tipo_vuoto": "manuale",
            "creato_da_user_id": user.user_id,
            "creato_at_iso": datetime.now(UTC).isoformat(),
        },
    )

    # Simula sequenza post-inserimento (per check fattibilità).
    sim_post = (
        blocchi_esistenti[:pos_inserimento]
        + [nuovo]
        + blocchi_esistenti[pos_inserimento:]
    )
    label = f"G{payload.giornata_target} V{payload.variant_index_target}"
    violazioni = _check_fattibilita_variante(sim_post, variante_target.id, label)
    has_errors = any(v.severity == "error" for v in violazioni)

    if payload.dry_run or (has_errors and not payload.force):
        return AggiungiVuotoResponse(
            applied=False,
            blocco_id=None,
            nuovo_seq=None,
            violazioni=violazioni,
        )

    # Applica: INSERT + re-numera seq.
    session.add(nuovo)
    await session.flush()  # ottiene nuovo.id

    # Re-numera con pattern offset negativo (Fausto fix entry 234).
    for idx, b in enumerate(sim_post, start=1):
        b.seq = -idx
    await session.flush()
    for idx, b in enumerate(sim_post, start=1):
        b.seq = idx
    await session.commit()
    await session.refresh(nuovo)

    return AggiungiVuotoResponse(
        applied=True,
        blocco_id=nuovo.id,
        nuovo_seq=nuovo.seq,
        violazioni=violazioni,
    )


# =====================================================================
# Sprint 8.0 MR-B.2 (entry 232): elimina blocco vuoto manuale
# =====================================================================
# Decisione utente entry 230: "io posso decidere di eliminare un vuoto
# perchè può dormire a milano centrale". Solo vuoti (`materiale_vuoto`)
# possono essere eliminati: i blocchi commerciali rappresentano corse
# del PdE e non sono cancellabili da UI (richiederebbe annullamento
# corsa). Re-numerazione seq + check fattibilità riuso del MR-B.1.


class EliminaBloccoResponse(BaseModel):
    """Esito dell'eliminazione di un blocco vuoto."""

    applied: bool
    blocco_id: int
    violazioni: list[ViolazioneFattibilita]


@giri_dettaglio_router.delete(
    "/{giro_id}/blocchi/{blocco_id}",
    response_model=EliminaBloccoResponse,
    summary=(
        "Sprint 8.0 MR-B.2 (entry 232): elimina un blocco vuoto del "
        "giro. Solo blocchi `materiale_vuoto` sono ammessi; i "
        "commerciali sono protetti."
    ),
)
async def elimina_blocco(
    giro_id: int,
    blocco_id: int,
    dry_run: bool = Query(
        False,
        description=(
            "Se true, calcola le violazioni post-eliminazione ma NON "
            "applica."
        ),
    ),
    force: bool = Query(
        False,
        description=(
            "Se true, applica anche se ci sono violazioni `severity=error`."
        ),
    ),
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> EliminaBloccoResponse:
    """Sprint 8.0 MR-B.2 (entry 232).

    Flusso:
    1. Lock pessimistico giro.
    2. Pipeline freeze check.
    3. Carica blocco + valida tipo `materiale_vuoto` (else 400).
    4. Simula sequenza variante senza il blocco.
    5. Check fattibilità: se errors e `not force` → no commit.
    6. Else: DELETE blocco + re-numera seq variante + commit.

    Errori:
    - 404 giro/blocco non trovato.
    - 400 blocco non eliminabile (tipo non vuoto).
    - 409 pipeline freezata.
    """
    giro = (
        await session.execute(
            select(GiroMateriale)
            .where(
                GiroMateriale.id == giro_id,
                GiroMateriale.azienda_id == user.azienda_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if giro is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="giro non trovato",
        )

    stato_pipeline = (
        await session.execute(
            select(ProgrammaMateriale.stato_pipeline_pdc).where(
                ProgrammaMateriale.id == giro.programma_id
            )
        )
    ).scalar_one_or_none()
    if stato_pipeline is not None and materiale_freezato(stato_pipeline):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"programma freezato (pipeline {stato_pipeline!r}): "
                "blocco read-only."
            ),
        )

    blocco = (
        await session.execute(
            select(GiroBlocco)
            .join(GiroVariante, GiroVariante.id == GiroBlocco.giro_variante_id)
            .join(GiroGiornata, GiroGiornata.id == GiroVariante.giro_giornata_id)
            .where(
                GiroBlocco.id == blocco_id,
                GiroGiornata.giro_materiale_id == giro_id,
            )
        )
    ).scalar_one_or_none()
    if blocco is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="blocco non trovato per questo giro",
        )

    # Solo i vuoti sono eliminabili da UI (decisione utente entry 232).
    # I blocchi commerciali rappresentano corse del PdE: non sono
    # cancellabili senza un'annullamento dichiarato della corsa.
    if blocco.tipo_blocco != "materiale_vuoto":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"blocco di tipo {blocco.tipo_blocco!r} non eliminabile: "
                "solo `materiale_vuoto` è ammesso."
            ),
        )

    # Sprint 8.0 MR-B.4 entry 233 (Fausto review #1 HIGH): pre-check
    # FK `turno_pdc_blocco.giro_blocco_id` (ondelete RESTRICT). Senza
    # questo pre-check il `session.delete()` esploderebbe con
    # `IntegrityError` (500) — restituiamo invece un 409 chiaro che
    # l'utente può capire (servono PdC rigenerati prima).
    from colazione.models.turni_pdc import TurnoPdcBlocco

    n_pdc_dipendenti = int(
        (
            await session.execute(
                select(func.count(TurnoPdcBlocco.id)).where(
                    TurnoPdcBlocco.giro_blocco_id == blocco.id
                )
            )
        ).scalar_one()
    )
    if n_pdc_dipendenti > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "pdc_dipendenti",
                "message": (
                    f"{n_pdc_dipendenti} blocchi PdC dipendono da "
                    "questo blocco vuoto. Rigenera o elimina prima i "
                    "turni PdC, poi riprova."
                ),
                "n_pdc_dipendenti": n_pdc_dipendenti,
            },
        )

    # Carica blocchi della variante e simula post-eliminazione.
    variante_id = blocco.giro_variante_id
    variante_blocchi = list(
        (
            await session.execute(
                select(GiroBlocco)
                .where(GiroBlocco.giro_variante_id == variante_id)
                .order_by(GiroBlocco.seq)
            )
        )
        .scalars()
        .all()
    )
    sim_post = [b for b in variante_blocchi if b.id != blocco.id]

    # Lookup label variante (giornata + variant_index).
    variante_info = (
        await session.execute(
            select(GiroVariante.variant_index, GiroGiornata.numero_giornata)
            .join(GiroGiornata, GiroGiornata.id == GiroVariante.giro_giornata_id)
            .where(GiroVariante.id == variante_id)
        )
    ).first()
    variante_label = (
        f"G{variante_info[1]} V{variante_info[0]}"
        if variante_info is not None
        else f"variante {variante_id}"
    )

    violazioni = _check_fattibilita_variante(sim_post, variante_id, variante_label)
    has_errors = any(v.severity == "error" for v in violazioni)

    if dry_run or (has_errors and not force):
        return EliminaBloccoResponse(
            applied=False,
            blocco_id=blocco.id,
            violazioni=violazioni,
        )

    # Applica: cancella blocco + re-numera seq.
    blocco_id_to_delete = blocco.id
    await session.delete(blocco)
    await session.flush()
    for idx, b in enumerate(sim_post, start=1):
        if b.seq != idx:
            b.seq = idx
    await session.commit()

    return EliminaBloccoResponse(
        applied=True,
        blocco_id=blocco_id_to_delete,
        violazioni=violazioni,
    )


@giri_dettaglio_router.post(
    "/{giro_id}/duplica",
    response_model=DuplicaGiroResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Duplica un giro materiale (MR η-bis: per doppia macchina)",
)
async def duplica_giro(
    giro_id: int,
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> DuplicaGiroResponse:
    """MR η-bis — clona un GiroMateriale completo (header + giornate +
    varianti + blocchi) per scenari di "doppia macchina".

    Il nuovo giro ottiene un suffisso ``-DUP-{N}`` sul ``numero_turno``
    (N progressivo se esiste già un duplicato). Tutti i campi
    ``materiale_tipo_codice``, ``localita_manutenzione_*``, ``programma_id``
    sono ereditati. Le FK alle ``corsa_commerciale``/``corsa_materiale_vuoto``
    sono mantenute (= il duplicato copre le stesse corse).
    """
    g_stmt = select(GiroMateriale).where(
        GiroMateriale.id == giro_id,
        GiroMateriale.azienda_id == user.azienda_id,
    )
    src = (await session.execute(g_stmt)).scalar_one_or_none()
    if src is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Giro non trovato")

    # Pipeline freeze.
    prog_stmt = select(ProgrammaMateriale.stato_pipeline_pdc).where(
        ProgrammaMateriale.id == src.programma_id
    )
    stato_pipeline = (await session.execute(prog_stmt)).scalar_one_or_none()
    if stato_pipeline is not None and materiale_freezato(stato_pipeline):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"programma freezato (pipeline {stato_pipeline!r}): "
                "duplicazione non ammessa."
            ),
        )

    # Calcola il nuovo numero_turno con suffisso progressivo.
    base_num = src.numero_turno
    # Se è già un duplicato, prendi la radice.
    import re

    m = re.match(r"^(.*?)-DUP-(\d+)$", base_num)
    radice = m.group(1) if m else base_num
    # Trova il prossimo N libero scansionando i giri esistenti del programma.
    existing_stmt = select(GiroMateriale.numero_turno).where(
        GiroMateriale.programma_id == src.programma_id,
        GiroMateriale.numero_turno.like(f"{radice}-DUP-%"),
    )
    existing = list((await session.execute(existing_stmt)).scalars().all())
    used_n = set()
    for nt in existing:
        m2 = re.match(rf"^{re.escape(radice)}-DUP-(\d+)$", nt)
        if m2:
            used_n.add(int(m2.group(1)))
    n_dup = 1
    while n_dup in used_n:
        n_dup += 1
    new_numero_turno = f"{radice}-DUP-{n_dup}"

    # 1. clone GiroMateriale.
    new_giro = GiroMateriale(
        azienda_id=src.azienda_id,
        programma_id=src.programma_id,
        numero_turno=new_numero_turno,
        validita_codice=src.validita_codice,
        tipo_materiale=src.tipo_materiale,
        descrizione_materiale=src.descrizione_materiale,
        materiale_tipo_codice=src.materiale_tipo_codice,
        numero_giornate=src.numero_giornate,
        km_media_giornaliera=src.km_media_giornaliera,
        km_media_annua=src.km_media_annua,
        posti_1cl=src.posti_1cl,
        posti_2cl=src.posti_2cl,
        localita_manutenzione_partenza_id=src.localita_manutenzione_partenza_id,
        localita_manutenzione_arrivo_id=src.localita_manutenzione_arrivo_id,
        stato="bozza",
        generation_metadata_json={
            **(src.generation_metadata_json or {}),
            "duplicato_da_giro_id": src.id,
            "duplicato_n": n_dup,
        },
    )
    session.add(new_giro)
    await session.flush()  # popola new_giro.id

    # 2. clone giornate (mantenendo `numero_giornata`).
    gg_src_stmt = (
        select(GiroGiornata)
        .where(GiroGiornata.giro_materiale_id == src.id)
        .order_by(GiroGiornata.numero_giornata)
    )
    giornate_src = list((await session.execute(gg_src_stmt)).scalars().all())
    map_giornata: dict[int, int] = {}
    for gg_src in giornate_src:
        gg_new = GiroGiornata(
            giro_materiale_id=new_giro.id,
            numero_giornata=gg_src.numero_giornata,
            km_giornata=gg_src.km_giornata,
        )
        session.add(gg_new)
        await session.flush()
        map_giornata[gg_src.id] = gg_new.id

    # 3. clone varianti.
    if giornate_src:
        gv_src_stmt = (
            select(GiroVariante)
            .where(GiroVariante.giro_giornata_id.in_([g.id for g in giornate_src]))
            .order_by(GiroVariante.giro_giornata_id, GiroVariante.variant_index)
        )
        varianti_src = list((await session.execute(gv_src_stmt)).scalars().all())
    else:
        varianti_src = []
    map_variante: dict[int, int] = {}
    for gv_src in varianti_src:
        gv_new = GiroVariante(
            giro_giornata_id=map_giornata[gv_src.giro_giornata_id],
            variant_index=gv_src.variant_index,
            validita_testo=gv_src.validita_testo,
            dates_apply_json=list(gv_src.dates_apply_json or []),
            dates_skip_json=list(gv_src.dates_skip_json or []),
        )
        session.add(gv_new)
        await session.flush()
        map_variante[gv_src.id] = gv_new.id

    # 4. clone blocchi.
    n_blocchi_clonati = 0
    if varianti_src:
        gb_src_stmt = (
            select(GiroBlocco)
            .where(GiroBlocco.giro_variante_id.in_([v.id for v in varianti_src]))
            .order_by(GiroBlocco.giro_variante_id, GiroBlocco.seq)
        )
        for gb_src in (await session.execute(gb_src_stmt)).scalars():
            gb_new = GiroBlocco(
                giro_variante_id=map_variante[gb_src.giro_variante_id],
                seq=gb_src.seq,
                tipo_blocco=gb_src.tipo_blocco,
                corsa_commerciale_id=gb_src.corsa_commerciale_id,
                corsa_materiale_vuoto_id=gb_src.corsa_materiale_vuoto_id,
                stazione_da_codice=gb_src.stazione_da_codice,
                stazione_a_codice=gb_src.stazione_a_codice,
                ora_inizio=gb_src.ora_inizio,
                ora_fine=gb_src.ora_fine,
                descrizione=gb_src.descrizione,
                is_validato_utente=gb_src.is_validato_utente,
                metadata_json=dict(gb_src.metadata_json or {}),
            )
            session.add(gb_new)
            n_blocchi_clonati += 1

    await session.commit()
    await session.refresh(new_giro)

    return DuplicaGiroResponse(
        nuovo_giro_id=new_giro.id,
        nuovo_numero_turno=new_giro.numero_turno,
        n_giornate_copiate=len(giornate_src),
        n_varianti_copiate=len(varianti_src),
        n_blocchi_copiati=n_blocchi_clonati,
    )


@giri_dettaglio_router.get(
    "/{giro_id}",
    response_model=GiroMaterialeDettaglioRead,
    summary="Dettaglio giro materiale (per visualizzatore Gantt)",
)
async def get_giro_dettaglio(
    giro_id: int,
    user: CurrentUser = _authz_read,
    session: AsyncSession = Depends(get_session),
) -> GiroMaterialeDettaglioRead:
    """Ritorna giro + giornate + varianti + blocchi (sequenza
    cronologica). Usato dal frontend per renderizzare la timeline Gantt.
    """
    stmt = select(GiroMateriale).where(
        GiroMateriale.id == giro_id,
        GiroMateriale.azienda_id == user.azienda_id,
    )
    g = (await session.execute(stmt)).scalar_one_or_none()
    if g is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Giro non trovato")

    # Giornate ordinate per numero
    gg_stmt = (
        select(GiroGiornata)
        .where(GiroGiornata.giro_materiale_id == giro_id)
        .order_by(GiroGiornata.numero_giornata)
    )
    giornate_orm = (await session.execute(gg_stmt)).scalars().all()
    giornata_ids = [gg.id for gg in giornate_orm]

    # Sprint 7.7 MR 5: schema giro→giornate→varianti→blocchi.
    # Step 1: carica le varianti di tutte le giornate.
    varianti_orm: list[GiroVariante] = []
    if giornata_ids:
        gv_stmt = (
            select(GiroVariante)
            .where(GiroVariante.giro_giornata_id.in_(giornata_ids))
            .order_by(GiroVariante.giro_giornata_id, GiroVariante.variant_index)
        )
        varianti_orm = list((await session.execute(gv_stmt)).scalars().all())
    variante_ids = [gv.id for gv in varianti_orm]

    # Step 2: carica i blocchi di tutte le varianti.
    blocchi_orm: list[GiroBlocco] = []
    if variante_ids:
        gb_stmt = (
            select(GiroBlocco)
            .where(GiroBlocco.giro_variante_id.in_(variante_ids))
            .order_by(GiroBlocco.giro_variante_id, GiroBlocco.seq)
        )
        blocchi_orm = list((await session.execute(gb_stmt)).scalars().all())

    # Lookup batch: nome stazione + numero treno (commerciale e vuoto)
    codici_stazione = {
        c
        for b in blocchi_orm
        for c in (b.stazione_da_codice, b.stazione_a_codice)
        if c is not None
    }
    nome_stazione: dict[str, str] = {}
    if codici_stazione:
        st_stmt = select(Stazione.codice, Stazione.nome).where(
            Stazione.codice.in_(codici_stazione),
            Stazione.azienda_id == user.azienda_id,
        )
        nome_stazione = dict((await session.execute(st_stmt)).tuples().all())

    corsa_ids = {b.corsa_commerciale_id for b in blocchi_orm if b.corsa_commerciale_id is not None}
    numero_treno_corsa: dict[int, str] = {}
    if corsa_ids:
        cc_stmt = select(CorsaCommerciale.id, CorsaCommerciale.numero_treno).where(
            CorsaCommerciale.id.in_(corsa_ids)
        )
        numero_treno_corsa = dict((await session.execute(cc_stmt)).tuples().all())

    vuoto_ids = {
        b.corsa_materiale_vuoto_id for b in blocchi_orm if b.corsa_materiale_vuoto_id is not None
    }
    numero_treno_vuoto: dict[int, str] = {}
    if vuoto_ids:
        cv_stmt = select(
            CorsaMaterialeVuoto.id, CorsaMaterialeVuoto.numero_treno_vuoto
        ).where(CorsaMaterialeVuoto.id.in_(vuoto_ids))
        numero_treno_vuoto = dict((await session.execute(cv_stmt)).tuples().all())

    def _to_blocco_read(b: GiroBlocco) -> GiroBloccoRead:
        num: str | None = None
        if b.corsa_commerciale_id is not None:
            num = numero_treno_corsa.get(b.corsa_commerciale_id)
        elif b.corsa_materiale_vuoto_id is not None:
            num = numero_treno_vuoto.get(b.corsa_materiale_vuoto_id)
        return GiroBloccoRead(
            id=b.id,
            seq=b.seq,
            tipo_blocco=b.tipo_blocco,
            corsa_commerciale_id=b.corsa_commerciale_id,
            corsa_materiale_vuoto_id=b.corsa_materiale_vuoto_id,
            stazione_da_codice=b.stazione_da_codice,
            stazione_a_codice=b.stazione_a_codice,
            stazione_da_nome=(
                nome_stazione.get(b.stazione_da_codice) if b.stazione_da_codice else None
            ),
            stazione_a_nome=(
                nome_stazione.get(b.stazione_a_codice) if b.stazione_a_codice else None
            ),
            numero_treno=num,
            ora_inizio=b.ora_inizio,
            ora_fine=b.ora_fine,
            descrizione=b.descrizione,
            is_validato_utente=b.is_validato_utente,
            metadata_json=dict(b.metadata_json or {}),
        )

    # Sprint 8.0 entry 205 (MR-1110 sotto-MR 6): etichetta calendariale
    # parlante stile PDF Trenord, calcolata server-side via
    # ``genera_etichetta_parlante`` (entry 202, MR-1110 sotto-MR 4).
    # Sostituisce ``calcola_etichetta_variante`` v1 ("Lavorativo+Festivo
    # (3 date)") con stringhe v2 tipo "LV 1:5", "F escluso FpF",
    # "Si eff. 22/3, 12/4". L'etichetta non è persistita nel DB
    # (decisione architetturale: sempre ricalcolata al request così le
    # nuove festività ufficiali importate diventano visibili senza
    # rigenerare i giri).
    #
    # Carica le festività rilevanti con UNA sola query batch sul
    # calendario aziendale (FestivitaUfficiale azienda + nazionali).
    # Range esteso di +1 giorno rispetto a max_date per riconoscere il
    # prefestivo dell'ultima data del giro (es. variante con ultima
    # data 24/4/2026 = vigilia di Liberazione 25/4).
    festivita: frozenset[date] = frozenset()
    periodo_giro: tuple[date, date] | None = None
    if varianti_orm:
        date_tutte: list[date] = []
        for gv in varianti_orm:
            for d_str in gv.dates_apply_json or []:
                if isinstance(d_str, str):
                    date_tutte.append(date.fromisoformat(d_str))
        if date_tutte:
            min_date = min(date_tutte)
            max_date = max(date_tutte)
            max_date_plus1 = date.fromordinal(max_date.toordinal() + 1)
            festivita = await carica_festivita_periodo(
                session, user.azienda_id, min_date, max_date_plus1
            )
            # Sprint 8.0 entry 205: il periodo per ``genera_etichetta_parlante``
            # è il range coperto dalle varianti del giro. La funzione lo
            # usa per partizionare in 4 categorie (lv_1_5/lv_6/sabato_festivo/
            # festivo) e calcolare esclusioni vs. pattern esatto.
            periodo_giro = (min_date, max_date)

    # Sprint 7.7 MR 5: blocchi raggruppati per variante.
    blocchi_per_variante: dict[int, list[GiroBloccoRead]] = {}
    for b in blocchi_orm:
        blocchi_per_variante.setdefault(b.giro_variante_id, []).append(_to_blocco_read(b))

    # Sprint 7.9 MR 9A (decisione utente 2026-05-03 entry 108):
    # rimossa l'aggregazione varianti per categoria_primaria
    # (precedentemente Sprint 7.8 MR 6). Il modello PDF Trenord turno
    # 1134 mostra varianti DISAGGREGATE — ogni cluster A1 con la sua
    # etichetta specifica (`Si eff. 26/2, 2-3-4/3`,
    # `LV 1:5 esclusi 2-3-4-5/3`, `Effettuato 6F`). L'aggregazione
    # MR 6 fondeva cluster con stessa categoria primaria producendo
    # etichette generiche (`Lavorativo+Festivo (15 date)`) che
    # nascondevano i veri pattern di servizio.
    #
    # L'aggregazione A2 a livello persistenza (Sprint 7.8 MR 2.5,
    # chiave = (materiale, sede)) garantisce già la disgiunzione
    # delle date e produce un numero ragionevole di varianti per
    # giornata = numero di cluster A1 distinti = numero di pattern
    # di servizio distinti nel PdE per quella giornata-K. Se A2
    # producesse troppe varianti, è bug di clustering A1 da
    # investigare separatamente, non da nascondere a livello UI.
    #
    # Ogni variante ORM post-A2 = 1 GiroVarianteRead. La propagazione
    # cross-giornata (MR 8A) usa `cluster_a1_ids` = [variant_index]
    # (lista singola), con identità invece di intersezione.
    varianti_per_giornata: dict[int, list[GiroVarianteRead]] = {}
    for gv in varianti_orm:
        dates_var: list[date] = []
        for d_str in gv.dates_apply_json or []:
            if isinstance(d_str, str):
                dates_var.append(date.fromisoformat(d_str))
        # Sprint 8.0 entry 205 (MR-1110 sotto-MR 6): etichetta v2 stile
        # PDF Trenord. Se il giro non ha date (variante vuota), fallback
        # alla stringa documentata della funzione.
        if periodo_giro is not None and dates_var:
            etichetta = genera_etichetta_parlante(
                frozenset(dates_var), periodo_giro, festivita
            )
        else:
            etichetta = "(nessuna data)"
        varianti_per_giornata.setdefault(gv.giro_giornata_id, []).append(
            GiroVarianteRead(
                id=gv.id,
                variant_index=gv.variant_index,
                validita_testo=gv.validita_testo,
                dates_apply_json=[d.isoformat() for d in sorted(dates_var)],
                dates_skip_json=list(gv.dates_skip_json or []),
                etichetta_parlante=etichetta,
                blocchi=blocchi_per_variante.get(gv.id, []),
                cluster_a1_ids=[gv.variant_index],
            )
        )

    # Ordinamento deterministico per variant_index dentro la giornata.
    for gg_id in varianti_per_giornata:
        varianti_per_giornata[gg_id].sort(key=lambda v: v.variant_index)

    giornate_out = [
        GiroGiornataRead(
            id=gg.id,
            numero_giornata=gg.numero_giornata,
            km_giornata=float(gg.km_giornata) if gg.km_giornata is not None else None,
            varianti=varianti_per_giornata.get(gg.id, []),
        )
        for gg in giornate_orm
    ]

    return GiroMaterialeDettaglioRead(
        id=g.id,
        numero_turno=g.numero_turno,
        tipo_materiale=g.tipo_materiale,
        materiale_tipo_codice=g.materiale_tipo_codice,
        numero_giornate=g.numero_giornate,
        km_media_giornaliera=float(g.km_media_giornaliera) if g.km_media_giornaliera is not None else None,
        km_media_annua=float(g.km_media_annua) if g.km_media_annua is not None else None,
        localita_manutenzione_partenza_id=g.localita_manutenzione_partenza_id,
        localita_manutenzione_arrivo_id=g.localita_manutenzione_arrivo_id,
        stato=g.stato,
        generation_metadata_json=dict(g.generation_metadata_json or {}),
        created_at=g.created_at,
        updated_at=g.updated_at,
        giornate=giornate_out,
    )


# =====================================================================
# Sprint 7.9 MR β2-4 — Thread materiale (L2)
# =====================================================================


class MaterialeThreadListItem(BaseModel):
    """Item lista thread di un giro per la UI."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    tipo_materiale_codice: str
    matricola_id: int | None
    km_totali: float
    minuti_servizio: int
    n_corse_commerciali: int


class MaterialeThreadEventoRead(BaseModel):
    """Evento singolo nella timeline di un thread."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    ordine: int
    tipo: str
    giro_blocco_id: int | None
    stazione_da_codice: str | None
    stazione_a_codice: str | None
    ora_inizio: time | None
    ora_fine: time | None
    data_giorno: date | None
    km_tratta: float | None
    numero_treno: str | None
    note: str | None


class MaterialeThreadDettaglioRead(BaseModel):
    """Dettaglio completo del thread con timeline eventi."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    tipo_materiale_codice: str
    matricola_id: int | None
    giro_materiale_id_origine: int
    km_totali: float
    minuti_servizio: int
    n_corse_commerciali: int
    eventi: list[MaterialeThreadEventoRead]


@giri_dettaglio_router.get(
    "/{giro_id}/threads",
    response_model=list[MaterialeThreadListItem],
    summary="Lista thread materiale del giro (L2 logici)",
)
async def list_threads_giro(
    giro_id: int,
    user: CurrentUser = _authz_read,
    session: AsyncSession = Depends(get_session),
) -> list[MaterialeThreadListItem]:
    """Sprint 7.9 MR β2-4: lista dei thread logici del giro.

    Per ogni "pezzo logico" della composizione massima del giro c'è
    un thread con km_totali, minuti_servizio, n_corse_commerciali
    aggregati. La UI mostra "thread di questo turno" con link al
    dettaglio.
    """
    # Verifica esistenza giro per ritornare 404 prima dei thread.
    g = (
        await session.execute(
            select(GiroMateriale).where(
                GiroMateriale.id == giro_id,
                GiroMateriale.azienda_id == user.azienda_id,
            )
        )
    ).scalar_one_or_none()
    if g is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Giro {giro_id} non trovato.",
        )
    stmt = (
        select(MaterialeThread)
        .where(MaterialeThread.giro_materiale_id_origine == giro_id)
        .order_by(MaterialeThread.tipo_materiale_codice, MaterialeThread.id)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [MaterialeThreadListItem.model_validate(r) for r in rows]


@giri_dettaglio_router.get(
    "/threads/{thread_id}",
    response_model=MaterialeThreadDettaglioRead,
    summary="Dettaglio thread materiale + timeline eventi",
)
async def get_thread_dettaglio(
    thread_id: int,
    user: CurrentUser = _authz_read,
    session: AsyncSession = Depends(get_session),
) -> MaterialeThreadDettaglioRead:
    """Sprint 7.9 MR β2-4: thread + lista eventi cronologica."""
    # Carico il thread con check azienda
    stmt = select(MaterialeThread).where(
        MaterialeThread.id == thread_id,
        MaterialeThread.azienda_id == user.azienda_id,
    )
    thread = (await session.execute(stmt)).scalar_one_or_none()
    if thread is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Thread {thread_id} non trovato.",
        )
    eventi_stmt = (
        select(MaterialeThreadEvento)
        .where(MaterialeThreadEvento.thread_id == thread_id)
        .order_by(MaterialeThreadEvento.ordine)
    )
    eventi = (await session.execute(eventi_stmt)).scalars().all()
    return MaterialeThreadDettaglioRead(
        id=thread.id,
        tipo_materiale_codice=thread.tipo_materiale_codice,
        matricola_id=thread.matricola_id,
        giro_materiale_id_origine=thread.giro_materiale_id_origine,
        km_totali=float(thread.km_totali),
        minuti_servizio=thread.minuti_servizio,
        n_corse_commerciali=thread.n_corse_commerciali,
        eventi=[MaterialeThreadEventoRead.model_validate(e) for e in eventi],
    )
