"""Schemas Pydantic per serializzazione I/O API (Sprint 1.8).

Schemi `Read` per le 31 entità del modello dati v0.5, organizzati per
strato (specchio della struttura `colazione/models/`):

- Strato 0 — anagrafica (`anagrafica.py`): 8 schemi
- Strato 1 — corse PdE (`corse.py`): 4 schemi
- Strato 2 — giro materiale (`giri.py`): 6 schemi
- Strato 2bis — revisioni (`revisioni.py`): 3 schemi
- Strato 3 — turno PdC (`turni_pdc.py`): 3 schemi
- Strato 4 — personale (`personale.py`): 3 schemi
- Strato 5 — auth + audit (`auth.py`): 4 schemi

Tutti gli schemi hanno `model_config = ConfigDict(from_attributes=True)`,
quindi si costruiscono direttamente da modelli ORM:

    user = await session.get(AppUser, 1)
    out = AppUserRead.model_validate(user)

Schemi `Create` / `Update` saranno aggiunti quando le route POST/PATCH
ne avranno bisogno (Sprint 4+). Schemi specifici per auth (login,
token) saranno in `schemas/security.py` dello Sprint 2.
"""

from colazione.schemas.anagrafica import (
    AziendaRead,
    DepotLineaAbilitataRead,
    DepotMaterialeAbilitatoRead,
    DepotRead,
    LocalitaManutenzioneDotazioneRead,
    LocalitaManutenzioneRead,
    MaterialeTipoRead,
    StazioneRead,
)
from colazione.schemas.auth import (
    AppUserRead,
    AppUserRuoloRead,
    AuditLogRead,
    NotificaRead,
)
from colazione.schemas.corse import (
    CorsaCommercialeRead,
    CorsaComposizioneRead,
    CorsaImportRunRead,
    CorsaMaterialeVuotoRead,
)
from colazione.schemas.giri import (
    GiroBloccoRead,
    GiroFinestraValiditaRead,
    GiroGiornataRead,
    GiroMaterialeRead,
    GiroVarianteRead,
    VersioneBaseGiroRead,
)
from colazione.schemas.personale import (
    AssegnazioneGiornataRead,
    IndisponibilitaPersonaRead,
    PersonaRead,
)
from colazione.schemas.programmi import (
    FiltroRegola,
    ProgrammaMaterialeCreate,
    ProgrammaMaterialeRead,
    ProgrammaMaterialeUpdate,
    ProgrammaRegolaAssegnazioneCreate,
    ProgrammaRegolaAssegnazioneRead,
    StrictOptions,
)
from colazione.schemas.revisioni import (
    RevisioneProvvisoriaBloccoRead,
    RevisioneProvvisoriaPdcRead,
    RevisioneProvvisoriaRead,
)
from colazione.schemas.turni_pdc import (
    TurnoPdcBloccoRead,
    TurnoPdcGiornataRead,
    TurnoPdcRead,
)

__all__ = [
    # Strato 0 — anagrafica
    "AziendaRead",
    "DepotLineaAbilitataRead",
    "DepotMaterialeAbilitatoRead",
    "DepotRead",
    "LocalitaManutenzioneDotazioneRead",
    "LocalitaManutenzioneRead",
    "MaterialeTipoRead",
    "StazioneRead",
    # Strato 1 — corse
    "CorsaCommercialeRead",
    "CorsaComposizioneRead",
    "CorsaImportRunRead",
    "CorsaMaterialeVuotoRead",
    # Strato 2 — giro materiale
    "GiroBloccoRead",
    "GiroFinestraValiditaRead",
    "GiroGiornataRead",
    "GiroMaterialeRead",
    "GiroVarianteRead",
    "VersioneBaseGiroRead",
    # Strato 2bis — revisioni
    "RevisioneProvvisoriaBloccoRead",
    "RevisioneProvvisoriaPdcRead",
    "RevisioneProvvisoriaRead",
    # Strato 3 — turno PdC
    "TurnoPdcBloccoRead",
    "TurnoPdcGiornataRead",
    "TurnoPdcRead",
    # Strato 4 — personale
    "AssegnazioneGiornataRead",
    "IndisponibilitaPersonaRead",
    "PersonaRead",
    # Strato 1bis — programma materiale (input umano del pianificatore)
    "FiltroRegola",
    "ProgrammaMaterialeCreate",
    "ProgrammaMaterialeRead",
    "ProgrammaMaterialeUpdate",
    "ProgrammaRegolaAssegnazioneCreate",
    "ProgrammaRegolaAssegnazioneRead",
    "StrictOptions",
    # Strato 5 — auth + audit
    "AppUserRead",
    "AppUserRuoloRead",
    "AuditLogRead",
    "NotificaRead",
]
