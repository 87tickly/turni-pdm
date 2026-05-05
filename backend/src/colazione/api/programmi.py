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

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, and_, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from colazione.auth import require_admin, require_any_role, require_role
from colazione.db import get_session
from colazione.domain.calendario import festivita_italiane, tipo_giorno
from colazione.domain.normativa.assegnazione_persone import (
    AssegnazioneEsistente,
    GiornataDaAssegnare,
    IndisponibilitaPeriodo,
    PersonaCandidata,
    auto_assegna,
)
from colazione.domain.pipeline import (
    StatoManutenzione,
    StatoPipelinePdc,
    TransizioneNonAmmessaError,
    materiale_freezato,
    programma_visibile_per_ruoli,
    soglia_pipeline_per_ruoli,
    stati_pdc_da,
    stato_manutenzione_precedente,
    stato_pdc_precedente,
    valida_transizione_manutenzione,
    valida_transizione_pdc,
)
from colazione.models.anagrafica import Depot, FestivitaUfficiale
from colazione.models.corse import CorsaImportRun
from colazione.models.giri import GiroMateriale
from colazione.models.personale import (
    AssegnazioneGiornata,
    IndisponibilitaPersona,
    Persona,
)
from colazione.models.programmi import (
    BuilderRun,
    ProgrammaMateriale,
    ProgrammaRegolaAssegnazione,
)
from colazione.models.turni_pdc import TurnoPdc, TurnoPdcGiornata
from colazione.schemas.corse import CorsaImportRunRead
from colazione.schemas.programmi import (
    AssegnazioneCreataRead,
    AutoAssegnaPersoneRequest,
    AutoAssegnaPersoneResponse,
    MancanzaRead,
    ProgrammaMaterialeCreate,
    ProgrammaMaterialeRead,
    ProgrammaMaterialeUpdate,
    ProgrammaRegolaAssegnazioneCreate,
    ProgrammaRegolaAssegnazioneRead,
    SbloccaProgrammaRequest,
    VariazionePdERequest,
    WarningSoftRead,
)
from colazione.schemas.security import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/programmi", tags=["programmi"])


# Tutti gli endpoint richiedono PIANIFICATORE_GIRO (admin bypassa via require_role).
_authz = Depends(require_role("PIANIFICATORE_GIRO"))

# Sprint 8.0 MR 0 (entry 164): deps dedicate per gli endpoint pipeline.
# Estratte a modulo-livello per evitare warning ruff B008 (function call
# in argument default) e per chiarire il mapping endpoint → ruolo.
_authz_pdc = Depends(require_role("PIANIFICATORE_PDC"))
_authz_personale = Depends(require_role("GESTIONE_PERSONALE"))
_authz_manutenzione = Depends(require_role("MANUTENZIONE"))
_authz_admin = Depends(require_admin())

# Sprint 8.0 MR 0: list/detail di programmi sono leggibili da tutti i 4
# ruoli pipeline (PdC, Personale, Manutenzione oltre a Giro Materiale).
# La visibilità per stato_pipeline_pdc è applicata nel body della route
# via ``soglia_pipeline_per_ruoli``.
_authz_view = Depends(
    require_any_role(
        "PIANIFICATORE_GIRO",
        "PIANIFICATORE_PDC",
        "GESTIONE_PERSONALE",
        "MANUTENZIONE",
    )
)


def _programma_visibile_per_user(
    programma: ProgrammaMateriale, user: CurrentUser
) -> bool:
    """Wrapper ORM intorno a :func:`programma_visibile_per_ruoli`."""
    return programma_visibile_per_ruoli(
        programma.stato_pipeline_pdc, user.roles, user.is_admin
    )


def _verifica_modificabile_o_409(programma: ProgrammaMateriale) -> None:
    """Solleva ``HTTPException(409)`` se il programma è in stato che
    congela parametri/regole/giri del ramo Materiale.

    Sprint 8.0 MR 1 (entry 165): freeze read-only post
    ``MATERIALE_CONFERMATO``. Per modificare oltre quella soglia,
    l'admin deve prima chiamare ``POST /programmi/{id}/sblocca``
    (regressione a ``MATERIALE_GENERATO``).
    """
    if materiale_freezato(programma.stato_pipeline_pdc):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"programma in stato pipeline {programma.stato_pipeline_pdc!r} "
                "(>= MATERIALE_CONFERMATO): regole, parametri e giri sono "
                "read-only. Per modificare richiedi a un admin POST "
                "/api/programmi/{id}/sblocca."
            ),
        )


# =====================================================================
# Helpers
# =====================================================================


async def _get_programma_or_404(
    session: AsyncSession,
    programma_id: int,
    azienda_id: int,
    *,
    for_update: bool = False,
) -> ProgrammaMateriale:
    """Carica un programma se esiste E appartiene all'azienda corrente.

    Sprint 8.0 MR 0 (entry 164): supporto opzionale ``SELECT ... FOR
    UPDATE`` per le route di transizione di stato. Senza row-lock, due
    chiamate concorrenti su rami diversi (es. ``sblocca`` + ``conferma-pdc``
    sullo stesso programma) potrebbero leggere lo stesso snapshot pre-
    transizione e l'ultima vincere, rendendo invisibile la transizione
    intermedia. Con ``for_update=True`` la seconda chiamata si serializza
    sul commit della prima.
    """
    stmt = (
        select(ProgrammaMateriale)
        .where(
            ProgrammaMateriale.id == programma_id,
            ProgrammaMateriale.azienda_id == azienda_id,
        )
        .limit(1)
    )
    if for_update:
        stmt = stmt.with_for_update()
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
    user: CurrentUser = _authz_view,
    session: AsyncSession = Depends(get_session),
    stato: str | None = Query(default=None, description="filtro per stato"),
) -> list[ProgrammaMateriale]:
    """Lista programmi dell'azienda corrente. Ordinati `valido_da DESC`.

    Eager-load `created_by` per popolare `created_by_username` nella
    response (entry 88 — schermata 3 design `arturo/03-dettaglio-programma.html`).

    Sprint 8.0 MR 0 (entry 164): filtro per ruolo via
    :func:`soglia_pipeline_per_ruoli`. PIANIFICATORE_GIRO + admin
    vedono tutto; gli altri ruoli vedono solo programmi con
    ``stato_pipeline_pdc >= soglia(ruolo)``.
    """
    stmt = (
        select(ProgrammaMateriale)
        .options(joinedload(ProgrammaMateriale.created_by))
        .where(ProgrammaMateriale.azienda_id == user.azienda_id)
    )
    if stato is not None:
        stmt = stmt.where(ProgrammaMateriale.stato == stato)
    soglia = soglia_pipeline_per_ruoli(user.roles, user.is_admin)
    if soglia is not None:
        stmt = stmt.where(
            ProgrammaMateriale.stato_pipeline_pdc.in_(stati_pdc_da(soglia))
        )
    stmt = stmt.order_by(ProgrammaMateriale.valido_da.desc())
    return list((await session.execute(stmt)).scalars().all())


class ProgrammaDettaglioRead(ProgrammaMaterialeRead):
    """Estende `Read` con la lista di regole."""

    regole: list[ProgrammaRegolaAssegnazioneRead] = []


@router.get("/{programma_id}", response_model=ProgrammaDettaglioRead)
async def get_programma(
    programma_id: int,
    user: CurrentUser = _authz_view,
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    """Dettaglio del programma + lista regole (eager loading via 1 query).

    Sprint 8.0 MR 0: 404 (privacy multi-tenant) anche se il programma
    esiste ma è invisibile per ruolo (vedi
    :func:`_programma_visibile_per_user`).
    """
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
    if p is None or not _programma_visibile_per_user(p, user):
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

    Sprint 8.0 MR 1: 409 se ``stato_pipeline_pdc >= MATERIALE_CONFERMATO``
    (parametri freezati al handoff Materiale → PdC).
    """
    p = await _get_programma_or_404(session, programma_id, user.azienda_id)
    _verifica_modificabile_o_409(p)

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
    - programma NON deve essere `archiviato` (read-only). Bozza e attivo
      sono entrambi modificabili (Sprint 7.9 MR 13, entry 119): dopo
      modifica delle regole su programma attivo l'utente rigenera i
      giri con `force=true` per allineare l'output.

    Entry 96: i vincoli HARD a livello tipo materiale non sono più
    applicati qui. Il pianificatore può creare regole "ampie"; il
    builder filtra a runtime con ``risolvi_corsa``.

    Sprint 8.0 MR 1: 409 se ``stato_pipeline_pdc >= MATERIALE_CONFERMATO``.
    """
    p = await _get_programma_or_404(session, programma_id, user.azienda_id)
    if p.stato == "archiviato":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="programma archiviato: regole non modificabili",
        )
    _verifica_modificabile_o_409(p)

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
    """Cancella una regola. Solo `archiviato` blocca la cancellazione
    (Sprint 7.9 MR 13, entry 119).

    Sprint 8.0 MR 1: 409 se ``stato_pipeline_pdc >= MATERIALE_CONFERMATO``.
    """
    p = await _get_programma_or_404(session, programma_id, user.azienda_id)
    if p.stato == "archiviato":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="programma archiviato: regole non cancellabili",
        )
    _verifica_modificabile_o_409(p)

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
# Pipeline state machine (Sprint 8.0 MR 0, entry 164)
# =====================================================================
#
# Ogni endpoint sotto è un "trigger" di transizione: niente body
# obbligatorio (eccetto sblocca, dove l'admin può tracciare un motivo).
# La validazione applicativa vive in ``colazione.domain.pipeline``;
# il DB ha CHECK constraint sui valori ammessi.
#
# Effetto collaterale documentato di ``conferma-materiale``: se il ramo
# manutenzione è ancora ``IN_ATTESA`` viene attivato in ``IN_LAVORAZIONE``.
# Coerente con la spec MR 0: il ramo manutenzione "si attiva quando
# stato_pipeline_pdc >= MATERIALE_CONFERMATO".
#
# Scope rinviato a MR 1: freeze read-only delle regole/giri al
# ``MATERIALE_CONFERMATO`` e invalidazione cache delle list-route giri
# dipendenti.
#


async def _transizione_pdc(
    session: AsyncSession,
    programma: ProgrammaMateriale,
    target: StatoPipelinePdc,
) -> None:
    """Helper: valida e applica una transizione del ramo PdC.

    Centralizza il pattern parse → valida → assegna usato dai 4
    endpoint di conferma pipeline (materiale, pdc, personale, vista).
    Solleva ``HTTPException(400)`` con il messaggio di
    :class:`TransizioneNonAmmessaError` se la transizione non è ammessa.
    """
    corrente = StatoPipelinePdc(programma.stato_pipeline_pdc)
    try:
        valida_transizione_pdc(corrente, target)
    except TransizioneNonAmmessaError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    programma.stato_pipeline_pdc = target.value
    programma.updated_at = datetime.now(UTC)


@router.post(
    "/{programma_id}/conferma-materiale",
    response_model=ProgrammaMaterialeRead,
    summary="Pianificatore Materiale conferma il giro materiale",
)
async def conferma_materiale(
    programma_id: int,
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> ProgrammaMateriale:
    """Transizione ``PDE_CONSOLIDATO`` o ``MATERIALE_GENERATO`` →
    ``MATERIALE_CONFERMATO``.

    Side effect: se ``stato_manutenzione == IN_ATTESA``, viene portato
    a ``IN_LAVORAZIONE`` (ramo manutenzione si attiva).
    """
    p = await _get_programma_or_404(
        session, programma_id, user.azienda_id, for_update=True
    )
    await _transizione_pdc(session, p, StatoPipelinePdc.MATERIALE_CONFERMATO)
    if p.stato_manutenzione == StatoManutenzione.IN_ATTESA.value:
        p.stato_manutenzione = StatoManutenzione.IN_LAVORAZIONE.value
    await session.commit()
    await session.refresh(p)
    return p


@router.post(
    "/{programma_id}/conferma-pdc",
    response_model=ProgrammaMaterialeRead,
    summary="Pianificatore PdC conferma i turni PdC",
)
async def conferma_pdc(
    programma_id: int,
    user: CurrentUser = _authz_pdc,
    session: AsyncSession = Depends(get_session),
) -> ProgrammaMateriale:
    """Transizione ``PDC_GENERATO`` → ``PDC_CONFERMATO``."""
    p = await _get_programma_or_404(
        session, programma_id, user.azienda_id, for_update=True
    )
    await _transizione_pdc(session, p, StatoPipelinePdc.PDC_CONFERMATO)
    await session.commit()
    await session.refresh(p)
    return p


@router.post(
    "/{programma_id}/conferma-personale",
    response_model=ProgrammaMaterialeRead,
    summary="Gestione Personale conferma le assegnazioni dei PdC",
)
async def conferma_personale(
    programma_id: int,
    user: CurrentUser = _authz_personale,
    session: AsyncSession = Depends(get_session),
) -> ProgrammaMateriale:
    """Transizione ``PDC_CONFERMATO`` → ``PERSONALE_ASSEGNATO``."""
    p = await _get_programma_or_404(
        session, programma_id, user.azienda_id, for_update=True
    )
    await _transizione_pdc(session, p, StatoPipelinePdc.PERSONALE_ASSEGNATO)
    await session.commit()
    await session.refresh(p)
    return p


# =====================================================================
# Auto-assegna persone — Sub-MR 2.bis-a (Sprint 8.0)
# =====================================================================


def _variante_matcha_tipo_giorno(variante: str, tipo: str) -> bool:
    """True se la ``variante_calendario`` di una ``TurnoPdcGiornata``
    copre il ``tipo`` calendariale di una data (feriale/sabato/domenica/festivo).

    Mapping pragmatico MVP — il campo ``variante_calendario`` (max 20
    char) deriva da ``GiroVariante.validita_testo`` che riprende il
    testo PdE grezzo (memoria utente: il PdE testo Periodicità è
    verità). Casi gestiti:

    - ``"GG"`` (default builder ``multi_turno.py``) → matches all
    - ``"LMXGV"`` / ``"LV"`` / token che inizia con ``"L"`` + giorno:
      → ``"feriale"`` (Lun-Ven)
    - ``"S"`` → ``"sabato"``
    - ``"D"`` → ``"domenica"``
    - ``"F"`` (e prefissi ``"FE"``/``"FEST"``) → ``"festivo"``
    - ``"SD"`` → ``"sabato"`` o ``"domenica"``

    **Fallback unknown**: una ``variante_calendario`` non riconosciuta
    matcha qualsiasi tipo (comportamento liberale "GG-like"). Decisione
    MVP per non bloccare l'algoritmo su varianti future; eventuali
    sovra-assegnazioni emergono come warning soft (riposo settimanale).
    Caso da rivisitare in 2.bis-c se si osservano problemi reali.
    """
    v = variante.strip().upper()
    if v in {"GG", "TUTTI", "GIORNALMENTE", "G", "OGNI"}:
        return True
    if tipo == "feriale":
        if v in {"LV", "FE", "FERIALE", "LAVORATIVO"} or v.startswith("LM"):
            return True
        # "L" da solo o "L1:5" → feriale
        if v == "L" or v.startswith("L"):
            # Esclude "LMXGV" già catturato sopra; gestisce "L" / "LV"
            return True
        return False
    if tipo == "sabato":
        if v == "S" or v == "SAB" or v == "SABATO":
            return True
        if v == "SD":
            return True
        return False
    if tipo == "domenica":
        if v == "D" or v == "DOM" or v == "DOMENICA":
            return True
        if v == "SD":
            return True
        return False
    if tipo == "festivo":
        if v == "F" or v.startswith("FES"):
            return True
        return False
    # Fallback liberale: variante non riconosciuta → match
    return True


@router.post(
    "/{programma_id}/auto-assegna-persone",
    response_model=AutoAssegnaPersoneResponse,
    summary="Auto-assegna persone PdC alle giornate dei turni del programma",
)
async def auto_assegna_persone_endpoint(
    programma_id: int,
    payload: AutoAssegnaPersoneRequest,
    user: CurrentUser = _authz_personale,
    session: AsyncSession = Depends(get_session),
) -> AutoAssegnaPersoneResponse:
    """Esegue l'algoritmo greedy di auto-assegnazione persone alle
    giornate dei turni del programma (sub-MR 2.bis-a).

    **Pre-condizioni**:

    - Il programma esiste e appartiene all'azienda corrente.
    - ``stato_pipeline_pdc == PDC_CONFERMATO`` (else 409): l'algoritmo
      gira solo su programmi consolidati dal Pianificatore PdC.

    **Effetti**:

    - Inserisce nuove ``AssegnazioneGiornata`` per ogni
      ``(turno_pdc_giornata, data)`` slot non già coperto, scegliendo
      una persona compatibile con i vincoli HARD (sede, indisp,
      doppia assegnazione, riposo intraturno §11.5).
    - Le esistenti ``AssegnazioneGiornata`` (manuali o di run
      precedenti) sono rispettate, mai sovrascritte.

    **Output**: ``AutoAssegnaPersoneResponse`` con KPI
    ``delta_copertura_pct`` + lista mancanze + warning soft (FR cap
    §10.6, riposo settimanale §11.4, primo giorno post-riposo §11.2).

    **Idempotenza**: una seconda chiamata con stessa finestra produce
    0 nuove assegnazioni se nulla è cambiato (le esistenti già
    coprono ogni slot).
    """
    p = await _get_programma_or_404(
        session, programma_id, user.azienda_id, for_update=True
    )
    if p.stato_pipeline_pdc != StatoPipelinePdc.PDC_CONFERMATO.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"programma in stato pipeline {p.stato_pipeline_pdc!r}: "
                "auto-assegna richiede PDC_CONFERMATO"
            ),
        )

    # Finestra: payload o default = valido_da..valido_a
    data_da = payload.data_da or p.valido_da
    data_a = payload.data_a or p.valido_a or p.valido_da
    if data_da > data_a:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"finestra invalida: data_da {data_da.isoformat()} > data_a {data_a.isoformat()}",
        )

    # Festività: italiane fisse + mobili per gli anni della finestra,
    # + festività ufficiali da DB per la stessa azienda (se esistono).
    fest_set: set[date] = set()
    for anno in range(data_da.year, data_a.year + 1):
        for d_fest, _nome in festivita_italiane(anno):
            fest_set.add(d_fest)
    db_fest_rows = await session.execute(
        select(FestivitaUfficiale.data).where(
            and_(
                FestivitaUfficiale.data >= data_da,
                FestivitaUfficiale.data <= data_a,
                or_(
                    FestivitaUfficiale.azienda_id.is_(None),
                    FestivitaUfficiale.azienda_id == user.azienda_id,
                ),
            )
        )
    )
    for (d_fest,) in db_fest_rows.all():
        fest_set.add(d_fest)
    festivita_set: frozenset[date] = frozenset(fest_set)

    # Carica turni del programma + giornate non riposo + stazione deposito.
    # Filter via JSONB cast (pattern MR 3, entry 168).
    giri_subq = (
        select(GiroMateriale.id)
        .where(
            GiroMateriale.programma_id == programma_id,
            GiroMateriale.azienda_id == user.azienda_id,
        )
        .scalar_subquery()
    )
    turni_giornate_stmt = (
        select(
            TurnoPdc.id.label("turno_id"),
            TurnoPdc.deposito_pdc_id.label("deposito_id"),
            Depot.stazione_principale_codice.label("deposito_stazione"),
            TurnoPdcGiornata.id.label("giornata_id"),
            TurnoPdcGiornata.variante_calendario,
            TurnoPdcGiornata.inizio_prestazione,
            TurnoPdcGiornata.fine_prestazione,
            TurnoPdcGiornata.is_notturno,
            TurnoPdcGiornata.stazione_fine,
        )
        .join(TurnoPdcGiornata, TurnoPdcGiornata.turno_pdc_id == TurnoPdc.id)
        .join(Depot, Depot.id == TurnoPdc.deposito_pdc_id, isouter=True)
        .where(
            TurnoPdc.azienda_id == user.azienda_id,
            cast(
                TurnoPdc.generation_metadata_json["giro_materiale_id"].astext,
                BigInteger,
            ).in_(giri_subq),
            TurnoPdcGiornata.is_riposo.is_(False),
            TurnoPdcGiornata.inizio_prestazione.is_not(None),
            TurnoPdcGiornata.fine_prestazione.is_not(None),
            TurnoPdc.deposito_pdc_id.is_not(None),
        )
    )
    turni_rows = (await session.execute(turni_giornate_stmt)).all()

    # Espansione calendariale: una GiornataDaAssegnare per ogni
    # combinazione (giornata, data) dove la variante matcha.
    giornate_da_assegnare: list[GiornataDaAssegnare] = []
    deposito_ids: set[int] = set()
    for tr in turni_rows:
        deposito_ids.add(tr.deposito_id)
        is_fr = (
            tr.stazione_fine is not None
            and tr.deposito_stazione is not None
            and tr.stazione_fine != tr.deposito_stazione
        )
        d = data_da
        while d <= data_a:
            tipo = tipo_giorno(d, festivita_set)
            if _variante_matcha_tipo_giorno(tr.variante_calendario, tipo):
                giornate_da_assegnare.append(
                    GiornataDaAssegnare(
                        turno_pdc_giornata_id=tr.giornata_id,
                        turno_pdc_id=tr.turno_id,
                        data=d,
                        deposito_pdc_id=tr.deposito_id,
                        inizio_prestazione=tr.inizio_prestazione,
                        fine_prestazione=tr.fine_prestazione,
                        is_notturno=tr.is_notturno,
                        is_fr=is_fr,
                    )
                )
            d = d + timedelta(days=1)

    # Persone candidate: PdC attivi del/i deposito/i dei turni.
    persone_data: list[tuple[int, int]] = []
    if deposito_ids:
        persone_rows = await session.execute(
            select(Persona.id, Persona.sede_residenza_id).where(
                Persona.azienda_id == user.azienda_id,
                Persona.profilo == "PdC",
                Persona.is_matricola_attiva.is_(True),
                Persona.sede_residenza_id.in_(deposito_ids),
            )
        )
        persone_data = [
            (pr.id, pr.sede_residenza_id) for pr in persone_rows.all()
        ]
    persona_ids = [pid for pid, _sede in persone_data]

    # Indisponibilità approvate sovrapposte alla finestra.
    indisp_per_persona: dict[int, list[IndisponibilitaPeriodo]] = {}
    if persona_ids:
        indisp_rows = await session.execute(
            select(
                IndisponibilitaPersona.persona_id,
                IndisponibilitaPersona.data_inizio,
                IndisponibilitaPersona.data_fine,
            ).where(
                IndisponibilitaPersona.persona_id.in_(persona_ids),
                IndisponibilitaPersona.is_approvato.is_(True),
                IndisponibilitaPersona.data_fine >= data_da,
                IndisponibilitaPersona.data_inizio <= data_a,
            )
        )
        for ir in indisp_rows.all():
            indisp_per_persona.setdefault(ir.persona_id, []).append(
                IndisponibilitaPeriodo(
                    data_inizio=ir.data_inizio, data_fine=ir.data_fine
                )
            )
    persone_candidate = [
        PersonaCandidata(
            id=pid,
            sede_residenza_id=sede,
            indisponibilita=tuple(indisp_per_persona.get(pid, [])),
        )
        for pid, sede in persone_data
    ]

    # Assegnazioni esistenti sulle giornate del programma in finestra
    # (escluse le annullate). Usiamo (turno_pdc_giornata_id, data) come
    # marker di slot già coperto.
    giornate_ids = {g.turno_pdc_giornata_id for g in giornate_da_assegnare}
    assegnazioni_esistenti: list[AssegnazioneEsistente] = []
    if giornate_ids:
        esist_rows = await session.execute(
            select(
                AssegnazioneGiornata.persona_id,
                AssegnazioneGiornata.data,
                AssegnazioneGiornata.turno_pdc_giornata_id,
            ).where(
                AssegnazioneGiornata.turno_pdc_giornata_id.in_(giornate_ids),
                AssegnazioneGiornata.data >= data_da,
                AssegnazioneGiornata.data <= data_a,
                AssegnazioneGiornata.stato != "annullato",
            )
        )
        assegnazioni_esistenti = [
            AssegnazioneEsistente(
                persona_id=er.persona_id,
                data=er.data,
                turno_pdc_giornata_id=er.turno_pdc_giornata_id,
            )
            for er in esist_rows.all()
        ]

    # Esegui algoritmo (pure)
    risultato = auto_assegna(
        giornate=giornate_da_assegnare,
        persone=persone_candidate,
        assegnazioni_esistenti=assegnazioni_esistenti,
    )

    # Persistenza nuove assegnazioni
    for ass in risultato.assegnazioni:
        session.add(
            AssegnazioneGiornata(
                persona_id=ass.persona_id,
                data=ass.data,
                turno_pdc_giornata_id=ass.turno_pdc_giornata_id,
                stato="pianificato",
            )
        )
    await session.commit()

    return AutoAssegnaPersoneResponse(
        finestra_data_da=data_da,
        finestra_data_a=data_a,
        n_giornate_totali=risultato.n_giornate_totali,
        n_giornate_coperte=risultato.n_giornate_coperte,
        n_assegnazioni_create=len(risultato.assegnazioni),
        delta_copertura_pct=risultato.delta_copertura_pct,
        assegnazioni=[
            AssegnazioneCreataRead(
                persona_id=a.persona_id,
                turno_pdc_giornata_id=a.turno_pdc_giornata_id,
                data=a.data,
            )
            for a in risultato.assegnazioni
        ],
        mancanze=[
            MancanzaRead(
                turno_pdc_giornata_id=m.turno_pdc_giornata_id,
                turno_pdc_id=m.turno_pdc_id,
                data=m.data,
                motivo=m.motivo.value,
            )
            for m in risultato.mancanze
        ],
        warning_soft=[
            WarningSoftRead(
                persona_id=w.persona_id,
                data=w.data,
                tipo=w.tipo.value,
                descrizione=w.descrizione,
            )
            for w in risultato.warning_soft
        ],
    )


@router.post(
    "/{programma_id}/pubblica-vista-pdc",
    response_model=ProgrammaMaterialeRead,
    summary="Gestione Personale pubblica la vista PdC al personale finale",
)
async def pubblica_vista_pdc(
    programma_id: int,
    user: CurrentUser = _authz_personale,
    session: AsyncSession = Depends(get_session),
) -> ProgrammaMateriale:
    """Transizione ``PERSONALE_ASSEGNATO`` → ``VISTA_PUBBLICATA`` (terminale)."""
    p = await _get_programma_or_404(
        session, programma_id, user.azienda_id, for_update=True
    )
    await _transizione_pdc(session, p, StatoPipelinePdc.VISTA_PUBBLICATA)
    await session.commit()
    await session.refresh(p)
    return p


@router.post(
    "/{programma_id}/conferma-manutenzione",
    response_model=ProgrammaMaterialeRead,
    summary="Manutenzione conferma l'assegnazione delle matricole",
)
async def conferma_manutenzione(
    programma_id: int,
    user: CurrentUser = _authz_manutenzione,
    session: AsyncSession = Depends(get_session),
) -> ProgrammaMateriale:
    """Transizione ramo manutenzione ``IN_LAVORAZIONE`` →
    ``MATRICOLE_ASSEGNATE`` (terminale del ramo).

    Indipendente dal ramo PdC: non altera ``stato_pipeline_pdc``.
    """
    p = await _get_programma_or_404(
        session, programma_id, user.azienda_id, for_update=True
    )
    corrente = StatoManutenzione(p.stato_manutenzione)
    try:
        valida_transizione_manutenzione(
            corrente, StatoManutenzione.MATRICOLE_ASSEGNATE
        )
    except TransizioneNonAmmessaError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    p.stato_manutenzione = StatoManutenzione.MATRICOLE_ASSEGNATE.value
    p.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(p)
    return p


@router.post(
    "/{programma_id}/sblocca",
    response_model=ProgrammaMaterialeRead,
    summary="[admin] Sblocca un programma facendolo regredire allo stato precedente",
)
async def sblocca_programma(
    programma_id: int,
    payload: SbloccaProgrammaRequest,
    user: CurrentUser = _authz_admin,
    session: AsyncSession = Depends(get_session),
) -> ProgrammaMateriale:
    """Regressione di **uno step** sul ramo specificato (``pdc`` o
    ``manutenzione``). Solo admin.

    400 se il ramo è già al primo stato (niente precedente). Il motivo
    è opzionale ma viene loggato a livello WARNING per audit.

    Race condition mitigata via ``SELECT FOR UPDATE``: una sblocca
    concorrente ad una conferma viene serializzata.
    """
    p = await _get_programma_or_404(
        session, programma_id, user.azienda_id, for_update=True
    )
    if payload.ramo == "pdc":
        corrente_pdc = StatoPipelinePdc(p.stato_pipeline_pdc)
        prev_pdc = stato_pdc_precedente(corrente_pdc)
        if prev_pdc is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"ramo PdC già al primo stato ({corrente_pdc.value}): "
                    "niente da sbloccare"
                ),
            )
        p.stato_pipeline_pdc = prev_pdc.value
        nuovo_stato = prev_pdc.value
    else:
        corrente_man = StatoManutenzione(p.stato_manutenzione)
        prev_man = stato_manutenzione_precedente(corrente_man)
        if prev_man is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"ramo manutenzione già al primo stato "
                    f"({corrente_man.value}): niente da sbloccare"
                ),
            )
        p.stato_manutenzione = prev_man.value
        nuovo_stato = prev_man.value

    logger.warning(
        "sblocca programma id=%s ramo=%s nuovo_stato=%s motivo=%r admin=%s",
        p.id,
        payload.ramo,
        nuovo_stato,
        payload.motivo,
        user.username,
    )
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


# =====================================================================
# Variazioni PdE (Sprint 8.0 MR 5, entry 170)
# =====================================================================


@router.post(
    "/{programma_id}/variazioni",
    response_model=CorsaImportRunRead,
    status_code=status.HTTP_201_CREATED,
    summary="Registra una variazione del PdE (INTEGRAZIONE/VARIAZIONE_*)",
)
async def registra_variazione_pde(
    programma_id: int,
    payload: VariazionePdERequest,
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> CorsaImportRun:
    """Registra una ``CorsaImportRun`` di tipo non-BASE collegata al
    programma.

    Sprint 8.0 MR 5 (entry 170): cattura **i metadati** della variazione
    (tipo, file sorgente, count). La **logica concreta** di applicazione
    (cancellare/modificare/aggiungere ``CorsaCommerciale``) è scope MR
    5.bis. Le variazioni sono ammesse anche post ``MATERIALE_CONFERMATO``
    perché il PdE Trenord cambia in corso d'anno (interruzioni linee,
    integrazioni servizi); il freeze del MR 1 si applica alle regole/
    parametri/giri *del programma*, non al PdE base.

    Auth: ``PIANIFICATORE_GIRO`` (admin bypassa).
    """
    p = await _get_programma_or_404(session, programma_id, user.azienda_id)
    run = CorsaImportRun(
        source_file=payload.source_file,
        n_corse=payload.n_corse,
        n_corse_create=0,
        n_corse_update=0,
        azienda_id=p.azienda_id,
        programma_materiale_id=p.id,
        tipo=payload.tipo,
        note=payload.note,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


@router.get(
    "/{programma_id}/variazioni",
    response_model=list[CorsaImportRunRead],
    summary="Lista variazioni del PdE registrate per il programma",
)
async def list_variazioni_pde(
    programma_id: int,
    user: CurrentUser = _authz_view,
    session: AsyncSession = Depends(get_session),
) -> list[CorsaImportRun]:
    """Storico delle ``CorsaImportRun`` collegate al programma.

    Include il run BASE (l'import originale, se è stato collegato al
    programma) + tutte le variazioni successive. Ordinato per
    ``started_at DESC`` (più recente in cima).

    Visibile a tutti i 4 ruoli pipeline (filter list-route applicato
    sul programma a monte: 404 se invisibile per ruolo).
    """
    p = await _get_programma_or_404(session, programma_id, user.azienda_id)
    if not _programma_visibile_per_user(p, user):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="programma non trovato"
        )
    stmt = (
        select(CorsaImportRun)
        .where(
            CorsaImportRun.programma_materiale_id == p.id,
            CorsaImportRun.azienda_id == user.azienda_id,
        )
        .order_by(CorsaImportRun.started_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())
