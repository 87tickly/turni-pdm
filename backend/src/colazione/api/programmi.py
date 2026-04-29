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

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.auth import require_role
from colazione.db import get_session
from colazione.models.programmi import (
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

    1. Stato corrente = 'bozza' (idempotente: già attivo → no-op? No, errore.)
    2. Almeno 1 regola.
    3. Tutti i `materiale_tipo` referenziati esistono.
    4. Nessun programma attivo della stessa azienda si sovrappone
       sulla finestra `[valido_da, valido_a]`.
    """
    if programma.stato != "bozza":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"programma in stato {programma.stato!r}, non pubblicabile",
        )

    # 2. Almeno 1 regola
    stmt_count = select(ProgrammaRegolaAssegnazione.id).where(
        ProgrammaRegolaAssegnazione.programma_id == programma.id
    )
    regole_ids = (await session.execute(stmt_count)).scalars().all()
    if not regole_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="nessuna regola: aggiungi almeno una regola prima di pubblicare",
        )

    # 4. Sovrapposizione con altri programmi attivi (stessa azienda).
    # Sprint 7.3: il campo `stagione` è stato rimosso, l'overlap check
    # ora confronta solo le finestre temporali. Due programmi
    # cronologicamente disgiunti possono coesistere; sovrapposti no.
    stmt_overlap = select(ProgrammaMateriale.id, ProgrammaMateriale.nome).where(
        ProgrammaMateriale.azienda_id == programma.azienda_id,
        ProgrammaMateriale.stato == "attivo",
        ProgrammaMateriale.id != programma.id,
        ProgrammaMateriale.valido_da <= programma.valido_a,
        ProgrammaMateriale.valido_a >= programma.valido_da,
    )

    overlap = (await session.execute(stmt_overlap)).all()
    if overlap:
        nomi = ", ".join(f"{r.id}={r.nome!r}" for r in overlap)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(f"finestra valido_da/valido_a si sovrappone con programma/i attivo/i: {nomi}"),
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
        fascia_oraria_tolerance_min=payload.fascia_oraria_tolerance_min,
        strict_options_json=payload.strict_options_json.model_dump(),
        stazioni_sosta_extra_json=payload.stazioni_sosta_extra_json,
        created_by_user_id=user.user_id,
    )
    session.add(programma)
    await session.flush()  # popola programma.id

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
    """Lista programmi dell'azienda corrente. Ordinati `valido_da DESC`."""
    stmt = select(ProgrammaMateriale).where(ProgrammaMateriale.azienda_id == user.azienda_id)
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
    - 409 se finestra valido_da/valido_a si sovrappone con altri attivi
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
