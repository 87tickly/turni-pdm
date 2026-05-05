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

from datetime import date, datetime, time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.auth import require_any_role, require_role
from colazione.db import get_session
from colazione.domain.builder_giro.builder import (
    BuilderResult,
    GiriEsistentiError,
    PdcDipendentiError,
    PeriodoFuoriProgrammaError,
    ProgrammaNonAttivoError,
    ProgrammaNonTrovatoError,
    StrictModeViolation,
    carica_festivita_periodo,
    genera_giri,
)
from colazione.domain.builder_giro.etichetta import calcola_etichetta_variante
from colazione.domain.builder_giro.persister import LocalitaNonTrovataError
from colazione.domain.builder_giro.risolvi_corsa import (
    ComposizioneNonAmmessaError,
    RegolaAmbiguaError,
)
from colazione.domain.pipeline import (
    programma_visibile_per_ruoli,
    soglia_pipeline_per_ruoli,
    stati_pdc_da,
)
from colazione.models.anagrafica import (
    MaterialeThread,
    MaterialeThreadEvento,
    Stazione,
)
from colazione.models.corse import CorsaCommerciale, CorsaMaterialeVuoto
from colazione.models.giri import GiroBlocco, GiroGiornata, GiroMateriale, GiroVariante
from colazione.models.programmi import ProgrammaMateriale
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
    """
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

    # Sprint 7.7 MR 6: etichetta categorica calcolata server-side via
    # ``calcola_etichetta_variante``. Carica le festività rilevanti
    # con UNA sola query batch sul calendario aziendale (FestivitaUfficiale
    # azienda + nazionali). Range esteso di +1 giorno rispetto a max_date
    # per riconoscere il prefestivo dell'ultima data del giro
    # (es. variante con ultima data 24/4/2026 = vigilia di Liberazione 25/4).
    festivita: frozenset[date] = frozenset()
    if varianti_orm:
        date_tutte: list[date] = []
        for gv in varianti_orm:
            for d_str in gv.dates_apply_json or []:
                if isinstance(d_str, str):
                    date_tutte.append(date.fromisoformat(d_str))
        if date_tutte:
            min_date = min(date_tutte)
            max_date_plus1 = date.fromordinal(max(date_tutte).toordinal() + 1)
            festivita = await carica_festivita_periodo(
                session, user.azienda_id, min_date, max_date_plus1
            )

    # Sprint 7.8 MR 3: per generare etichette stile Trenord
    # (`Lv` / `F` / `P escl. 3/3, 4/3` / `Si eff. 3/3, 4/3, 5/3`),
    # `calcola_etichetta_variante` ha bisogno del periodo per categoria
    # della GIORNATA-PATTERN. Costruiamo un dizionario per giornata-K
    # raccogliendo `dates_apply` di tutte le sue varianti, raggruppate
    # per ``tipo_giorno_categoria``. Le varianti della stessa giornata
    # hanno date disgiunte per costruzione del clustering A1+A2.
    from colazione.domain.calendario import tipo_giorno_categoria

    periodo_per_giornata: dict[int, dict[str, frozenset[date]]] = {}
    for gv in varianti_orm:
        dates_v: set[date] = set()
        for d_str in gv.dates_apply_json or []:
            if isinstance(d_str, str):
                dates_v.add(date.fromisoformat(d_str))
        periodo_per_giornata.setdefault(gv.giro_giornata_id, {})
        for d in dates_v:
            cat = tipo_giorno_categoria(d, festivita)
            cat_set = set(periodo_per_giornata[gv.giro_giornata_id].get(cat, frozenset()))
            cat_set.add(d)
            periodo_per_giornata[gv.giro_giornata_id][cat] = frozenset(cat_set)

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
        etichetta = calcola_etichetta_variante(
            dates_var, festivita, periodo_per_giornata.get(gv.giro_giornata_id)
        )
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
