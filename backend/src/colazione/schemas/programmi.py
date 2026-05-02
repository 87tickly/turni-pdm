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
from typing import Any, Literal

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
    km_max_giornaliero: int | None = None
    km_max_ciclo: int | None = None
    n_giornate_default: int
    fascia_oraria_tolerance_min: int
    strict_options_json: dict[str, Any]
    stazioni_sosta_extra_json: list[str] = Field(default_factory=list)
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
    """

    model_config = ConfigDict(extra="forbid")

    filtri_json: list[FiltroRegola] = Field(default_factory=list)
    composizione: list[ComposizioneItem] = Field(min_length=1)
    is_composizione_manuale: bool = False
    priorita: int = Field(default=60, ge=0, le=100)
    # Sprint 7.7 MR 1: cap km del ciclo specifico per questa regola
    # (es. ETR526 ~4500 km/ciclo, E464 ~6000). Se vuoto, builder usa
    # il fallback DEFAULT_KM_MEDIO_GIORNALIERO * n_giornate_safety.
    km_max_ciclo: int | None = Field(default=None, ge=1)
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
    fascia_oraria_tolerance_min: int = Field(default=30, ge=0, le=120)
    strict_options_json: StrictOptions = Field(default_factory=StrictOptions)
    stazioni_sosta_extra_json: list[str] = Field(default_factory=list)
    regole: list[ProgrammaRegolaAssegnazioneCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_validita(self) -> ProgrammaMaterialeCreate:
        if self.valido_a < self.valido_da:
            raise ValueError("valido_a deve essere >= valido_da")
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
    fascia_oraria_tolerance_min: int | None = Field(default=None, ge=0, le=120)
    strict_options_json: StrictOptions | None = None
    stazioni_sosta_extra_json: list[str] | None = None
