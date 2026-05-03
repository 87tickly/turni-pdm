"""Route HTTP per `programma_materiale` + regole — Sprint 4.3.

Endpoints:

- `POST /api/programmi` — crea programma (stato 'bozza'), regole nested opt.
- `GET /api/programmi` — lista programmi dell'azienda corrente.
- `GET /api/programmi/{id}` — dettaglio + regole.
- `PATCH /api/programmi/{id}` — aggiorna intestazione (no stato).
- `POST /api/programmi/{id}/regole` — aggiungi regola.
- `DELETE /api/programmi/{id}/regole/{regola_id}` — rimuovi regola.
- `POST /api/programmi/{id}/pubblica` — bozza → attivo con validazione.
- `POST /api/programmi/{id}/archivia` — attivo → archiviato.

**Multi-tenant**: l'`azienda_id` è preso dal JWT (`CurrentUser.azienda_id`),
mai dal client. Programmi di altre aziende ritornano 404 (non 403, per
non rivelare l'esistenza).

**Auth**: tutti gli endpoint richiedono ruolo `PIANIFICATORE_GIRO`
(l'admin bypassa, vedi `require_role`).
"""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from colazione.auth import require_role
from colazione.db import get_session
from colazione.models.programmi import (
    BuilderRun,
    ProgrammaMateriale,
    ProgrammaRegolaAssegnazione,
)
from colazione.schemas.programmi import (
    ProgrammaMaterialeCreate,
    ProgrammaMaterialeRead,
    ProgrammaMaterialeUpdate,
    ProgrammaRegolaAssegnazioneCreate,
    ProgrammaRegolaAssegnazioneRead,
)
from colazione.schemas.security import CurrentUser

router = APIRouter(prefix="/api/programmi", tags=["programmi"])


# Tutti gli endpoint richiedono PIANIFICATORE_GIRO (admin bypassa via require_role).
_authz = Depends(require_role("PIANIFICATORE_GIRO"))


# =====================================================================
# Helpers
# =====================================================================


async def _get_programma_or_404(
    session: AsyncSession, programma_id: int, azienda_id: int
) -> ProgrammaMateriale:
    """Carica un programma se esiste E appartiene all'azienda corrente."""
    stmt = (
        select(ProgrammaMateriale)
        .where(
            ProgrammaMateriale.id == programma_id,
            ProgrammaMateriale.azienda_id == azienda_id,
        )
        .limit(1)
    )
    p = (await session.execute(stmt)).scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="programma non trovato")
    return p


async def _validate_pubblicabile(session: AsyncSession, programma: ProgrammaMateriale) -> None:
    """Validazione pre-pubblicazione (bozza → attivo).

    1. Stato corrente = 'bozza'.
    2. Almeno 1 regola.

    Nota Sprint 7.9 (entry 107): rimosso il check di sovrapposizione
    finestre. Programmi paralleli sulla stessa finestra temporale sono
    legittimi: tipicamente coprono materiali diversi (es. ETR526 Tirano
    + ATR803 Cremona + ETR522 Malpensa attivi insieme su 2026-03→06).
    Il builder filtra per `programma_id` singolo, quindi due programmi
    sulla stessa finestra producono insiemi di giri indipendenti — non
    c'è ambiguità a livello di builder. La responsabilità di non
    sovrapporre regole sullo stesso materiale è del pianificatore.
    """
    if programma.stato != "bozza":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"programma in stato {programma.stato!r}, non pubblicabile",
        )

    stmt_count = select(ProgrammaRegolaAssegnazione.id).where(
        ProgrammaRegolaAssegnazione.programma_id == programma.id
    )
    regole_ids = (await session.execute(stmt_count)).scalars().all()
    if not regole_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="nessuna regola: aggiungi almeno una regola prima di pubblicare",
        )


# =====================================================================
# POST / GET — programma
# =====================================================================


@router.post(
    "",
    response_model=ProgrammaMaterialeRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_programma(
    payload: ProgrammaMaterialeCreate,
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> ProgrammaMateriale:
    """Crea un nuovo programma (stato `bozza`). Regole nested opzionali."""
    programma = ProgrammaMateriale(
        azienda_id=user.azienda_id,
        nome=payload.nome,
        valido_da=payload.valido_da,
        valido_a=payload.valido_a,
        stato="bozza",
        km_max_giornaliero=payload.km_max_giornaliero,
        km_max_ciclo=payload.km_max_ciclo,
        n_giornate_default=payload.n_giornate_default,
        n_giornate_min=payload.n_giornate_min,
        n_giornate_max=payload.n_giornate_max,
        fascia_oraria_tolerance_min=payload.fascia_oraria_tolerance_min,
        strict_options_json=payload.strict_options_json.model_dump(),
        stazioni_sosta_extra_json=payload.stazioni_sosta_extra_json,
        created_by_user_id=user.user_id,
    )
    session.add(programma)
    await session.flush()  # popola programma.id

    # Entry 96: nessun check vincoli inviolabili sulle regole nested.
    # Il builder applica i vincoli a livello corsa (residua se incompatibile).

    for regola_payload in payload.regole:
        # Sprint 5.1: composizione è la fonte autorevole. I campi legacy
        # (materiale_tipo_codice, numero_pezzi) sono ri-popolati dal primo
        # elemento per retrocompat con `risolvi_corsa()` fino a Sub 5.5.
        composizione = regola_payload.composizione
        regola = ProgrammaRegolaAssegnazione(
            programma_id=programma.id,
            filtri_json=[f.model_dump() for f in regola_payload.filtri_json],
            composizione_json=[item.model_dump() for item in composizione],
            is_composizione_manuale=regola_payload.is_composizione_manuale,
            materiale_tipo_codice=composizione[0].materiale_tipo_codice,
            numero_pezzi=composizione[0].n_pezzi,
            priorita=regola_payload.priorita,
            km_max_ciclo=regola_payload.km_max_ciclo,
            note=regola_payload.note,
        )
        session.add(regola)

    await session.commit()
    await session.refresh(programma)
    return programma


@router.get("", response_model=list[ProgrammaMaterialeRead])
async def list_programmi(
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
    stato: str | None = Query(default=None, description="filtro per stato"),
) -> list[ProgrammaMateriale]:
    """Lista programmi dell'azienda corrente. Ordinati `valido_da DESC`.

    Eager-load `created_by` per popolare `created_by_username` nella
    response (entry 88 — schermata 3 design `arturo/03-dettaglio-programma.html`).
    """
    stmt = (
        select(ProgrammaMateriale)
        .options(joinedload(ProgrammaMateriale.created_by))
        .where(ProgrammaMateriale.azienda_id == user.azienda_id)
    )
    if stato is not None:
        stmt = stmt.where(ProgrammaMateriale.stato == stato)
    stmt = stmt.order_by(ProgrammaMateriale.valido_da.desc())
    return list((await session.execute(stmt)).scalars().all())


class ProgrammaDettaglioRead(ProgrammaMaterialeRead):
    """Estende `Read` con la lista di regole."""

    regole: list[ProgrammaRegolaAssegnazioneRead] = []


@router.get("/{programma_id}", response_model=ProgrammaDettaglioRead)
async def get_programma(
    programma_id: int,
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    """Dettaglio del programma + lista regole (eager loading via 1 query)."""
    stmt = (
        select(ProgrammaMateriale)
        .options(joinedload(ProgrammaMateriale.created_by))
        .where(
            ProgrammaMateriale.id == programma_id,
            ProgrammaMateriale.azienda_id == user.azienda_id,
        )
        .limit(1)
    )
    p = (await session.execute(stmt)).scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="programma non trovato")

    stmt_regole = (
        select(ProgrammaRegolaAssegnazione)
        .where(ProgrammaRegolaAssegnazione.programma_id == programma_id)
        .order_by(
            ProgrammaRegolaAssegnazione.priorita.desc(),
            ProgrammaRegolaAssegnazione.id.asc(),
        )
    )
    regole = list((await session.execute(stmt_regole)).scalars().all())

    return {
        **ProgrammaMaterialeRead.model_validate(p).model_dump(),
        "regole": [ProgrammaRegolaAssegnazioneRead.model_validate(r) for r in regole],
    }


# =====================================================================
# PATCH programma
# =====================================================================


@router.patch("/{programma_id}", response_model=ProgrammaMaterialeRead)
async def update_programma(
    programma_id: int,
    payload: ProgrammaMaterialeUpdate,
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> ProgrammaMateriale:
    """Aggiorna intestazione + parametri globali. Stato escluso (usa
    /pubblica e /archivia).

    Solo i campi forniti vengono aggiornati (Pydantic exclude_unset).
    Il programma deve appartenere all'azienda corrente.
    """
    p = await _get_programma_or_404(session, programma_id, user.azienda_id)

    data = payload.model_dump(exclude_unset=True)
    # Stato non si tocca via PATCH
    data.pop("stato", None)
    if "strict_options_json" in data and data["strict_options_json"] is not None:
        data["strict_options_json"] = payload.strict_options_json.model_dump()  # type: ignore[union-attr]

    # Sprint 7.8: valida range n_giornate_min ≤ n_giornate_max sul valore
    # finale (merge di payload + valori esistenti). Evita 500 da CHECK
    # constraint DB se il pianificatore patcha solo uno dei due campi.
    nuovo_min = data.get("n_giornate_min", p.n_giornate_min)
    nuovo_max = data.get("n_giornate_max", p.n_giornate_max)
    if nuovo_min is not None and nuovo_max is not None and nuovo_max < nuovo_min:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"n_giornate_max ({nuovo_max}) deve essere >= "
                f"n_giornate_min ({nuovo_min})"
            ),
        )

    for k, v in data.items():
        setattr(p, k, v)
    p.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(p)
    return p


# =====================================================================
# POST/DELETE regole
# =====================================================================


@router.post(
    "/{programma_id}/regole",
    response_model=ProgrammaRegolaAssegnazioneRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_regola(
    programma_id: int,
    payload: ProgrammaRegolaAssegnazioneCreate,
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> ProgrammaRegolaAssegnazione:
    """Aggiunge una regola al programma. Vincoli:

    - programma deve esistere e appartenere all'azienda corrente
    - programma deve essere in stato `bozza` (mod. di un attivo richiede
      revisione futura, fuori MVP)

    Entry 96: i vincoli HARD a livello tipo materiale
    (`data/vincoli_materiale_inviolabili.json`) **non sono più
    applicati qui**. Il pianificatore può creare regole "ampie" senza
    essere bloccato. Il check viene fatto dal builder (``risolvi_corsa``):
    le corse incompatibili col materiale di una regola cadono come
    residue invece che bloccare la creazione.
    """
    p = await _get_programma_or_404(session, programma_id, user.azienda_id)
    if p.stato != "bozza":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"programma in stato {p.stato!r}: regole modificabili solo in bozza",
        )

    composizione = payload.composizione
    regola = ProgrammaRegolaAssegnazione(
        programma_id=programma_id,
        filtri_json=[f.model_dump() for f in payload.filtri_json],
        composizione_json=[item.model_dump() for item in composizione],
        is_composizione_manuale=payload.is_composizione_manuale,
        materiale_tipo_codice=composizione[0].materiale_tipo_codice,
        numero_pezzi=composizione[0].n_pezzi,
        priorita=payload.priorita,
        km_max_ciclo=payload.km_max_ciclo,
        note=payload.note,
    )
    session.add(regola)
    await session.commit()
    await session.refresh(regola)
    return regola


@router.delete(
    "/{programma_id}/regole/{regola_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_regola(
    programma_id: int,
    regola_id: int,
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Cancella una regola. Programma deve essere in `bozza`."""
    p = await _get_programma_or_404(session, programma_id, user.azienda_id)
    if p.stato != "bozza":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"programma in stato {p.stato!r}: regole modificabili solo in bozza",
        )

    stmt = (
        select(ProgrammaRegolaAssegnazione)
        .where(
            ProgrammaRegolaAssegnazione.id == regola_id,
            ProgrammaRegolaAssegnazione.programma_id == programma_id,
        )
        .limit(1)
    )
    regola = (await session.execute(stmt)).scalar_one_or_none()
    if regola is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="regola non trovata")
    await session.delete(regola)
    await session.commit()


# =====================================================================
# Stato lifecycle: pubblica + archivia
# =====================================================================


@router.post("/{programma_id}/pubblica", response_model=ProgrammaMaterialeRead)
async def pubblica_programma(
    programma_id: int,
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> ProgrammaMateriale:
    """Transizione `bozza` → `attivo` con validazione completa.

    Errori possibili:
    - 400 se non in `bozza`
    - 400 se nessuna regola

    Nota: programmi paralleli sulla stessa finestra temporale sono
    consentiti (entry 107). Il builder lavora per `programma_id`
    singolo, niente conflitti automatici.
    """
    p = await _get_programma_or_404(session, programma_id, user.azienda_id)
    await _validate_pubblicabile(session, p)
    p.stato = "attivo"
    p.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(p)
    return p


@router.post("/{programma_id}/archivia", response_model=ProgrammaMaterialeRead)
async def archivia_programma(
    programma_id: int,
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> ProgrammaMateriale:
    """Transizione `attivo` → `archiviato`. Idempotente non supportata."""
    p = await _get_programma_or_404(session, programma_id, user.azienda_id)
    if p.stato == "archiviato":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="programma già archiviato",
        )
    p.stato = "archiviato"
    p.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(p)
    return p


# =====================================================================
# Builder run (Sprint 7.9 MR 11C, entry 116)
# =====================================================================


class BuilderRunRead(BaseModel):
    """Esito di una run del builder + metriche di copertura."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    programma_id: int
    localita_codice: str
    eseguito_at: datetime
    eseguito_da_user_id: int | None
    n_giri_creati: int
    n_giri_chiusi: int
    n_giri_non_chiusi: int
    n_corse_processate: int
    n_corse_residue: int
    n_eventi_composizione: int
    n_incompatibilita_materiale: int
    warnings_json: list[Any]
    force: bool


@router.get(
    "/{programma_id}/last-run",
    response_model=BuilderRunRead | None,
    summary="Ritorna l'esito dell'ultima run del builder per il programma",
)
async def get_last_builder_run(
    programma_id: int,
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> BuilderRun | None:
    """Recupera l'ultimo ``BuilderRun`` per il programma (per mostrarne
    warnings + copertura PdE in UI).

    Restituisce ``null`` se il programma non ha ancora avuto run, oppure
    se non esiste / appartiene ad altra azienda (404 silenzioso per
    privacy multi-tenant — coerente con il pattern di altre route).
    """
    p = await _get_programma_or_404(session, programma_id, user.azienda_id)
    stmt = (
        select(BuilderRun)
        .where(BuilderRun.programma_id == p.id, BuilderRun.azienda_id == user.azienda_id)
        .order_by(BuilderRun.eseguito_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


@router.get(
    "/{programma_id}/runs",
    response_model=list[BuilderRunRead],
    summary="Storico run del builder per il programma (più recente per primo)",
)
async def list_builder_runs(
    programma_id: int,
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
    limit: int = Query(20, ge=1, le=100),
) -> list[BuilderRun]:
    """Storico run del builder. Ordinato per ``eseguito_at DESC``."""
    p = await _get_programma_or_404(session, programma_id, user.azienda_id)
    stmt = (
        select(BuilderRun)
        .where(BuilderRun.programma_id == p.id, BuilderRun.azienda_id == user.azienda_id)
        .order_by(BuilderRun.eseguito_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())
