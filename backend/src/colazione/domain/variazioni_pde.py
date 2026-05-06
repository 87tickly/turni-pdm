"""Pure logic per applicazione variazioni PdE alle CorsaCommerciale.

Sprint 8.0 MR 5.bis (entry 173). Il MR 5 (entry 170) ha esposto gli
endpoint REST che registrano i metadati di una variazione del PdE in
``CorsaImportRun`` (tipo + source_file + n_corse). Questo modulo
implementa la **logica concreta** di applicazione: dato un set di righe
parsate da un file PdE incrementale e lo stato corrente delle corse in
DB, calcola le operazioni da eseguire.

## Decisioni di design

### Strato pure DB-agnostic

Il modulo opera su dataclass frozen — non conosce SQLAlchemy. L'endpoint
API si occupa di:

1. caricare le corse esistenti dal DB (filtrate per azienda),
2. parsare il file uploaded con :func:`colazione.importers.pde.parse_corsa_row`,
3. invocare la funzione di pianificazione corretta per il ``tipo`` della run,
4. applicare le operazioni ritornate alle ``CorsaCommerciale``,
5. aggiornare la run con ``n_corse_create`` / ``n_corse_update``.

Pattern allineato al MR 2.bis-a (entry 172) per ``assegnazione_persone``:
pure logic + endpoint orchestratore + test integration.

### Chiavi di match

Il PdE Trenord 2025-2026 ha **8 coppie di righe identiche al byte**:
chiavi business "ragionevoli" non sono univoche. Il MR β/MR 3.7 ha
risolto importando ogni riga (multiset di ``row_hash``).

Per le **variazioni**, devo identificare quale corsa esistente è
oggetto di modifica. Per i 4 tipi:

- ``INTEGRAZIONE``: identità per :func:`compute_row_hash` (la riga
  parsata è "nuova" se il suo hash non è già presente in DB).
- ``VARIAZIONE_ORARIO`` / ``VARIAZIONE_CANCELLAZIONE``: chiave a 5
  campi ``(numero_treno, valido_da, valido_a, codice_origine,
  codice_destinazione)``. Se ambigua (>1 match), warning + applica a
  tutte le matching (semantica conservativa: corse identiche per
  questi 5 campi vanno modificate insieme).
- ``VARIAZIONE_INTERRUZIONE``: chiave a 3 ``(numero_treno, valido_da,
  valido_a)``. L'interruzione spesso è dichiarata su una linea
  intera (tutte le corse di quel treno nello stesso intervallo),
  quindi la chiave non include origine/destinazione.

### Algoritmo per tipo

**INTEGRAZIONE**: per ogni parsed row, calcolo ``row_hash``. Se non è
in ``hash_esistenti``, accodo una :class:`OpInsert`. Idempotente: ri-
applicare la stessa variazione due volte non duplica nulla.

**VARIAZIONE_ORARIO**: cerco corse esistenti con chiave a 5 matching.
Per ogni match, costruisco una :class:`OpUpdateOrari` con i 9 campi
orario/durata/distanza dal parsed row. Se il match è 0, warning. Se
>1, warning + applico a tutte.

**VARIAZIONE_INTERRUZIONE**: cerco corse esistenti con chiave a 3
matching. Per ogni match, ricavo la nuova lista ``valido_in_date_json``
prendendo l'**intersezione** delle date vecchie con quelle del file
incrementale (perché le date assenti nel file sono "interrotte").
Caveat: se ``new ⊋ old`` (il file dichiara date non presenti in DB),
emetto warning ma resto sull'intersezione (non aggiungo date nuove —
quello sarebbe scope INTEGRAZIONE).

**VARIAZIONE_CANCELLAZIONE**: cerco corse esistenti con chiave a 5
matching. Per ogni match, costruisco :class:`OpCancella` (svuota
``valido_in_date_json`` ma mantiene la riga in DB per audit trail).
Decisione utente: niente DELETE, sempre soft-cancellation.

## Memoria utente rilevante

- "PdE testo Periodicità = verità": niente parser DSL del Codice
  Periodicità, niente auto-suppress festività. Il file di variazione
  segue la stessa convenzione del PdE base.
- "Niente errori sui dati DB": le corse non vengono mai DELETE-ate da
  questo modulo. Cancellazioni sono soft (svuoto il calendario, lascio
  la riga). Ambiguità di match → warning, non crash.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from decimal import Decimal

# =====================================================================
# Snapshot input — solo i campi necessari al match/diff
# =====================================================================


@dataclass(frozen=True)
class CorsaEsistente:
    """Snapshot DB-agnostic di una ``CorsaCommerciale`` esistente.

    L'endpoint API costruisce questa lista da una query
    ``SELECT id, row_hash, numero_treno, valido_da, valido_a,
    codice_origine, codice_destinazione, valido_in_date_json,
    is_cancellata`` sull'azienda del programma. Tutti i campi necessari
    al match (chiave a 3 o 5) e al diff (per INTERRUZIONE), più il
    flag di soft-delete (sub-MR 5.bis-a alignment, entry 176): le
    corse già cancellate vengono skippate dai planner per idempotenza.
    """

    id: int
    row_hash: str
    numero_treno: str
    valido_da: date
    valido_a: date
    codice_origine: str
    codice_destinazione: str
    valido_in_date_json: tuple[str, ...]
    """Tuple di date ISO (immutabile per essere ``frozen``)."""
    is_cancellata: bool = False
    """Sub-MR 5.bis-a (entry 176): True se ``corsa_commerciale.is_cancellata``.
    Usato dai planner per idempotenza (cancellazione su corsa già
    cancellata è skip silenzioso) e per warning (interruzione/orario su
    corsa cancellata = errore di workflow). Default False per
    retrocompatibilità con i test esistenti."""


@dataclass(frozen=True)
class ParsedTarget:
    """Snapshot DB-agnostic di una riga del file PdE incrementale.

    Subset dei campi di :class:`colazione.importers.pde.CorsaParsedRow`
    necessari per match + diff. Costruito dall'endpoint a partire dal
    parsed row.
    """

    row_hash: str
    numero_treno: str
    valido_da: date
    valido_a: date
    codice_origine: str
    codice_destinazione: str
    ora_partenza: time
    ora_arrivo: time
    ora_inizio_cds: time | None
    ora_fine_cds: time | None
    min_tratta: int | None
    min_cds: int | None
    km_tratta: Decimal | None
    km_cds: Decimal | None
    valido_in_date_json: tuple[str, ...]


# =====================================================================
# Operazioni da applicare al DB
# =====================================================================


@dataclass(frozen=True)
class OpInsert:
    """Inserire una nuova corsa nel DB. ``parsed_index`` è l'indice
    della parsed_row originale (l'endpoint la converte in payload
    completo per la INSERT)."""

    parsed_index: int
    row_hash: str


@dataclass(frozen=True)
class OpUpdateOrari:
    """Aggiornare i campi orario/durata/distanza di una corsa esistente."""

    corsa_id: int
    ora_partenza: time
    ora_arrivo: time
    ora_inizio_cds: time | None
    ora_fine_cds: time | None
    min_tratta: int | None
    min_cds: int | None
    km_tratta: Decimal | None
    km_cds: Decimal | None


@dataclass(frozen=True)
class OpUpdateValidoInDate:
    """Aggiornare ``valido_in_date_json`` di una corsa esistente.

    Usato per ``VARIAZIONE_INTERRUZIONE`` (intersezione delle date).
    NON è più usato per ``VARIAZIONE_CANCELLAZIONE`` dopo l'alignment
    sub-MR 5.bis-a (entry 176): la cancellazione passa attraverso
    :class:`OpSoftCancella` che setta il flag dedicato
    ``corsa_commerciale.is_cancellata`` (migration 0034).
    """

    corsa_id: int
    valido_in_date_json: tuple[str, ...]


@dataclass(frozen=True)
class OpSoftCancella:
    """Soft-delete di una corsa esistente (sub-MR 5.bis-a alignment, entry 176).

    Mappa ``VARIAZIONE_CANCELLAZIONE`` sul flag dedicato della migration
    0034 (``is_cancellata=True``, ``cancellata_da_run_id=run.id``,
    ``cancellata_at=now()``). Sostituisce la vecchia semantica "svuoto
    ``valido_in_date_json``": più tracciabile (audit trail completo) e
    coerente col CHECK constraint ``corsa_commerciale_cancellazione_coerente``.

    Hard-DELETE è impossibile per FK RESTRICT da ``turno_pdc_blocco``
    (corse consumate da turni PdC).
    """

    corsa_id: int


@dataclass(frozen=True)
class RisultatoPianificazione:
    """Esito della pianificazione: lista operazioni + warning testuali.

    L'endpoint applica le operazioni in ordine arbitrario (sono
    indipendenti — non c'è ordering necessario fra INSERT e UPDATE).
    I warning vanno persistiti nel campo ``note`` della run, separati
    da ``\\n``, troncati a max 1000 char (limite schema).
    """

    insert: list[OpInsert] = field(default_factory=list)
    update_orari: list[OpUpdateOrari] = field(default_factory=list)
    update_valido_in_date: list[OpUpdateValidoInDate] = field(default_factory=list)
    cancellazioni: list[OpSoftCancella] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def n_create(self) -> int:
        return len(self.insert)

    @property
    def n_update(self) -> int:
        # Sub-MR 5.bis-a alignment (entry 176): le ``cancellazioni`` sono
        # contate come "update" (modifica del flag su riga esistente).
        return (
            len(self.update_orari)
            + len(self.update_valido_in_date)
            + len(self.cancellazioni)
        )


# =====================================================================
# Match helpers
# =====================================================================


_KEY3 = tuple[str, date, date]
_KEY5 = tuple[str, date, date, str, str]


def _key3(numero_treno: str, valido_da: date, valido_a: date) -> _KEY3:
    return (numero_treno, valido_da, valido_a)


def _key5(
    numero_treno: str,
    valido_da: date,
    valido_a: date,
    codice_origine: str,
    codice_destinazione: str,
) -> _KEY5:
    return (numero_treno, valido_da, valido_a, codice_origine, codice_destinazione)


def _index_by_key3(esistenti: list[CorsaEsistente]) -> dict[_KEY3, list[int]]:
    """Indicizza per chiave a 3 → lista id (>1 se ci sono duplicati)."""
    out: dict[_KEY3, list[int]] = {}
    for c in esistenti:
        k = _key3(c.numero_treno, c.valido_da, c.valido_a)
        out.setdefault(k, []).append(c.id)
    return out


def _index_by_key5(esistenti: list[CorsaEsistente]) -> dict[_KEY5, list[int]]:
    """Indicizza per chiave a 5 → lista id."""
    out: dict[_KEY5, list[int]] = {}
    for c in esistenti:
        k = _key5(
            c.numero_treno,
            c.valido_da,
            c.valido_a,
            c.codice_origine,
            c.codice_destinazione,
        )
        out.setdefault(k, []).append(c.id)
    return out


def _index_by_id(esistenti: list[CorsaEsistente]) -> dict[int, CorsaEsistente]:
    return {c.id: c for c in esistenti}


# =====================================================================
# Pianificazione per i 4 tipi
# =====================================================================


def pianifica_integrazione(
    targets: list[ParsedTarget],
    esistenti: list[CorsaEsistente],
) -> RisultatoPianificazione:
    """Variazione di tipo ``INTEGRAZIONE``: aggiunge corse nuove.

    Identità per ``row_hash``. Per ogni parsed target:

    - se ``row_hash`` è già in DB (almeno 1 occorrenza fra
      ``esistenti``) → skip silenzioso (idempotente).
    - altrimenti → :class:`OpInsert` accodato.

    Il "row_hash duplicato nello stesso file" è preservato: se il file
    ha 2 righe identiche con hash X non presente in DB, si genera 2
    OpInsert (allineato al principio "no train left behind" del MR β).

    Ritorna risultato con ``insert`` popolato, niente warning per il
    caso normale.
    """
    hash_esistenti: set[str] = {c.row_hash for c in esistenti}
    insert: list[OpInsert] = []
    warnings: list[str] = []

    for idx, t in enumerate(targets):
        if t.row_hash in hash_esistenti:
            # Skip idempotente — la corsa esiste già.
            continue
        insert.append(OpInsert(parsed_index=idx, row_hash=t.row_hash))

    if not insert and targets:
        warnings.append(
            f"INTEGRAZIONE: tutte le {len(targets)} corse del file erano "
            "già presenti in DB (skip idempotente)"
        )

    return RisultatoPianificazione(insert=insert, warnings=warnings)


def pianifica_variazione_orario(
    targets: list[ParsedTarget],
    esistenti: list[CorsaEsistente],
) -> RisultatoPianificazione:
    """Variazione di tipo ``VARIAZIONE_ORARIO``: aggiorna orari/durate.

    Match per chiave a 5 ``(numero_treno, valido_da, valido_a,
    codice_origine, codice_destinazione)``. Per ogni parsed target:

    - 0 match → warning "corsa target non trovata".
    - 1+ match → :class:`OpUpdateOrari` per ognuno (semantica
      conservativa: corse identiche per i 5 campi sono variazioni
      sincrone).

    Aggiornati solo i campi orario/durata/distanza. Non si tocca
    ``valido_in_date_json``: per quello c'è ``VARIAZIONE_INTERRUZIONE``.
    """
    idx5 = _index_by_key5(esistenti)
    update_orari: list[OpUpdateOrari] = []
    warnings: list[str] = []

    for t in targets:
        key = _key5(
            t.numero_treno,
            t.valido_da,
            t.valido_a,
            t.codice_origine,
            t.codice_destinazione,
        )
        match_ids = idx5.get(key, [])
        if not match_ids:
            warnings.append(
                f"VARIAZIONE_ORARIO: corsa target non trovata in DB — "
                f"treno {t.numero_treno}, valido {t.valido_da}→{t.valido_a}, "
                f"{t.codice_origine}→{t.codice_destinazione}"
            )
            continue
        if len(match_ids) > 1:
            warnings.append(
                f"VARIAZIONE_ORARIO: match ambiguo per treno {t.numero_treno} "
                f"({len(match_ids)} corse identiche per chiave a 5) — "
                "applicato a tutte"
            )
        # NB: idempotenza fine-grained (skip se i 9 campi orario coincidono
        # con quelli in DB) richiederebbe di caricare ora/min/km in
        # ``CorsaEsistente``. Non lo facciamo per non appesantire la query
        # di lettura. UPDATE no-op a livello DB è innocuo (PostgreSQL
        # rileva ``NEW IS NOT DISTINCT FROM OLD`` e non scrive davvero
        # tuple identiche; non ci sono trigger su corsa_commerciale).
        for cid in match_ids:
            update_orari.append(
                OpUpdateOrari(
                    corsa_id=cid,
                    ora_partenza=t.ora_partenza,
                    ora_arrivo=t.ora_arrivo,
                    ora_inizio_cds=t.ora_inizio_cds,
                    ora_fine_cds=t.ora_fine_cds,
                    min_tratta=t.min_tratta,
                    min_cds=t.min_cds,
                    km_tratta=t.km_tratta,
                    km_cds=t.km_cds,
                )
            )

    return RisultatoPianificazione(update_orari=update_orari, warnings=warnings)


def pianifica_variazione_interruzione(
    targets: list[ParsedTarget],
    esistenti: list[CorsaEsistente],
) -> RisultatoPianificazione:
    """Variazione di tipo ``VARIAZIONE_INTERRUZIONE``: rimuove date.

    Match per chiave a 3 ``(numero_treno, valido_da, valido_a)``.
    Una linea interrotta tipicamente coinvolge tutte le corse di
    quel treno nell'intervallo (origine/destinazione possono
    differire), quindi la chiave non include codice_origine/destinazione.

    Algoritmo:

    - 0 match → warning.
    - 1+ match → per ognuno calcolo la nuova lista come **intersezione**
      di ``existing.valido_in_date_json`` con ``target.valido_in_date_json``.
    - Se ``target ⊋ existing`` (il file dichiara date non presenti in
      DB), warning ma applico l'intersezione (non aggiungo date nuove —
      sarebbe scope INTEGRAZIONE).
    - Se l'intersezione coincide con la lista esistente (niente da
      togliere), skip silenzioso (idempotente).
    """
    idx3 = _index_by_key3(esistenti)
    by_id = _index_by_id(esistenti)
    updates: list[OpUpdateValidoInDate] = []
    warnings: list[str] = []

    for t in targets:
        key = _key3(t.numero_treno, t.valido_da, t.valido_a)
        match_ids = idx3.get(key, [])
        if not match_ids:
            warnings.append(
                f"VARIAZIONE_INTERRUZIONE: corsa target non trovata in DB — "
                f"treno {t.numero_treno}, valido {t.valido_da}→{t.valido_a}"
            )
            continue
        if len(match_ids) > 1:
            warnings.append(
                f"VARIAZIONE_INTERRUZIONE: match ambiguo per treno "
                f"{t.numero_treno} ({len(match_ids)} corse identiche per "
                "chiave a 3) — applicato a tutte"
            )

        target_dates: set[str] = set(t.valido_in_date_json)
        if not target_dates:
            # Target con periodicità vuota = "interruzione totale" del
            # treno nell'intervallo. Lecito ma equivale a una
            # CANCELLAZIONE — emetto warning informativo per l'utente.
            warnings.append(
                f"VARIAZIONE_INTERRUZIONE: treno {t.numero_treno} senza "
                f"date attive nel file — equivale a cancellazione totale "
                f"({t.valido_da}→{t.valido_a}). Considera "
                "VARIAZIONE_CANCELLAZIONE se intenzionale."
            )

        for cid in match_ids:
            existing = by_id[cid]
            existing_dates: set[str] = set(existing.valido_in_date_json)

            extra_in_file = target_dates - existing_dates
            if extra_in_file:
                warnings.append(
                    f"VARIAZIONE_INTERRUZIONE: il file di variazione per "
                    f"treno {t.numero_treno} dichiara {len(extra_in_file)} "
                    "date non presenti in DB (ignorate — scope INTEGRAZIONE)"
                )

            new_dates = existing_dates & target_dates
            if new_dates == existing_dates:
                # Idempotenza: nessuna data da rimuovere.
                continue

            updates.append(
                OpUpdateValidoInDate(
                    corsa_id=cid,
                    valido_in_date_json=tuple(sorted(new_dates)),
                )
            )

    return RisultatoPianificazione(update_valido_in_date=updates, warnings=warnings)


def pianifica_variazione_cancellazione(
    targets: list[ParsedTarget],
    esistenti: list[CorsaEsistente],
) -> RisultatoPianificazione:
    """Variazione di tipo ``VARIAZIONE_CANCELLAZIONE``: soft-delete via flag.

    Sub-MR 5.bis-a alignment (entry 176): la cancellazione setta il
    flag ``is_cancellata`` (migration 0034) invece di svuotare
    ``valido_in_date_json``. Il vecchio approccio "lista vuota" era
    ambiguo (non si distingueva da una corsa con periodicità vuota
    legittima) e privo di audit trail. Il flag dedicato risolve
    entrambi i problemi: ``cancellata_da_run_id`` + ``cancellata_at``
    tracciano chi e quando.

    Match per chiave a 5. Per ogni corsa matching:

    - 0 match → warning.
    - 1+ match → emetto :class:`OpSoftCancella` per ognuno.
    - Se la corsa è già cancellata (``is_cancellata=True``), skip
      idempotente (no-op).

    Hard-DELETE è impossibile per FK RESTRICT da ``turno_pdc_blocco``.
    """
    idx5 = _index_by_key5(esistenti)
    by_id = _index_by_id(esistenti)
    cancellazioni: list[OpSoftCancella] = []
    warnings: list[str] = []

    for t in targets:
        key = _key5(
            t.numero_treno,
            t.valido_da,
            t.valido_a,
            t.codice_origine,
            t.codice_destinazione,
        )
        match_ids = idx5.get(key, [])
        if not match_ids:
            warnings.append(
                f"VARIAZIONE_CANCELLAZIONE: corsa target non trovata in DB — "
                f"treno {t.numero_treno}, valido {t.valido_da}→{t.valido_a}, "
                f"{t.codice_origine}→{t.codice_destinazione}"
            )
            continue
        if len(match_ids) > 1:
            warnings.append(
                f"VARIAZIONE_CANCELLAZIONE: match ambiguo per treno "
                f"{t.numero_treno} ({len(match_ids)} corse identiche) — "
                "cancellate tutte"
            )

        for cid in match_ids:
            existing = by_id[cid]
            if existing.is_cancellata:
                # Già cancellata, idempotente (no-op silenzioso).
                continue
            cancellazioni.append(OpSoftCancella(corsa_id=cid))

    return RisultatoPianificazione(
        cancellazioni=cancellazioni, warnings=warnings
    )
