"""Route HTTP — dashboard pipeline trasversale (Sprint 8.0 MR 6, entry 171).

Endpoint admin-only che mostra **tutti** i programmi dell'azienda con
lo stato del ramo PdC + ramo Manutenzione, ed evidenzia quanto tempo
il programma è bloccato sullo stesso stato. Pensato per il
super-user / coordinatore che orchestra il flusso fra ruoli.

Endpoint:

- ``GET /api/admin/pipeline-overview`` — lista programmi con stato
  pipeline + giorni dall'ultimo aggiornamento + ruolo responsabile
  del prossimo step.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.auth import require_admin
from colazione.db import get_session
from colazione.domain.pipeline import (
    StatoManutenzione,
    StatoPipelinePdc,
)
from colazione.models.programmi import ProgrammaMateriale
from colazione.schemas.security import CurrentUser

router = APIRouter(prefix="/api/admin", tags=["admin"])

_authz_admin = Depends(require_admin())


# Mappa stato → ruolo responsabile dello step successivo. Quando il
# programma è bloccato su uno stato, è chi tiene questo ruolo che deve
# agire (o un admin che usa POST /sblocca per sbloccarlo).
_RESPONSABILE_PROSSIMO_STEP: dict[StatoPipelinePdc, str] = {
    StatoPipelinePdc.PDE_IN_LAVORAZIONE: "PIANIFICATORE_GIRO",
    StatoPipelinePdc.PDE_CONSOLIDATO: "PIANIFICATORE_GIRO",
    StatoPipelinePdc.MATERIALE_GENERATO: "PIANIFICATORE_GIRO",
    StatoPipelinePdc.MATERIALE_CONFERMATO: "PIANIFICATORE_PDC",
    StatoPipelinePdc.PDC_GENERATO: "PIANIFICATORE_PDC",
    StatoPipelinePdc.PDC_CONFERMATO: "GESTIONE_PERSONALE",
    StatoPipelinePdc.PERSONALE_ASSEGNATO: "GESTIONE_PERSONALE",
    StatoPipelinePdc.VISTA_PUBBLICATA: "—",  # terminale
}

_RESPONSABILE_MANUTENZIONE: dict[StatoManutenzione, str] = {
    StatoManutenzione.IN_ATTESA: "PIANIFICATORE_GIRO",  # attiva con conferma materiale
    StatoManutenzione.IN_LAVORAZIONE: "MANUTENZIONE",
    StatoManutenzione.MATRICOLE_ASSEGNATE: "—",  # terminale
}


class PipelineProgrammaItem(BaseModel):
    """Riga della dashboard trasversale."""

    programma_id: int
    nome: str
    stato_pipeline_pdc: str
    stato_manutenzione: str
    pdc_responsabile_prossimo: str
    manutenzione_responsabile_prossimo: str
    giorni_in_stato: int
    is_bloccato: bool
    """``True`` se il programma è in uno stato non terminale da > 7 giorni."""


class PipelineOverviewResponse(BaseModel):
    """Aggregato per la dashboard admin."""

    programmi: list[PipelineProgrammaItem]
    counters_per_stato_pdc: dict[str, int]
    counters_per_stato_manutenzione: dict[str, int]
    n_bloccati: int


_BLOCCATO_SOGLIA_GIORNI = 7


def _giorni_da(updated_at: datetime, now: datetime) -> int:
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)
    delta = now - updated_at
    return max(0, delta.days)


def _is_terminale_pdc(stato: StatoPipelinePdc) -> bool:
    return stato == StatoPipelinePdc.VISTA_PUBBLICATA


@router.get(
    "/pipeline-overview",
    response_model=PipelineOverviewResponse,
    summary="Dashboard trasversale stati pipeline (admin only)",
)
async def get_pipeline_overview(
    user: CurrentUser = _authz_admin,
    session: AsyncSession = Depends(get_session),
) -> PipelineOverviewResponse:
    """Tutti i programmi dell'azienda con stato pipeline + tempo
    in stato + ruolo responsabile.

    Filtraggio: solo programmi dell'``azienda_id`` dell'admin loggato
    (multi-tenant). Niente filtro per stato — l'admin vede TUTTO.
    """
    stmt = (
        select(ProgrammaMateriale)
        .where(ProgrammaMateriale.azienda_id == user.azienda_id)
        .order_by(ProgrammaMateriale.updated_at.desc())
    )
    rows = (await session.execute(stmt)).scalars().all()

    now = datetime.now(UTC)
    counters_pdc: dict[str, int] = {}
    counters_man: dict[str, int] = {}
    items: list[PipelineProgrammaItem] = []
    n_bloccati = 0

    for p in rows:
        try:
            stato_pdc = StatoPipelinePdc(p.stato_pipeline_pdc)
        except ValueError:
            # Stato fuori enum (CHECK DB dovrebbe impedirlo): skippiamo.
            continue
        try:
            stato_man = StatoManutenzione(p.stato_manutenzione)
        except ValueError:
            continue

        giorni = _giorni_da(p.updated_at, now)
        bloccato = giorni > _BLOCCATO_SOGLIA_GIORNI and not _is_terminale_pdc(
            stato_pdc
        )
        if bloccato:
            n_bloccati += 1

        counters_pdc[stato_pdc.value] = counters_pdc.get(stato_pdc.value, 0) + 1
        counters_man[stato_man.value] = counters_man.get(stato_man.value, 0) + 1

        items.append(
            PipelineProgrammaItem(
                programma_id=p.id,
                nome=p.nome,
                stato_pipeline_pdc=stato_pdc.value,
                stato_manutenzione=stato_man.value,
                pdc_responsabile_prossimo=_RESPONSABILE_PROSSIMO_STEP[stato_pdc],
                manutenzione_responsabile_prossimo=_RESPONSABILE_MANUTENZIONE[
                    stato_man
                ],
                giorni_in_stato=giorni,
                is_bloccato=bloccato,
            )
        )

    return PipelineOverviewResponse(
        programmi=items,
        counters_per_stato_pdc=counters_pdc,
        counters_per_stato_manutenzione=counters_man,
        n_bloccati=n_bloccati,
    )


__all__ = ["router", "PipelineOverviewResponse", "PipelineProgrammaItem"]
