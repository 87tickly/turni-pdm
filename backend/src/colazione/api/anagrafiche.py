"""Route HTTP read-side per anagrafiche (Sprint 5.6 R1).

Endpoint di sola lettura per popolare i menu/UI del frontend
Pianificatore Giro Materiale:

- ``GET /api/stazioni`` — lista stazioni PdE per filtri regola e visualizzatore
- ``GET /api/materiali`` — lista materiale_tipo per composizione regole
- ``GET /api/depots`` — 25 depot PdC + stazione_principale_codice (default
  sosta extra)
- ``GET /api/direttrici`` — distinct delle direttrici nel PdE
- ``GET /api/localita-manutenzione`` — sedi (codice, codice_breve, stazione_collegata)
- ``GET /api/calendario/{anno}`` — Sprint 7.7 MR 2: festività dell'azienda
  (nazionali + locali) per l'anno indicato + tag giorno per ogni data del
  periodo richiesto.

Multi-tenant: ``azienda_id`` dal JWT, niente input client.
Auth: ruolo ``PIANIFICATORE_GIRO`` (admin bypassa).
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import distinct, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.auth import require_role
from colazione.db import get_session
from colazione.domain.calendario import tipo_giorno
from colazione.models.anagrafica import (
    Depot,
    FestivitaUfficiale,
    LocalitaManutenzione,
    LocalitaSosta,
    MaterialeDotazioneAzienda,
    MaterialeTipo,
    Stazione,
)
from colazione.models.corse import CorsaCommerciale
from colazione.schemas.security import CurrentUser

router = APIRouter(prefix="/api", tags=["anagrafiche"])

_authz = Depends(require_role("PIANIFICATORE_GIRO"))


class StazioneRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    codice: str
    nome: str


class MaterialeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    codice: str
    nome_commerciale: str | None
    famiglia: str | None
    # Sprint 7.9 MR 7D: dotazione fisica per l'azienda corrente.
    # ``None`` = capacity illimitata (es. ETR524 FLIRT TILO) o non
    # registrata in `materiale_dotazione_azienda`.
    pezzi_disponibili: int | None = None


class DepotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    codice: str
    display_name: str
    stazione_principale_codice: str | None


class LocalitaManutenzioneRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    codice: str
    codice_breve: str | None
    nome_canonico: str
    stazione_collegata_codice: str | None
    is_pool_esterno: bool


class LocalitaSostaRead(BaseModel):
    """Sprint 7.9 MR β2-0: località di sosta intermedia (es. Milano
    San Rocco). Distinta da LocalitaManutenzione."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    codice: str
    nome: str
    stazione_collegata_codice: str | None
    is_attiva: bool
    note: str | None


class LocalitaSostaCreate(BaseModel):
    """Body per POST /api/localita-sosta (admin)."""

    codice: str
    nome: str
    stazione_collegata_codice: str | None = None
    note: str | None = None


@router.get("/stazioni", response_model=list[StazioneRead])
async def list_stazioni(
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> list[StazioneRead]:
    """Tutte le stazioni dell'azienda corrente, ordinate per nome.

    Usato dai menu a tendina del frontend (filtri regola, visualizzatore
    Gantt per labels stazioni).
    """
    stmt = (
        select(Stazione)
        .where(Stazione.azienda_id == user.azienda_id)
        .order_by(Stazione.nome)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [StazioneRead.model_validate(r) for r in rows]


@router.get("/materiali", response_model=list[MaterialeRead])
async def list_materiali(
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> list[MaterialeRead]:
    """Tutti i materiali_tipo dell'azienda corrente.

    Usato dal frontend per popolare il menu a tendina della composizione
    regola (es. selezione ETR526 + ETR425).

    Sprint 7.9 MR 7D: include ``pezzi_disponibili`` da
    ``materiale_dotazione_azienda`` per la capacity check nella
    dashboard "Convogli necessari". ``None`` se la dotazione non è
    registrata o se è esplicitamente illimitata (es. FLIRT TILO).
    """
    stmt = (
        select(MaterialeTipo)
        .where(MaterialeTipo.azienda_id == user.azienda_id)
        .order_by(MaterialeTipo.codice)
    )
    rows = (await session.execute(stmt)).scalars().all()
    # Carica dotazione in batch
    dotazione_stmt = select(MaterialeDotazioneAzienda).where(
        MaterialeDotazioneAzienda.azienda_id == user.azienda_id
    )
    dotazioni = {
        d.materiale_codice: d.pezzi_disponibili
        for d in (await session.execute(dotazione_stmt)).scalars().all()
    }
    out: list[MaterialeRead] = []
    for r in rows:
        item = MaterialeRead.model_validate(r)
        if r.codice in dotazioni:
            item.pezzi_disponibili = dotazioni[r.codice]
        out.append(item)
    return out


@router.get("/depots", response_model=list[DepotRead])
async def list_depots(
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> list[DepotRead]:
    """Depot PdC dell'azienda corrente con stazione principale collegata.

    Usato dal frontend per popolare il default delle stazioni di sosta
    notturna del programma materiale (decisione utente Sprint 5.6).
    """
    stmt = (
        select(Depot)
        .where(Depot.azienda_id == user.azienda_id, Depot.is_attivo)
        .order_by(Depot.codice)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [DepotRead.model_validate(r) for r in rows]


@router.get("/direttrici", response_model=list[str])
async def list_direttrici(
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> list[str]:
    """Distinct delle direttrici presenti nel PdE per l'azienda.

    Usato dal frontend per popolare il menu a tendina del filtro regola
    sul campo `direttrice`. Esclude NULL.
    """
    stmt = (
        select(distinct(CorsaCommerciale.direttrice))
        .where(
            CorsaCommerciale.azienda_id == user.azienda_id,
            CorsaCommerciale.direttrice.is_not(None),
        )
        .order_by(CorsaCommerciale.direttrice)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [str(r) for r in rows if r is not None]


@router.get("/localita-manutenzione", response_model=list[LocalitaManutenzioneRead])
async def list_localita_manutenzione(
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> list[LocalitaManutenzioneRead]:
    """Località manutenzione (sedi materiale) dell'azienda.

    Usato dal frontend per il selettore di sede del programma e per il
    parametro `localita_codice` di `POST /genera-giri`.
    """
    stmt = (
        select(LocalitaManutenzione)
        .where(
            LocalitaManutenzione.azienda_id == user.azienda_id,
            LocalitaManutenzione.is_attiva,
        )
        .order_by(LocalitaManutenzione.codice_breve)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [LocalitaManutenzioneRead.model_validate(r) for r in rows]


# =====================================================================
# Sprint 7.9 MR β2-0 — Località di sosta intermedia
# =====================================================================


@router.get("/localita-sosta", response_model=list[LocalitaSostaRead])
async def list_localita_sosta(
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> list[LocalitaSostaRead]:
    """Lista località di sosta intermedia attive dell'azienda.

    Sprint 7.9 MR β2-0: distinte dai depositi di manutenzione, sono
    overflow per stazioni che non hanno capacità di sosta lunga (es.
    Milano San Rocco per Milano Porta Garibaldi). Usate dall'algoritmo
    builder + dalle regole d'invio (``regola_invio_sosta``).
    """
    stmt = (
        select(LocalitaSosta)
        .where(
            LocalitaSosta.azienda_id == user.azienda_id,
            LocalitaSosta.is_attiva,
        )
        .order_by(LocalitaSosta.codice)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [LocalitaSostaRead.model_validate(r) for r in rows]


@router.post(
    "/localita-sosta",
    response_model=LocalitaSostaRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_localita_sosta(
    body: LocalitaSostaCreate,
    user: CurrentUser = Depends(require_role("ADMIN")),
    session: AsyncSession = Depends(get_session),
) -> LocalitaSostaRead:
    """Crea una nuova località di sosta (admin only).

    Sprint 7.9 MR β2-0: il pianificatore non crea direttamente le
    località di sosta — è anagrafica gestita dall'admin azienda. La
    UI di amministrazione ne consumerà questo endpoint quando l'azienda
    avrà bisogno di aggiungere uno scalo nuovo (es. Treviglio Ovest).

    Errori:

    - **409**: codice già esistente per l'azienda corrente.
    - **400**: ``stazione_collegata_codice`` non valido (FK).
    """
    # Check duplicato
    stmt_dup = select(LocalitaSosta).where(
        LocalitaSosta.azienda_id == user.azienda_id,
        LocalitaSosta.codice == body.codice,
    )
    if (await session.execute(stmt_dup)).scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Località di sosta {body.codice!r} già esistente per "
            f"azienda_id={user.azienda_id}.",
        )

    # Validazione FK stazione (opzionale)
    if body.stazione_collegata_codice is not None:
        stmt_staz = select(Stazione).where(
            Stazione.codice == body.stazione_collegata_codice
        )
        if (await session.execute(stmt_staz)).scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Stazione collegata {body.stazione_collegata_codice!r} "
                f"non trovata.",
            )

    nuova = LocalitaSosta(
        codice=body.codice,
        nome=body.nome,
        azienda_id=user.azienda_id,
        stazione_collegata_codice=body.stazione_collegata_codice,
        note=body.note,
    )
    session.add(nuova)
    await session.commit()
    await session.refresh(nuova)
    return LocalitaSostaRead.model_validate(nuova)


# =====================================================================
# Sprint 7.7 MR 2 — Calendario ufficiale festività
# =====================================================================


class FestivitaRead(BaseModel):
    """Una festività del calendario ufficiale (nazionale o azienda)."""

    model_config = ConfigDict(from_attributes=True)

    data: date
    nome: str
    tipo: str  # "nazionale" | "religiosa" | "patronale"
    azienda_id: int | None  # NULL = nazionale universale


class CalendarioRead(BaseModel):
    """Risposta di ``GET /api/calendario/{anno}``: festività + tag giorno."""

    anno: int
    festivita: list[FestivitaRead]


@router.get("/calendario/{anno}", response_model=CalendarioRead)
async def get_calendario(
    anno: int,
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> CalendarioRead:
    """Festività dell'anno per l'azienda corrente: nazionali (azienda_id NULL)
    + locali (azienda_id = user.azienda_id).

    Sprint 7.7 MR 2. Il frontend usa questa lista per visualizzare il
    calendario nel programma e per etichettare i giorni come
    feriale/sabato/domenica/festivo.
    """
    if anno < 2025 or anno > 2030:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Anno {anno} fuori dal range seedato (2025-2030). "
                "Per anni futuri estendere la migration 0015."
            ),
        )
    stmt = (
        select(FestivitaUfficiale)
        .where(
            FestivitaUfficiale.data >= date(anno, 1, 1),
            FestivitaUfficiale.data <= date(anno, 12, 31),
            or_(
                FestivitaUfficiale.azienda_id.is_(None),
                FestivitaUfficiale.azienda_id == user.azienda_id,
            ),
        )
        .order_by(FestivitaUfficiale.data, FestivitaUfficiale.nome)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return CalendarioRead(
        anno=anno,
        festivita=[FestivitaRead.model_validate(r) for r in rows],
    )


# Esposto per riuso da altri moduli backend (es. builder Sprint 7.7.3).
__all__ = ["router", "tipo_giorno"]
