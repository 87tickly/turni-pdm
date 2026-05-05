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
from colazione.models.anagrafica import Depot
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


class TurniPerDepositoItem(BaseModel):
    """Sprint 7.9 MR η — distribuzione turni per deposito PdC.

    Più semantico di ``TurniPerImpiantoItem`` (impianto = string
    materiale o deposito a seconda dell'epoca del turno), perché
    pesca direttamente sulla FK ``turno_pdc.deposito_pdc_id``.
    """

    deposito_pdc_id: int | None
    deposito_pdc_codice: str | None
    deposito_pdc_display: str | None
    count: int
    n_dormite_fr_totali: int = 0


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

    Sprint 7.9 MR η:

    - ``turni_pdc_per_deposito`` — vera distribuzione per deposito
      PdC (FK), accompagnata dal totale dormite FR del deposito.
    - ``dormite_fr_totali`` — somma di ``len(fr_giornate)`` su tutti
      i turni dell'azienda.
    - ``turni_con_fr_cap_violazioni`` — n. turni PdC con almeno 1
      violazione cap FR (1/sett, 3/28gg, NORMATIVA-PDC §10.6).
    - ``depositi_pdc_totali`` — anagrafica depot attivi per il
      denominatore del KPI "impianti coperti".
    """

    giri_materiali_count: int
    turni_pdc_per_impianto: list[TurniPerImpiantoItem]
    turni_pdc_per_deposito: list[TurniPerDepositoItem] = []
    turni_con_violazioni_hard: int
    revisioni_cascading_attive: int
    dormite_fr_totali: int = 0
    turni_con_fr_cap_violazioni: int = 0
    depositi_pdc_totali: int = 0


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

    Sprint 7.9 MR η: estesa con KPI deposito + FR (NORMATIVA-PDC §10).
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

    # --- Sprint 7.9 MR η: KPI deposito + FR ----------------------------
    # Cardinalità depositi PdC attivi (denominatore "impianti coperti").
    depositi_totali = (
        await session.execute(
            select(func.count(Depot.id)).where(
                Depot.azienda_id == azienda_id, Depot.is_attivo
            )
        )
    ).scalar_one()

    # Carica turni + (deposito) joinando in left outer per i turni
    # legacy senza FK valorizzata. Volume tipico per azienda: O(centinaia),
    # processabile in Python senza JSONB SQL gymnastics.
    turni_meta_stmt = (
        select(
            TurnoPdc.id,
            TurnoPdc.deposito_pdc_id,
            TurnoPdc.generation_metadata_json,
            Depot.codice,
            Depot.display_name,
        )
        .join(Depot, Depot.id == TurnoPdc.deposito_pdc_id, isouter=True)
        .where(TurnoPdc.azienda_id == azienda_id)
    )
    turni_meta_rows = (await session.execute(turni_meta_stmt)).all()

    # Aggregazione per deposito.
    per_deposito_acc: dict[
        tuple[int | None, str | None, str | None], dict[str, int]
    ] = {}
    dormite_fr_totali = 0
    turni_con_fr_cap = 0
    for _tid, dep_id, meta_json, dep_codice, dep_display in turni_meta_rows:
        meta = meta_json or {}
        n_fr = len(meta.get("fr_giornate") or [])
        n_fr_cap = len(meta.get("fr_cap_violazioni") or [])
        dormite_fr_totali += n_fr
        if n_fr_cap > 0:
            turni_con_fr_cap += 1
        key = (dep_id, dep_codice, dep_display)
        bucket = per_deposito_acc.setdefault(key, {"count": 0, "fr": 0})
        bucket["count"] += 1
        bucket["fr"] += n_fr

    # Ordinamento: codici depot alfabetici prima, NULL (legacy) in coda.
    per_deposito_sorted = sorted(
        per_deposito_acc.items(),
        key=lambda kv: (kv[0][1] is None, kv[0][1] or ""),
    )
    turni_pdc_per_deposito = [
        TurniPerDepositoItem(
            deposito_pdc_id=key[0],
            deposito_pdc_codice=key[1],
            deposito_pdc_display=key[2],
            count=v["count"],
            n_dormite_fr_totali=v["fr"],
        )
        for key, v in per_deposito_sorted
    ]

    return OverviewResponse(
        giri_materiali_count=int(giri_materiali_count),
        turni_pdc_per_impianto=turni_pdc_per_impianto,
        turni_pdc_per_deposito=turni_pdc_per_deposito,
        turni_con_violazioni_hard=int(turni_con_violazioni_hard),
        revisioni_cascading_attive=0,  # placeholder Sprint 7.6+
        dormite_fr_totali=int(dormite_fr_totali),
        turni_con_fr_cap_violazioni=int(turni_con_fr_cap),
        depositi_pdc_totali=int(depositi_totali),
    )
