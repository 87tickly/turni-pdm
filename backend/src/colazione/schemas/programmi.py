"""Schemas Pydantic — Strato 1bis (programma materiale).

Schemi `Read` + `Create` + `Update` per `programma_materiale` e
`programma_regola_assegnazione`. Vedi `docs/PROGRAMMA-MATERIALE.md` v0.2
per la spec completa.

Centro del modulo: la validazione di **`filtri_json`**, che è JSONB
opaco al DB ma deve seguire un schema applicativo rigoroso. La
classe `FiltroRegola` valida ogni singolo filtro (campo + op + valore
shape coerente).
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# =====================================================================
# Validazione filtri (vedi PROGRAMMA-MATERIALE.md §2.3)
# =====================================================================

#: Campi della corsa su cui un filtro può applicarsi.
#: Estendibile in futuro senza migration (filtri_json è JSONB opaco).
CAMPI_AMMESSI: frozenset[str] = frozenset(
    {
        "codice_linea",
        "direttrice",
        "categoria",
        "numero_treno",
        "rete",
        "codice_origine",
        "codice_destinazione",
        "is_treno_garantito_feriale",
        "is_treno_garantito_festivo",
        "fascia_oraria",
        "giorno_tipo",
    }
)

#: Operatori supportati. Compatibilità con i campi è validata caso per caso.
OP_AMMESSI: frozenset[str] = frozenset({"eq", "in", "between", "gte", "lte"})

#: Mapping campo → op ammessi (valori `bool` solo `eq`, `time` per range, ecc.)
_CAMPO_OP_COMPATIBILI: dict[str, frozenset[str]] = {
    "codice_linea": frozenset({"eq", "in"}),
    "direttrice": frozenset({"eq", "in"}),
    "categoria": frozenset({"eq", "in"}),
    "numero_treno": frozenset({"eq", "in"}),
    "rete": frozenset({"eq", "in"}),
    "codice_origine": frozenset({"eq", "in"}),
    "codice_destinazione": frozenset({"eq", "in"}),
    "is_treno_garantito_feriale": frozenset({"eq"}),
    "is_treno_garantito_festivo": frozenset({"eq"}),
    "fascia_oraria": frozenset({"between", "gte", "lte"}),
    "giorno_tipo": frozenset({"eq", "in"}),
}

#: Valori ammessi per `giorno_tipo` (validati a parte se l'op è `eq`/`in`).
_GIORNO_TIPO_VALIDI: frozenset[str] = frozenset({"feriale", "sabato", "festivo"})


class FiltroRegola(BaseModel):
    """Singolo filtro della regola.

    Esempi validi::

        {"campo": "codice_linea", "op": "eq", "valore": "S5"}
        {"campo": "categoria", "op": "in", "valore": ["RE", "R"]}
        {"campo": "fascia_oraria", "op": "between",
         "valore": ["04:00", "15:59"]}
        {"campo": "giorno_tipo", "op": "in", "valore": ["feriale"]}
        {"campo": "is_treno_garantito_feriale", "op": "eq", "valore": true}

    La validazione check:
    1. `campo` ∈ `CAMPI_AMMESSI`
    2. `op` ∈ `OP_AMMESSI`
    3. `op` compatibile con il `campo` (vedi `_CAMPO_OP_COMPATIBILI`)
    4. `valore` shape coerente con `op`:
       - `eq`/`gte`/`lte`: valore scalare (str/int/bool/time)
       - `in`: lista non vuota
       - `between`: lista di esattamente 2 elementi (low, high)
    5. Per `giorno_tipo`: i valori devono essere in `_GIORNO_TIPO_VALIDI`.
    6. Per `fascia_oraria`: i valori devono essere parsabili come `time`
       in formato HH:MM o HH:MM:SS.
    """

    model_config = ConfigDict(extra="forbid")

    campo: str
    op: str
    valore: Any

    @model_validator(mode="after")
    def _validate_full(self) -> FiltroRegola:
        # 1) campo ∈ ammessi
        if self.campo not in CAMPI_AMMESSI:
            raise ValueError(
                f"campo {self.campo!r} non supportato. Ammessi: {sorted(CAMPI_AMMESSI)}"
            )
        # 2) op ∈ ammessi
        if self.op not in OP_AMMESSI:
            raise ValueError(f"op {self.op!r} non supportato. Ammessi: {sorted(OP_AMMESSI)}")
        # 3) campo + op compatibili
        ops_for_campo = _CAMPO_OP_COMPATIBILI.get(self.campo, OP_AMMESSI)
        if self.op not in ops_for_campo:
            raise ValueError(
                f"op {self.op!r} non compatibile con campo {self.campo!r}. "
                f"Per questo campo ammessi: {sorted(ops_for_campo)}"
            )
        # 4) valore shape coerente con op
        if self.op in {"eq", "gte", "lte"}:
            if isinstance(self.valore, list | tuple | dict):
                raise ValueError(
                    f"op {self.op!r} richiede un valore scalare, ricevuto {type(self.valore).__name__}"
                )
        elif self.op == "in":
            if not isinstance(self.valore, list) or len(self.valore) == 0:
                raise ValueError("op 'in' richiede una lista non vuota")
        elif self.op == "between":
            if not isinstance(self.valore, list) or len(self.valore) != 2:
                raise ValueError("op 'between' richiede una lista di esattamente 2 elementi")

        # 5) giorno_tipo valori controllati
        if self.campo == "giorno_tipo":
            valori = self.valore if isinstance(self.valore, list) else [self.valore]
            for v in valori:
                if v not in _GIORNO_TIPO_VALIDI:
                    raise ValueError(
                        f"giorno_tipo {v!r} non valido. Ammessi: {sorted(_GIORNO_TIPO_VALIDI)}"
                    )

        # 6) fascia_oraria parsabili come time
        if self.campo == "fascia_oraria":
            valori = self.valore if isinstance(self.valore, list) else [self.valore]
            for v in valori:
                _parse_time_or_raise(v)

        return self


def _parse_time_or_raise(s: Any) -> time:
    """Parsa 'HH:MM' o 'HH:MM:SS' in time, solleva ValueError se mal formato."""
    if isinstance(s, time):
        return s
    if not isinstance(s, str):
        raise ValueError(
            f"fascia_oraria valore deve essere stringa HH:MM, ricevuto {type(s).__name__}"
        )
    parts = s.split(":")
    if len(parts) not in (2, 3):
        raise ValueError(f"fascia_oraria {s!r} non in formato HH:MM o HH:MM:SS")
    try:
        h = int(parts[0])
        m = int(parts[1])
        sec = int(parts[2]) if len(parts) == 3 else 0
        return time(h, m, sec)
    except (ValueError, TypeError) as e:
        raise ValueError(f"fascia_oraria {s!r} non valida: {e}") from e


# =====================================================================
# Strict options
# =====================================================================


class StrictOptions(BaseModel):
    """6 flag granulari di strict mode (vedi PROGRAMMA-MATERIALE.md §2.7).

    Default tutto `False` (tolerant) durante editing. Tutto `True`
    (strict) per pubblicazione.

    Sprint 5.1 ha rinominato `no_giro_non_chiuso_a_localita` →
    `no_giro_appeso` per riflettere la nuova semantica multi-giornata:
    un giro non deve essere "appeso" (cioè avere un rientro programmato
    a fine ciclo, NON ogni sera).
    """

    model_config = ConfigDict(extra="forbid")

    no_corse_residue: bool = False
    no_overcapacity: bool = False
    no_aggancio_non_validato: bool = False
    no_orphan_blocks: bool = False
    no_giro_appeso: bool = False
    no_km_eccesso: bool = False


# =====================================================================
# Composizione (Sprint 5.1)
# =====================================================================


class ComposizioneItem(BaseModel):
    """Singolo elemento della composizione di una regola.

    Una regola può avere una composizione di 1 o più elementi:
    - 1 elemento → regola single-material (es. `[{ETR526, 2}]`)
    - 2+ elementi → composizione mista
      (es. `[{ETR526, 1}, {ETR425, 1}]` per Mi.Centrale↔Tirano)

    Vedi `docs/SPRINT-5-RIPENSAMENTO.md` §3 ("Composizione regola").
    """

    model_config = ConfigDict(extra="forbid")

    materiale_tipo_codice: str = Field(min_length=1)
    n_pezzi: int = Field(ge=1)


# =====================================================================
# Read schemas (per API GET)
# =====================================================================


class ProgrammaRegolaAssegnazioneRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    programma_id: int
    filtri_json: list[Any]
    # Composizione "vera" (Sprint 5.1). Lista di 1+ elementi.
    composizione_json: list[Any]
    is_composizione_manuale: bool = False
    # Campi legacy (deprecati, nullable da migration 0007). Esposti per
    # retrocompat finché Sub 5.5 non rimuoverà l'ultimo consumatore
    # (`risolvi_corsa()`).
    materiale_tipo_codice: str | None = None
    numero_pezzi: int | None = None
    priorita: int
    # Sprint 7.7 MR 1: cap km del ciclo specifico per regola.
    km_max_ciclo: int | None = None
    # MR β (migration 0036): sede preferita memorizzata sulla regola.
    # NULL = da scegliere nel wizard pre-generazione.
    localita_codice: str | None = None
    note: str | None = None
    created_at: datetime


class ProgrammaMaterialeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    azienda_id: int
    nome: str
    valido_da: date
    valido_a: date
    stato: str
    # Sprint 8.0 MR 0 (entry 164): pipeline state machine per la
    # concatenazione fra ruoli. Validati lato applicazione da
    # ``StatoPipelinePdc`` / ``StatoManutenzione`` in
    # ``colazione.domain.pipeline``; lato DB CHECK constraint.
    stato_pipeline_pdc: str = "PDE_IN_LAVORAZIONE"
    stato_manutenzione: str = "IN_ATTESA"
    # Sub-MR 2.bis-c (entry 174): % copertura ultima run auto-assegna.
    # NULL se nessun run effettuato. Range 0..100 (CHECK DB).
    copertura_pct: float | None = None
    km_max_giornaliero: int | None = None
    km_max_ciclo: int | None = None
    n_giornate_default: int
    # Sprint 7.8: range lunghezza giri generati (soft min, hard max).
    n_giornate_min: int = 4
    n_giornate_max: int = 12
    fascia_oraria_tolerance_min: int
    # Sprint 8.0 MR-4 (entry 224): vincoli soste configurabili per programma.
    max_sosta_diurna_min: int | None = None
    min_servizio_giornata_pct: int | None = None
    strict_options_json: dict[str, Any]
    stazioni_sosta_extra_json: list[str] = Field(default_factory=list)
    # MR α (migration 0035): subset di codici MaterialeTipo "a disposizione"
    # del programma. `[]` = tutti i materiali della dotazione azienda.
    materiali_disponibili_codici_json: list[str] = Field(default_factory=list)
    # Sub-MR 5.bis-fork (migration 0037, entry 190): FK self verso il
    # programma genitore di cui questo è figlio (variazione di periodo).
    # NULL = programma base autonomo.
    programma_genitore_id: int | None = None
    # MR-1110 sotto-MR 10 (migration 0038, entry 206): tag pipeline
    # builder. ``"v1"`` = legacy (default), ``"v2"`` = pipeline
    # ``costruisci_turni_v2`` (entry 202).
    builder_version: Literal["v1", "v2"] = "v1"
    # Sprint 8.1 MR-A1 (migration 0041, entry 242): logica assegnazione
    # corsa→regola. ``"rigido"`` = filtra-e-scarta legacy.
    # ``"esplorativo"`` (default da MR-A8 entry 251) = esplora-e-rilassa
    # con vincoli soft + fallback governato. Ortogonale a ``builder_version``.
    builder_mode: Literal["rigido", "esplorativo", "linea_centrica"] = "esplorativo"
    created_by_user_id: int | None = None
    # Sprint dashboard 1° ruolo (entry 88): popolato via JOIN con `app_user`
    # quando la query usa `joinedload(ProgrammaMateriale.created_by)`.
    # `None` se l'utente è stato eliminato o la relazione non è stata caricata.
    created_by_username: str | None = None
    created_at: datetime
    updated_at: datetime


# =====================================================================
# Create / Update schemas (per API POST/PATCH)
# =====================================================================


class ProgrammaRegolaAssegnazioneCreate(BaseModel):
    """Payload per creare una regola dentro un programma esistente.

    Sprint 5.1: la firma è cambiata. La composizione è ora una lista di
    1+ elementi (`composizione: list[ComposizioneItem]`), invece dei
    campi singoli `materiale_tipo_codice + numero_pezzi`. L'handler API
    salva `composizione_json` e ri-popola i campi legacy dal primo
    elemento per retrocompat con `risolvi_corsa()` fino a Sub 5.5.

    Sprint 7.9 MR 7A (decisione utente 2026-05-03): ``filtri_json`` è
    OBBLIGATORIO (min_length=1). Una regola senza filtri catturerebbe
    TUTTE le corse del programma, costringendo il builder a coprirle
    con un singolo materiale → output ingestibile (caos di varianti).
    Il pianificatore deve definire scope esplicito (es. linea X +
    tipo treno Y) per ogni regola.
    """

    model_config = ConfigDict(extra="forbid")

    filtri_json: list[FiltroRegola] = Field(min_length=1)
    # MR γ: composizione opzionale. `[]` = "ipotesi non ancora dichiarata",
    # il wizard pre-generazione obbligherà l'utente a sceglierla per quel
    # run e farà auto-save sulla regola via PATCH.
    composizione: list[ComposizioneItem] = Field(default_factory=list)
    is_composizione_manuale: bool = False
    priorita: int = Field(default=60, ge=0, le=100)
    # Sprint 7.7 MR 1: cap km del ciclo specifico per questa regola
    # (es. ETR526 ~4500 km/ciclo, E464 ~6000). Se vuoto, builder usa
    # il fallback DEFAULT_KM_MEDIO_GIORNALIERO * n_giornate_safety.
    km_max_ciclo: int | None = Field(default=None, ge=1)
    # MR β: sede manutentiva preferita. Opzionale alla creazione (può
    # essere settata nel wizard pre-generazione e auto-salvata).
    localita_codice: str | None = Field(default=None, min_length=1)
    note: str | None = None


class ProgrammaRegolaAssegnazioneUpdate(BaseModel):
    """MR β — payload PATCH per editare una regola esistente.

    Tutti i campi opzionali. Mantiene parità con ``Create`` ma senza
    obbligatorietà. La modifica di ``filtri_json`` o ``composizione``
    invalida i giri persistiti del programma — la UI mostra warning.
    """

    model_config = ConfigDict(extra="forbid")

    filtri_json: list[FiltroRegola] | None = Field(default=None, min_length=1)
    # MR γ: composizione opzionale anche in PATCH. Empty list valida (=
    # rimuove ipotesi). None = non toccare il valore esistente.
    composizione: list[ComposizioneItem] | None = None
    is_composizione_manuale: bool | None = None
    priorita: int | None = Field(default=None, ge=0, le=100)
    km_max_ciclo: int | None = Field(default=None, ge=1)
    localita_codice: str | None = None
    note: str | None = None


class ProgrammaMaterialeCreate(BaseModel):
    """Payload per creare un nuovo programma materiale (stato `bozza`)."""

    model_config = ConfigDict(extra="forbid")

    nome: str = Field(min_length=1)
    valido_da: date
    valido_a: date
    km_max_giornaliero: int | None = Field(default=None, ge=1)
    km_max_ciclo: int | None = Field(default=None, ge=1)
    n_giornate_default: int = Field(default=1, ge=1)
    # Sprint 7.8: range lunghezza giri (soft min, hard max).
    n_giornate_min: int = Field(default=4, ge=1, le=30)
    n_giornate_max: int = Field(default=12, ge=1, le=30)
    fascia_oraria_tolerance_min: int = Field(default=30, ge=0, le=120)
    # Sprint 8.0 MR-4 (entry 224): vincoli soste configurabili.
    max_sosta_diurna_min: int | None = Field(default=None, ge=0, le=1440)
    min_servizio_giornata_pct: int | None = Field(default=None, ge=0, le=100)
    strict_options_json: StrictOptions = Field(default_factory=StrictOptions)
    stazioni_sosta_extra_json: list[str] = Field(default_factory=list)
    # MR α: subset di codici MaterialeTipo dichiarato dal pianificatore.
    # `[]` (default) = tutti i materiali della dotazione azienda.
    materiali_disponibili_codici_json: list[str] = Field(default_factory=list)
    # MR-1110 sotto-MR 10 (entry 206): pipeline builder. Default ``"v1"``
    # (legacy) per nuovi programmi creati via API; il pianificatore può
    # esplicitare ``"v2"`` per attivare il nuovo builder a varianti
    # calendariali (PDF Trenord). Migration 0038 setta tutti i programmi
    # esistenti a ``"v1"`` server_default.
    builder_version: Literal["v1", "v2"] = "v1"
    # Sprint 8.1 MR-A1 (entry 242): logica assegnazione corsa→regola.
    # Default ``"esplorativo"`` da MR-A8 entry 251 (post-validazione A7
    # con fix HIGH-1 SEVERO: sotto-min 52%→8% prog 17, 33%→4% prog 16).
    # Il pianificatore può forzare ``"rigido"`` per programmi specifici
    # se necessario (es. ripristinare comportamento legacy).
    builder_mode: Literal["rigido", "esplorativo", "linea_centrica"] = "esplorativo"
    regole: list[ProgrammaRegolaAssegnazioneCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_validita(self) -> ProgrammaMaterialeCreate:
        if self.valido_a < self.valido_da:
            raise ValueError("valido_a deve essere >= valido_da")
        if self.n_giornate_max < self.n_giornate_min:
            raise ValueError(
                f"n_giornate_max ({self.n_giornate_max}) deve essere >= "
                f"n_giornate_min ({self.n_giornate_min})"
            )
        return self


class ProgrammaMaterialeUpdate(BaseModel):
    """Payload per aggiornare un programma esistente. Tutti i campi opzionali."""

    model_config = ConfigDict(extra="forbid")

    nome: str | None = Field(default=None, min_length=1)
    valido_da: date | None = None
    valido_a: date | None = None
    stato: Literal["bozza", "attivo", "archiviato"] | None = None
    km_max_giornaliero: int | None = Field(default=None, ge=1)
    km_max_ciclo: int | None = Field(default=None, ge=1)
    n_giornate_default: int | None = Field(default=None, ge=1)
    # Sprint 7.8: range lunghezza giri (soft min, hard max).
    n_giornate_min: int | None = Field(default=None, ge=1, le=30)
    n_giornate_max: int | None = Field(default=None, ge=1, le=30)
    fascia_oraria_tolerance_min: int | None = Field(default=None, ge=0, le=120)
    # Sprint 8.0 MR-4 (entry 224): vincoli soste configurabili.
    max_sosta_diurna_min: int | None = Field(default=None, ge=0, le=1440)
    min_servizio_giornata_pct: int | None = Field(default=None, ge=0, le=100)
    strict_options_json: StrictOptions | None = None
    stazioni_sosta_extra_json: list[str] | None = None
    # MR α: aggiornamento subset codici materiale disponibili.
    materiali_disponibili_codici_json: list[str] | None = None
    # MR-1110 sotto-MR 10 (entry 206): switch tra pipeline builder
    # legacy ("v1") e nuova ("v2"). Cambio invasivo: rigenerare i giri
    # del programma dopo il PATCH.
    builder_version: Literal["v1", "v2"] | None = None
    # Sprint 8.1 MR-A1 (entry 242): switch tra logica assegnazione
    # legacy ("rigido") ed esplorativa ("esplorativo"). Cambio invasivo
    # come builder_version: rigenerare i giri dopo il PATCH per vedere
    # l'effetto. Foundation in MR-A1: il valore è settabile ma nessun
    # consumatore lo legge fino a MR-A3.
    builder_mode: Literal["rigido", "esplorativo", "linea_centrica"] | None = None


# =====================================================================
# Pipeline state machine — Sprint 8.0 MR 0 (entry 164)
# =====================================================================


class VariazionePdERequest(BaseModel):
    """Body per ``POST /api/programmi/{id}/variazioni`` (Sprint 8.0 MR 5).

    Registra una ``CorsaImportRun`` di tipo non-BASE collegata al
    programma. La logica concreta di applicazione delle variazioni
    (cancellare/modificare/aggiungere corse) è scope MR 5.bis: per ora
    si tracciano solo i metadati per audit trail e timeline.
    """

    model_config = ConfigDict(extra="forbid")

    tipo: Literal[
        "INTEGRAZIONE",
        "VARIAZIONE_INTERRUZIONE",
        "VARIAZIONE_ORARIO",
        "VARIAZIONE_CANCELLAZIONE",
    ]
    source_file: str = Field(min_length=1, max_length=500)
    n_corse: int = Field(default=0, ge=0)
    note: str | None = Field(default=None, max_length=1000)


class ApplicaVariazionePdEResponse(BaseModel):
    """Response del ``POST /api/programmi/{id}/variazioni/{run_id}/applica``
    (Sprint 8.0 MR 5.bis, entry 173).

    Riassume le operazioni eseguite dal parser incrementale + planner
    (vedi ``colazione.domain.variazioni_pde``):

    - ``n_corse_create``: nuove ``CorsaCommerciale`` inserite
      (solo per ``INTEGRAZIONE``).
    - ``n_corse_update``: corse esistenti modificate (orari per
      ``VARIAZIONE_ORARIO``, calendario per ``VARIAZIONE_INTERRUZIONE``
      / ``VARIAZIONE_CANCELLAZIONE``).
    - ``warnings``: lista di problemi non bloccanti (es. corse target
      non trovate, match ambigui). Persistite anche in ``run.note``
      per audit trail.
    - ``programmi_impattati``: sub-MR 5.bis-impact (entry 179) — list
      dei programmi materiali che hanno giri/turni PdC che referenziano
      le corse coinvolte. Permette UI di alertare l'utente prima che
      decida se forkare o lasciar proseguire.

    La run viene marcata ``completed_at != NULL`` dopo questa chiamata
    e diventa **non riapplicabile** (nuovo POST /applica → 409).
    """

    model_config = ConfigDict(extra="forbid")

    run_id: int
    tipo: str
    n_corse_lette_da_file: int
    """Righe parsate dal file (al netto dei BUS sostitutivi scartati)."""
    n_corse_create: int
    n_corse_update: int
    n_warnings: int
    warnings: list[str]
    completed_at: datetime
    programmi_impattati: list[ProgrammaImpattoRead] = Field(default_factory=list)
    """Sub-MR 5.bis-impact (entry 179): programmi materiali con giri/
    turni PdC che referenziano le corse coinvolte dalla variazione.
    Lista vuota = nessun impatto (caso comune per INTEGRAZIONE pura).
    Forward reference perché ``ProgrammaImpattoRead`` è definito sotto."""


class SbloccaProgrammaRequest(BaseModel):
    """Body opzionale per ``POST /programmi/{id}/sblocca`` (admin only).

    L'admin può sbloccare un programma facendolo regredire allo stato
    immediatamente precedente sul ramo specificato. Il motivo è
    facoltativo ma raccomandato: viene tracciato nei log del backend
    (decisione MR 0: niente persistenza dedicata, basta il log).
    """

    model_config = ConfigDict(extra="forbid")

    ramo: Literal["pdc", "manutenzione"] = "pdc"
    motivo: str | None = Field(default=None, max_length=500)


# =====================================================================
# Auto-assegna persone — Sub-MR 2.bis-a (Sprint 8.0)
# =====================================================================


class AutoAssegnaPersoneRequest(BaseModel):
    """Body per ``POST /api/programmi/{id}/auto-assegna-persone``.

    Specifica la finestra calendariale ``[data_da, data_a]`` da
    auto-assegnare. Entrambi i campi sono opzionali: se omessi, il
    backend usa ``programma.valido_da`` / ``programma.valido_a``.
    """

    model_config = ConfigDict(extra="forbid")

    data_da: date | None = Field(
        default=None,
        description="Inizio finestra (incluso). Default = programma.valido_da.",
    )
    data_a: date | None = Field(
        default=None,
        description="Fine finestra (inclusa). Default = programma.valido_a.",
    )

    @model_validator(mode="after")
    def _validate_finestra(self) -> AutoAssegnaPersoneRequest:
        if self.data_da and self.data_a and self.data_da > self.data_a:
            raise ValueError("data_da deve essere ≤ data_a")
        return self


class AssegnazioneCreataRead(BaseModel):
    """Una assegnazione persona → giornata creata dall'algoritmo."""

    model_config = ConfigDict(extra="forbid")

    persona_id: int
    turno_pdc_giornata_id: int
    data: date


class MancanzaRead(BaseModel):
    """Una giornata non coperta + motivo (richiede override manuale)."""

    model_config = ConfigDict(extra="forbid")

    turno_pdc_giornata_id: int
    turno_pdc_id: int
    data: date
    motivo: str
    """Valore di ``MotivoMancanza`` enum (vedi
    ``domain/normativa/assegnazione_persone.py``)."""


class WarningSoftRead(BaseModel):
    """Un warning soft: assegnazione effettuata ma con possibile
    violazione di vincolo non rigido."""

    model_config = ConfigDict(extra="forbid")

    persona_id: int
    data: date
    tipo: str
    """Valore di ``TipoWarningSoft`` enum."""
    descrizione: str


class AutoAssegnaPersoneResponse(BaseModel):
    """Response del ``POST /auto-assegna-persone``.

    KPI principale: ``delta_copertura_pct`` (0..100). Il side-effect su
    ``conferma-personale`` (sub-MR 2.bis-c) gaterà la transizione a
    ``PERSONALE_ASSEGNATO`` su questo valore.
    """

    model_config = ConfigDict(extra="forbid")

    finestra_data_da: date
    finestra_data_a: date
    n_giornate_totali: int
    n_giornate_coperte: int
    n_assegnazioni_create: int
    """Quante NUOVE assegnazioni l'algoritmo ha persistito (≠
    ``n_giornate_coperte`` perché alcune erano già coperte)."""
    delta_copertura_pct: float
    assegnazioni: list[AssegnazioneCreataRead]
    mancanze: list[MancanzaRead]
    warning_soft: list[WarningSoftRead]


class AssegnaManualeRequest(BaseModel):
    """Body per ``POST /api/programmi/{id}/assegna-manuale`` (sub-MR 2.bis-b).

    Override manuale: assegna una specifica persona a una specifica
    ``(turno_pdc_giornata, data)`` bypassando i vincoli HARD del greedy.

    Use case principale: chiudere mancanze residue dell'algoritmo
    auto-assegna (es. ``tutti_riposo_intraturno_violato`` quando il
    deposito è sotto-staffato e il pianificatore accetta consapevolmente
    una violazione del riposo).

    Vincoli applicati lato backend:

    - Programma in stato ``PDC_CONFERMATO`` (stesso check di auto-assegna).
    - Persona esiste, stessa azienda, ``profilo='PdC'``,
      ``is_matricola_attiva=True``.
    - Giornata esiste e appartiene a un turno del programma.
    - Niente conflitto: persona non già assegnata sulla stessa data,
      giornata non già coperta sulla stessa data (409 in entrambi i casi).
    - **Non si controlla**: sede, indisponibilità, riposo intraturno,
      qualifiche. È l'override consapevole del pianificatore.
    """

    model_config = ConfigDict(extra="forbid")

    persona_id: int = Field(gt=0)
    turno_pdc_giornata_id: int = Field(gt=0)
    data: date


# =====================================================================
# Apply variazioni PdE — Sub-MR 5.bis-a (entry 176, alignment con MR 5.bis)
# =====================================================================
#
# Endpoint generico ``POST /variazioni/{run_id}/apply`` che riceve
# operazioni Pydantic già parsate da N input (form UI / file delta / PdE
# intero). Complementare a ``POST /applica`` (entry 175) che invece
# riceve un file PdE multipart e lo parsa internamente. I 2 endpoint
# convivono e applicano le stesse 4 semantiche, sullo stesso schema
# soft-delete via flag ``is_cancellata`` (migration 0034).


class _OperazioneBase(BaseModel):
    """Base privata per le operazioni di variazione."""

    model_config = ConfigDict(extra="forbid")


class OperazioneInsertCorsaRequest(_OperazioneBase):
    """Inserisce una nuova ``corsa_commerciale`` (per ``INTEGRAZIONE``).

    Limitazione dichiarata sub-MR 5.bis-a: la corsa creata **non** ha
    le 9 ``corsa_composizione`` associate (richiede campi PdE
    aggiuntivi che il payload core non porta). Per le composizioni
    usare l'endpoint multipart ``/applica`` (entry 175) che parsa il
    file PdE completo.
    """

    tipo: Literal["INSERT_CORSA"]
    numero_treno: str = Field(min_length=1, max_length=20)
    codice_origine: str = Field(min_length=1, max_length=20)
    codice_destinazione: str = Field(min_length=1, max_length=20)
    ora_partenza: time
    ora_arrivo: time
    valido_da: date
    valido_a: date
    valido_in_date_json: list[str] = Field(default_factory=list)
    rete: str | None = Field(default=None, max_length=10)
    codice_linea: str | None = Field(default=None, max_length=20)
    direttrice: str | None = None
    categoria: str | None = Field(default=None, max_length=20)
    min_tratta: int | None = Field(default=None, ge=0)
    km_tratta: Decimal | None = None
    row_hash: str | None = Field(default=None, max_length=64)


class OperazioneUpdateOrarioRequest(_OperazioneBase):
    """Aggiorna orari di una corsa esistente (per ``VARIAZIONE_ORARIO``)."""

    tipo: Literal["UPDATE_ORARIO"]
    corsa_id: int = Field(gt=0)
    ora_partenza: time | None = None
    ora_arrivo: time | None = None
    min_tratta: int | None = Field(default=None, ge=0)
    km_tratta: Decimal | None = None


class OperazioneRimuoviDateRequest(_OperazioneBase):
    """Esclude date dal ``valido_in_date_json`` (per
    ``VARIAZIONE_INTERRUZIONE``)."""

    tipo: Literal["RIMUOVI_DATE_VALIDITA"]
    corsa_id: int = Field(gt=0)
    date_da_rimuovere: list[date] = Field(min_length=1)


class OperazioneCancellaCorsaRequest(_OperazioneBase):
    """Soft-delete di una corsa (per ``VARIAZIONE_CANCELLAZIONE``)."""

    tipo: Literal["CANCELLA_CORSA"]
    corsa_id: int = Field(gt=0)


OperazioneVariazioneRequest = Annotated[
    OperazioneInsertCorsaRequest
    | OperazioneUpdateOrarioRequest
    | OperazioneRimuoviDateRequest
    | OperazioneCancellaCorsaRequest,
    Field(discriminator="tipo"),
]


class ApplyVariazioneRequest(BaseModel):
    """Body di ``POST /api/programmi/{id}/variazioni/{run_id}/apply``.

    Sub-MR 5.bis-a: porta una lista di operazioni atomiche già parsate
    dal generatore (form UI / file delta / PdE intero via 5.bis-b/c/d).
    Il backend valida tutto contro lo stato corse esistente e applica
    in transazione.

    ``fail_on_any_error``:

    - ``True`` (default, sicuro): se anche **una sola** operazione ha
      errori, il backend ritorna 400 con la lista errori, **niente**
      è applicato (atomico tutto-o-niente).
    - ``False``: applica solo le operazioni valide, ritorna 200 con
      gli errori delle scartate. Modalità "best-effort" per workflow
      tolleranti.
    """

    model_config = ConfigDict(extra="forbid")

    operazioni: list[OperazioneVariazioneRequest] = Field(
        min_length=1, max_length=10000
    )
    fail_on_any_error: bool = True


class ApplyVariazioneErroreRead(BaseModel):
    """Errore su una singola operazione (mappato da
    ``ErroreValidazione`` del dominio)."""

    model_config = ConfigDict(extra="forbid")

    indice_operazione: int
    codice: str
    """Valore di ``CodiceErrore`` enum (vedi ``domain/variazioni.py``)."""
    motivo: str
    corsa_id: int | None = None


class ApplyVariazioneResponse(BaseModel):
    """Response di ``POST /apply``.

    Counter granulari per il report UX. ``n_no_op`` traccia operazioni
    valide che non hanno mutato stato (idempotenza).
    """

    model_config = ConfigDict(extra="forbid")

    run_id: int
    completed_at: datetime
    n_insert_corsa: int
    n_update_orario: int
    n_rimuovi_date: int
    n_cancella_corsa: int
    n_no_op: int
    n_errori: int
    n_date_rimosse_totale: int
    """Somma delle date effettivamente rimosse da ``valido_in_date_json``
    per le ``RimuoviDateValidita`` applicate (può essere < somma date
    richieste se alcune erano già fuori dalla validità)."""
    errori: list[ApplyVariazioneErroreRead]
    programmi_impattati: list[ProgrammaImpattoRead] = Field(default_factory=list)
    """Sub-MR 5.bis-impact (entry 179): programmi materiali con giri/
    turni PdC che referenziano le corse coinvolte. Stesso campo di
    ``ApplicaVariazionePdEResponse`` per coerenza tra i 2 endpoint."""


# =====================================================================
# PdE livello azienda (Sub-MR 5.bis-d, entry 177)
# =====================================================================
#
# Il PdE Trenord è un singolo file annuale per azienda (~10580 corse,
# validità 14/12 → 12/12 dell'anno successivo). Caricato 1 volta a
# inizio stagione. Le variazioni infrannuali (interruzioni RFI,
# integrazioni weekend, modifiche orari) si accumulano cronologicamente
# e modificano lo stato delle corse — il PdE base resta come record.
#
# Le variazioni a livello azienda hanno ``programma_materiale_id IS NULL``
# (FK SET NULL già esistente sul modello). Tutti i programmi vedono
# automaticamente lo stato corrente delle corse.


class PdEStatusRead(BaseModel):
    """Stato del PdE corrente dell'azienda dell'utente loggato.

    Letto dal pannello "PdE Annuale" della dashboard PIANIFICATORE_GIRO.
    Rappresenta una vista aggregata: ultimo run BASE caricato + count
    delle variazioni applicate nel tempo.
    """

    model_config = ConfigDict(extra="forbid")

    base_run: dict[str, Any] | None = None
    """Ultimo ``CorsaImportRun`` di tipo ``BASE`` (= ``CorsaImportRunRead``
    serializzato come dict per evitare circular import). ``None`` se
    non è mai stato caricato un PdE base per questa azienda."""

    n_corse_attive: int
    """Conteggio corse non cancellate (``is_cancellata=False``) per
    l'azienda. Stato corrente del PdE applicato."""

    n_corse_totali: int
    """Conteggio corse totali (incluse cancellate). Differenza con
    ``n_corse_attive`` = corse soft-deleted via VARIAZIONE_CANCELLAZIONE."""

    n_variazioni_totali: int
    """Conteggio ``CorsaImportRun`` di tipo non-BASE collegate
    all'azienda con ``programma_materiale_id IS NULL`` (variazioni
    globali). Tutte (applicate + non applicate)."""

    n_variazioni_applicate: int
    """Subset di ``n_variazioni_totali`` con ``completed_at IS NOT NULL``."""

    ultima_variazione_at: datetime | None = None
    """Timestamp ``completed_at`` della variazione applicata più recente.
    ``None`` se nessuna variazione è ancora stata applicata."""

    validity_da: date | None = None
    """``MIN(valido_da)`` delle corse non cancellate. Tipicamente
    14/12 dell'anno precedente."""

    validity_a: date | None = None
    """``MAX(valido_a)`` delle corse non cancellate. Tipicamente
    12/12 dell'anno corrente."""


class CaricaPdEBaseResponse(BaseModel):
    """Risposta dell'endpoint ``POST /api/aziende/me/pde/base``.

    Mappa diretta di ``ImportSummary`` (vedi ``importers/pde_importer.py``).
    Counter delta-sync: il caricamento applica diff multiset rispetto
    allo stato corrente (kept = id stabile, create = nuovo, delete =
    rimosso dal file ma presente in DB).
    """

    model_config = ConfigDict(extra="forbid")

    skipped: bool
    """``True`` se il file è già stato importato (stesso SHA-256). Il
    body include ``run_id`` del run originale per riferimento."""

    skip_reason: str | None = None
    """Descrizione del motivo dello skip (per UI feedback)."""

    run_id: int | None = None
    n_total: int
    n_create: int
    n_delete: int
    n_kept: int
    n_warnings: int
    duration_s: float


# =====================================================================
# Impatto variazioni su giri/turni esistenti (Sub-MR 5.bis-impact, entry 179)
# =====================================================================
#
# Una variazione modifica/cancella corse del PdE. Le corse possono
# essere già state consumate da giri materiali e turni PdC esistenti
# (FK RESTRICT su ``giro_blocco.corsa_commerciale_id`` e
# ``turno_pdc_blocco.corsa_commerciale_id``). Detection-only: il
# response di ``/applica`` include la lista programmi impattati con
# counter per UI alert. La gestione concreta (rigenerazione, fork)
# è scope MR successivo.


class ProgrammaImpattoRead(BaseModel):
    """Riepilogo dell'impatto di una variazione su un programma materiale.

    Un programma è "impattato" se almeno un suo ``giro_materiale`` o
    ``turno_pdc`` ha blocchi che referenziano corse coinvolte dalla
    variazione (UPDATE_ORARIO / RIMUOVI_DATE_VALIDITA / CANCELLAZIONE).
    Le INTEGRAZIONI non producono impatto: aggiungono corse nuove che
    nessun giro referenzia ancora.
    """

    model_config = ConfigDict(extra="forbid")

    programma_id: int
    nome: str
    valido_da: date
    valido_a: date | None
    n_giri_impattati: int
    """Conteggio ``giro_materiale`` distinti del programma con almeno
    un ``giro_blocco`` che referenzia una corsa coinvolta."""
    n_turni_pdc_impattati: int
    """Conteggio ``turno_pdc`` distinti del programma con almeno un
    ``turno_pdc_blocco`` che referenzia una corsa coinvolta. La
    relazione turno→programma passa via
    ``generation_metadata_json['giro_materiale_id']``."""
    n_assegnazioni_impattate: int
    """Conteggio ``assegnazione_giornata`` su giornate dei turni PdC
    impattati. Approssimazione: una giornata può avere molti blocchi,
    qui contiamo le assegnazioni delle giornate che hanno ALMENO un
    blocco impattato."""


# =====================================================================
# Crea programma di variazione (fork) — Sub-MR 5.bis-fork (entry 190)
# =====================================================================


class CreaForkVariazioneRequest(BaseModel):
    """Body di ``POST /api/aziende/me/variazioni/{run_id}/crea-fork``.

    Crea un nuovo ``programma_materiale`` con
    ``programma_genitore_id = genitore_id`` e finestra di validità
    coincidente col periodo della variazione.

    Il programma figlio è in stato ``bozza`` (default) e lo stato
    pipeline parte da ``PDE_IN_LAVORAZIONE`` come per un programma
    base. Il pianificatore ci genera giri e turni via il flusso
    standard. Per le date del proprio range il figlio prevale sul
    genitore (convenzione "merge per data" — vedi migration 0037).
    """

    model_config = ConfigDict(extra="forbid")

    nome: str = Field(min_length=1, max_length=200)
    """Nome del programma figlio. Convenzione consigliata:
    ``"<nome_genitore> — variazione <descrizione>"``. Validato
    solo per lunghezza, niente vincoli di unicità (il backend non
    impone uniqueness su ``nome``)."""

    valido_da: date
    valido_a: date

    genitore_id: int = Field(gt=0)
    """ID del ``programma_materiale`` genitore. Deve appartenere
    all'azienda dell'utente corrente (404 altrimenti)."""

    @model_validator(mode="after")
    def _validate(self) -> CreaForkVariazioneRequest:
        if self.valido_da > self.valido_a:
            raise ValueError("valido_da deve essere ≤ valido_a")
        return self
