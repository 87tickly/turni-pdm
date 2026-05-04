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
- `etichetta.py` (Sprint 7.7 MR 3) — funzione pura
  ``calcola_etichetta_giro`` che classifica un giro come
  ``feriale | sabato | domenica | festivo | data_specifica |
  personalizzata``. **Sprint 7.7 MR 5**: non più usato dal
  persister (varianti per giornata supersede l'etichetta-su-giro);
  resta esposto per consumi futuri.
- `aggregazione_a2.py` (Sprint 7.7 MR 5) — funzione pura
  ``aggrega_a2`` che fonde ``GiroAssegnato`` per chiave
  ``(materiale, sede, n_giornate)`` in ``GiroAggregato`` con
  varianti calendariali per giornata.
- `persister.py` (Sprint 4.4.5a → 7.7 MR 5) — bridge dataclass
  dominio → ORM: ``persisti_giri()`` async che scrive
  ``GiroMateriale + GiroGiornata + GiroVariante + GiroBlocco +
  CorsaMaterialeVuoto``. Solo INSERT, no commit (lo decide il
  caller).
- `builder.py` (Sprint 4.4.5b) — loader DB + orchestrator end-to-end
  ``genera_giri()``. Endpoint API in ``api/giri.py``.

Tutto è **DB-agnostic**: ricevi dataclass/oggetti, ritorni dataclass.
La persistenza è in `api/` o CLI in `interfaces/`.
"""

from colazione.domain.builder_giro.builder import (
    BuilderResult,
    GiriEsistentiError,
    PdcDipendentiError,
    ProgrammaNonAttivoError,
    ProgrammaNonTrovatoError,
    StrictModeViolation,
    carica_festivita_periodo,
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
from colazione.domain.builder_giro.aggregazione_a2 import (
    GiornataAggregata,
    GiroAggregato,
    VarianteGiornata,
    aggrega_a2,
)
from colazione.domain.builder_giro.etichetta import (
    ETICHETTE_AMMESSE,
    calcola_etichetta_giro,
    calcola_etichetta_variante,
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
    primo_tipo_materiale,
    wrap_assegnato_in_aggregato,
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
    "ETICHETTE_AMMESSE",
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
    "GiornataAggregata",
    "GiriEsistentiError",
    "GiroAggregato",
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
    "PdcDipendentiError",
    "ParamMultiGiornata",
    "ParamPosizionamento",
    "PosizionamentoImpossibileError",
    "ProgrammaNonAttivoError",
    "ProgrammaNonTrovatoError",
    "RegolaAmbiguaError",
    "StrictModeViolation",
    "TipoEvento",
    "VarianteGiornata",
    "aggrega_a2",
    "assegna_e_rileva_eventi",
    "assegna_materiali",
    "calcola_etichetta_giro",
    "calcola_etichetta_variante",
    "carica_festivita_periodo",
    "costruisci_catene",
    "costruisci_giri_multigiornata",
    "determina_giorno_tipo",
    "estrai_valore_corsa",
    "genera_giri",
    "matches_all",
    "matches_filtro",
    "persisti_giri",
    "posiziona_su_localita",
    "primo_tipo_materiale",
    "rileva_eventi_composizione",
    "risolvi_corsa",
    "wrap_assegnato_in_aggregato",
]
