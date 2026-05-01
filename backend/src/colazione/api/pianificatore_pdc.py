"""Route HTTP dashboard Pianificatore Turno PdC — Sprint 7.3.

Apre il 2° ruolo dell'ecosistema (PIANIFICATORE_PDC). Per ora espone
un solo endpoint:

- ``GET /api/pianificatore-pdc/overview`` — KPI per la home della
  dashboard PdC (n. giri materiali pubblicati, n. turni PdC raggruppati
  per impianto, n. turni con violazioni hard di prestazione/condotta).

Auth: ruolo ``PIANIFICATORE_PDC`` (admin bypassa). Multi-tenant:
filtro ``azienda_id`` dal JWT.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import and_, distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.auth import require_role
from colazione.db import get_session
from colazione.domain.builder_pdc.builder import (
    CONDOTTA_MAX_MIN,
    PRESTAZIONE_MAX_NOTTURNO,
    PRESTAZIONE_MAX_STANDARD,
)
from colazione.models.giri import GiroMateriale
from colazione.models.turni_pdc import TurnoPdc, TurnoPdcGiornata
from colazione.schemas.security import CurrentUser

router = APIRouter(prefix="/api/pianificatore-pdc", tags=["pianificatore-pdc"])


# =====================================================================
# Schemi response
# =====================================================================


class TurniPerImpiantoItem(BaseModel):
    impianto: str
    count: int


class OverviewResponse(BaseModel):
    """KPI aggregati per la home dashboard PIANIFICATORE_PDC.

    `giri_materiali_count` — totale giri materiali dell'azienda
    (sorgente per costruire turni PdC).

    `turni_pdc_per_impianto` — breakdown turni PdC esistenti per
    impianto (deposito personale). Ordinato alfabeticamente per
    rendere stabile l'output a parità di dati.

    `turni_con_violazioni_hard` — n. turni PdC distinti che hanno
    almeno una giornata con `prestazione_min` oltre cap normativo
    (510 standard / 420 notturno) o `condotta_min` oltre cap (330).
    Le violazioni soft (es. refezione mancante) non sono incluse.

    `revisioni_cascading_attive` — placeholder Sprint 7.6+: il
    modello `revisione_provvisoria` non esiste ancora nel codice,
    ritorniamo sempre 0 finché non lo implementiamo.
    """

    giri_materiali_count: int
    turni_pdc_per_impianto: list[TurniPerImpiantoItem]
    turni_con_violazioni_hard: int
    revisioni_cascading_attive: int


# =====================================================================
# GET /api/pianificatore-pdc/overview
# =====================================================================


@router.get("/overview", response_model=OverviewResponse)
async def get_overview(
    user: CurrentUser = Depends(require_role("PIANIFICATORE_PDC")),
    session: AsyncSession = Depends(get_session),
) -> OverviewResponse:
    """KPI dashboard PIANIFICATORE_PDC scoped all'azienda dell'utente.

    Tre query SQL aggregate (no N+1, no scan in Python). La condizione
    "violazione hard" è espressa via OR esplicito sui 3 cap distinti
    (notturno vs standard sul campo prestazione, più cap condotta).
    """
    azienda_id = user.azienda_id

    # --- giri materiali totali nell'azienda ---
    giri_count_stmt = select(func.count(GiroMateriale.id)).where(
        GiroMateriale.azienda_id == azienda_id
    )
    giri_materiali_count = (await session.execute(giri_count_stmt)).scalar_one()

    # --- turni PdC per impianto (group by) ---
    per_impianto_stmt = (
        select(TurnoPdc.impianto, func.count(TurnoPdc.id))
        .where(TurnoPdc.azienda_id == azienda_id)
        .group_by(TurnoPdc.impianto)
        .order_by(TurnoPdc.impianto)
    )
    per_impianto_rows = (await session.execute(per_impianto_stmt)).all()
    turni_pdc_per_impianto = [
        TurniPerImpiantoItem(impianto=row[0], count=int(row[1]))
        for row in per_impianto_rows
    ]

    # --- turni con violazioni hard ---
    violazioni_clause = or_(
        and_(
            TurnoPdcGiornata.is_notturno.is_(True),
            TurnoPdcGiornata.prestazione_min > PRESTAZIONE_MAX_NOTTURNO,
        ),
        and_(
            TurnoPdcGiornata.is_notturno.is_(False),
            TurnoPdcGiornata.prestazione_min > PRESTAZIONE_MAX_STANDARD,
        ),
        TurnoPdcGiornata.condotta_min > CONDOTTA_MAX_MIN,
    )
    violazioni_stmt = (
        select(func.count(distinct(TurnoPdc.id)))
        .join(TurnoPdcGiornata, TurnoPdcGiornata.turno_pdc_id == TurnoPdc.id)
        .where(TurnoPdc.azienda_id == azienda_id)
        .where(violazioni_clause)
    )
    turni_con_violazioni_hard = (await session.execute(violazioni_stmt)).scalar_one()

    return OverviewResponse(
        giri_materiali_count=int(giri_materiali_count),
        turni_pdc_per_impianto=turni_pdc_per_impianto,
        turni_con_violazioni_hard=int(turni_con_violazioni_hard),
        revisioni_cascading_attive=0,  # placeholder Sprint 7.6+
    )
