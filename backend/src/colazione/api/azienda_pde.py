"""Route HTTP per il PdE livello azienda — Sub-MR 5.bis-d (entry 177).

Il PdE Trenord è un singolo file annuale per azienda (~10580 corse,
validità 14/12 → 12/12 dell'anno successivo). Le variazioni infrannuali
si accumulano cronologicamente.

Endpoint forniti:

- ``GET /api/aziende/me/pde/status`` — stato corrente: ultimo BASE +
  count variazioni + range validità. Per il pannello "PdE Annuale"
  della dashboard PIANIFICATORE_GIRO.
- ``POST /api/aziende/me/pde/base`` — multipart upload PdE base
  (``.numbers`` o ``.xlsx``). Wrappa ``importers.pde_importer.importa_pde``
  (CLI-equivalent). Idempotente per SHA-256 file.
- ``GET /api/aziende/me/variazioni`` — timeline variazioni globali
  (``programma_materiale_id IS NULL``).
- ``POST /api/aziende/me/variazioni`` — registra metadati di una
  variazione globale (parallelo a
  ``POST /api/programmi/{id}/variazioni`` ma a livello azienda).
- ``POST /api/aziende/me/variazioni/{run_id}/applica`` — multipart
  upload file PdE incrementale + applica al DB. Riusa gli helper
  privati di ``api.programmi`` (``_carica_corse_esistenti``,
  ``_to_parsed_target``, ``_planner_per_tipo``, ``_applica_operazioni``)
  per evitare duplicazione di logica.

**Auth**: tutti gli endpoint richiedono ``PIANIFICATORE_GIRO``
(l'admin bypassa).

**Multi-tenant**: ``azienda_id`` dal JWT (``CurrentUser.azienda_id``),
mai dal client. Path usa ``me`` come marker semantico.
"""

from __future__ import annotations

import logging
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.api.programmi import (
    _applica_operazioni,
    _carica_corse_esistenti,
    _planner_per_tipo,
    _to_parsed_target,
)
from colazione.api.variazioni_impatto import (
    calcola_impatto_su_programmi,
    estrai_corse_ids_da_risultato_pianificazione,
)
from colazione.auth import require_role
from colazione.db import get_session
from colazione.importers.pde import (
    parse_corsa_row,
    read_pde_file,
)
from colazione.importers.pde_importer import (
    compute_row_hash,
    importa_pde,
)
from colazione.models.anagrafica import Azienda
from colazione.models.corse import CorsaCommerciale, CorsaImportRun
from colazione.models.programmi import ProgrammaMateriale
from colazione.schemas.corse import CorsaImportRunRead
from colazione.schemas.programmi import (
    ApplicaVariazionePdEResponse,
    CaricaPdEBaseResponse,
    CreaForkVariazioneRequest,
    PdEStatusRead,
    ProgrammaMaterialeRead,
    VariazionePdERequest,
)
from colazione.schemas.security import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/aziende/me", tags=["azienda-pde"])

#: Auth dep: solo ``PIANIFICATORE_GIRO`` (admin bypassa via require_role).
_authz = Depends(require_role("PIANIFICATORE_GIRO"))


# =====================================================================
# Helpers
# =====================================================================


async def _get_azienda_codice(session: AsyncSession, azienda_id: int) -> str:
    """Lookup ``azienda.codice`` (es. ``'trenord'``) dato l'``azienda_id``.

    ``importa_pde`` (CLI) accetta il codice non l'id — lookup minimo per
    riuso dell'importer senza refactor della funzione.
    """
    row = await session.execute(
        select(Azienda.codice).where(Azienda.id == azienda_id)
    )
    codice = row.scalar_one_or_none()
    if codice is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"azienda_id={azienda_id} dal token non trovata in DB",
        )
    return str(codice)


# =====================================================================
# Endpoint: stato PdE
# =====================================================================


@router.get(
    "/pde/status",
    response_model=PdEStatusRead,
    summary="Stato del PdE annuale dell'azienda dell'utente loggato",
)
async def pde_status(
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> PdEStatusRead:
    """Restituisce un riepilogo aggregato del PdE corrente.

    Letto dal pannello "PdE Annuale" della dashboard PIANIFICATORE_GIRO:

    - Ultimo run BASE caricato (o ``None`` se mai caricato).
    - Conteggio corse attive (``is_cancellata=False``) e totali.
    - Conteggio variazioni globali (``programma_materiale_id IS NULL``)
      totali e applicate.
    - Range validità (``MIN(valido_da)`` → ``MAX(valido_a)``) delle
      corse attive.

    Performance: 4 query aggregate, latenza target < 100ms su PdE Trenord.
    """
    az_id = user.azienda_id

    # Ultimo run BASE
    base_run = (
        await session.execute(
            select(CorsaImportRun)
            .where(
                CorsaImportRun.azienda_id == az_id,
                CorsaImportRun.tipo == "BASE",
            )
            .order_by(CorsaImportRun.completed_at.desc().nullslast())
            .limit(1)
        )
    ).scalar_one_or_none()

    # Conteggi corse + range validità
    corse_stats = (
        await session.execute(
            select(
                func.count(CorsaCommerciale.id).label("n_totali"),
                func.count(CorsaCommerciale.id)
                .filter(CorsaCommerciale.is_cancellata.is_(False))
                .label("n_attive"),
                func.min(CorsaCommerciale.valido_da)
                .filter(CorsaCommerciale.is_cancellata.is_(False))
                .label("validity_da"),
                func.max(CorsaCommerciale.valido_a)
                .filter(CorsaCommerciale.is_cancellata.is_(False))
                .label("validity_a"),
            ).where(CorsaCommerciale.azienda_id == az_id)
        )
    ).first()
    n_totali = int(corse_stats.n_totali) if corse_stats else 0
    n_attive = int(corse_stats.n_attive) if corse_stats else 0
    validity_da = corse_stats.validity_da if corse_stats else None
    validity_a = corse_stats.validity_a if corse_stats else None

    # Conteggi variazioni globali (programma_materiale_id IS NULL,
    # tipo != BASE)
    var_stats = (
        await session.execute(
            select(
                func.count(CorsaImportRun.id).label("n_totali"),
                func.count(CorsaImportRun.id)
                .filter(CorsaImportRun.completed_at.is_not(None))
                .label("n_applicate"),
                func.max(CorsaImportRun.completed_at).label("ultima"),
            ).where(
                CorsaImportRun.azienda_id == az_id,
                CorsaImportRun.programma_materiale_id.is_(None),
                CorsaImportRun.tipo != "BASE",
            )
        )
    ).first()
    n_var_totali = int(var_stats.n_totali) if var_stats else 0
    n_var_applicate = int(var_stats.n_applicate) if var_stats else 0
    ultima_variazione_at = var_stats.ultima if var_stats else None

    base_run_dict: dict[str, object] | None = None
    if base_run is not None:
        # Serializzo via pydantic per consistenza con altri endpoint.
        base_run_dict = CorsaImportRunRead.model_validate(base_run).model_dump(
            mode="json"
        )

    return PdEStatusRead(
        base_run=base_run_dict,
        n_corse_attive=n_attive,
        n_corse_totali=n_totali,
        n_variazioni_totali=n_var_totali,
        n_variazioni_applicate=n_var_applicate,
        ultima_variazione_at=ultima_variazione_at,
        validity_da=validity_da,
        validity_a=validity_a,
    )


# =====================================================================
# Endpoint: carica PdE base
# =====================================================================


@router.post(
    "/pde/base",
    response_model=CaricaPdEBaseResponse,
    summary="Carica il PdE base annuale dell'azienda (multipart upload)",
)
async def carica_pde_base(
    file: UploadFile = File(  # noqa: B008
        ..., description="File PdE Trenord (.numbers o .xlsx)"
    ),
    force: bool = Query(
        False,
        description=(
            "Se True, salta il check di idempotenza SHA-256 e re-importa "
            "anche se il file è già stato caricato. Usare solo per bug fix "
            "del parser."
        ),
    ),
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> CaricaPdEBaseResponse:
    """Carica il PdE annuale dell'azienda, equivalente a CLI
    ``python -m colazione.importers.pde_importer --file <path> --azienda <codice>``.

    Wrappa ``importers.pde_importer.importa_pde`` per esporlo via HTTP
    multipart. ``importa_pde`` apre la propria session interna (bulk
    INSERT/DELETE in transazione dedicata) — la session FastAPI di
    questo endpoint è solo per il lookup ``azienda.codice``.

    **Idempotenza** (default): se un file con stesso SHA-256 è già stato
    importato per questa azienda, lo skip è silenzioso (``skipped=True``).
    Per re-importare lo stesso file (es. dopo bug fix nel parser) passa
    ``?force=true``.

    **File supportati**: ``.numbers`` (Apple Numbers, formato nativo
    Trenord) o ``.xlsx`` (export equivalente). Altri formati → 415.

    **Performance**: PdE Trenord 2026 (10580 corse) ~25-30s su laptop
    decente. Timeout client consigliato ≥ 60s.

    **Auth**: ``PIANIFICATORE_GIRO`` (admin bypassa).
    """
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".numbers", ".xlsx"}:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"estensione file non supportata: {suffix!r}. "
                "Usa .numbers o .xlsx"
            ),
        )

    # Lookup azienda.codice per chiamare importa_pde (che prende il codice).
    az_codice = await _get_azienda_codice(session, user.azienda_id)

    file_bytes = await file.read()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(file_bytes)
        tmp.flush()
        try:
            summary = await importa_pde(
                Path(tmp.name), az_codice, force=force
            )
        except FileNotFoundError as exc:
            # Non dovrebbe accadere (l'abbiamo appena scritto), ma per
            # robustezza.
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"errore lettura file salvato: {exc}",
            ) from exc
        except ValueError as exc:
            # azienda_codice non trovato — non dovrebbe accadere visto che
            # il lookup sopra ha avuto successo, ma per robustezza.
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"errore importer: {exc}",
            ) from exc
        except Exception as exc:  # noqa: BLE001 - errori di parsing PdE
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"errore parsing PdE: {exc}",
            ) from exc

    return CaricaPdEBaseResponse(
        skipped=summary.skipped,
        skip_reason=summary.skip_reason,
        run_id=summary.run_id,
        n_total=summary.n_total,
        n_create=summary.n_create,
        n_delete=summary.n_delete,
        n_kept=summary.n_kept,
        n_warnings=summary.n_warnings,
        duration_s=summary.duration_s,
    )


# =====================================================================
# Endpoint: variazioni globali (registra + lista + applica)
# =====================================================================


@router.post(
    "/variazioni",
    response_model=CorsaImportRunRead,
    status_code=status.HTTP_201_CREATED,
    summary="Registra una variazione PdE globale (azienda)",
)
async def registra_variazione_globale(
    payload: VariazionePdERequest,
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> CorsaImportRun:
    """Registra una ``CorsaImportRun`` di tipo non-BASE collegata
    all'azienda (``programma_materiale_id IS NULL``).

    Parallelo a ``POST /api/programmi/{id}/variazioni`` (entry 170) ma
    senza programma — la variazione modifica direttamente lo stato
    delle corse aziendali. Tutti i programmi materiali esistenti
    vedono automaticamente lo stato corrente.

    Cattura solo i metadati (tipo, source_file, count). L'applicazione
    concreta è separata: ``POST /variazioni/{run_id}/applica``.
    """
    run = CorsaImportRun(
        source_file=payload.source_file,
        n_corse=payload.n_corse,
        n_corse_create=0,
        n_corse_update=0,
        azienda_id=user.azienda_id,
        programma_materiale_id=None,
        tipo=payload.tipo,
        note=payload.note,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


@router.get(
    "/variazioni",
    response_model=list[CorsaImportRunRead],
    summary="Lista variazioni PdE globali dell'azienda",
)
async def list_variazioni_globali(
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
    limit: int = Query(50, ge=1, le=500),
) -> list[CorsaImportRun]:
    """Ritorna la timeline delle variazioni globali (escluse BASE).

    Ordinata per ``started_at DESC`` (più recente in cima). Filtro
    ``programma_materiale_id IS NULL`` per escludere le variazioni
    associate a programmi specifici (vedi
    ``GET /api/programmi/{id}/variazioni``).
    """
    stmt = (
        select(CorsaImportRun)
        .where(
            CorsaImportRun.azienda_id == user.azienda_id,
            CorsaImportRun.programma_materiale_id.is_(None),
            CorsaImportRun.tipo != "BASE",
        )
        .order_by(CorsaImportRun.started_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


@router.post(
    "/variazioni/{run_id}/applica",
    response_model=ApplicaVariazionePdEResponse,
    summary="Applica una variazione PdE globale (multipart file)",
)
async def applica_variazione_globale(
    run_id: int,
    file: UploadFile = File(  # noqa: B008
        ..., description="File PdE incrementale (.numbers o .xlsx)"
    ),
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> ApplicaVariazionePdEResponse:
    """Applica una variazione globale registrata.

    Specchio di ``POST /api/programmi/{id}/variazioni/{run_id}/applica``
    (entry 175) ma a livello azienda: il run deve avere
    ``programma_materiale_id IS NULL``. Riusa gli stessi helper privati
    (``_carica_corse_esistenti``, ``_to_parsed_target``,
    ``_planner_per_tipo``, ``_applica_operazioni``) per coerenza
    semantica con la versione per-programma.

    Errori HTTP:
    - 404 se il run non esiste o appartiene a un programma (non globale).
    - 409 se ``run.completed_at`` non è NULL (già applicato).
    - 415 se l'estensione file non è ``.numbers`` o ``.xlsx``.
    - 400 se il parsing del file fallisce.

    Auth: ``PIANIFICATORE_GIRO``.
    """
    run = (
        await session.execute(
            select(CorsaImportRun).where(
                CorsaImportRun.id == run_id,
                CorsaImportRun.azienda_id == user.azienda_id,
                CorsaImportRun.programma_materiale_id.is_(None),
            )
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"variazione globale run_id={run_id} non trovata per "
                "questa azienda"
            ),
        )
    if run.completed_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"run {run_id} già applicata il "
                f"{run.completed_at:%Y-%m-%d %H:%M} — "
                "registra una nuova variazione"
            ),
        )

    planner = _planner_per_tipo(run.tipo)

    # Salva file in tempfile + parse.
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".numbers", ".xlsx"}:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"estensione file non supportata: {suffix!r}. "
                "Usa .numbers o .xlsx"
            ),
        )

    file_bytes = await file.read()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(file_bytes)
        tmp.flush()
        try:
            raw_rows = read_pde_file(Path(tmp.name))
        except Exception as exc:  # noqa: BLE001 - errore di parsing PdE
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"errore lettura file PdE: {exc}",
            ) from exc

    raw_rows = [
        r for r in raw_rows if r.get("Modalità di effettuazione") != "B"
    ]
    if not raw_rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="il file di variazione non contiene righe (post filtro BUS)",
        )

    parsed_rows = [parse_corsa_row(r) for r in raw_rows]
    row_hashes = [compute_row_hash(r) for r in raw_rows]
    targets = [
        _to_parsed_target(parsed, h)
        for parsed, h in zip(parsed_rows, row_hashes, strict=True)
    ]

    esistenti = await _carica_corse_esistenti(session, user.azienda_id)
    risultato = planner(targets, esistenti)

    await _applica_operazioni(
        session,
        azienda_id=user.azienda_id,
        run_id=run_id,
        parsed_rows=parsed_rows,
        risultato=risultato,
    )

    n_create = risultato.n_create
    n_update = risultato.n_update
    note_warning = (
        "\n".join(risultato.warnings)[:1000] if risultato.warnings else None
    )
    await session.execute(
        update(CorsaImportRun)
        .where(CorsaImportRun.id == run_id)
        .values(
            n_corse=len(parsed_rows),
            n_corse_create=n_create,
            n_corse_update=n_update,
            completed_at=datetime.now(UTC),
            note=note_warning,
        )
    )

    await session.commit()
    await session.refresh(run)

    # Detection impatto su programmi esistenti (sub-MR 5.bis-impact,
    # entry 179). Stesso pattern dell'endpoint per-programma.
    corse_coinvolte = estrai_corse_ids_da_risultato_pianificazione(risultato)
    impatti = await calcola_impatto_su_programmi(
        session, corse_ids=corse_coinvolte, azienda_id=user.azienda_id
    )

    completed_at = run.completed_at or datetime.now(UTC)
    return ApplicaVariazionePdEResponse(
        run_id=run.id,
        tipo=run.tipo,
        n_corse_lette_da_file=len(parsed_rows),
        n_corse_create=n_create,
        n_corse_update=n_update,
        n_warnings=len(risultato.warnings),
        warnings=risultato.warnings,
        completed_at=completed_at,
        programmi_impattati=impatti,
    )


# =====================================================================
# Crea programma di variazione (fork) — Sub-MR 5.bis-fork (entry 190)
# =====================================================================


@router.post(
    "/variazioni/{run_id}/crea-fork",
    response_model=ProgrammaMaterialeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Crea un programma di variazione figlio dal periodo della run",
)
async def crea_fork_variazione(
    run_id: int,
    payload: CreaForkVariazioneRequest,
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> ProgrammaMateriale:
    """Crea un nuovo ``programma_materiale`` come **figlio** del genitore
    indicato, in risposta a una variazione PdE applicata.

    **Pre-condizioni**:

    - Run esiste, appartiene all'azienda, ha ``programma_materiale_id
      IS NULL`` (variazione globale, non legata a un programma) +
      ``completed_at IS NOT NULL`` (già applicata) + ``tipo != BASE``.
    - Genitore esiste e appartiene all'azienda corrente.
    - Periodo del fork (``valido_da..valido_a``) compatibile con quello
      del genitore (consigliato ma non imposto: il fork può uscire dal
      periodo del genitore, es. estensione retroattiva).

    **Effetto**:

    - Crea ``ProgrammaMateriale`` figlio con
      ``programma_genitore_id=genitore_id``, stato ``bozza``,
      ``stato_pipeline_pdc=PDE_IN_LAVORAZIONE``.
    - Eredita ``materiali_disponibili_codici_json`` e
      ``stazioni_sosta_extra_json`` dal genitore (consigliato per
      coerenza, ma il pianificatore può modificarli sul figlio).
    - Eredita anche ``km_max_giornaliero``, ``km_max_ciclo``,
      ``n_giornate_*`` dal genitore.
    - Niente cascading di regole / giri / turni: il pianificatore
      genera dal figlio come per un programma nuovo.

    Auth: ``PIANIFICATORE_GIRO`` (admin bypassa).
    """
    # 1) Run esiste + globale + completata + non BASE.
    run = (
        await session.execute(
            select(CorsaImportRun).where(
                CorsaImportRun.id == run_id,
                CorsaImportRun.azienda_id == user.azienda_id,
                CorsaImportRun.programma_materiale_id.is_(None),
            )
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"variazione globale run_id={run_id} non trovata per "
                "questa azienda"
            ),
        )
    if run.tipo == "BASE":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"run {run_id} è di tipo BASE: il fork si crea da una "
                "variazione, non dal primo import"
            ),
        )
    if run.completed_at is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"run {run_id} non ancora applicata: applica la variazione "
                "prima di creare un programma di variazione"
            ),
        )

    # 2) Genitore esiste e appartiene all'azienda.
    genitore = (
        await session.execute(
            select(ProgrammaMateriale).where(
                ProgrammaMateriale.id == payload.genitore_id,
                ProgrammaMateriale.azienda_id == user.azienda_id,
            )
        )
    ).scalar_one_or_none()
    if genitore is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"programma genitore_id={payload.genitore_id} non trovato "
                "per questa azienda"
            ),
        )

    # 3) Crea figlio ereditando i parametri di pianificazione dal
    # genitore. Il pianificatore può poi sovrascriverli via PATCH.
    figlio = ProgrammaMateriale(
        azienda_id=user.azienda_id,
        nome=payload.nome,
        valido_da=payload.valido_da,
        valido_a=payload.valido_a,
        stato="bozza",
        stato_pipeline_pdc="PDE_IN_LAVORAZIONE",
        stato_manutenzione="IN_ATTESA",
        km_max_giornaliero=genitore.km_max_giornaliero,
        km_max_ciclo=genitore.km_max_ciclo,
        n_giornate_default=genitore.n_giornate_default,
        n_giornate_min=genitore.n_giornate_min,
        n_giornate_max=genitore.n_giornate_max,
        fascia_oraria_tolerance_min=genitore.fascia_oraria_tolerance_min,
        strict_options_json=dict(genitore.strict_options_json),
        stazioni_sosta_extra_json=list(genitore.stazioni_sosta_extra_json),
        materiali_disponibili_codici_json=list(
            genitore.materiali_disponibili_codici_json
        ),
        programma_genitore_id=genitore.id,
        created_by_user_id=user.user_id,
    )
    session.add(figlio)
    await session.commit()
    await session.refresh(figlio)
    return figlio

