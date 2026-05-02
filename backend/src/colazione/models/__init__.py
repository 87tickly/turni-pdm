"""Modelli SQLAlchemy ORM (Sprint 1.7).

Mappano le 31 tabelle create dalle migrazioni 0001 + 0002. Organizzati
per strato del modello dati v0.5 (vedi `docs/MODELLO-DATI.md`):

- Strato 0 — anagrafica (`anagrafica.py`): 8 entità
- Strato 1 — corse PdE (`corse.py`): 4 entità
- Strato 2 — giro materiale (`giri.py`): 5 entità
- Strato 2bis — revisioni provvisorie (`revisioni.py`): 3 entità
- Strato 3 — turno PdC (`turni_pdc.py`): 3 entità
- Strato 4 — personale (`personale.py`): 3 entità
- Strato 5 — auth + audit (`auth.py`): 4 entità

Tutte ereditano da `colazione.db.Base`. Importare da qui per avere
tutto registrato sul `Base.metadata` (importante per i test e per
eventuali `alembic --autogenerate` futuri).
"""

from colazione.models.anagrafica import (
    Azienda,
    Depot,
    DepotLineaAbilitata,
    DepotMaterialeAbilitato,
    FestivitaUfficiale,
    LocalitaManutenzione,
    LocalitaManutenzioneDotazione,
    LocalitaStazioneVicina,
    MaterialeAccoppiamentoAmmesso,
    MaterialeTipo,
    Stazione,
)
from colazione.models.auth import (
    AppUser,
    AppUserRuolo,
    AuditLog,
    Notifica,
)
from colazione.models.corse import (
    CorsaCommerciale,
    CorsaComposizione,
    CorsaImportRun,
    CorsaMaterialeVuoto,
)
from colazione.models.giri import (
    GiroBlocco,
    GiroFinestraValidita,
    GiroGiornata,
    GiroMateriale,
    VersioneBaseGiro,
)
from colazione.models.personale import (
    AssegnazioneGiornata,
    IndisponibilitaPersona,
    Persona,
)
from colazione.models.programmi import (
    ProgrammaMateriale,
    ProgrammaRegolaAssegnazione,
)
from colazione.models.revisioni import (
    RevisioneProvvisoria,
    RevisioneProvvisoriaBlocco,
    RevisioneProvvisoriaPdc,
)
from colazione.models.turni_pdc import (
    TurnoPdc,
    TurnoPdcBlocco,
    TurnoPdcGiornata,
)

__all__ = [
    # Strato 0 — anagrafica
    "Azienda",
    "Depot",
    "DepotLineaAbilitata",
    "DepotMaterialeAbilitato",
    "FestivitaUfficiale",
    "LocalitaManutenzione",
    "LocalitaManutenzioneDotazione",
    "LocalitaStazioneVicina",
    "MaterialeAccoppiamentoAmmesso",
    "MaterialeTipo",
    "Stazione",
    # Strato 1 — corse
    "CorsaCommerciale",
    "CorsaComposizione",
    "CorsaImportRun",
    "CorsaMaterialeVuoto",
    # Strato 2 — giro materiale
    "GiroBlocco",
    "GiroFinestraValidita",
    "GiroGiornata",
    "GiroMateriale",
    "VersioneBaseGiro",
    # Strato 2bis — revisioni provvisorie
    "RevisioneProvvisoria",
    "RevisioneProvvisoriaBlocco",
    "RevisioneProvvisoriaPdc",
    # Strato 3 — turno PdC
    "TurnoPdc",
    "TurnoPdcBlocco",
    "TurnoPdcGiornata",
    # Strato 4 — personale
    "AssegnazioneGiornata",
    "IndisponibilitaPersona",
    "Persona",
    # Strato 1bis — programma materiale (input umano del pianificatore)
    "ProgrammaMateriale",
    "ProgrammaRegolaAssegnazione",
    # Strato 5 — auth + audit
    "AppUser",
    "AppUserRuolo",
    "AuditLog",
    "Notifica",
]
