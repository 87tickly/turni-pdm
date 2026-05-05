"""Route HTTP read-side per il ruolo GESTIONE_PERSONALE (Sprint 7.9 MR ζ).

Endpoint di sola lettura per la dashboard Gestione Personale:

- ``GET /api/persone`` — lista anagrafica con filtri deposito/profilo/search
- ``GET /api/persone/{id}`` — scheda persona + indisponibilità correnti
- ``GET /api/depots/{codice}/persone`` — drilldown PdC del deposito
- ``GET /api/indisponibilita`` — lista ferie/malattie/ROL filtrabili
- ``GET /api/gestione-personale/kpi`` — KPI dashboard (in servizio, ferie, malattia)
- ``GET /api/gestione-personale/kpi-depositi`` — breakdown per deposito

Multi-tenant: ``azienda_id`` dal JWT, niente input client.
Auth: ruolo ``GESTIONE_PERSONALE`` (admin bypassa). Lettura concessa
anche a ``PIANIFICATORE_PDC`` per il cross-link "chi è al deposito X".
"""

from __future__ import annotations

from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.auth import require_any_role
from colazione.db import get_session
from colazione.models.anagrafica import Depot
from colazione.models.personale import (
    IndisponibilitaPersona,
    Persona,
)
from colazione.schemas.personale import (
    GestionePersonaleKpiPerDepositoRead,
    GestionePersonaleKpiRead,
    IndisponibilitaWithPersonaRead,
    PersonaWithDepositoRead,
)
from colazione.schemas.security import CurrentUser

router = APIRouter(prefix="/api", tags=["gestione-personale"])

# Lettura concessa al ruolo Gestione Personale e — per il cross-link
# "chi è al deposito X" — anche al Pianificatore PdC (ammette anche admin).
_authz = Depends(require_any_role("GESTIONE_PERSONALE", "PIANIFICATORE_PDC"))


def _categoria_assenza(tipo: str) -> str:
    """Mappa il tipo indisponibilità nelle 4 categorie KPI dashboard."""
    if tipo == "ferie":
        return "ferie"
    if tipo == "malattia":
        return "malattia"
    if tipo == "ROL":
        return "rol"
    return "altra"  # sciopero/formazione/congedo


# ─────────────────────────────────────────────────────────────────────
# /api/persone
# ─────────────────────────────────────────────────────────────────────


@router.get("/persone", response_model=list[PersonaWithDepositoRead])
async def list_persone(
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
    depot: str | None = Query(None, description="Filtra per codice deposito PdC"),
    profilo: str | None = Query(None, description="Filtra per profilo (PdC/CT/...)"),
    search: str | None = Query(None, description="Ricerca su nome/cognome/codice"),
    only_active: bool = Query(True, description="Solo matricole attive"),
) -> list[PersonaWithDepositoRead]:
    """Lista persone dell'azienda corrente, opzionalmente filtrabile.

    L'output è arricchito con:
    - codice/display_name del deposito di residenza (LEFT JOIN Depot)
    - tipo indisponibilità in corso oggi (subquery), o ``None`` se in servizio.
    """
    today = date_type.today()

    # Subquery: per ogni persona, l'indisponibilità approvata che include oggi.
    # Se più di una matcha (raro), l'ORM prende la prima — sufficiente per UI.
    indisp_subq = (
        select(
            IndisponibilitaPersona.persona_id,
            IndisponibilitaPersona.tipo,
        )
        .where(
            and_(
                IndisponibilitaPersona.data_inizio <= today,
                IndisponibilitaPersona.data_fine >= today,
                IndisponibilitaPersona.is_approvato.is_(True),
            )
        )
        .subquery("indisp_oggi")
    )

    stmt = (
        select(
            Persona.id,
            Persona.codice_dipendente,
            Persona.nome,
            Persona.cognome,
            Persona.profilo,
            Persona.is_matricola_attiva,
            Persona.data_assunzione,
            Persona.qualifiche_json,
            Depot.codice.label("depot_codice"),
            Depot.display_name.label("depot_display_name"),
            indisp_subq.c.tipo.label("indisp_tipo"),
        )
        .select_from(Persona)
        .outerjoin(Depot, Depot.id == Persona.sede_residenza_id)
        .outerjoin(indisp_subq, indisp_subq.c.persona_id == Persona.id)
        .where(Persona.azienda_id == user.azienda_id)
        .order_by(Persona.cognome, Persona.nome)
    )

    if only_active:
        stmt = stmt.where(Persona.is_matricola_attiva.is_(True))
    if depot is not None:
        stmt = stmt.where(Depot.codice == depot)
    if profilo is not None:
        stmt = stmt.where(Persona.profilo == profilo)
    if search is not None and search.strip():
        like = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Persona.nome).like(like),
                func.lower(Persona.cognome).like(like),
                func.lower(Persona.codice_dipendente).like(like),
            )
        )

    result = await session.execute(stmt)
    rows = result.all()

    return [
        PersonaWithDepositoRead(
            id=r.id,
            codice_dipendente=r.codice_dipendente,
            nome=r.nome,
            cognome=r.cognome,
            profilo=r.profilo,
            is_matricola_attiva=r.is_matricola_attiva,
            data_assunzione=r.data_assunzione,
            depot_codice=r.depot_codice,
            depot_display_name=r.depot_display_name,
            qualifiche=list(r.qualifiche_json or []),
            indisponibilita_oggi=r.indisp_tipo,
        )
        for r in rows
    ]


@router.get("/persone/{persona_id}", response_model=PersonaWithDepositoRead)
async def get_persona(
    persona_id: int,
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> PersonaWithDepositoRead:
    """Scheda persona singola con deposito + indisponibilità in corso."""
    today = date_type.today()

    indisp_subq = (
        select(
            IndisponibilitaPersona.persona_id,
            IndisponibilitaPersona.tipo,
        )
        .where(
            and_(
                IndisponibilitaPersona.data_inizio <= today,
                IndisponibilitaPersona.data_fine >= today,
                IndisponibilitaPersona.is_approvato.is_(True),
            )
        )
        .subquery("indisp_oggi_one")
    )

    stmt = (
        select(
            Persona.id,
            Persona.codice_dipendente,
            Persona.nome,
            Persona.cognome,
            Persona.profilo,
            Persona.is_matricola_attiva,
            Persona.data_assunzione,
            Persona.qualifiche_json,
            Depot.codice.label("depot_codice"),
            Depot.display_name.label("depot_display_name"),
            indisp_subq.c.tipo.label("indisp_tipo"),
        )
        .select_from(Persona)
        .outerjoin(Depot, Depot.id == Persona.sede_residenza_id)
        .outerjoin(indisp_subq, indisp_subq.c.persona_id == Persona.id)
        .where(
            and_(
                Persona.id == persona_id,
                Persona.azienda_id == user.azienda_id,
            )
        )
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Persona non trovata")

    return PersonaWithDepositoRead(
        id=row.id,
        codice_dipendente=row.codice_dipendente,
        nome=row.nome,
        cognome=row.cognome,
        profilo=row.profilo,
        is_matricola_attiva=row.is_matricola_attiva,
        data_assunzione=row.data_assunzione,
        depot_codice=row.depot_codice,
        depot_display_name=row.depot_display_name,
        qualifiche=list(row.qualifiche_json or []),
        indisponibilita_oggi=row.indisp_tipo,
    )


# ─────────────────────────────────────────────────────────────────────
# /api/depots/{codice}/persone
# ─────────────────────────────────────────────────────────────────────


@router.get("/depots/{depot_codice}/persone", response_model=list[PersonaWithDepositoRead])
async def list_persone_by_depot(
    depot_codice: str,
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> list[PersonaWithDepositoRead]:
    """PdC residenti in un deposito specifico (drilldown dashboard depositi)."""
    return await list_persone(
        user=user,
        session=session,
        depot=depot_codice,
        profilo=None,
        search=None,
        only_active=True,
    )


# ─────────────────────────────────────────────────────────────────────
# /api/indisponibilita
# ─────────────────────────────────────────────────────────────────────


@router.get("/indisponibilita", response_model=list[IndisponibilitaWithPersonaRead])
async def list_indisponibilita(
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
    tipo: str | None = Query(None, description="ferie/malattia/ROL/sciopero/formazione/congedo"),
    attive_oggi: bool = Query(False, description="Solo quelle in corso oggi"),
    depot: str | None = Query(None, description="Filtra per deposito persona"),
) -> list[IndisponibilitaWithPersonaRead]:
    """Lista indisponibilità arricchite con anagrafica persona e deposito."""
    today = date_type.today()

    stmt = (
        select(
            IndisponibilitaPersona.id,
            IndisponibilitaPersona.persona_id,
            IndisponibilitaPersona.tipo,
            IndisponibilitaPersona.data_inizio,
            IndisponibilitaPersona.data_fine,
            IndisponibilitaPersona.is_approvato,
            IndisponibilitaPersona.note,
            Persona.nome.label("persona_nome"),
            Persona.cognome.label("persona_cognome"),
            Persona.codice_dipendente.label("persona_codice"),
            Depot.codice.label("depot_codice"),
            Depot.display_name.label("depot_display_name"),
        )
        .select_from(IndisponibilitaPersona)
        .join(Persona, Persona.id == IndisponibilitaPersona.persona_id)
        .outerjoin(Depot, Depot.id == Persona.sede_residenza_id)
        .where(Persona.azienda_id == user.azienda_id)
        .order_by(IndisponibilitaPersona.data_inizio.desc())
    )
    if tipo is not None:
        stmt = stmt.where(IndisponibilitaPersona.tipo == tipo)
    if attive_oggi:
        stmt = stmt.where(
            and_(
                IndisponibilitaPersona.data_inizio <= today,
                IndisponibilitaPersona.data_fine >= today,
            )
        )
    if depot is not None:
        stmt = stmt.where(Depot.codice == depot)

    rows = (await session.execute(stmt)).all()
    return [
        IndisponibilitaWithPersonaRead(
            id=r.id,
            persona_id=r.persona_id,
            persona_nome=r.persona_nome,
            persona_cognome=r.persona_cognome,
            persona_codice_dipendente=r.persona_codice,
            depot_codice=r.depot_codice,
            depot_display_name=r.depot_display_name,
            tipo=r.tipo,
            data_inizio=r.data_inizio,
            data_fine=r.data_fine,
            giorni_totali=(r.data_fine - r.data_inizio).days + 1,
            is_approvato=r.is_approvato,
            note=r.note,
        )
        for r in rows
    ]


# ─────────────────────────────────────────────────────────────────────
# /api/gestione-personale/kpi  (riepilogativo)
# ─────────────────────────────────────────────────────────────────────


@router.get("/gestione-personale/kpi", response_model=GestionePersonaleKpiRead)
async def get_kpi(
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> GestionePersonaleKpiRead:
    """KPI riepilogativi cross-azienda."""
    today = date_type.today()

    # Totale matricole attive
    total_stmt = select(func.count()).select_from(Persona).where(
        and_(
            Persona.azienda_id == user.azienda_id,
            Persona.is_matricola_attiva.is_(True),
        )
    )
    persone_attive = int((await session.execute(total_stmt)).scalar_one() or 0)

    # Conteggio per categoria delle indisponibilità in corso oggi
    cat_stmt = (
        select(
            IndisponibilitaPersona.tipo,
            func.count().label("n"),
        )
        .select_from(IndisponibilitaPersona)
        .join(Persona, Persona.id == IndisponibilitaPersona.persona_id)
        .where(
            and_(
                Persona.azienda_id == user.azienda_id,
                Persona.is_matricola_attiva.is_(True),
                IndisponibilitaPersona.data_inizio <= today,
                IndisponibilitaPersona.data_fine >= today,
                IndisponibilitaPersona.is_approvato.is_(True),
            )
        )
        .group_by(IndisponibilitaPersona.tipo)
    )
    in_ferie = 0
    in_malattia = 0
    in_rol = 0
    in_altra = 0
    for r in (await session.execute(cat_stmt)).all():
        cat = _categoria_assenza(r.tipo)
        if cat == "ferie":
            in_ferie += int(r.n)
        elif cat == "malattia":
            in_malattia += int(r.n)
        elif cat == "rol":
            in_rol += int(r.n)
        else:
            in_altra += int(r.n)

    indisponibili = in_ferie + in_malattia + in_rol + in_altra
    in_servizio = max(0, persone_attive - indisponibili)
    copertura = (in_servizio / persone_attive * 100.0) if persone_attive > 0 else 0.0

    return GestionePersonaleKpiRead(
        persone_attive=persone_attive,
        in_servizio_oggi=in_servizio,
        in_ferie=in_ferie,
        in_malattia=in_malattia,
        in_rol=in_rol,
        in_altra_assenza=in_altra,
        copertura_pct=round(copertura, 1),
    )


# ─────────────────────────────────────────────────────────────────────
# /api/gestione-personale/kpi-depositi  (breakdown per deposito)
# ─────────────────────────────────────────────────────────────────────


@router.get(
    "/gestione-personale/kpi-depositi",
    response_model=list[GestionePersonaleKpiPerDepositoRead],
)
async def get_kpi_depositi(
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> list[GestionePersonaleKpiPerDepositoRead]:
    """KPI breakdown per deposito PdC dell'azienda corrente.

    Restituisce **tutti** i depositi dell'azienda (anche quelli senza
    persone assegnate, con count 0) — utile per la dashboard a griglia
    completa. Ordinati alfabeticamente per ``codice``.
    """
    today = date_type.today()

    indisp_oggi_subq = (
        select(IndisponibilitaPersona.persona_id)
        .where(
            and_(
                IndisponibilitaPersona.data_inizio <= today,
                IndisponibilitaPersona.data_fine >= today,
                IndisponibilitaPersona.is_approvato.is_(True),
            )
        )
        .subquery("indisp_oggi_pids")
    )

    stmt = (
        select(
            Depot.codice,
            Depot.display_name,
            func.count(Persona.id).label("attivi"),
            func.sum(
                case(
                    (indisp_oggi_subq.c.persona_id.is_not(None), 1),
                    else_=0,
                )
            ).label("indisponibili"),
        )
        .select_from(Depot)
        .outerjoin(
            Persona,
            and_(
                Persona.sede_residenza_id == Depot.id,
                Persona.is_matricola_attiva.is_(True),
                Persona.azienda_id == user.azienda_id,
            ),
        )
        .outerjoin(indisp_oggi_subq, indisp_oggi_subq.c.persona_id == Persona.id)
        .where(Depot.azienda_id == user.azienda_id)
        .group_by(Depot.codice, Depot.display_name)
        .order_by(Depot.codice)
    )

    result = []
    for r in (await session.execute(stmt)).all():
        attivi = int(r.attivi or 0)
        indisp = int(r.indisponibili or 0)
        in_servizio = max(0, attivi - indisp)
        copertura = (in_servizio / attivi * 100.0) if attivi > 0 else 0.0
        result.append(
            GestionePersonaleKpiPerDepositoRead(
                depot_codice=r.codice,
                depot_display_name=r.display_name,
                persone_attive=attivi,
                in_servizio_oggi=in_servizio,
                indisponibili_oggi=indisp,
                copertura_pct=round(copertura, 1),
            )
        )
    return result
