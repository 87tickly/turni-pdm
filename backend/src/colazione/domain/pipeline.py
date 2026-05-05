"""Pipeline state machine — Sprint 8.0 MR 0 (entry 164).

Definisce due catene di stati paralleli per la concatenazione fra ruoli
del programma materiale:

- :class:`StatoPipelinePdc` (8 stati, vincolante): la catena principale
  ``PdE → Materiale → PdC → Personale → Vista``.
- :class:`StatoManutenzione` (3 stati, parallela): si attiva quando la
  catena PdC raggiunge ``MATERIALE_CONFERMATO`` ma non blocca le
  transizioni del ramo PdC.
- :class:`TipoImportRun` (5 tipi): ``BASE`` per il primo import,
  ``INTEGRAZIONE`` / ``VARIAZIONE_*`` per il versioning multi-import.

Schema DB: la migration ``0032_pipeline_state_machine`` impone le 3
liste valori via ``CHECK constraint`` sulle colonne
``programma_materiale.stato_pipeline_pdc``,
``programma_materiale.stato_manutenzione`` e
``corsa_import_run.tipo``. **L'ordinamento e la matrice di transizioni
sono validati solo qui**: il DB conosce l'insieme dei valori, non la
sequenza ammessa fra di loro. Tenere le tuple nello stesso ordine del
file di migration (le costanti ``STATI_PIPELINE_PDC`` e
``STATI_MANUTENZIONE``).

Errori::

    StatoPipelinePdc("FOOBAR")            # ValueError (Enum)
    valida_transizione_pdc(...)           # TransizioneNonAmmessaError

Esempio d'uso negli endpoint::

    corrente = StatoPipelinePdc(programma.stato_pipeline_pdc)
    valida_transizione_pdc(corrente, StatoPipelinePdc.MATERIALE_CONFERMATO)
    programma.stato_pipeline_pdc = StatoPipelinePdc.MATERIALE_CONFERMATO.value
"""

from __future__ import annotations

import logging
from enum import StrEnum

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Enum (sincronizzati con migration 0032 — ordine = sequenza pipeline)
# ---------------------------------------------------------------------------


class StatoPipelinePdc(StrEnum):
    """Stati della catena principale (vincolante per Personale)."""

    PDE_IN_LAVORAZIONE = "PDE_IN_LAVORAZIONE"
    PDE_CONSOLIDATO = "PDE_CONSOLIDATO"
    MATERIALE_GENERATO = "MATERIALE_GENERATO"
    MATERIALE_CONFERMATO = "MATERIALE_CONFERMATO"
    PDC_GENERATO = "PDC_GENERATO"
    PDC_CONFERMATO = "PDC_CONFERMATO"
    PERSONALE_ASSEGNATO = "PERSONALE_ASSEGNATO"
    VISTA_PUBBLICATA = "VISTA_PUBBLICATA"


class StatoManutenzione(StrEnum):
    """Stati del ramo manutenzione (parallelo)."""

    IN_ATTESA = "IN_ATTESA"
    IN_LAVORAZIONE = "IN_LAVORAZIONE"
    MATRICOLE_ASSEGNATE = "MATRICOLE_ASSEGNATE"


class TipoImportRun(StrEnum):
    """Tipi di import del PdE: BASE + variazioni successive."""

    BASE = "BASE"
    INTEGRAZIONE = "INTEGRAZIONE"
    VARIAZIONE_INTERRUZIONE = "VARIAZIONE_INTERRUZIONE"
    VARIAZIONE_ORARIO = "VARIAZIONE_ORARIO"
    VARIAZIONE_CANCELLAZIONE = "VARIAZIONE_CANCELLAZIONE"


# ---------------------------------------------------------------------------
# Matrici di transizione (in avanti)
# ---------------------------------------------------------------------------
#
# Decisione di scope MR 0: la catena è essenzialmente lineare. La sola
# eccezione è ``PDE_CONSOLIDATO → MATERIALE_CONFERMATO`` (skip dello
# stato intermedio ``MATERIALE_GENERATO``), prevista dal piano per il
# caso in cui il pianificatore conferma il materiale **senza un nuovo
# run del builder** (es. il programma è stato consolidato dal PdE base
# e il pianificatore approva direttamente la composizione esistente,
# senza rigenerare). Lo stato ``MATERIALE_GENERATO`` rappresenta "run
# del builder eseguito ma in attesa di conferma", quindi ha senso
# saltarlo se nessun run è stato eseguito. Tutti gli altri salti sono
# vietati.
#
TRANSIZIONI_PDC_AMMESSE: dict[StatoPipelinePdc, frozenset[StatoPipelinePdc]] = {
    StatoPipelinePdc.PDE_IN_LAVORAZIONE: frozenset(
        {StatoPipelinePdc.PDE_CONSOLIDATO}
    ),
    StatoPipelinePdc.PDE_CONSOLIDATO: frozenset(
        {
            StatoPipelinePdc.MATERIALE_GENERATO,
            StatoPipelinePdc.MATERIALE_CONFERMATO,
        }
    ),
    StatoPipelinePdc.MATERIALE_GENERATO: frozenset(
        {StatoPipelinePdc.MATERIALE_CONFERMATO}
    ),
    StatoPipelinePdc.MATERIALE_CONFERMATO: frozenset(
        {StatoPipelinePdc.PDC_GENERATO}
    ),
    StatoPipelinePdc.PDC_GENERATO: frozenset({StatoPipelinePdc.PDC_CONFERMATO}),
    StatoPipelinePdc.PDC_CONFERMATO: frozenset(
        {StatoPipelinePdc.PERSONALE_ASSEGNATO}
    ),
    StatoPipelinePdc.PERSONALE_ASSEGNATO: frozenset(
        {StatoPipelinePdc.VISTA_PUBBLICATA}
    ),
    StatoPipelinePdc.VISTA_PUBBLICATA: frozenset(),  # terminale
}

TRANSIZIONI_MANUTENZIONE_AMMESSE: dict[
    StatoManutenzione, frozenset[StatoManutenzione]
] = {
    StatoManutenzione.IN_ATTESA: frozenset({StatoManutenzione.IN_LAVORAZIONE}),
    StatoManutenzione.IN_LAVORAZIONE: frozenset(
        {StatoManutenzione.MATRICOLE_ASSEGNATE}
    ),
    StatoManutenzione.MATRICOLE_ASSEGNATE: frozenset(),  # terminale
}


class TransizioneNonAmmessaError(ValueError):
    """Tentativo di transizione non presente in matrice ammesse."""


def valida_transizione_pdc(
    corrente: StatoPipelinePdc, target: StatoPipelinePdc
) -> None:
    """Solleva ``TransizioneNonAmmessaError`` se ``corrente → target``
    non è nella matrice :data:`TRANSIZIONI_PDC_AMMESSE`."""
    ammesse = TRANSIZIONI_PDC_AMMESSE.get(corrente, frozenset())
    if target not in ammesse:
        raise TransizioneNonAmmessaError(
            f"transizione PdC {corrente.value} → {target.value} non ammessa. "
            f"Da {corrente.value} sono ammessi: "
            f"{sorted(s.value for s in ammesse) or '<terminale>'}"
        )


def valida_transizione_manutenzione(
    corrente: StatoManutenzione, target: StatoManutenzione
) -> None:
    """Solleva ``TransizioneNonAmmessaError`` se ``corrente → target``
    non è nella matrice :data:`TRANSIZIONI_MANUTENZIONE_AMMESSE`."""
    ammesse = TRANSIZIONI_MANUTENZIONE_AMMESSE.get(corrente, frozenset())
    if target not in ammesse:
        raise TransizioneNonAmmessaError(
            f"transizione manutenzione {corrente.value} → {target.value} "
            f"non ammessa. Da {corrente.value} sono ammessi: "
            f"{sorted(s.value for s in ammesse) or '<terminale>'}"
        )


# ---------------------------------------------------------------------------
# Ordinamento (per filtri ``>= soglia`` lato API)
# ---------------------------------------------------------------------------
_ORDINE_PDC: tuple[StatoPipelinePdc, ...] = tuple(StatoPipelinePdc)
_ORDINE_MANUTENZIONE: tuple[StatoManutenzione, ...] = tuple(StatoManutenzione)


def ordinale_pdc(stato: StatoPipelinePdc) -> int:
    """Indice 0-based di ``stato`` nella sequenza pipeline PdC."""
    return _ORDINE_PDC.index(stato)


def ordinale_manutenzione(stato: StatoManutenzione) -> int:
    """Indice 0-based di ``stato`` nella sequenza manutenzione."""
    return _ORDINE_MANUTENZIONE.index(stato)


def stati_pdc_da(stato_min: StatoPipelinePdc) -> tuple[str, ...]:
    """Tutti i valori string ``>= stato_min`` (sequenza pipeline PdC).

    Pensato per where-clause SQL ``stato_pipeline_pdc IN (...)`` quando
    una list-route filtra per ruolo (es. ``PIANIFICATORE_PDC`` vede
    solo programmi con stato ``>= MATERIALE_CONFERMATO``).
    """
    soglia = ordinale_pdc(stato_min)
    return tuple(s.value for s in _ORDINE_PDC[soglia:])


def stati_manutenzione_da(stato_min: StatoManutenzione) -> tuple[str, ...]:
    """Tutti i valori string ``>= stato_min`` (sequenza manutenzione)."""
    soglia = ordinale_manutenzione(stato_min)
    return tuple(s.value for s in _ORDINE_MANUTENZIONE[soglia:])


# ---------------------------------------------------------------------------
# Sblocco admin: torna allo stato immediatamente precedente
# ---------------------------------------------------------------------------


def stato_pdc_precedente(stato: StatoPipelinePdc) -> StatoPipelinePdc | None:
    """Stato immediatamente precedente nella catena PdC, o ``None`` se
    ``stato`` è il primo (``PDE_IN_LAVORAZIONE``)."""
    idx = ordinale_pdc(stato)
    return _ORDINE_PDC[idx - 1] if idx > 0 else None


def stato_manutenzione_precedente(
    stato: StatoManutenzione,
) -> StatoManutenzione | None:
    """Stato immediatamente precedente nella catena manutenzione, o
    ``None`` se ``stato`` è ``IN_ATTESA``."""
    idx = ordinale_manutenzione(stato)
    return _ORDINE_MANUTENZIONE[idx - 1] if idx > 0 else None


# ---------------------------------------------------------------------------
# Policy di visibilità list-route per ruolo (Sprint 8.0 MR 0)
# ---------------------------------------------------------------------------
#
# Specifica MR 0:
#
# - PIANIFICATORE_GIRO + admin    → vedono tutto (proprietari ramo Materiale).
# - PIANIFICATORE_PDC             → solo programmi >= MATERIALE_CONFERMATO.
# - GESTIONE_PERSONALE            → solo programmi >= PDC_CONFERMATO.
# - MANUTENZIONE                  → solo programmi >= MATERIALE_CONFERMATO.
#
# Logica unione: se un utente possiede più ruoli, vince il più permissivo
# (ordinale minimo). Esempio: ``[PIANIFICATORE_PDC, GESTIONE_PERSONALE]``
# → soglia ``MATERIALE_CONFERMATO`` (più bassa).
#
SOGLIE_PIPELINE_PER_RUOLO: dict[str, StatoPipelinePdc] = {
    "PIANIFICATORE_PDC": StatoPipelinePdc.MATERIALE_CONFERMATO,
    "GESTIONE_PERSONALE": StatoPipelinePdc.PDC_CONFERMATO,
    "MANUTENZIONE": StatoPipelinePdc.MATERIALE_CONFERMATO,
}


def soglia_pipeline_per_ruoli(
    roles: list[str], is_admin: bool
) -> StatoPipelinePdc | None:
    """Calcola lo stato minimo pipeline visibile per l'utente.

    Restituisce ``None`` se l'utente vede tutti i programmi senza filtro
    (admin o ``PIANIFICATORE_GIRO``); altrimenti lo stato di soglia
    derivato dal ruolo più permissivo possesso.

    **Semantica multi-ruolo (decisione MR 0)**: la policy fra ruoli è
    "OR funzionale" (l'utente può fare ciò che almeno uno dei suoi
    ruoli gli abilita), non "AND" (intersezione least-privilege). Per
    questo si usa ``min(soglie, key=ordinale_pdc)``: se l'utente ha
    ``PIANIFICATORE_PDC`` deve poter agire su programmi ``>=
    MATERIALE_CONFERMATO`` indipendentemente dal fatto che abbia anche
    ``GESTIONE_PERSONALE`` (che richiederebbe ``>= PDC_CONFERMATO``).
    Applicare il MAX (più restrittivo) sarebbe contraddittorio: un
    utente multi-ruolo vedrebbe MENO di un utente con il solo ruolo
    più basso. La sicurezza per-azione resta affidata a
    ``require_role(...)`` sui singoli endpoint.

    Se l'utente non ha alcun ruolo conosciuto, restituisce ``None``: la
    dependency d'auth a monte (``require_any_role(...)``) avrà già
    rifiutato la chiamata, quindi il caller non deve mai ritrovarsi
    qui senza ruoli ammissibili.
    """
    if is_admin or "PIANIFICATORE_GIRO" in roles:
        return None
    soglie = [
        SOGLIE_PIPELINE_PER_RUOLO[r] for r in roles if r in SOGLIE_PIPELINE_PER_RUOLO
    ]
    if not soglie:
        return None
    return min(soglie, key=ordinale_pdc)


def programma_visibile_per_ruoli(
    stato_pipeline_pdc: str, roles: list[str], is_admin: bool
) -> bool:
    """``True`` se ``stato_pipeline_pdc`` rispetta la soglia derivata dai
    ruoli dell'utente.

    Versione "valore string" pensata per chi non vuole importare l'ORM
    (es. helper di api/programmi.py vs api/giri.py vs api/turni_pdc.py:
    ognuna passa il valore string e mantiene il proprio modello ORM).

    Difensivo: se ``stato_pipeline_pdc`` non è un valore valido di
    :class:`StatoPipelinePdc`, ritorna ``False`` (non far trapelare
    programmi corrotti a ruoli a valle — il CHECK constraint DB
    dovrebbe già impedirlo). Il caso viene loggato a WARNING per
    permettere alert ops senza bloccare la list-route con un 500.
    """
    soglia = soglia_pipeline_per_ruoli(roles, is_admin)
    if soglia is None:
        return True
    try:
        stato = StatoPipelinePdc(stato_pipeline_pdc)
    except ValueError:
        _logger.warning(
            "stato_pipeline_pdc fuori enum (%r): programma trattato come "
            "invisibile. Indica disallineamento DB/codice (CHECK constraint "
            "dovrebbe impedirlo).",
            stato_pipeline_pdc,
        )
        return False
    return ordinale_pdc(stato) >= ordinale_pdc(soglia)
