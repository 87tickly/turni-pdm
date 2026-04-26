"""Builder Giro Materiale (Algoritmo A) — `domain/builder_giro/`.

Ricostruisce i giri del materiale rotabile dal PdE + programma materiale.
Vedi `docs/LOGICA-COSTRUZIONE.md` §3 e `docs/PROGRAMMA-MATERIALE.md`.

Sub-moduli:

- `risolvi_corsa.py` (Sprint 4.2) — funzione pura che assegna a una
  corsa il rotabile vincente in base alle regole del programma.
- `catena.py` (Sprint 4.4.1) — funzione pura greedy chain single-day:
  data una lista di corse, produce catene massimali per continuità
  geografica + gap minimo.
- `builder.py` (Sprint 4.4.5, futuro) — orchestrator multi-giornata
  che persiste sul DB.

Tutto è **DB-agnostic**: ricevi dataclass/oggetti, ritorni dataclass.
La persistenza è in `api/` o CLI in `interfaces/`.
"""

from colazione.domain.builder_giro.catena import (
    Catena,
    ParamCatena,
    costruisci_catene,
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
    "Catena",
    "ParamCatena",
    "RegolaAmbiguaError",
    "costruisci_catene",
    "determina_giorno_tipo",
    "estrai_valore_corsa",
    "matches_all",
    "matches_filtro",
    "risolvi_corsa",
]
