"""Applicazione concreta delle variazioni PdE → corse esistenti.

Sub-MR 5.bis-a (Sprint 8.0 follow-up). Modulo pure-Python DB-agnostic
che valida e categorizza un set di **operazioni atomiche** contro lo
snapshot delle corse esistenti. Il caller (endpoint API) persiste le
operazioni valide in DB.

**Architettura**: i 3 input MR 5.bis-b/c/d (PdE intero, file delta,
form UI) generano una lista di ``Operazione`` → questo modulo le
valida → il caller le applica. Logica di applicazione centralizzata
qui per evitare divergenze tra i 3 ingressi.

**4 tipi di operazione** (mappano i 4 ``tipo`` di ``CorsaImportRun``):

- ``InsertCorsa`` (per ``INTEGRAZIONE``): nuova riga in
  ``corsa_commerciale`` con tutti i campi PdE.
- ``UpdateOrario`` (per ``VARIAZIONE_ORARIO``): aggiorna
  ``ora_partenza``/``ora_arrivo`` (e opz. min/km) di una corsa
  esistente.
- ``RimuoviDateValidita`` (per ``VARIAZIONE_INTERRUZIONE``): esclude
  date dal ``valido_in_date_json`` di una corsa esistente.
- ``CancellaCorsa`` (per ``VARIAZIONE_CANCELLAZIONE``): soft-delete
  via flag ``is_cancellata`` (vedi migration 0034). Hard-DELETE
  impossibile per FK RESTRICT da ``turno_pdc_blocco``.

**Validazione**: ogni operazione viene validata contro lo snapshot
delle corse esistenti (azienda + esistenza + cancellazione + range
date). Le operazioni con errore sono escluse dalla lista applicabile;
gli errori sono ritornati al caller per esposizione UX.

**Idempotenza**: ``CancellaCorsa`` su corsa già cancellata è skip
silenzioso (no errore). ``RimuoviDateValidita`` con date già rimosse
è no-op. Re-apply della stessa variazione non cambia stato (ma genera
un nuovo run con conteggi a 0).

**Reversibilità**: una variazione applicata è **immutabile** (decisione
2026-05-06). Per "rollback" si emette una variazione di compenso (es.
``INTEGRAZIONE`` che ricrea le corse cancellate). Audit trail completo
via ``cancellata_da_run_id`` + ``cancellata_at``.

DB-agnostic: il caller carica i ``CorsaSnapshot`` dal DB e costruisce
gli ``Operazione`` da Pydantic; questo modulo non importa SQLAlchemy.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal
from enum import StrEnum

# =====================================================================
# Enum
# =====================================================================


class TipoOperazione(StrEnum):
    """4 tipi di operazione atomica derivabili dai 4 tipi di variazione."""

    INSERT_CORSA = "INSERT_CORSA"
    UPDATE_ORARIO = "UPDATE_ORARIO"
    RIMUOVI_DATE_VALIDITA = "RIMUOVI_DATE_VALIDITA"
    CANCELLA_CORSA = "CANCELLA_CORSA"


class CodiceErrore(StrEnum):
    """Categorie di errore di validazione (esposte all'UI per messaging)."""

    CORSA_NON_TROVATA = "CORSA_NON_TROVATA"
    CORSA_DI_ALTRA_AZIENDA = "CORSA_DI_ALTRA_AZIENDA"
    CORSA_GIA_CANCELLATA = "CORSA_GIA_CANCELLATA"
    DATA_FUORI_RANGE_VALIDITA = "DATA_FUORI_RANGE_VALIDITA"
    LISTA_DATE_VUOTA = "LISTA_DATE_VUOTA"
    UPDATE_ORARIO_VUOTO = "UPDATE_ORARIO_VUOTO"
    INSERT_CAMPI_OBBLIGATORI_MANCANTI = "INSERT_CAMPI_OBBLIGATORI_MANCANTI"
    INSERT_VALIDO_DA_DOPO_VALIDO_A = "INSERT_VALIDO_DA_DOPO_VALIDO_A"


# =====================================================================
# Snapshot input
# =====================================================================


@dataclass(frozen=True)
class CorsaSnapshot:
    """Stato di una corsa esistente al momento della validazione.

    Caricata dal caller via ``SELECT FROM corsa_commerciale WHERE
    azienda_id = ?``. Solo i campi rilevanti per la validazione delle
    operazioni; il caller ha l'oggetto ORM completo per la mutazione.
    """

    id: int
    azienda_id: int
    numero_treno: str
    valido_da: date
    valido_a: date
    valido_in_date_json: tuple[str, ...]  # ISO date strings, frozen via tuple
    is_cancellata: bool


# =====================================================================
# Operazioni atomiche (input)
# =====================================================================


@dataclass(frozen=True)
class InsertCorsa:
    """Inserisce una nuova ``corsa_commerciale``.

    Mappa una riga di un file di INTEGRAZIONE (sub-MR 5.bis-b/c) o un
    record creato dal form UI (5.bis-d). Solo i campi obbligatori per
    soddisfare i vincoli NOT NULL del modello + i derivati cruciali
    (``valido_in_date_json``); gli optional vengono passati come None
    e il caller li trasforma in ORM.
    """

    numero_treno: str
    codice_origine: str
    codice_destinazione: str
    ora_partenza: time
    ora_arrivo: time
    valido_da: date
    valido_a: date
    valido_in_date_json: tuple[str, ...] = ()
    rete: str | None = None
    codice_linea: str | None = None
    direttrice: str | None = None
    categoria: str | None = None
    min_tratta: int | None = None
    km_tratta: Decimal | None = None
    row_hash: str | None = None  # opzionale: se generato dal parser

    @property
    def tipo(self) -> TipoOperazione:
        return TipoOperazione.INSERT_CORSA


@dataclass(frozen=True)
class UpdateOrario:
    """Aggiorna orari di una corsa esistente.

    Mappa una riga di VARIAZIONE_ORARIO. Almeno uno dei 4 campi
    opzionali deve essere valorizzato (validato da
    ``valida_e_normalizza``).
    """

    corsa_id: int
    ora_partenza: time | None = None
    ora_arrivo: time | None = None
    min_tratta: int | None = None
    km_tratta: Decimal | None = None

    @property
    def tipo(self) -> TipoOperazione:
        return TipoOperazione.UPDATE_ORARIO


@dataclass(frozen=True)
class RimuoviDateValidita:
    """Esclude date specifiche dal ``valido_in_date_json`` di una corsa.

    Mappa VARIAZIONE_INTERRUZIONE: la linea X è interrotta dal Y al Z,
    le corse sulla linea hanno quelle date rimosse dalla validità.
    Il caller estrae la lista date dal range + filtri linea/tratta e
    crea una operazione per corsa impattata.

    Idempotente: date già non presenti in ``valido_in_date_json`` sono
    no-op (nessun errore, nessun count).
    """

    corsa_id: int
    date_da_rimuovere: tuple[date, ...]

    @property
    def tipo(self) -> TipoOperazione:
        return TipoOperazione.RIMUOVI_DATE_VALIDITA


@dataclass(frozen=True)
class CancellaCorsa:
    """Soft-delete di una corsa esistente.

    Mappa VARIAZIONE_CANCELLAZIONE. Setta ``is_cancellata=TRUE``,
    ``cancellata_da_run_id``, ``cancellata_at`` (caller). Idempotente:
    su corsa già cancellata è skip silenzioso.
    """

    corsa_id: int

    @property
    def tipo(self) -> TipoOperazione:
        return TipoOperazione.CANCELLA_CORSA


Operazione = InsertCorsa | UpdateOrario | RimuoviDateValidita | CancellaCorsa


# =====================================================================
# Output
# =====================================================================


@dataclass(frozen=True)
class ErroreValidazione:
    """Errore di validazione su una singola operazione."""

    indice_operazione: int
    """Posizione 0-based nella lista input. Permette UI di evidenziare
    la riga problematica."""

    codice: CodiceErrore
    """Codice machine-readable per i test e per i mapping i18n."""

    motivo: str
    """Descrizione human-readable per esposizione UI."""

    corsa_id: int | None = None
    """ID corsa coinvolto (se applicabile)."""


@dataclass(frozen=True)
class OperazioneNormalizzata:
    """Operazione validata, pronta per essere applicata dal caller.

    Wrapper che porta dietro l'indice originale e segnala se è no-op
    (es. ``CancellaCorsa`` su corsa già cancellata): il caller la
    skippa nelle mutazioni ma la conta come "vista" nel report.
    """

    indice_operazione: int
    operazione: Operazione
    is_no_op: bool = False
    """True se applicata sarebbe no-op (corsa già cancellata, date già
    fuori validità). Il caller non muta DB ma può loggare."""


@dataclass(frozen=True)
class RisultatoValidazione:
    """Risultato della validazione + categorizzazione di un batch."""

    operazioni_valide: tuple[OperazioneNormalizzata, ...] = ()
    errori: tuple[ErroreValidazione, ...] = ()

    @property
    def n_insert_corsa(self) -> int:
        return sum(
            1
            for o in self.operazioni_valide
            if isinstance(o.operazione, InsertCorsa) and not o.is_no_op
        )

    @property
    def n_update_orario(self) -> int:
        return sum(
            1
            for o in self.operazioni_valide
            if isinstance(o.operazione, UpdateOrario) and not o.is_no_op
        )

    @property
    def n_rimuovi_date(self) -> int:
        return sum(
            1
            for o in self.operazioni_valide
            if isinstance(o.operazione, RimuoviDateValidita) and not o.is_no_op
        )

    @property
    def n_cancella_corsa(self) -> int:
        return sum(
            1
            for o in self.operazioni_valide
            if isinstance(o.operazione, CancellaCorsa) and not o.is_no_op
        )

    @property
    def n_no_op(self) -> int:
        return sum(1 for o in self.operazioni_valide if o.is_no_op)

    @property
    def n_errori(self) -> int:
        return len(self.errori)

    @property
    def is_valido(self) -> bool:
        """``True`` se non ci sono errori (le no-op sono ammesse)."""
        return not self.errori


# =====================================================================
# Validazione
# =====================================================================


def valida_e_normalizza(
    operazioni: Sequence[Operazione],
    corse_esistenti: dict[int, CorsaSnapshot],
    azienda_id: int,
) -> RisultatoValidazione:
    """Valida + categorizza una lista di operazioni atomiche.

    - ``corse_esistenti``: mappa ``corsa.id → CorsaSnapshot``. Tipicamente
      caricata via ``SELECT FROM corsa_commerciale WHERE azienda_id = ?``
      (o filter più stretto se la variazione ha scope programma).
    - ``azienda_id``: id azienda corrente, per validare che la corsa
      target appartenga effettivamente a chi sta applicando la variazione.

    Strategia: per ogni operazione applico le validazioni specifiche del
    tipo, costruisco un ``OperazioneNormalizzata`` o un
    ``ErroreValidazione``. Le 4 tipologie sono indipendenti: errori in
    una operazione non bloccano le altre (il caller decide se applicare
    parziale o richiedere zero-errori).
    """
    valide: list[OperazioneNormalizzata] = []
    errori: list[ErroreValidazione] = []

    for idx, op in enumerate(operazioni):
        if isinstance(op, InsertCorsa):
            err = _valida_insert(idx, op)
            if err is None:
                valide.append(OperazioneNormalizzata(idx, op, is_no_op=False))
            else:
                errori.append(err)
        elif isinstance(op, UpdateOrario):
            esito = _valida_update_orario(idx, op, corse_esistenti, azienda_id)
            if isinstance(esito, ErroreValidazione):
                errori.append(esito)
            else:
                valide.append(esito)
        elif isinstance(op, RimuoviDateValidita):
            esito = _valida_rimuovi_date(idx, op, corse_esistenti, azienda_id)
            if isinstance(esito, ErroreValidazione):
                errori.append(esito)
            else:
                valide.append(esito)
        elif isinstance(op, CancellaCorsa):
            esito = _valida_cancella(idx, op, corse_esistenti, azienda_id)
            if isinstance(esito, ErroreValidazione):
                errori.append(esito)
            else:
                valide.append(esito)

    return RisultatoValidazione(
        operazioni_valide=tuple(valide),
        errori=tuple(errori),
    )


# =====================================================================
# Validazioni per tipo (private)
# =====================================================================


def _valida_insert(idx: int, op: InsertCorsa) -> ErroreValidazione | None:
    """Validazioni di forma per ``InsertCorsa``.

    Le validazioni di unicità (``row_hash`` collidente, treno duplicato)
    sono delegate al DB / caller — qui controllo solo coerenza interna
    dell'operazione.
    """
    campi_mancanti: list[str] = []
    if not op.numero_treno.strip():
        campi_mancanti.append("numero_treno")
    if not op.codice_origine.strip():
        campi_mancanti.append("codice_origine")
    if not op.codice_destinazione.strip():
        campi_mancanti.append("codice_destinazione")
    if campi_mancanti:
        return ErroreValidazione(
            indice_operazione=idx,
            codice=CodiceErrore.INSERT_CAMPI_OBBLIGATORI_MANCANTI,
            motivo=f"Campi obbligatori vuoti: {', '.join(campi_mancanti)}",
        )
    if op.valido_da > op.valido_a:
        return ErroreValidazione(
            indice_operazione=idx,
            codice=CodiceErrore.INSERT_VALIDO_DA_DOPO_VALIDO_A,
            motivo=(
                f"valido_da ({op.valido_da.isoformat()}) "
                f"posteriore a valido_a ({op.valido_a.isoformat()})"
            ),
        )
    return None


def _valida_update_orario(
    idx: int,
    op: UpdateOrario,
    corse: dict[int, CorsaSnapshot],
    azienda_id: int,
) -> OperazioneNormalizzata | ErroreValidazione:
    """Validazioni per ``UpdateOrario``."""
    snap = corse.get(op.corsa_id)
    if snap is None:
        return ErroreValidazione(
            indice_operazione=idx,
            codice=CodiceErrore.CORSA_NON_TROVATA,
            motivo=f"corsa_id={op.corsa_id} non trovata",
            corsa_id=op.corsa_id,
        )
    if snap.azienda_id != azienda_id:
        return ErroreValidazione(
            indice_operazione=idx,
            codice=CodiceErrore.CORSA_DI_ALTRA_AZIENDA,
            motivo=f"corsa_id={op.corsa_id} appartiene ad altra azienda",
            corsa_id=op.corsa_id,
        )
    if snap.is_cancellata:
        return ErroreValidazione(
            indice_operazione=idx,
            codice=CodiceErrore.CORSA_GIA_CANCELLATA,
            motivo=f"corsa_id={op.corsa_id} è già cancellata, no UPDATE",
            corsa_id=op.corsa_id,
        )
    # Almeno un campo deve essere valorizzato (altrimenti è un no-op
    # patologico — segnaliamo come errore: probabile bug del parser).
    if (
        op.ora_partenza is None
        and op.ora_arrivo is None
        and op.min_tratta is None
        and op.km_tratta is None
    ):
        return ErroreValidazione(
            indice_operazione=idx,
            codice=CodiceErrore.UPDATE_ORARIO_VUOTO,
            motivo=(
                f"corsa_id={op.corsa_id}: nessun campo da aggiornare "
                "(specifica almeno uno tra ora_partenza, ora_arrivo, "
                "min_tratta, km_tratta)"
            ),
            corsa_id=op.corsa_id,
        )
    return OperazioneNormalizzata(idx, op, is_no_op=False)


def _valida_rimuovi_date(
    idx: int,
    op: RimuoviDateValidita,
    corse: dict[int, CorsaSnapshot],
    azienda_id: int,
) -> OperazioneNormalizzata | ErroreValidazione:
    """Validazioni per ``RimuoviDateValidita``."""
    snap = corse.get(op.corsa_id)
    if snap is None:
        return ErroreValidazione(
            indice_operazione=idx,
            codice=CodiceErrore.CORSA_NON_TROVATA,
            motivo=f"corsa_id={op.corsa_id} non trovata",
            corsa_id=op.corsa_id,
        )
    if snap.azienda_id != azienda_id:
        return ErroreValidazione(
            indice_operazione=idx,
            codice=CodiceErrore.CORSA_DI_ALTRA_AZIENDA,
            motivo=f"corsa_id={op.corsa_id} appartiene ad altra azienda",
            corsa_id=op.corsa_id,
        )
    if snap.is_cancellata:
        return ErroreValidazione(
            indice_operazione=idx,
            codice=CodiceErrore.CORSA_GIA_CANCELLATA,
            motivo=(
                f"corsa_id={op.corsa_id} è già cancellata, "
                "RIMUOVI_DATE_VALIDITA non applicabile"
            ),
            corsa_id=op.corsa_id,
        )
    if not op.date_da_rimuovere:
        return ErroreValidazione(
            indice_operazione=idx,
            codice=CodiceErrore.LISTA_DATE_VUOTA,
            motivo=f"corsa_id={op.corsa_id}: lista date_da_rimuovere è vuota",
            corsa_id=op.corsa_id,
        )
    fuori_range = [
        d.isoformat()
        for d in op.date_da_rimuovere
        if d < snap.valido_da or d > snap.valido_a
    ]
    if fuori_range:
        return ErroreValidazione(
            indice_operazione=idx,
            codice=CodiceErrore.DATA_FUORI_RANGE_VALIDITA,
            motivo=(
                f"corsa_id={op.corsa_id}: date {fuori_range} fuori dal "
                f"range di validità "
                f"[{snap.valido_da.isoformat()}, {snap.valido_a.isoformat()}]"
            ),
            corsa_id=op.corsa_id,
        )
    # No-op se nessuna delle date è effettivamente in valido_in_date_json
    # (la corsa non circolava in quei giorni, niente da rimuovere).
    iso_richieste = {d.isoformat() for d in op.date_da_rimuovere}
    iso_presenti = set(snap.valido_in_date_json)
    is_no_op = iso_richieste.isdisjoint(iso_presenti)
    return OperazioneNormalizzata(idx, op, is_no_op=is_no_op)


def _valida_cancella(
    idx: int,
    op: CancellaCorsa,
    corse: dict[int, CorsaSnapshot],
    azienda_id: int,
) -> OperazioneNormalizzata | ErroreValidazione:
    """Validazioni per ``CancellaCorsa``."""
    snap = corse.get(op.corsa_id)
    if snap is None:
        return ErroreValidazione(
            indice_operazione=idx,
            codice=CodiceErrore.CORSA_NON_TROVATA,
            motivo=f"corsa_id={op.corsa_id} non trovata",
            corsa_id=op.corsa_id,
        )
    if snap.azienda_id != azienda_id:
        return ErroreValidazione(
            indice_operazione=idx,
            codice=CodiceErrore.CORSA_DI_ALTRA_AZIENDA,
            motivo=f"corsa_id={op.corsa_id} appartiene ad altra azienda",
            corsa_id=op.corsa_id,
        )
    # Idempotente: corsa già cancellata = no-op (non errore).
    return OperazioneNormalizzata(idx, op, is_no_op=snap.is_cancellata)


# =====================================================================
# Helper applicazione (pure transformation)
# =====================================================================


def applica_rimozione_date(
    valido_in_date_json: Sequence[str],
    date_da_rimuovere: Sequence[date],
) -> tuple[list[str], int]:
    """Applica una ``RimuoviDateValidita`` a un ``valido_in_date_json``.

    Pure-transformation: non muta input. Ritorna ``(nuova_lista,
    n_date_rimosse_effettive)``. Le date richieste ma non presenti
    nell'input sono ignorate (idempotente).
    """
    iso_da_rimuovere = {d.isoformat() for d in date_da_rimuovere}
    nuova: list[str] = [d for d in valido_in_date_json if d not in iso_da_rimuovere]
    n_rimosse = len(valido_in_date_json) - len(nuova)
    return nuova, n_rimosse
