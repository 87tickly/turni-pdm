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
- `builder.py` (Sprint 4.4.5, futuro) — orchestrator che persiste sul DB.

Tutto è **DB-agnostic**: ricevi dataclass/oggetti, ritorni dataclass.
La persistenza è in `api/` o CLI in `interfaces/`.
"""

from colazione.domain.builder_giro.catena import (
    Catena,
    ParamCatena,
    costruisci_catene,
)
from colazione.domain.builder_giro.multi_giornata import (
    GiornataGiro,
    Giro,
    MotivoChiusura,
    ParamMultiGiornata,
    costruisci_giri_multigiornata,
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
    RegolaAmbiguaError,
    determina_giorno_tipo,
    estrai_valore_corsa,
    matches_all,
    matches_filtro,
    risolvi_corsa,
)

__all__ = [
    "AssegnazioneRisolta",
    "BloccoMaterialeVuoto",
    "Catena",
    "CatenaPosizionata",
    "Giro",
    "GiornataGiro",
    "LocalitaSenzaStazioneError",
    "MotivoChiusura",
    "ParamCatena",
    "ParamMultiGiornata",
    "ParamPosizionamento",
    "PosizionamentoImpossibileError",
    "RegolaAmbiguaError",
    "costruisci_catene",
    "costruisci_giri_multigiornata",
    "determina_giorno_tipo",
    "estrai_valore_corsa",
    "matches_all",
    "matches_filtro",
    "posiziona_su_localita",
    "risolvi_corsa",
]
