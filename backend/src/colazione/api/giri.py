"""Route HTTP per generazione giri materiali — Sprint 4.4.5b.

Endpoint:

- ``POST /api/programmi/{id}/genera-giri`` — esegue il builder
  end-to-end e persiste i giri.

Multi-tenant: ``azienda_id`` dal JWT, niente input client.
Auth: ruolo ``PIANIFICATORE_GIRO`` (admin bypassa).

Strategia di rigenerazione (decisione utente, vedi
``docs/PROGRAMMA-MATERIALE.md``): se il programma ha già giri
persistiti, l'endpoint ritorna **409 Conflict** salvo
``?force=true`` esplicito (cancella tutti i giri e rigenera).

Modalità di generazione (decisione utente):
- **Istanze 1:1**: ogni giro è generato per date concrete dal
  parametro ``data_inizio + n_giornate``. Pattern ricorrenza
  (un giro vale tutti i lunedì) è scope futuro.
- **Una località per chiamata**: parametro ``localita_codice``
  obbligatorio. Per N località il pianificatore lancia N chiamate.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.auth import require_role
from colazione.db import get_session
from colazione.domain.builder_giro.builder import (
    BuilderResult,
    GiriEsistentiError,
    ProgrammaNonAttivoError,
    ProgrammaNonTrovatoError,
    StrictModeViolation,
    genera_giri,
)
from colazione.domain.builder_giro.persister import LocalitaNonTrovataError
from colazione.domain.builder_giro.risolvi_corsa import RegolaAmbiguaError
from colazione.schemas.security import CurrentUser

router = APIRouter(prefix="/api/programmi", tags=["giri"])

_authz = Depends(require_role("PIANIFICATORE_GIRO"))


# =====================================================================
# Response schema
# =====================================================================


class BuilderResultResponse(BaseModel):
    """Risposta di ``POST /genera-giri``: stats + warning."""

    giri_ids: list[int] = Field(description="ID dei GiroMateriale creati.")
    n_giri_creati: int
    n_corse_processate: int = Field(description="Totale blocchi corsa assegnati nei giri.")
    n_corse_residue: int = Field(description="Corse senza regola applicabile (warning).")
    n_giri_chiusi: int
    n_giri_non_chiusi: int = Field(description="Giri con motivo_chiusura != 'naturale' (warning).")
    n_eventi_composizione: int = Field(
        description="Blocchi aggancio/sgancio inseriti (da validare in editor)."
    )
    n_incompatibilita_materiale: int
    warnings: list[str]


def _to_response(result: BuilderResult) -> BuilderResultResponse:
    return BuilderResultResponse(
        giri_ids=result.giri_ids,
        n_giri_creati=result.n_giri_creati,
        n_corse_processate=result.n_corse_processate,
        n_corse_residue=result.n_corse_residue,
        n_giri_chiusi=result.n_giri_chiusi,
        n_giri_non_chiusi=result.n_giri_non_chiusi,
        n_eventi_composizione=result.n_eventi_composizione,
        n_incompatibilita_materiale=result.n_incompatibilita_materiale,
        warnings=result.warnings,
    )


# =====================================================================
# Endpoint
# =====================================================================


@router.post(
    "/{programma_id}/genera-giri",
    response_model=BuilderResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Genera giri materiali per un programma in una finestra di date",
)
async def genera_giri_endpoint(
    programma_id: int,
    data_inizio: date = Query(..., description="Prima data del range (YYYY-MM-DD)."),
    n_giornate: int = Query(7, ge=1, le=180, description="Numero giornate (1-180)."),
    localita_codice: str = Query(
        ..., description="Codice località manutenzione (es. IMPMAN_MILANO_FIORENZA)."
    ),
    force: bool = Query(
        False,
        description="Se true, cancella i giri esistenti del programma e rigenera.",
    ),
    user: CurrentUser = _authz,
    session: AsyncSession = Depends(get_session),
) -> BuilderResultResponse:
    """Lancia il builder end-to-end (pipeline 4.4.1→4.4.5a) per il
    programma + finestra + località indicati.

    Errori HTTP:

    - **404**: programma o località non trovati per l'azienda corrente.
    - **400**: programma non in stato 'attivo', o ``n_giornate`` invalido,
      o regole ambigue, o strict mode violato.
    - **409**: il programma ha già giri persistiti — passa
      ``?force=true`` per cancellare e rigenerare.

    Risposta 200: ``BuilderResultResponse`` con ``giri_ids`` (id dei
    `GiroMateriale` creati) + statistiche per il pianificatore.
    """
    try:
        result = await genera_giri(
            programma_id=programma_id,
            data_inizio=data_inizio,
            n_giornate=n_giornate,
            localita_codice=localita_codice,
            session=session,
            azienda_id=user.azienda_id,
            force=force,
        )
    except ProgrammaNonTrovatoError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LocalitaNonTrovataError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ProgrammaNonAttivoError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except GiriEsistentiError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except StrictModeViolation as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RegolaAmbiguaError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return _to_response(result)
