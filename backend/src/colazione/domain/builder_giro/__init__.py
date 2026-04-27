"""Builder Giro Materiale (Algoritmo A) — `domain/builder_giro/`.

Ricostruisce i giri del materiale rotabile dal PdE + programma materiale.
Vedi `docs/LOGICA-COSTRUZIONE.md` §3 e `docs/PROGRAMMA-MATERIALE.md`.

Sub-moduli:

- `risolvi_corsa.py` (Sprint 4.2) — funzione pura che assegna a una
  corsa il rotabile vincente in base alle regole del programma.
- `catena.py` (Sprint 4.4.1) — funzione pura greedy chain single-day:
  data una lista di corse, produce catene massimali per continuità
  geografica + gap minimo.
- `posizionamento.py` (Sprint 4.4.2) — funzione pura che chiude una
  catena su una località manutenzione, generando blocchi
  ``materiale_vuoto`` di testa/coda quando necessario.
- `multi_giornata.py` (Sprint 4.4.3) — concatenazione cross-notte:
  da catene posizionate single-day a `Giro` multi-giornata che
  attraversano la mezzanotte.
- `composizione.py` (Sprint 4.4.4) — assegnazione regole a ogni
  blocco corsa (chiama ``risolvi_corsa``) + rilevamento eventi
  ``aggancio``/``sgancio`` (delta numero_pezzi intra-giornata).
- `persister.py` (Sprint 4.4.5a) — bridge dataclass dominio → ORM:
  ``persisti_giri()`` async che scrive ``GiroMateriale + GiroGiornata
  + GiroVariante + GiroBlocco + CorsaMaterialeVuoto``. Solo INSERT,
  no commit (lo decide il caller).
- `builder.py` (Sprint 4.4.5b) — loader DB + orchestrator end-to-end
  ``genera_giri()``. Endpoint API in ``api/giri.py``.

Tutto è **DB-agnostic**: ricevi dataclass/oggetti, ritorni dataclass.
La persistenza è in `api/` o CLI in `interfaces/`.
"""

from colazione.domain.builder_giro.builder import (
    BuilderResult,
    GiriEsistentiError,
    ProgrammaNonAttivoError,
    ProgrammaNonTrovatoError,
    StrictModeViolation,
    genera_giri,
)
from colazione.domain.builder_giro.catena import (
    Catena,
    ParamCatena,
    costruisci_catene,
)
from colazione.domain.builder_giro.composizione import (
    BloccoAssegnato,
    CorsaResidua,
    EventoComposizione,
    GiornataAssegnata,
    GiroAssegnato,
    IncompatibilitaMateriale,
    TipoEvento,
    assegna_e_rileva_eventi,
    assegna_materiali,
    rileva_eventi_composizione,
)
from colazione.domain.builder_giro.multi_giornata import (
    GiornataGiro,
    Giro,
    MotivoChiusura,
    ParamMultiGiornata,
    costruisci_giri_multigiornata,
)
from colazione.domain.builder_giro.persister import (
    PERSISTER_VERSION,
    GiroDaPersistere,
    LocalitaNonTrovataError,
    persisti_giri,
)
from colazione.domain.builder_giro.posizionamento import (
    BloccoMaterialeVuoto,
    CatenaPosizionata,
    LocalitaSenzaStazioneError,
    ParamPosizionamento,
    PosizionamentoImpossibileError,
    posiziona_su_localita,
)
from colazione.domain.builder_giro.risolvi_corsa import (
    AssegnazioneRisolta,
    ComposizioneItem,
    ComposizioneNonAmmessaError,
    IsAccoppiamentoAmmesso,
    RegolaAmbiguaError,
    determina_giorno_tipo,
    estrai_valore_corsa,
    matches_all,
    matches_filtro,
    risolvi_corsa,
)

__all__ = [
    "PERSISTER_VERSION",
    "AssegnazioneRisolta",
    "BloccoAssegnato",
    "BloccoMaterialeVuoto",
    "BuilderResult",
    "Catena",
    "CatenaPosizionata",
    "ComposizioneItem",
    "ComposizioneNonAmmessaError",
    "CorsaResidua",
    "EventoComposizione",
    "GiriEsistentiError",
    "Giro",
    "GiornataAssegnata",
    "GiornataGiro",
    "GiroAssegnato",
    "GiroDaPersistere",
    "IncompatibilitaMateriale",
    "IsAccoppiamentoAmmesso",
    "LocalitaNonTrovataError",
    "LocalitaSenzaStazioneError",
    "MotivoChiusura",
    "ParamCatena",
    "ParamMultiGiornata",
    "ParamPosizionamento",
    "PosizionamentoImpossibileError",
    "ProgrammaNonAttivoError",
    "ProgrammaNonTrovatoError",
    "RegolaAmbiguaError",
    "StrictModeViolation",
    "TipoEvento",
    "assegna_e_rileva_eventi",
    "assegna_materiali",
    "costruisci_catene",
    "costruisci_giri_multigiornata",
    "determina_giorno_tipo",
    "estrai_valore_corsa",
    "genera_giri",
    "matches_all",
    "matches_filtro",
    "persisti_giri",
    "posiziona_su_localita",
    "rileva_eventi_composizione",
    "risolvi_corsa",
]
