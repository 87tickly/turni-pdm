"""Orchestratore pipeline linea-centrica (Sprint 8.2 MR-D5).

Plan-D MR-D5 baseline: integra MR-D0..D4 in una pipeline pure-domain
end-to-end. Input = corse PdE + parametri programma. Output =
``list[Giro]`` compatibile col persister legacy.

# Pipeline

```
corse PdE
    │
    ▼
raggruppa_corse_per_linea     (MR-D0)
    │
    ▼
analizza_linee_da_corse       (MR-D1: split multi-tronco)
    │
    ▼   (per ogni segmento)
genera_calendario_segmento    (MR-D0.5)
    │
    ▼
assegna_convogli_segmenti     (MR-D2: vincoli HARD inc. SEVERO #2)
    │
    ▼
costruisci_turni_da_assegnazione  (MR-D3: cuore architetturale)
    │
    ▼
traduci_turni_in_giri         (MR-D4: bridge → Giro)
    │
    ▼
list[Giro]
```

# Cosa NON fa MR-D5

- **Non integra col builder.py**: la pipeline è pure-domain
  invocabile direttamente dai test. L'integrazione builder
  (branching `builder_mode='linea_centrica'`) è scope MR-D5b
  separato per ridurre rischio strangler.
- **Non persiste su DB**: chi vuole salvare i `Giro` chiama
  `persister.persisti_giri()` separatamente.
- **Non gestisce vuoti tecnici** fra segmenti diversi (= scope
  MR-D6 ``vuoti_tecnici``).
- **Non valida con dati reali Trenord**: smoke test su input
  sintetici. Validazione su prog 17/14 reali = scope MR-D7 e2e.

DB-agnostic. Test 100% mocked.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any, cast

from colazione.domain.builder_giro.aggregazione_linea_centrica import (
    traduci_turni_in_giri,
)
from colazione.domain.builder_giro.analizza_linee import (
    analizza_linee_da_corse,
)
from colazione.domain.builder_giro.assegna_convogli_linea import (
    ParamAssegnazione,
    RisultatoAssegnazione,
    assegna_convogli_segmenti,
)
from colazione.domain.builder_giro.costruisci_turno_linea import (
    TurnoConvoglio,
    _CorsaTurnoLike,
    costruisci_turni_da_assegnazione,
)
from colazione.domain.builder_giro.definizione_linea import (
    Linea,
    SegmentoLinea,
    VincoliSosta,
)
from colazione.domain.builder_giro.gestione_calendario_linea import (
    CalendarioSegmento,
    festivita_per_anno,
    genera_calendario_segmento,
)
from colazione.domain.builder_giro.multi_giornata import Giro

# =====================================================================
# Output dataclass
# =====================================================================


@dataclass(frozen=True, kw_only=True)
class RisultatoPipelineLineaCentrica:
    """Output completo della pipeline linea-centrica.

    Attributi:
        giri: lista di `Giro` prodotti, ordinati per
            ``(localita_codice, prima_data)``.
        linee: lista di `Linea` analizzate (output MR-D1).
        assegnazione: output completo MR-D2 con statistiche per sede +
            materiale.
        turni: lista di `TurnoConvoglio` prodotti (output MR-D3),
            utili per debug/log.
        warnings: messaggi diagnostici aggregati (assegnazione +
            costruzione turno).
    """

    giri: list[Giro]
    linee: list[Linea]
    assegnazione: RisultatoAssegnazione
    turni: list[TurnoConvoglio]
    warnings: list[str] = field(default_factory=list)

    def n_giri_chiusi(self) -> int:
        return sum(1 for g in self.giri if g.chiuso)

    def n_giri_non_chiusi(self) -> int:
        return sum(1 for g in self.giri if not g.chiuso)

    def n_segmenti_non_assegnati(self) -> int:
        return self.assegnazione.n_segmenti_con_errore()


# =====================================================================
# Parametri input
# =====================================================================


@dataclass(frozen=True, kw_only=True)
class ParamPipelineLineaCentrica:
    """Parametri della pipeline linea-centrica.

    Attributi:
        sedi_disponibili: mapping ``codice_sede → stazione_collegata``.
            Tipicamente passato dal builder.py dopo aver caricato
            ``LocalitaManutenzione`` per le regole del programma.
        area_per_stazione: mapping ``stazione → area_metropolitana``.
            Necessario per il vincolo HARD di compatibilità sede-segmento
            (raccomandazione SEVERO #2).
        dotazione_per_materiale: capacity flotta per materiale (es.
            ETR522: 71). Vuoto = capacity illimitata.
        materiale_per_segmento: mapping segmento_codice → materiale.
            Calcolato dalla regola dominante delle corse del segmento.
        periodo_da/periodo_a: periodo PdE del programma.
        festivita_set: festività attive per l'azienda (italiane fisse +
            Pasqua + locali). Se ``None``, ricavate via
            ``festivita_per_anno()`` per gli anni del periodo.
        descrizioni_linea: opzionale, mapping codice_linea → descrizione UI.
        vincoli_default: vincoli sosta default per i segmenti (override
            in MR-D1 se serve).
        ore_servizio_die: usato da MR-D2 per stima n_convogli (default 18h).
        regola_per_segmento: opzionale, mapping segmento → regola_id per
            propagare la `regola_id` al `CatenaPosizionata` finale.
        sede_target_per_regola: Sprint 8.2 MR-D5h-DUAL (entry 276) —
            opzionale, mapping ``regola_id → sede_target_codice`` (=
            ``regola.localita_codice`` dato utente). Se passato, il
            bridge MR-D4 produce ``Giro.localita_codice`` = sede target
            (per modello cumulativo + persistenza) e
            ``Giro.sede_operativa_codice`` = sede operativa MR-D2 (se
            differisce da target). Senza questo mapping, il bridge
            mantiene il comportamento legacy (target=operativa).
    """

    sedi_disponibili: dict[str, str]
    area_per_stazione: dict[str, int] = field(default_factory=dict)
    dotazione_per_materiale: dict[str, int] = field(default_factory=dict)
    materiale_per_segmento: dict[str, str] = field(default_factory=dict)
    periodo_da: date
    periodo_a: date
    festivita_set: frozenset[date] | None = None
    descrizioni_linea: dict[str, str] = field(default_factory=dict)
    vincoli_default: VincoliSosta | None = None
    ore_servizio_die: float = 18.0
    regola_per_segmento: dict[str, int] = field(default_factory=dict)
    sede_target_per_regola: dict[int, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.periodo_da > self.periodo_a:
            raise ValueError(
                f"periodo_da ({self.periodo_da}) > periodo_a "
                f"({self.periodo_a})"
            )
        if not self.sedi_disponibili:
            raise ValueError("sedi_disponibili non può essere vuoto")


# =====================================================================
# Helpers interni
# =====================================================================


def _carica_festivita_periodo(
    periodo_da: date,
    periodo_a: date,
) -> frozenset[date]:
    """Festività italiane fisse + Pasqua + Pasquetta per gli anni del
    periodo PdE.

    Helper di convenienza per chiamanti che non hanno il DB
    `FestivitaUfficiale` accessibile (test, batch). Per uso in
    produzione si dovrebbe caricare anche le festività locali
    azienda; questo helper copre solo le nazionali.
    """
    anni_periodo = set(range(periodo_da.year, periodo_a.year + 1))
    out: set[date] = set()
    for anno in anni_periodo:
        out |= festivita_per_anno(anno)
    return frozenset(out)


def _materiale_segmento_default(
    segmento_codice: str,
    materiale_per_segmento: dict[str, str],
) -> str:
    """Default materiale: '' (capacity check skip per segmento)."""
    return materiale_per_segmento.get(segmento_codice, "")


# =====================================================================
# Algoritmo principale
# =====================================================================


def esegui_pipeline_linea_centrica(
    corse: Sequence[_CorsaTurnoLike],
    params: ParamPipelineLineaCentrica,
) -> RisultatoPipelineLineaCentrica:
    """Esegue la pipeline pure-domain D0..D4 end-to-end.

    Args:
        corse: corse PdE del periodo (tutte le linee del programma).
        params: parametri vincoli + periodo.

    Returns:
        `RisultatoPipelineLineaCentrica` con giri pronti per il
        persister + diagnostica completa per log/debug.

    Determinismo: stesso input → stesso output (tutti gli step interni
    sono deterministici per costruzione).
    """
    warnings: list[str] = []

    # Step 1 (MR-D0): raggruppa corse per linea.
    # Helper inline tipizzato per _CorsaTurnoLike (raggruppa_corse_per_linea
    # di MR-D0 è tipizzato per _CorsaLike, mypy strict non accetta sub-Protocol).
    corse_per_linea: dict[str, list[_CorsaTurnoLike]] = defaultdict(list)
    for c in corse:
        corse_per_linea[c.codice_linea].append(c)
    corse_per_linea = dict(corse_per_linea)

    # Step 2 (MR-D1): analizza linee → list[Linea] con segmenti raffinati.
    # Cast: _CorsaTurnoLike è un super-Protocol di _CorsaLike (ha tutti
    # i campi richiesti), quindi è strutturalmente compatibile.
    n_giorni = (params.periodo_a - params.periodo_da).days + 1
    linee = analizza_linee_da_corse(
        cast("dict[str, list[Any]]", corse_per_linea),
        n_giorni_perimetro=n_giorni,
        descrizioni_linea=params.descrizioni_linea,
        vincoli_default=params.vincoli_default,
    )

    # Indicizza segmenti + raggruppa corse per segmento
    segmenti: list[SegmentoLinea] = []
    corse_per_segmento: dict[str, list[_CorsaTurnoLike]] = {}
    for linea in linee:
        for seg in linea.segmenti:
            segmenti.append(seg)
            # Per MR-D5 baseline, tutte le corse della linea
            # finiscono nel segmento "completo" (MR-D1 raffina ma
            # senza separare le corse per coppia capolinea — scope
            # MR-D6+).
            corse_per_segmento[seg.codice] = list(
                corse_per_linea.get(linea.codice_linea, [])
            )

    # Step 3 (MR-D0.5): genera calendario per ogni segmento
    festivita = (
        params.festivita_set
        if params.festivita_set is not None
        else _carica_festivita_periodo(params.periodo_da, params.periodo_a)
    )
    calendari: list[CalendarioSegmento] = []
    for seg in segmenti:
        cal = genera_calendario_segmento(
            seg,
            corse_per_segmento.get(seg.codice, []),
            periodo_da=params.periodo_da,
            periodo_a=params.periodo_a,
            festivita_set=festivita,
        )
        calendari.append(cal)

    # Step 4 (MR-D2): assegna convogli a segmenti
    param_assegnazione = ParamAssegnazione(
        sedi_disponibili=params.sedi_disponibili,
        area_per_stazione=params.area_per_stazione,
        dotazione_per_materiale=params.dotazione_per_materiale,
        materiale_per_segmento=params.materiale_per_segmento,
        ore_servizio_die=params.ore_servizio_die,
    )
    assegnazione = assegna_convogli_segmenti(segmenti, param_assegnazione)
    warnings.extend(assegnazione.warnings)

    # Step 5 (MR-D3): costruisci turni
    turni = costruisci_turni_da_assegnazione(
        assegnazione.assegnazioni,
        segmenti=segmenti,
        calendari=calendari,
        corse_per_segmento=corse_per_segmento,
    )
    for t in turni:
        warnings.extend(t.warnings_globali)
        for g in t.giornate:
            warnings.extend(g.warnings_sosta)

    # Step 6 (MR-D4): bridge turni → Giri
    # MR-D5h-DUAL: passa anche sede_target_per_regola per scissione
    # sede target (regola, dato utente) vs sede operativa (MR-D2 ottima).
    giri = traduci_turni_in_giri(
        turni,
        stazione_collegata_per_sede=params.sedi_disponibili,
        regola_per_segmento=params.regola_per_segmento,
        sede_target_per_regola=params.sede_target_per_regola,
    )

    return RisultatoPipelineLineaCentrica(
        giri=giri,
        linee=linee,
        assegnazione=assegnazione,
        turni=turni,
        warnings=warnings,
    )


__all__ = [
    "ParamPipelineLineaCentrica",
    "RisultatoPipelineLineaCentrica",
    "esegui_pipeline_linea_centrica",
]
