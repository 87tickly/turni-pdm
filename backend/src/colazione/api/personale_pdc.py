"""Route HTTP — vista PdC finale (Sprint 8.0 MR 3, entry 168).

Apre il 5° ruolo dell'ecosistema (``PERSONALE_PDC``): il singolo
macchinista vede il proprio turno, filtrato per ``programma_materiale.
stato_pipeline_pdc == VISTA_PUBBLICATA``. Se il programma non è ancora
pubblicato, il PdC non vede nulla — l'output del lavoro di Pianificatori
e Gestione Personale è "consegnato" solo al raggiungimento dello stato
terminale del ramo.

Endpoint:

- ``GET /api/personale-pdc/mio-turno`` — lista assegnazioni-giornata
  della persona collegata all'utente loggato, filtrate per turni di
  programmi in ``VISTA_PUBBLICATA``. Per ogni assegnazione: data, codice
  turno, numero giornata, ora inizio/fine, KPI minuti.

Multi-tenant via ``user.azienda_id``. Se l'utente non ha una persona
associata (``persona.user_id IS NULL`` o non esiste persona con
``user_id == user.user_id``), la response è ``204 No Content`` con
nessun body — coerente con "nessun turno da mostrare".
"""

from __future__ import annotations

from datetime import date, time

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, cast, select
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.auth import require_any_role
from colazione.db import get_session
from colazione.domain.pipeline import StatoPipelinePdc
from colazione.models.giri import GiroMateriale
from colazione.models.personale import AssegnazioneGiornata, Persona
from colazione.models.programmi import ProgrammaMateriale
from colazione.models.turni_pdc import TurnoPdc, TurnoPdcGiornata
from colazione.schemas.security import CurrentUser

router = APIRouter(prefix="/api/personale-pdc", tags=["personale-pdc"])

# Lettura ammessa al PdC titolare + admin/PIANIFICATORE_PDC per debug.
# Niente endpoint di scrittura in MR 3: il personale NON modifica le
# proprie assegnazioni.
_authz = Depends(
    require_any_role("PERSONALE_PDC", "PIANIFICATORE_PDC")
)


class MioTurnoGiornata(BaseModel):
    """Una giornata di assegnazione per la vista personale."""

    model_config = ConfigDict(from_attributes=True)

    assegnazione_id: int
    data: date
    stato_assegnazione: str
    turno_pdc_id: int
    turno_codice: str
    turno_impianto: str
    numero_giornata: int
    variante_calendario: str
    inizio_prestazione: time | None
    fine_prestazione: time | None
    prestazione_min: int
    condotta_min: int
    refezione_min: int
    is_notturno: bool
    is_riposo: bool


@router.get(
    "/mio-turno",
    response_model=list[MioTurnoGiornata],
    summary="Le mie assegnazioni-giornata (turni in VISTA_PUBBLICATA)",
)
async def get_mio_turno(
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> list[MioTurnoGiornata]:
    """Restituisce le giornate assegnate alla persona collegata
    all'utente loggato, ordinate per data.

    Filtro applicato: solo turni il cui programma proprietario è in
    stato ``VISTA_PUBBLICATA`` (terminale del ramo PdC). I programmi
    pre-pubblicazione restano invisibili al PdC anche se gli sono già
    state assegnate giornate dal Gestione Personale (caso transitorio
    ammesso, vedi MR 2).
    """
    persona_id = (
        await session.execute(
            select(Persona.id).where(
                Persona.user_id == user.user_id,
                Persona.azienda_id == user.azienda_id,
            )
        )
    ).scalar_one_or_none()
    if persona_id is None:
        # Nessuna persona collegata → nessun turno. 200 con [] è più
        # ergonomico per il frontend (no branch di gestione 204/404).
        return []

    # Sub-query dei giri-materiali appartenenti a programmi pubblicati.
    # ON CONFLICT con turni "legacy" senza giro_materiale_id nei
    # metadata: il cast NULL → ``IN (...)`` ritorna NULL = false, quindi
    # quei turni vengono esclusi (atteso: niente pubblicazione → niente
    # vista PdC).
    giri_pubblicati_subq = (
        select(GiroMateriale.id)
        .join(
            ProgrammaMateriale,
            ProgrammaMateriale.id == GiroMateriale.programma_id,
        )
        .where(
            GiroMateriale.azienda_id == user.azienda_id,
            ProgrammaMateriale.stato_pipeline_pdc
            == StatoPipelinePdc.VISTA_PUBBLICATA.value,
        )
        .scalar_subquery()
    )

    stmt = (
        select(
            AssegnazioneGiornata.id.label("assegnazione_id"),
            AssegnazioneGiornata.data,
            AssegnazioneGiornata.stato.label("stato_assegnazione"),
            TurnoPdc.id.label("turno_pdc_id"),
            TurnoPdc.codice.label("turno_codice"),
            TurnoPdc.impianto.label("turno_impianto"),
            TurnoPdcGiornata.numero_giornata,
            TurnoPdcGiornata.variante_calendario,
            TurnoPdcGiornata.inizio_prestazione,
            TurnoPdcGiornata.fine_prestazione,
            TurnoPdcGiornata.prestazione_min,
            TurnoPdcGiornata.condotta_min,
            TurnoPdcGiornata.refezione_min,
            TurnoPdcGiornata.is_notturno,
            TurnoPdcGiornata.is_riposo,
        )
        .join(
            TurnoPdcGiornata,
            TurnoPdcGiornata.id == AssegnazioneGiornata.turno_pdc_giornata_id,
        )
        .join(TurnoPdc, TurnoPdc.id == TurnoPdcGiornata.turno_pdc_id)
        .where(
            AssegnazioneGiornata.persona_id == persona_id,
            TurnoPdc.azienda_id == user.azienda_id,
            cast(
                TurnoPdc.generation_metadata_json["giro_materiale_id"].astext,
                BigInteger,
            ).in_(giri_pubblicati_subq),
        )
        .order_by(AssegnazioneGiornata.data, TurnoPdcGiornata.numero_giornata)
    )
    rows = (await session.execute(stmt)).all()
    return [
        MioTurnoGiornata(
            assegnazione_id=r.assegnazione_id,
            data=r.data,
            stato_assegnazione=r.stato_assegnazione,
            turno_pdc_id=r.turno_pdc_id,
            turno_codice=r.turno_codice,
            turno_impianto=r.turno_impianto,
            numero_giornata=r.numero_giornata,
            variante_calendario=r.variante_calendario,
            inizio_prestazione=r.inizio_prestazione,
            fine_prestazione=r.fine_prestazione,
            prestazione_min=r.prestazione_min,
            condotta_min=r.condotta_min,
            refezione_min=r.refezione_min,
            is_notturno=r.is_notturno,
            is_riposo=r.is_riposo,
        )
        for r in rows
    ]


__all__ = ["router", "MioTurnoGiornata"]


_ = status  # keep import for potential 4xx codes added later
