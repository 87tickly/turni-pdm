"""Importer Programma di Esercizio (PdE) — Sprint 3.

Spec: `docs/IMPORT-PDE.md`. Pipeline:

    file .numbers / .xlsx
        → read_pde_file()  → list[dict[colonna → valore]]
        → parse_corsa_row() → CorsaParsedRow (con composizioni nested)
            └── parse_periodicita() → PeriodicitaParsed
            └── compute_valido_in_date() → set[date]
            └── (info) cross_check_gg_mensili() → list[str] warning

Questo modulo contiene **solo le funzioni pure di parsing**. L'inserimento
in DB + idempotenza + CLI vivono in `pde_importer.py` (Sprint 3.6+).

## Convenzioni del PdE Trenord (decisione utente, 2026-04-26)

Il campo testuale `Periodicità` è la **fonte di verità** per quando un
treno circola. Il parser estrae **letteralmente** quanto scritto:

1. **Filtro giorno-della-settimana globale**: frasi tipo
   "Circola il sabato e la domenica" → solo sab/dom in tutto il range
   di validità.
2. **Apply intervals**: "Circola dal X al Y" o
   "Circola tutti i giorni dal X al Y" → tutti i giorni dell'intervallo.
3. **Apply dates esplicite**: "Circola DD/MM/YYYY, DD/MM/YYYY, ...".
4. **Skip intervals/dates**: "Non circola dal X al Y" o
   "Non circola DD/MM/YYYY, ...".

Il parser **non** auto-sopprime le festività italiane: se il testo dice
"Circola tutti i giorni", il treno circola anche a Natale. Le festività
sono escluse solo se elencate esplicitamente in `Non circola DD/MM/YYYY`.

Il modulo `holidays.py` resta disponibile come utility (può servire al
builder giro materiale o ad altre logiche), ma `compute_valido_in_date`
non lo usa.

Il campo `Codice Periodicità` (mini-DSL Trenord interno con token
EC/NCG/S/CP/P/ECF/G1-G7) **non** è parsato: per decisione utente, la
fonte di verità è il testo, e il Codice è solo backup informativo.

I `Gg_*` mensili e `Gg_anno` sono salvati nel DB come dati informativi
del PdE; eventuali discrepanze tra date calcolate e `Gg_*` producono
**warning informativi** (non bloccano l'import). Le discrepanze
indicano che il testo `Periodicità` Trenord differisce dai conteggi
interni Trenord (probabilmente derivati dal `Codice Periodicità`).
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# =====================================================================
# Pydantic models intermedi
# =====================================================================


class PeriodicitaParsed(BaseModel):
    """Output del parser del campo testuale 'Periodicità'.

    - `is_tutti_giorni`: True se appare 'Circola tutti i giorni' come
      frase pura (senza intervallo `dal X al Y`).
    - `filtro_giorni_settimana`: insieme di weekday (`0`=lun ... `6`=dom)
      che fungono da filtro globale (es. "Circola il sabato e la domenica"
      → `{5, 6}`). Vuoto = nessun filtro.
    - `apply_intervals`: intervalli `Circola dal X al Y` (estremi inclusi).
      Sono **override del filtro globale**: dentro l'intervallo circola
      tutti i giorni, non solo quelli filtrati.
    - `apply_dates`: date singole `Circola DD/MM/YYYY`. Sono **override
      delle festività auto-soppresse**: una data esplicitamente elencata
      circola anche se è festività.
    - `skip_intervals`: intervalli `Non circola dal X al Y`.
    - `skip_dates`: date singole `Non circola DD/MM/YYYY`.
    """

    is_tutti_giorni: bool = False
    filtro_giorni_settimana: set[int] = Field(default_factory=set)
    apply_intervals: list[tuple[date, date]] = Field(default_factory=list)
    apply_dates: set[date] = Field(default_factory=set)
    skip_intervals: list[tuple[date, date]] = Field(default_factory=list)
    skip_dates: set[date] = Field(default_factory=set)


class ComposizioneParsed(BaseModel):
    """Riga di `corsa_composizione` (1 di 9 combinazioni stagione × giorno_tipo)."""

    stagione: str  # 'invernale' | 'estiva' | 'agosto'
    giorno_tipo: str  # 'feriale' | 'sabato' | 'festivo'
    categoria_posti: str | None = None
    is_doppia_composizione: bool = False
    tipologia_treno: str | None = None
    vincolo_dichiarato: str | None = None
    categoria_bici: str | None = None
    categoria_prm: str | None = None


class CorsaParsedRow(BaseModel):
    """Singola riga PdE parsata, prima dell'inserimento in DB.

    Campi mappati 1:1 su `corsa_commerciale` + sottolista
    `composizioni` con i 9 record di `corsa_composizione`.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Identificativi
    numero_treno: str
    rete: str | None = None
    numero_treno_rfi: str | None = None
    numero_treno_fn: str | None = None
    categoria: str | None = None
    codice_linea: str | None = None
    direttrice: str | None = None

    # Geografia
    codice_origine: str
    codice_destinazione: str
    codice_inizio_cds: str | None = None
    codice_fine_cds: str | None = None

    # Orari
    ora_partenza: time
    ora_arrivo: time
    ora_inizio_cds: time | None = None
    ora_fine_cds: time | None = None
    min_tratta: int | None = None
    min_cds: int | None = None
    km_tratta: Decimal | None = None
    km_cds: Decimal | None = None

    # Periodicità
    valido_da: date
    valido_a: date
    codice_periodicita: str | None = None
    periodicita_breve: str | None = None
    is_treno_garantito_feriale: bool = False
    is_treno_garantito_festivo: bool = False
    fascia_oraria: str | None = None

    # Calendario
    giorni_per_mese_json: dict[str, int] = Field(default_factory=dict)
    valido_in_date_json: list[str] = Field(default_factory=list)

    # Aggregati
    totale_km: Decimal | None = None
    totale_minuti: int | None = None
    posti_km: Decimal | None = None
    velocita_commerciale: Decimal | None = None

    # Composizioni nested (9 righe)
    composizioni: list[ComposizioneParsed] = Field(default_factory=list)

    # Warning del parser (cross-check Gg_*, valori incompleti, ecc.)
    warnings: list[str] = Field(default_factory=list)


# =====================================================================
# Reader: file .numbers o .xlsx → list[dict]
# =====================================================================


def read_pde_file(path: Path) -> list[dict[str, Any]]:
    """Legge un file PdE e ritorna le righe come dict (header → valore).

    Supporta `.numbers` (via `numbers-parser`) e `.xlsx` (via `openpyxl`).
    Il primo sheet/tabella è quello dei treni ('PdE RL' nel file Trenord).
    Il primo riga è interpretata come header.
    """
    suffix = path.suffix.lower()
    if suffix == ".numbers":
        return _read_numbers(path)
    if suffix == ".xlsx":
        return _read_xlsx(path)
    raise ValueError(f"Formato non supportato: {suffix}. Usa .numbers o .xlsx.")


def _read_numbers(path: Path) -> list[dict[str, Any]]:
    from numbers_parser import Document

    doc = Document(str(path))
    table = doc.sheets[0].tables[0]
    rows = list(table.rows())
    if not rows:
        return []
    header = [str(cell.value) if cell.value is not None else "" for cell in rows[0]]
    out: list[dict[str, Any]] = []
    for row in rows[1:]:
        values = [cell.value for cell in row]
        out.append(dict(zip(header, values, strict=False)))
    return out


def _read_xlsx(path: Path) -> list[dict[str, Any]]:
    from openpyxl import load_workbook

    wb = load_workbook(str(path), read_only=True, data_only=True)
    ws = wb.active
    if ws is None:
        return []
    rows = list(ws.values)
    if not rows:
        return []
    header = [str(h) if h is not None else "" for h in rows[0]]
    out: list[dict[str, Any]] = []
    for row in rows[1:]:
        out.append(dict(zip(header, row, strict=False)))
    return out


# =====================================================================
# Helper di normalizzazione (gestiscono int/float/str/datetime/None)
# =====================================================================


def _to_str_treno(value: Any) -> str:
    """Converte numero treno: float 13.0 → '13', int 13 → '13', str '13' → '13'."""
    if value is None or value == "":
        raise ValueError("numero treno mancante")
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(value)
    return str(value).strip()


def _to_opt_str(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(value)
    return str(value).strip()


def _to_opt_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int | float):
        return int(value)
    return int(str(value).strip())


def _to_opt_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _to_date(value: Any) -> date:
    """Converte datetime/date → date. Accetta anche string 'DD/MM/YYYY' o ISO."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        s = value.strip()
        if "/" in s:
            return _parse_date_it(s)
        return date.fromisoformat(s)
    raise TypeError(f"valore non convertibile in date: {value!r} ({type(value).__name__})")


def _to_time(value: Any) -> time:
    """Converte string 'HH:MM:SS' / time / datetime → time."""
    if isinstance(value, time):
        return value
    if isinstance(value, datetime):
        return value.time()
    if isinstance(value, str):
        s = value.strip()
        parts = s.split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        sec = int(parts[2]) if len(parts) > 2 else 0
        return time(h, m, sec)
    raise TypeError(f"valore non convertibile in time: {value!r} ({type(value).__name__})")


def _to_opt_time(value: Any) -> time | None:
    if value is None or value == "":
        return None
    return _to_time(value)


def _to_bool_si_no(value: Any) -> bool:
    """Converte 'SI'/'NO' (e True/False) → bool. Default False."""
    if value is None or value == "":
        return False
    if isinstance(value, bool):
        return value
    s = str(value).strip().upper()
    return s == "SI"


# =====================================================================
# Parser singola riga → CorsaParsedRow
# =====================================================================

# Le 11 chiavi mensili nello schema giorni_per_mese_json
_MONTH_COLUMNS = [
    ("Gg_dic1AP", "gg_dic1AP"),
    ("Gg_dic2AP", "gg_dic2AP"),
    ("Gg_gen", "gg_gen"),
    ("Gg_feb", "gg_feb"),
    ("Gg_mar", "gg_mar"),
    ("Gg_apr", "gg_apr"),
    ("Gg_mag", "gg_mag"),
    ("Gg_giu", "gg_giu"),
    ("Gg_lug", "gg_lug"),
    ("Gg_ago", "gg_ago"),
    ("Gg_set", "gg_set"),
    ("Gg_ott", "gg_ott"),
    ("Gg_nov", "gg_nov"),
    ("Gg_dic1", "gg_dic1"),
    ("Gg_dic2", "gg_dic2"),
    ("Gg_anno", "gg_anno"),
]


def parse_corsa_row(row: dict[str, Any]) -> CorsaParsedRow:
    """Parsa una riga PdE in `CorsaParsedRow`.

    - Calcola `valido_in_date_json` denormalizzato dalla periodicità
      testuale + intervallo di validità.
    - Cross-check con i `Gg_*` mensili e `Gg_anno`. Discrepanze
      vanno in `warnings` (non solleva eccezioni).
    """
    valido_da = _to_date(row["Valido da"])
    valido_a = _to_date(row["Valido a"])

    # Periodicità → date denormalizzate
    periodicita_text = row.get("Periodicità") or ""
    periodicita = parse_periodicita(str(periodicita_text))
    valido_in_date = compute_valido_in_date(valido_da, valido_a, periodicita)

    # Calendario mensile (cross-check)
    gg_per_mese: dict[str, int] = {}
    for src_key, dst_key in _MONTH_COLUMNS:
        v = row.get(src_key)
        if v is not None and v != "":
            gg_per_mese[dst_key] = int(v)

    warnings = cross_check_gg_mensili(valido_in_date, gg_per_mese)

    composizioni = parse_composizioni(row)

    return CorsaParsedRow(
        # Identificativi
        numero_treno=_to_str_treno(row.get("Treno 1")),
        rete=_to_opt_str(row.get("Rete 1")),
        numero_treno_rfi=_to_opt_str(row.get("Treno RFI")),
        numero_treno_fn=_to_opt_str(row.get("Treno FN")),
        categoria=_to_opt_str(row.get("Categoria linea")),
        codice_linea=_to_opt_str(row.get("Codice linea")),
        direttrice=_to_opt_str(row.get("Direttrice")),
        # Geografia
        codice_origine=str(row["Cod Origine"]).strip(),
        codice_destinazione=str(row["Cod Destinazione"]).strip(),
        codice_inizio_cds=_to_opt_str(row.get("Cod inizio CdS")),
        codice_fine_cds=_to_opt_str(row.get("Cod Fine CdS")),
        # Orari
        ora_partenza=_to_time(row["Ora Or"]),
        ora_arrivo=_to_time(row["Ora Des"]),
        ora_inizio_cds=_to_opt_time(row.get("Ora In Cds")),
        ora_fine_cds=_to_opt_time(row.get("Ora Fin cds")),
        min_tratta=_to_opt_int(row.get("Min Tratta")),
        min_cds=_to_opt_int(row.get("Min CdS")),
        km_tratta=_to_opt_decimal(row.get("Km tratta")),
        km_cds=_to_opt_decimal(row.get("Km CdS")),
        # Periodicità
        valido_da=valido_da,
        valido_a=valido_a,
        codice_periodicita=_to_opt_str(row.get("Codice Periodicità")),
        periodicita_breve=_to_opt_str(row.get("Periodicità Breve")),
        is_treno_garantito_feriale=_to_bool_si_no(row.get("Treno garantito feriale")),
        is_treno_garantito_festivo=_to_bool_si_no(row.get("Treno garantito festivo")),
        fascia_oraria=_to_opt_str(row.get("Fascia oraria")),
        # Calendario
        giorni_per_mese_json=gg_per_mese,
        valido_in_date_json=sorted(d.isoformat() for d in valido_in_date),
        # Aggregati
        totale_km=_to_opt_decimal(row.get("Totale Km")),
        totale_minuti=_to_opt_int(row.get("Totale Minuti")),
        posti_km=_to_opt_decimal(row.get("Postikm")),
        velocita_commerciale=_to_opt_decimal(row.get("Velocità commerciale")),
        # Nested
        composizioni=composizioni,
        warnings=warnings,
    )


# =====================================================================
# Parser composizione 9 combinazioni
# =====================================================================

# (stagione, giorno_tipo) → suffisso colonna PdE
_COMPOSITION_KEYS: list[tuple[str, str, str]] = [
    ("invernale", "feriale", "Invernale Feriale"),
    ("invernale", "sabato", "Invernale Sabato"),
    ("invernale", "festivo", "Invernale Festivo"),
    ("estiva", "feriale", "Estiva Feriale"),
    ("estiva", "sabato", "Estiva Sabato"),
    ("estiva", "festivo", "Estiva Festivo"),
    ("agosto", "feriale", "Agosto Feriale"),
    ("agosto", "sabato", "Agosto Sabato"),
    ("agosto", "festivo", "Agosto Festivo"),
]


def parse_composizioni(row: dict[str, Any]) -> list[ComposizioneParsed]:
    """Estrae le 9 righe di composizione dal row PdE.

    Le 9 combinazioni stagione × giorno_tipo sono **sempre presenti**
    (anche se vuote). Il parser le emette tutte; sta al chiamante
    decidere se filtrare quelle interamente NULL.
    """
    out: list[ComposizioneParsed] = []
    for stagione, giorno_tipo, suffisso in _COMPOSITION_KEYS:
        # Le 6 colonne con questo suffisso (case identico al PdE)
        # Note: nel PdE 'Categoria Bici' usa 'feriale' lowercase per Invernale,
        # mentre tutti gli altri attributi usano 'Feriale' capitalized.
        bici_suffisso = (
            suffisso[0].upper() + suffisso[1:].lower() if stagione == "invernale" else suffisso
        )
        out.append(
            ComposizioneParsed(
                stagione=stagione,
                giorno_tipo=giorno_tipo,
                categoria_posti=_to_opt_str(row.get(f"CATEGORIA POSTI VALIDATA - {suffisso}")),
                is_doppia_composizione=_to_bool_si_no(row.get(f"Doppia Composizione - {suffisso}")),
                tipologia_treno=_to_opt_str(row.get(f"Tipologia Treno - {suffisso}")),
                vincolo_dichiarato=_to_opt_str(row.get(f"VINCOLO DICHIARATO - {suffisso}")),
                categoria_bici=_to_opt_str(row.get(f"Categoria Bici - {bici_suffisso}")),
                categoria_prm=_to_opt_str(row.get(f"Categoria PRM - {suffisso}")),
            )
        )
    return out


# =====================================================================
# Parser periodicità testuale
# =====================================================================

# Match 'DD/MM/YYYY' (italian short date)
_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
# Match 'dal DD/MM/YYYY al DD/MM/YYYY'
_INTERVAL_RE = re.compile(
    r"dal\s+(\d{1,2}/\d{1,2}/\d{4})\s+al\s+(\d{1,2}/\d{1,2}/\d{4})",
    re.IGNORECASE,
)
# Mappatura nomi giorno-settimana italiani → datetime.weekday() (0=lun ... 6=dom)
_WEEKDAY_ITA: dict[str, int] = {
    "lunedì": 0,
    "lunedi": 0,
    "martedì": 1,
    "martedi": 1,
    "mercoledì": 2,
    "mercoledi": 2,
    "giovedì": 3,
    "giovedi": 3,
    "venerdì": 4,
    "venerdi": 4,
    "sabato": 5,
    "domenica": 6,
}
_WEEKDAY_RE = re.compile(
    r"\b(lunedì|lunedi|martedì|martedi|mercoledì|mercoledi"
    r"|giovedì|giovedi|venerdì|venerdi|sabato|domenica)\b",
    re.IGNORECASE,
)


def _parse_date_it(s: str) -> date:
    """Parsa 'DD/MM/YYYY' o 'D/M/YYYY' → date."""
    parts = s.split("/")
    if len(parts) != 3:
        raise ValueError(f"Data italiana mal formata: {s!r}")
    return date(int(parts[2]), int(parts[1]), int(parts[0]))


def parse_periodicita(text: str) -> PeriodicitaParsed:
    """Parsa il testo libero del campo 'Periodicità' del PdE.

    Esempi gestiti::

        "Circola tutti i giorni. Non circola dal 01/12/2025 al 13/12/2025."
        "Circola dal 14/01/2026 al 17/01/2026."
        "Circola 12/01/2026, 13/01/2026."
        "Circola tutti i giorni dal 02/03/2026 al 22/03/2026. Circola 28/03/2026."
        "Circola il sabato e la domenica. Circola tutti i giorni dal X al Y."
        "Circola 19/12/2025, 20/12/2025, ..., 26/12/2026."

    Approccio: split per frasi su '. ', poi per ogni frase distingue
    apply (Circola...) da skip (Non circola...), estrae intervalli,
    date singole e nomi giorno-settimana con regex.

    Una frase apply che contiene SOLO giorni-settimana (no intervalli,
    no date) imposta il filtro globale `filtro_giorni_settimana`.
    """
    if not text or not text.strip():
        return PeriodicitaParsed()

    is_tutti = False
    filtro_giorni: set[int] = set()
    apply_intervals: list[tuple[date, date]] = []
    apply_dates: set[date] = set()
    skip_intervals: list[tuple[date, date]] = []
    skip_dates: set[date] = set()

    # Tokenize per frasi su '. ' (poi rimuovo punto finale).
    parts = [s.strip() for s in text.split(". ") if s.strip()]
    if parts:
        parts[-1] = parts[-1].rstrip(".")

    for sentence in parts:
        if not sentence:
            continue
        is_skip_sentence = sentence.lower().startswith("non circola")

        # Estrai intervalli + memorizza spans per escludere date dentro
        intervals: list[tuple[date, date]] = []
        interval_spans: list[tuple[int, int]] = []
        for match in _INTERVAL_RE.finditer(sentence):
            try:
                a = _parse_date_it(match.group(1))
                b = _parse_date_it(match.group(2))
            except ValueError:
                continue
            intervals.append((a, b))
            interval_spans.append((match.start(), match.end()))

        # Estrai date singole NON contenute in nessun intervallo
        single_dates: set[date] = set()
        for match in _DATE_RE.finditer(sentence):
            in_interval = any(s <= match.start() < e for s, e in interval_spans)
            if in_interval:
                continue
            try:
                single_dates.add(_parse_date_it(match.group(0)))
            except ValueError:
                continue

        # Estrai nomi giorno-settimana presenti nella frase
        weekdays_in_sentence: set[int] = set()
        for match in _WEEKDAY_RE.finditer(sentence):
            weekdays_in_sentence.add(_WEEKDAY_ITA[match.group(1).lower()])

        if is_skip_sentence:
            skip_intervals.extend(intervals)
            skip_dates.update(single_dates)
            # Skip-by-weekday non ancora osservato in dataset reale: skip.
        else:
            apply_intervals.extend(intervals)
            apply_dates.update(single_dates)
            # 'Circola tutti i giorni' senza intervallo → flag
            if "tutti i giorni" in sentence.lower() and not intervals:
                is_tutti = True
            # 'Circola il sabato e la domenica' (solo giorni-settimana,
            # niente intervalli/date) → filtro globale
            elif weekdays_in_sentence and not intervals and not single_dates:
                filtro_giorni.update(weekdays_in_sentence)

    return PeriodicitaParsed(
        is_tutti_giorni=is_tutti,
        filtro_giorni_settimana=filtro_giorni,
        apply_intervals=apply_intervals,
        apply_dates=apply_dates,
        skip_intervals=skip_intervals,
        skip_dates=skip_dates,
    )


# =====================================================================
# Calendario: calcolo valido_in_date_json
# =====================================================================


def _date_range(from_date: date, to_date: date) -> list[date]:
    """Lista di date inclusa, da from_date a to_date."""
    if from_date > to_date:
        return []
    days = (to_date - from_date).days + 1
    return [from_date + timedelta(days=i) for i in range(days)]


def compute_valido_in_date(
    valido_da: date,
    valido_a: date,
    periodicita: PeriodicitaParsed,
) -> set[date]:
    """Calcola l'insieme di date in cui la corsa circola effettivamente.

    Algoritmo (l'ordine conta):

    1. **Default base**:
       - Se `is_tutti_giorni`, parto da tutto l'intervallo `[valido_da, valido_a]`.
       - Altrimenti, se `filtro_giorni_settimana`, prendo solo i giorni
         dell'intervallo che cadono in quei weekday (es. `{5,6}` = sab+dom).
    2. **Apply intervals** (override del filtro): per ogni intervallo
       "Circola dal X al Y", aggiungo TUTTI i giorni dell'intervallo
       (clipped a `[valido_da, valido_a]`).
    3. **Apply dates esplicite**: aggiungo ogni date in `apply_dates`
       (filtrata per range).
    4. **Skip intervals**: rimuovo ogni intervallo "Non circola dal X al Y".
    5. **Skip dates**: rimuovo ogni date in `skip_dates`.

    Il parser segue letteralmente il testo `Periodicità`: nessuna
    auto-soppressione di festività. Il modulo `holidays.py` resta
    disponibile come utility per altre logiche (builder giro materiale).
    """
    result: set[date] = set()

    # Step 1 — default base
    if periodicita.is_tutti_giorni:
        result.update(_date_range(valido_da, valido_a))
    elif periodicita.filtro_giorni_settimana:
        for d in _date_range(valido_da, valido_a):
            if d.weekday() in periodicita.filtro_giorni_settimana:
                result.add(d)

    # Step 2 — apply intervals (override del filtro: tutti i giorni)
    for a, b in periodicita.apply_intervals:
        clipped_from = max(a, valido_da)
        clipped_to = min(b, valido_a)
        result.update(_date_range(clipped_from, clipped_to))

    # Step 3 — apply dates esplicite
    for d in periodicita.apply_dates:
        if valido_da <= d <= valido_a:
            result.add(d)

    # Step 4 — skip intervals
    for a, b in periodicita.skip_intervals:
        clipped_from = max(a, valido_da)
        clipped_to = min(b, valido_a)
        for d in _date_range(clipped_from, clipped_to):
            result.discard(d)

    # Step 5 — skip dates
    for d in periodicita.skip_dates:
        result.discard(d)

    return result


# Mappatura Gg_<mese> → numero mese (1-12) per l'anno di esercizio.
# Il PdE Trenord ha 4 colonne dicembre: dic1AP/dic2AP per l'anno
# precedente (preludio del PdE), dic1/dic2 per l'anno corrente.
# Per ora cross-check solo i 11 mesi gen-nov + somma annuale.
_GG_TO_MONTH = {
    "gg_gen": 1,
    "gg_feb": 2,
    "gg_mar": 3,
    "gg_apr": 4,
    "gg_mag": 5,
    "gg_giu": 6,
    "gg_lug": 7,
    "gg_ago": 8,
    "gg_set": 9,
    "gg_ott": 10,
    "gg_nov": 11,
}


def cross_check_gg_mensili(
    dates: set[date],
    gg_per_mese: dict[str, int],
) -> list[str]:
    """Verifica che il numero di date calcolate matchi i `Gg_*` PdE.

    Cross-check effettuati:
    - Mesi gen-nov dell'anno principale (1 colonna ciascuno).
    - Dicembre dell'anno principale: somma `Gg_dic1 + Gg_dic2` = 31.
    - Dicembre dell'anno precedente: somma `Gg_dic1AP + Gg_dic2AP` =
      giorni del 2025 (per PdE 14/12/2025 → 12/12/2026).
    - Totale annuale `Gg_anno` = somma 12 mesi dell'anno principale
      (NON include i giorni di dicembre dell'anno precedente).

    NB: il PdE Trenord ha 4 colonne dicembre (dic1AP/dic2AP/dic1/dic2)
    perché il calendario di esercizio sfora l'anno solare. La spaccatura
    dic1 vs dic2 (ad es. 1-12 vs 13-31) non è verificata qui — solo
    il totale dicembre.

    Ritorna lista di warning testuali (lista vuota = nessuna discrepanza).
    """
    warnings: list[str] = []

    if not dates:
        gg_anno = gg_per_mese.get("gg_anno")
        if gg_anno is not None and gg_anno > 0:
            warnings.append(f"valido_in_date vuoto ma gg_anno={gg_anno}: parser fallito")
        return warnings

    # Anno principale = quello con più date
    year_counts: dict[int, int] = {}
    for d in dates:
        year_counts[d.year] = year_counts.get(d.year, 0) + 1
    main_year = max(year_counts, key=lambda y: year_counts[y])

    # Cross-check mesi gen-nov anno principale
    for gg_key, month_num in _GG_TO_MONTH.items():
        expected = gg_per_mese.get(gg_key)
        if expected is None:
            continue
        actual = sum(1 for d in dates if d.year == main_year and d.month == month_num)
        if expected != actual:
            warnings.append(
                f"{gg_key}: PdE={expected}, parser={actual} (mese {month_num}/{main_year})"
            )

    # Cross-check dicembre anno principale (dic1 + dic2)
    gg_dic_main = gg_per_mese.get("gg_dic1", 0) + gg_per_mese.get("gg_dic2", 0)
    if "gg_dic1" in gg_per_mese or "gg_dic2" in gg_per_mese:
        actual_dic_main = sum(1 for d in dates if d.year == main_year and d.month == 12)
        if gg_dic_main != actual_dic_main:
            warnings.append(
                f"gg_dic1+gg_dic2: PdE={gg_dic_main}, parser={actual_dic_main} "
                f"(dicembre {main_year})"
            )

    # Cross-check dicembre anno precedente (dic1AP + dic2AP)
    gg_dic_ap = gg_per_mese.get("gg_dic1AP", 0) + gg_per_mese.get("gg_dic2AP", 0)
    if "gg_dic1AP" in gg_per_mese or "gg_dic2AP" in gg_per_mese:
        actual_dic_ap = sum(1 for d in dates if d.year == main_year - 1 and d.month == 12)
        if gg_dic_ap != actual_dic_ap:
            warnings.append(
                f"gg_dic1AP+gg_dic2AP: PdE={gg_dic_ap}, parser={actual_dic_ap} "
                f"(dicembre {main_year - 1})"
            )

    # Cross-check totale anno principale (NON include dic_AP)
    expected_anno = gg_per_mese.get("gg_anno")
    if expected_anno is not None:
        actual_anno = sum(1 for d in dates if d.year == main_year)
        if expected_anno != actual_anno:
            warnings.append(
                f"gg_anno: PdE={expected_anno}, parser={actual_anno} (anno {main_year})"
            )

    return warnings
