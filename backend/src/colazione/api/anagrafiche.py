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

from datetime import date, time

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import distinct, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.auth import require_any_role, require_role
from colazione.db import get_session
from colazione.domain.calendario import tipo_giorno
from colazione.models.anagrafica import (
    Depot,
    FestivitaUfficiale,
    LocalitaManutenzione,
    LocalitaSosta,
    MaterialeDotazioneAzienda,
    MaterialeIstanza,
    MaterialeTipo,
    RegolaInvioSosta,
    Stazione,
)
from colazione.models.corse import CorsaCommerciale
from colazione.schemas.security import CurrentUser

router = APIRouter(prefix="/api", tags=["anagrafiche"])

_authz = Depends(require_role("PIANIFICATORE_GIRO"))
# Sprint 7.9 MR η: l'anagrafica depot serve anche a PIANIFICATORE_PDC
# (selettore deposito target nella generazione turni) e a
# GESTIONE_PERSONALE (vista Depositi sotto Gestione Personale).
_authz_depots = Depends(
    require_any_role("PIANIFICATORE_GIRO", "PIANIFICATORE_PDC", "GESTIONE_PERSONALE")
)


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
    # Sprint 7.9 MR η — esposto l'``id`` per i selettori UI che devono
    # passare la FK alle API di scrittura (es. genera turno PdC).
    id: int
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
    user: CurrentUser = _authz_depots,
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
# Sprint 7.9 MR β2-1 — Istanze materiale (matricole L3)
# =====================================================================


class MaterialeIstanzaRead(BaseModel):
    """Sprint 7.9 MR β2-1: istanza fisica L3 di un materiale."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    tipo_materiale_codice: str
    matricola: str
    sede_codice: str | None
    stato: str
    note: str | None


@router.get("/materiale-istanze", response_model=list[MaterialeIstanzaRead])
async def list_materiale_istanze(
    tipo_materiale_codice: str | None = None,
    sede_codice: str | None = None,
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> list[MaterialeIstanzaRead]:
    """Lista istanze materiale dell'azienda, filtrabili per tipo e sede.

    Sprint 7.9 MR β2-1. Le istanze sono seedate dalla migration 0023
    a partire dalla `materiale_dotazione_azienda` (es. dotazione
    Trenord ETR526=11 → matricole `ETR526-000`..`ETR526-010`).

    Filtri opzionali:
    - ``tipo_materiale_codice``: es. ``"ETR526"``.
    - ``sede_codice``: es. ``"IMPMAN_MILANO_FIORENZA"`` o stringa
      vuota per filtrare le istanze NON ancora assegnate
      (sede_codice IS NULL).
    """
    stmt = (
        select(MaterialeIstanza)
        .where(MaterialeIstanza.azienda_id == user.azienda_id)
        .order_by(MaterialeIstanza.tipo_materiale_codice, MaterialeIstanza.matricola)
    )
    if tipo_materiale_codice is not None:
        stmt = stmt.where(
            MaterialeIstanza.tipo_materiale_codice == tipo_materiale_codice
        )
    if sede_codice is not None:
        if sede_codice == "":
            stmt = stmt.where(MaterialeIstanza.sede_codice.is_(None))
        else:
            stmt = stmt.where(MaterialeIstanza.sede_codice == sede_codice)
    rows = (await session.execute(stmt)).scalars().all()
    return [MaterialeIstanzaRead.model_validate(r) for r in rows]


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


# =====================================================================
# Sprint 7.9 MR β2-7 — Regole pre-builder invio a sosta intermedia
# =====================================================================


class RegolaInvioSostaRead(BaseModel):
    """Sprint 7.9 MR β2-7: regola operativa di invio a sosta."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    programma_id: int
    stazione_sgancio_codice: str
    tipo_materiale_codice: str
    finestra_oraria_inizio: time
    finestra_oraria_fine: time
    localita_sosta_id: int
    fallback_sosta_id: int | None
    note: str | None


class RegolaInvioSostaCreate(BaseModel):
    """Body POST /api/programmi/{id}/regole-invio-sosta."""

    stazione_sgancio_codice: str
    tipo_materiale_codice: str
    finestra_oraria_inizio: time
    finestra_oraria_fine: time
    localita_sosta_id: int
    fallback_sosta_id: int | None = None
    note: str | None = None


@router.get(
    "/programmi/{programma_id}/regole-invio-sosta",
    response_model=list[RegolaInvioSostaRead],
)
async def list_regole_invio_sosta(
    programma_id: int,
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> list[RegolaInvioSostaRead]:
    """Lista regole di invio sosta per il programma indicato.

    Sprint 7.9 MR β2-7: il pianificatore le configura per dichiarare
    "ETR421 sganciato a Garibaldi tra 06:00-19:00 → invia a Misr"
    (anziché lasciare il fallback "deposito sede" del builder).
    """
    # Verifica programma esiste e appartiene all'azienda
    from colazione.models.programmi import ProgrammaMateriale

    prog = (
        await session.execute(
            select(ProgrammaMateriale).where(
                ProgrammaMateriale.id == programma_id,
                ProgrammaMateriale.azienda_id == user.azienda_id,
            )
        )
    ).scalar_one_or_none()
    if prog is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    stmt = (
        select(RegolaInvioSosta)
        .where(RegolaInvioSosta.programma_id == programma_id)
        .order_by(
            RegolaInvioSosta.stazione_sgancio_codice,
            RegolaInvioSosta.tipo_materiale_codice,
            RegolaInvioSosta.finestra_oraria_inizio,
        )
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [RegolaInvioSostaRead.model_validate(r) for r in rows]


@router.post(
    "/programmi/{programma_id}/regole-invio-sosta",
    response_model=RegolaInvioSostaRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_regola_invio_sosta(
    programma_id: int,
    body: RegolaInvioSostaCreate,
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> RegolaInvioSostaRead:
    """Crea una regola di invio sosta per il programma."""
    from colazione.models.programmi import ProgrammaMateriale

    prog = (
        await session.execute(
            select(ProgrammaMateriale).where(
                ProgrammaMateriale.id == programma_id,
                ProgrammaMateriale.azienda_id == user.azienda_id,
            )
        )
    ).scalar_one_or_none()
    if prog is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    # Valida FK localita_sosta (deve appartenere all'azienda).
    sosta = (
        await session.execute(
            select(LocalitaSosta).where(
                LocalitaSosta.id == body.localita_sosta_id,
                LocalitaSosta.azienda_id == user.azienda_id,
            )
        )
    ).scalar_one_or_none()
    if sosta is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Località di sosta {body.localita_sosta_id} non trovata.",
        )

    if body.fallback_sosta_id is not None:
        fallback = (
            await session.execute(
                select(LocalitaSosta).where(
                    LocalitaSosta.id == body.fallback_sosta_id,
                    LocalitaSosta.azienda_id == user.azienda_id,
                )
            )
        ).scalar_one_or_none()
        if fallback is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Località fallback {body.fallback_sosta_id} non trovata.",
            )

    nuova = RegolaInvioSosta(
        programma_id=programma_id,
        stazione_sgancio_codice=body.stazione_sgancio_codice,
        tipo_materiale_codice=body.tipo_materiale_codice,
        finestra_oraria_inizio=body.finestra_oraria_inizio,
        finestra_oraria_fine=body.finestra_oraria_fine,
        localita_sosta_id=body.localita_sosta_id,
        fallback_sosta_id=body.fallback_sosta_id,
        note=body.note,
    )
    session.add(nuova)
    await session.commit()
    await session.refresh(nuova)
    return RegolaInvioSostaRead.model_validate(nuova)


@router.delete(
    "/programmi/{programma_id}/regole-invio-sosta/{regola_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_regola_invio_sosta(
    programma_id: int,
    regola_id: int,
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Cancella una regola di invio sosta (cancellabile dal pianificatore)."""
    from colazione.models.programmi import ProgrammaMateriale

    prog = (
        await session.execute(
            select(ProgrammaMateriale).where(
                ProgrammaMateriale.id == programma_id,
                ProgrammaMateriale.azienda_id == user.azienda_id,
            )
        )
    ).scalar_one_or_none()
    if prog is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    regola = (
        await session.execute(
            select(RegolaInvioSosta).where(
                RegolaInvioSosta.id == regola_id,
                RegolaInvioSosta.programma_id == programma_id,
            )
        )
    ).scalar_one_or_none()
    if regola is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await session.delete(regola)
    await session.commit()


# Esposto per riuso da altri moduli backend (es. builder Sprint 7.7.3).
__all__ = ["router", "tipo_giorno"]
