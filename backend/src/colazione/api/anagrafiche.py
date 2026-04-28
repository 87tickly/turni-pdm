"""Route HTTP read-side per anagrafiche (Sprint 5.6 R1).

Endpoint di sola lettura per popolare i menu/UI del frontend
Pianificatore Giro Materiale:

- ``GET /api/stazioni`` — lista stazioni PdE per filtri regola e visualizzatore
- ``GET /api/materiali`` — lista materiale_tipo per composizione regole
- ``GET /api/depots`` — 25 depot PdC + stazione_principale_codice (default
  sosta extra)
- ``GET /api/direttrici`` — distinct delle direttrici nel PdE
- ``GET /api/localita-manutenzione`` — sedi (codice, codice_breve, stazione_collegata)

Multi-tenant: ``azienda_id`` dal JWT, niente input client.
Auth: ruolo ``PIANIFICATORE_GIRO`` (admin bypassa).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.auth import require_role
from colazione.db import get_session
from colazione.models.anagrafica import (
    Depot,
    LocalitaManutenzione,
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
    """
    stmt = (
        select(MaterialeTipo)
        .where(MaterialeTipo.azienda_id == user.azienda_id)
        .order_by(MaterialeTipo.codice)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [MaterialeRead.model_validate(r) for r in rows]


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
