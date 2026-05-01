"""Route HTTP turni PdC — Sprint 7.2.

Endpoint:

- ``POST /api/giri/{giro_id}/genera-turno-pdc`` — genera 1 turno PdC
  derivato dal giro materiale (builder MVP).
- ``GET /api/giri/{giro_id}/turni-pdc`` — lista turni PdC associati al
  giro (lookup via `generation_metadata_json->>'giro_materiale_id'`).
- ``GET /api/turni-pdc/{turno_id}`` — dettaglio turno PdC (giornate +
  blocchi ordinati) per visualizzatore Gantt.

Auth: ruolo ``PIANIFICATORE_PDC`` (admin bypassa). Multi-tenant:
``azienda_id`` dal JWT.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.auth import require_any_role, require_role
from colazione.db import get_session
from colazione.domain.builder_pdc.builder import (
    BuilderTurnoPdcResult,
    GiriEsistentiError,
    GiroNonTrovatoError,
    GiroVuotoError,
    genera_turno_pdc,
)
from colazione.models.anagrafica import Stazione
from colazione.models.corse import CorsaCommerciale, CorsaMaterialeVuoto
from colazione.models.turni_pdc import TurnoPdc, TurnoPdcBlocco, TurnoPdcGiornata
from colazione.schemas.security import CurrentUser

router = APIRouter(prefix="/api/giri", tags=["turni-pdc"])
turni_pdc_router = APIRouter(prefix="/api/turni-pdc", tags=["turni-pdc"])

_authz = Depends(require_role("PIANIFICATORE_GIRO"))
# Sprint 7.3 MR 2: lettura cross-giro ammessa anche al PIANIFICATORE_PDC
# (vedi RUOLI-E-DASHBOARD §4.3). La generazione/scrittura turni resta
# scope MR 3 — per ora gli endpoint write usano `_authz` (Giro).
_authz_read = Depends(require_any_role("PIANIFICATORE_GIRO", "PIANIFICATORE_PDC"))


# =====================================================================
# Schemi response
# =====================================================================


class TurnoPdcGenerazioneResponse(BaseModel):
    turno_pdc_id: int
    codice: str
    n_giornate: int
    prestazione_totale_min: int
    condotta_totale_min: int
    violazioni: list[str]
    warnings: list[str]
    # Sprint 7.4 MR 3: campi split CV intermedio. `is_ramo_split=True`
    # quando il TurnoPdc è il ramo di una giornata-giro splittata in
    # più rami; `split_origine_giornata` è il numero della giornata-
    # giro originale, `split_ramo` è 1-based, `split_totale_rami`
    # quanti rami in totale per quella giornata.
    is_ramo_split: bool = False
    split_origine_giornata: int | None = None
    split_ramo: int | None = None
    split_totale_rami: int | None = None


class TurnoPdcListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codice: str
    impianto: str
    profilo: str
    ciclo_giorni: int
    valido_da: date
    stato: str
    created_at: datetime
    n_giornate: int
    prestazione_totale_min: int
    condotta_totale_min: int
    n_violazioni: int
    n_dormite_fr: int
    # Sprint 7.4 MR 3: stessi campi split di TurnoPdcGenerazioneResponse,
    # popolati a partire da `generation_metadata_json` per la lista turni.
    is_ramo_split: bool = False
    split_origine_giornata: int | None = None
    split_ramo: int | None = None
    split_totale_rami: int | None = None


class TurnoPdcBloccoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    seq: int
    tipo_evento: str
    corsa_commerciale_id: int | None
    corsa_materiale_vuoto_id: int | None
    giro_blocco_id: int | None
    stazione_da_codice: str | None
    stazione_a_codice: str | None
    stazione_da_nome: str | None
    stazione_a_nome: str | None
    numero_treno: str | None
    numero_treno_variante_indice: int | None
    numero_treno_variante_totale: int | None
    ora_inizio: time | None
    ora_fine: time | None
    durata_min: int | None
    is_accessori_maggiorati: bool
    accessori_note: str | None
    fonte_orario: str


class TurnoPdcGiornataRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    numero_giornata: int
    variante_calendario: str
    stazione_inizio: str | None
    stazione_fine: str | None
    stazione_inizio_nome: str | None
    stazione_fine_nome: str | None
    inizio_prestazione: time | None
    fine_prestazione: time | None
    prestazione_min: int
    condotta_min: int
    refezione_min: int
    is_notturno: bool
    blocchi: list[TurnoPdcBloccoRead]


class TurnoPdcDettaglioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codice: str
    impianto: str
    profilo: str
    ciclo_giorni: int
    valido_da: date
    stato: str
    created_at: datetime
    updated_at: datetime
    generation_metadata_json: dict[str, Any]
    giornate: list[TurnoPdcGiornataRead]


# =====================================================================
# POST /api/giri/{giro_id}/genera-turno-pdc
# =====================================================================


@router.post(
    "/{giro_id}/genera-turno-pdc",
    response_model=list[TurnoPdcGenerazioneResponse],
    summary="Genera turni PdC dal giro materiale (1 per variante calendario)",
)
async def genera_turno_pdc_endpoint(
    giro_id: int,
    valido_da: date | None = Query(default=None, description="Data validità turno (default: oggi)"),
    force: bool = Query(default=False, description="Sovrascrive turni precedenti"),
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> list[TurnoPdcGenerazioneResponse]:
    """Sprint 7.5 MR 5 (decisione utente D1): ritorna **lista** di turni
    PdC, uno per ogni combinazione di varianti calendario delle giornate
    del giro. Con A1 strict (default oggi) la lista contiene 1 elemento;
    con varianti multiple aggiunte manualmente la lista cresce.
    """
    try:
        results: list[BuilderTurnoPdcResult] = await genera_turno_pdc(
            session=session,
            azienda_id=user.azienda_id,
            giro_id=giro_id,
            valido_da=valido_da,
            force=force,
        )
    except GiroNonTrovatoError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except GiroVuotoError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e
    except GiriEsistentiError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e

    return [
        TurnoPdcGenerazioneResponse(
            turno_pdc_id=r.turno_pdc_id,
            codice=r.codice,
            n_giornate=r.n_giornate,
            prestazione_totale_min=r.prestazione_totale_min,
            condotta_totale_min=r.condotta_totale_min,
            violazioni=r.violazioni,
            warnings=r.warnings,
            is_ramo_split=r.is_ramo_split,
            split_origine_giornata=r.split_origine_giornata,
            split_ramo=r.split_ramo,
            split_totale_rami=r.split_totale_rami,
        )
        for r in results
    ]


# =====================================================================
# GET /api/giri/{giro_id}/turni-pdc
# =====================================================================


@router.get(
    "/{giro_id}/turni-pdc",
    response_model=list[TurnoPdcListItem],
    summary="Lista turni PdC associati al giro",
)
async def list_turni_pdc_giro(
    giro_id: int,
    user: CurrentUser = _authz_read,
    session: AsyncSession = Depends(get_session),
) -> list[TurnoPdcListItem]:
    stmt = (
        select(TurnoPdc)
        .where(
            TurnoPdc.azienda_id == user.azienda_id,
            cast(
                TurnoPdc.generation_metadata_json["giro_materiale_id"].astext,
                BigInteger,
            )
            == giro_id,
        )
        .order_by(TurnoPdc.codice)
    )
    turni = list((await session.execute(stmt)).scalars())
    if not turni:
        return []

    turno_ids = [t.id for t in turni]
    giornate = list(
        (
            await session.execute(
                select(TurnoPdcGiornata).where(TurnoPdcGiornata.turno_pdc_id.in_(turno_ids))
            )
        ).scalars()
    )
    giornate_per_turno: dict[int, list[TurnoPdcGiornata]] = {}
    for g in giornate:
        giornate_per_turno.setdefault(g.turno_pdc_id, []).append(g)

    out: list[TurnoPdcListItem] = []
    for t in turni:
        gg = giornate_per_turno.get(t.id, [])
        meta = t.generation_metadata_json or {}
        out.append(
            TurnoPdcListItem(
                id=t.id,
                codice=t.codice,
                impianto=t.impianto,
                profilo=t.profilo,
                ciclo_giorni=t.ciclo_giorni,
                valido_da=t.valido_da,
                stato=t.stato,
                created_at=t.created_at,
                n_giornate=len(gg),
                prestazione_totale_min=sum(g.prestazione_min for g in gg),
                condotta_totale_min=sum(g.condotta_min for g in gg),
                n_violazioni=len(meta.get("violazioni", []) or []),
                n_dormite_fr=len(meta.get("fr_giornate", []) or []),
                is_ramo_split=bool(meta.get("is_ramo_split", False)),
                split_origine_giornata=meta.get("split_origine_giornata"),
                split_ramo=meta.get("split_ramo"),
                split_totale_rami=meta.get("split_totale_rami"),
            )
        )
    return out


# =====================================================================
# GET /api/turni-pdc — lista cross-giro per dashboard PIANIFICATORE_PDC
# =====================================================================


@turni_pdc_router.get(
    "",
    response_model=list[TurnoPdcListItem],
    summary="Lista turni PdC dell'azienda (cross-giro, con filtri)",
)
async def list_turni_pdc_azienda(
    impianto: str | None = Query(
        None, description="Filtra per impianto (deposito personale)."
    ),
    stato: str | None = Query(None, description="Filtra per stato (es. 'bozza')."),
    profilo: str | None = Query(None, description="Filtra per profilo (es. 'Condotta')."),
    valido_da_min: date | None = Query(
        None, description="Filtra turni con valido_da >= questa data."
    ),
    valido_da_max: date | None = Query(
        None, description="Filtra turni con valido_da <= questa data."
    ),
    q: str | None = Query(
        None,
        description="Ricerca testuale su codice (case-insensitive contiene).",
        min_length=1,
        max_length=50,
    ),
    limit: int = Query(100, ge=1, le=500, description="Max righe ritornate."),
    offset: int = Query(0, ge=0, description="Offset paginazione."),
    user: CurrentUser = _authz_read,
    session: AsyncSession = Depends(get_session),
) -> list[TurnoPdcListItem]:
    """Lista turni PdC dell'azienda, ordinata per ``codice``.

    Sprint 7.3 MR 2: alimenta la schermata 4.3
    `/pianificatore-pdc/turni`. La response usa lo stesso shape di
    `GET /api/giri/{id}/turni-pdc` (`TurnoPdcListItem`) per consentire
    il riuso dei componenti UI tabella.
    """
    stmt = select(TurnoPdc).where(TurnoPdc.azienda_id == user.azienda_id)
    if impianto is not None:
        stmt = stmt.where(TurnoPdc.impianto == impianto)
    if stato is not None:
        stmt = stmt.where(TurnoPdc.stato == stato)
    if profilo is not None:
        stmt = stmt.where(TurnoPdc.profilo == profilo)
    if valido_da_min is not None:
        stmt = stmt.where(TurnoPdc.valido_da >= valido_da_min)
    if valido_da_max is not None:
        stmt = stmt.where(TurnoPdc.valido_da <= valido_da_max)
    if q is not None:
        stmt = stmt.where(TurnoPdc.codice.ilike(f"%{q}%"))
    stmt = stmt.order_by(TurnoPdc.codice).limit(limit).offset(offset)
    turni = list((await session.execute(stmt)).scalars())
    if not turni:
        return []

    # Stessa strategia batch di `list_turni_pdc_giro`: una query per le
    # giornate di tutti i turni → mappa per turno_id → list items.
    turno_ids = [t.id for t in turni]
    giornate = list(
        (
            await session.execute(
                select(TurnoPdcGiornata).where(TurnoPdcGiornata.turno_pdc_id.in_(turno_ids))
            )
        ).scalars()
    )
    giornate_per_turno: dict[int, list[TurnoPdcGiornata]] = {}
    for g in giornate:
        giornate_per_turno.setdefault(g.turno_pdc_id, []).append(g)

    out: list[TurnoPdcListItem] = []
    for t in turni:
        gg = giornate_per_turno.get(t.id, [])
        meta = t.generation_metadata_json or {}
        out.append(
            TurnoPdcListItem(
                id=t.id,
                codice=t.codice,
                impianto=t.impianto,
                profilo=t.profilo,
                ciclo_giorni=t.ciclo_giorni,
                valido_da=t.valido_da,
                stato=t.stato,
                created_at=t.created_at,
                n_giornate=len(gg),
                prestazione_totale_min=sum(g.prestazione_min for g in gg),
                condotta_totale_min=sum(g.condotta_min for g in gg),
                n_violazioni=len(meta.get("violazioni", []) or []),
                n_dormite_fr=len(meta.get("fr_giornate", []) or []),
                is_ramo_split=bool(meta.get("is_ramo_split", False)),
                split_origine_giornata=meta.get("split_origine_giornata"),
                split_ramo=meta.get("split_ramo"),
                split_totale_rami=meta.get("split_totale_rami"),
            )
        )
    return out


# =====================================================================
# GET /api/turni-pdc/{turno_id}
# =====================================================================


@turni_pdc_router.get(
    "/{turno_id}",
    response_model=TurnoPdcDettaglioRead,
    summary="Dettaglio turno PdC per visualizzatore Gantt",
)
async def get_turno_pdc_dettaglio(
    turno_id: int,
    user: CurrentUser = _authz_read,
    session: AsyncSession = Depends(get_session),
) -> TurnoPdcDettaglioRead:
    turno = (
        await session.execute(
            select(TurnoPdc).where(
                TurnoPdc.id == turno_id,
                TurnoPdc.azienda_id == user.azienda_id,
            )
        )
    ).scalar_one_or_none()
    if turno is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Turno PdC non trovato"
        )

    giornate_orm = list(
        (
            await session.execute(
                select(TurnoPdcGiornata)
                .where(TurnoPdcGiornata.turno_pdc_id == turno_id)
                .order_by(TurnoPdcGiornata.numero_giornata)
            )
        ).scalars()
    )
    giornata_ids = [g.id for g in giornate_orm]

    blocchi_orm: list[TurnoPdcBlocco] = []
    if giornata_ids:
        blocchi_orm = list(
            (
                await session.execute(
                    select(TurnoPdcBlocco)
                    .where(TurnoPdcBlocco.turno_pdc_giornata_id.in_(giornata_ids))
                    .order_by(TurnoPdcBlocco.turno_pdc_giornata_id, TurnoPdcBlocco.seq)
                )
            ).scalars()
        )

    # Lookup batch nomi stazione + numero treno
    codici_stazione: set[str] = set()
    for b in blocchi_orm:
        for c in (b.stazione_da_codice, b.stazione_a_codice):
            if c is not None:
                codici_stazione.add(c)
    for g in giornate_orm:
        for c in (g.stazione_inizio, g.stazione_fine):
            if c is not None:
                codici_stazione.add(c)

    nome_stazione: dict[str, str] = {}
    if codici_stazione:
        nome_stazione = dict(
            (
                await session.execute(
                    select(Stazione.codice, Stazione.nome).where(
                        Stazione.codice.in_(codici_stazione),
                        Stazione.azienda_id == user.azienda_id,
                    )
                )
            )
            .tuples()
            .all()
        )

    corsa_ids = {b.corsa_commerciale_id for b in blocchi_orm if b.corsa_commerciale_id is not None}
    numero_treno_corsa: dict[int, str] = {}
    if corsa_ids:
        numero_treno_corsa = dict(
            (
                await session.execute(
                    select(CorsaCommerciale.id, CorsaCommerciale.numero_treno).where(
                        CorsaCommerciale.id.in_(corsa_ids)
                    )
                )
            )
            .tuples()
            .all()
        )

    # Sprint 7.3: trasparenza varianti numero_treno (vedi
    # `api/giri.py` per la stessa logica). Stessi `numero_treno`
    # → contiamo varianti totali per azienda + indice 1-based per
    # `valido_da` di ciascuna corsa.
    varianti_per_corsa: dict[int, tuple[int, int]] = {}
    if numero_treno_corsa:
        numeri_treno = set(numero_treno_corsa.values())
        cnt_subq = (
            select(
                CorsaCommerciale.numero_treno,
                func.count().label("totale"),
            )
            .where(
                CorsaCommerciale.azienda_id == user.azienda_id,
                CorsaCommerciale.numero_treno.in_(numeri_treno),
            )
            .group_by(CorsaCommerciale.numero_treno)
            .subquery()
        )
        var_stmt = (
            select(
                CorsaCommerciale.id,
                cnt_subq.c.totale,
                func.row_number()
                .over(
                    partition_by=CorsaCommerciale.numero_treno,
                    order_by=(CorsaCommerciale.valido_da, CorsaCommerciale.id),
                )
                .label("indice"),
            )
            .join(cnt_subq, cnt_subq.c.numero_treno == CorsaCommerciale.numero_treno)
            .where(
                CorsaCommerciale.azienda_id == user.azienda_id,
                CorsaCommerciale.numero_treno.in_(numeri_treno),
            )
        )
        for row in (await session.execute(var_stmt)).all():
            cid, tot, idx = row
            if cid in corsa_ids:
                varianti_per_corsa[cid] = (int(idx), int(tot))

    vuoto_ids = {
        b.corsa_materiale_vuoto_id for b in blocchi_orm if b.corsa_materiale_vuoto_id is not None
    }
    numero_treno_vuoto: dict[int, str] = {}
    if vuoto_ids:
        numero_treno_vuoto = dict(
            (
                await session.execute(
                    select(CorsaMaterialeVuoto.id, CorsaMaterialeVuoto.numero_treno_vuoto).where(
                        CorsaMaterialeVuoto.id.in_(vuoto_ids)
                    )
                )
            )
            .tuples()
            .all()
        )

    blocchi_per_giornata: dict[int, list[TurnoPdcBloccoRead]] = {}
    for b in blocchi_orm:
        num: str | None = None
        idx_var: int | None = None
        tot_var: int | None = None
        if b.corsa_commerciale_id is not None:
            num = numero_treno_corsa.get(b.corsa_commerciale_id)
            par = varianti_per_corsa.get(b.corsa_commerciale_id)
            if par is not None:
                idx_var, tot_var = par
        elif b.corsa_materiale_vuoto_id is not None:
            num = numero_treno_vuoto.get(b.corsa_materiale_vuoto_id)
        blocchi_per_giornata.setdefault(b.turno_pdc_giornata_id, []).append(
            TurnoPdcBloccoRead(
                id=b.id,
                seq=b.seq,
                tipo_evento=b.tipo_evento,
                corsa_commerciale_id=b.corsa_commerciale_id,
                corsa_materiale_vuoto_id=b.corsa_materiale_vuoto_id,
                giro_blocco_id=b.giro_blocco_id,
                stazione_da_codice=b.stazione_da_codice,
                stazione_a_codice=b.stazione_a_codice,
                stazione_da_nome=(
                    nome_stazione.get(b.stazione_da_codice) if b.stazione_da_codice else None
                ),
                stazione_a_nome=(
                    nome_stazione.get(b.stazione_a_codice) if b.stazione_a_codice else None
                ),
                numero_treno=num,
                numero_treno_variante_indice=idx_var,
                numero_treno_variante_totale=tot_var,
                ora_inizio=b.ora_inizio,
                ora_fine=b.ora_fine,
                durata_min=b.durata_min,
                is_accessori_maggiorati=b.is_accessori_maggiorati,
                accessori_note=b.accessori_note,
                fonte_orario=b.fonte_orario,
            )
        )

    giornate_out: list[TurnoPdcGiornataRead] = []
    for g in giornate_orm:
        giornate_out.append(
            TurnoPdcGiornataRead(
                id=g.id,
                numero_giornata=g.numero_giornata,
                variante_calendario=g.variante_calendario,
                stazione_inizio=g.stazione_inizio,
                stazione_fine=g.stazione_fine,
                stazione_inizio_nome=(
                    nome_stazione.get(g.stazione_inizio) if g.stazione_inizio else None
                ),
                stazione_fine_nome=(
                    nome_stazione.get(g.stazione_fine) if g.stazione_fine else None
                ),
                inizio_prestazione=g.inizio_prestazione,
                fine_prestazione=g.fine_prestazione,
                prestazione_min=g.prestazione_min,
                condotta_min=g.condotta_min,
                refezione_min=g.refezione_min,
                is_notturno=g.is_notturno,
                blocchi=blocchi_per_giornata.get(g.id, []),
            )
        )

    return TurnoPdcDettaglioRead(
        id=turno.id,
        codice=turno.codice,
        impianto=turno.impianto,
        profilo=turno.profilo,
        ciclo_giorni=turno.ciclo_giorni,
        valido_da=turno.valido_da,
        stato=turno.stato,
        created_at=turno.created_at,
        updated_at=turno.updated_at,
        generation_metadata_json=dict(turno.generation_metadata_json or {}),
        giornate=giornate_out,
    )
