"""Builder Giro Materiale (Algoritmo A) — `domain/builder_giro/`.

Ricostruisce i giri del materiale rotabile dal PdE + programma materiale.
Vedi `docs/LOGICA-COSTRUZIONE.md` §3 e `docs/PROGRAMMA-MATERIALE.md`.

Sub-moduli:

- `risolvi_corsa.py` (Sprint 4.2) — funzione pura che assegna a una
  corsa il rotabile vincente in base alle regole del programma.
- `builder.py` (Sprint 4.4, futuro) — orchestrator multi-giornata che
  costruisce i giri completi.

Tutto è **DB-agnostic**: ricevi dataclass/oggetti, ritorni dataclass.
La persistenza è in `api/` o CLI in `interfaces/`.
"""

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
    "RegolaAmbiguaError",
    "determina_giorno_tipo",
    "estrai_valore_corsa",
    "matches_all",
    "matches_filtro",
    "risolvi_corsa",
]
