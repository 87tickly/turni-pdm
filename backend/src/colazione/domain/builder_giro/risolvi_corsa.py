"""Risoluzione corsa → assegnazione (Sprint 4.2 → esteso Sprint 5.5
con composizione lista).

Funzione **pura** che, data una corsa + un programma materiale + una
data, ritorna l'assegnazione vincente (composizione di rotabili)
secondo le regole con priorità più alta + specificità.

Spec: `docs/PROGRAMMA-MATERIALE.md` §4 e `docs/SPRINT-5-RIPENSAMENTO.md` §5.5.

Il modulo è **DB-agnostic**: accetta oggetti che hanno gli attributi
giusti (ORM, dataclass, qualunque). Le sue responsabilità:

1. Determinare `giorno_tipo` dalla data (feriale/sabato/festivo) usando
   `italian_holidays`.
2. Filtrare le regole del programma che matchano la corsa (AND di
   tutti i filtri).
3. Ordinare per (priorità DESC, specificità DESC).
4. Detect ambiguità top-2 → `RegolaAmbiguaError`.
5. Validare la composizione (Sprint 5.5): se la regola ha più di 1
   elemento E ``is_composizione_manuale=False``, ogni coppia di
   materiali deve essere in ``materiale_accoppiamento_ammesso``
   (callback iniettato dal chiamante). Altrimenti
   ``ComposizioneNonAmmessaError``.
6. Ritornare ``AssegnazioneRisolta`` con la lista ``composizione`` o
   ``None`` se nessuna regola matcha.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, time
from typing import Any, Protocol

from colazione.importers.holidays import italian_holidays

# =====================================================================
# Errori
# =====================================================================


class RegolaAmbiguaError(Exception):
    """Due (o più) regole con identica priorità + specificità → ambiguità.

    Il pianificatore deve disambiguare in UI, alzando la priorità di
    una regola o aggiungendo un filtro più specifico.

    Attributi:
        corsa_id: identificatore della corsa che ha generato l'ambiguità
            (es. `numero_treno`).
        regole_ids: id delle regole top-2 indistinguibili.
    """

    def __init__(self, *, corsa_id: Any, regole_ids: list[int]) -> None:
        super().__init__(
            f"Regole ambigue per corsa {corsa_id!r}: regole {regole_ids} hanno "
            "priorità + specificità identiche. Disambigua manualmente "
            "(alza la priorità di una o aggiungi filtri)."
        )
        self.corsa_id = corsa_id
        self.regole_ids = regole_ids


class ComposizioneNonAmmessaError(Exception):
    """La composizione della regola viola
    ``materiale_accoppiamento_ammesso`` (Sprint 5.5).

    Sollevata da ``risolvi_corsa()`` quando la regola ha 2+ materiali,
    ``is_composizione_manuale=False``, e una coppia non è registrata
    come ammessa.

    Per bypassare il check (composizione custom), il pianificatore
    deve flaggare ``is_composizione_manuale=True`` sulla regola.
    """

    def __init__(self, regola_id: int, coppia_non_ammessa: tuple[str, str]) -> None:
        a, b = coppia_non_ammessa
        super().__init__(
            f"Regola {regola_id}: composizione contiene la coppia ({a!r}, {b!r}) "
            f"NON in materiale_accoppiamento_ammesso. Aggiungi la coppia ai "
            f"vincoli ammessi oppure flagga is_composizione_manuale=True."
        )
        self.regola_id = regola_id
        self.coppia_non_ammessa = coppia_non_ammessa


# =====================================================================
# Output
# =====================================================================


@dataclass(frozen=True)
class ComposizioneItem:
    """Singolo elemento della composizione (dataclass interno al
    dominio, mappa a ``schemas.programmi.ComposizioneItem`` Pydantic).

    Sprint 5.5: la composizione di una regola è una sequenza di 1+
    elementi. ``[ComposizioneItem("ETR526", 1)]`` per regola
    single-material, ``[ComposizioneItem("ETR526",1),
    ComposizioneItem("ETR425",1)]`` per doppia.
    """

    materiale_tipo_codice: str
    n_pezzi: int


@dataclass(frozen=True)
class AssegnazioneRisolta:
    """Risultato della risoluzione: regola vincente + composizione.

    Sprint 5.5: ``composizione`` è una tupla di 1+ ``ComposizioneItem``,
    sostituisce i campi legacy ``materiale_tipo_codice + numero_pezzi``.
    """

    regola_id: int
    composizione: tuple[ComposizioneItem, ...]
    is_composizione_manuale: bool = False

    @property
    def numero_pezzi_totali(self) -> int:
        """Somma ``n_pezzi`` di tutta la composizione."""
        return sum(c.n_pezzi for c in self.composizione)

    @property
    def materiali_codici(self) -> frozenset[str]:
        """Insieme dei codici materiale presenti nella composizione."""
        return frozenset(c.materiale_tipo_codice for c in self.composizione)


# Callback per validazione accoppiamento materiali (Sprint 5.5).
# Riceve due codici materiale, ritorna True se la coppia è ammessa.
# Le coppie sono normalizzate lex (a <= b) dal chiamante: il callback
# può assumere ordering e fare lookup diretto.
IsAccoppiamentoAmmesso = Callable[[str, str], bool]


# =====================================================================
# Protocol — duck-typing dei tipi di input
# =====================================================================


class _RegolaLike(Protocol):
    """Una regola (ORM `ProgrammaRegolaAssegnazione` o dataclass test).

    Sprint 5.5: ``composizione_json`` è la fonte di verità (lista di
    dict ``[{"materiale_tipo_codice": str, "n_pezzi": int}, ...]``).
    I campi legacy ``materiale_tipo_codice + numero_pezzi`` esistono
    ancora ma non vengono più letti da questo modulo (resta backfill
    per `risolvi_corsa()` retrocompat finché non rimossi).
    """

    id: int
    filtri_json: list[Any]
    composizione_json: list[Any]
    is_composizione_manuale: bool
    priorita: int


# Il tipo della corsa è `Any` di proposito: i campi richiesti dipendono
# dai filtri usati nelle regole (lazy duck-typing). Il chiamante è
# responsabile di passare un oggetto con gli attributi necessari (vedi
# `CAMPI_AMMESSI` in `schemas/programmi.py`).
_CorsaLike = Any


# =====================================================================
# Determina giorno_tipo da data
# =====================================================================


def determina_giorno_tipo(d: date) -> str:
    """Una data → ``'feriale'`` | ``'sabato'`` | ``'festivo'``.

    Regole (in ordine di priorità):

    1. Festività italiana (vedi `holidays.italian_holidays`) → festivo
    2. Domenica (`weekday()==6`) → festivo
    3. Sabato (`weekday()==5`) non festivo → sabato
    4. Lun-Ven non festivi → feriale

    Esempi:
        >>> determina_giorno_tipo(date(2026, 1, 1))  # Capodanno (giovedì)
        'festivo'
        >>> determina_giorno_tipo(date(2026, 4, 25))  # Liberazione (sabato)
        'festivo'
        >>> determina_giorno_tipo(date(2026, 4, 18))  # sabato normale
        'sabato'
        >>> determina_giorno_tipo(date(2026, 4, 20))  # lunedì normale
        'feriale'
    """
    if d in italian_holidays(d.year):
        return "festivo"
    weekday = d.weekday()
    if weekday == 6:
        return "festivo"
    if weekday == 5:
        return "sabato"
    return "feriale"


# =====================================================================
# Estrazione valore + parsing time
# =====================================================================


def estrai_valore_corsa(campo: str, corsa: _CorsaLike, giorno_tipo: str) -> Any:
    """Mapping nome-campo del filtro → attributo della corsa (o derivato)."""
    if campo == "giorno_tipo":
        return giorno_tipo
    if campo == "fascia_oraria":
        # Si confronta con `ora_partenza` della corsa (decisione utente
        # in `PROGRAMMA-MATERIALE.md` §6.3: la partenza decide).
        return corsa.ora_partenza
    return getattr(corsa, campo)


def _parse_time_str(s: Any) -> time:
    """Parsa stringa 'HH:MM' o 'HH:MM:SS' in `time`. Pass-through se già `time`."""
    if isinstance(s, time):
        return s
    if not isinstance(s, str):
        raise TypeError(f"fascia_oraria valore deve essere stringa, ricevuto {type(s).__name__}")
    parts = s.split(":")
    if len(parts) not in (2, 3):
        raise ValueError(f"fascia_oraria {s!r} non in formato HH:MM o HH:MM:SS")
    return time(
        int(parts[0]),
        int(parts[1]),
        int(parts[2]) if len(parts) == 3 else 0,
    )


# =====================================================================
# Match filtro singolo / regola completa
# =====================================================================


def matches_filtro(filtro: dict[str, Any], corsa: _CorsaLike, giorno_tipo: str) -> bool:
    """Un singolo filtro matcha la corsa?

    Il filtro è un dict con chiavi `campo`, `op`, `valore` (validato
    a monte da Pydantic in `schemas/programmi.py`).
    """
    campo = filtro["campo"]
    op = filtro["op"]
    valore_filtro = filtro["valore"]

    valore_corsa = estrai_valore_corsa(campo, corsa, giorno_tipo)

    if op == "eq":
        return bool(valore_corsa == valore_filtro)

    if op == "in":
        return valore_corsa in valore_filtro

    if op == "between":
        lo, hi = valore_filtro
        if campo == "fascia_oraria":
            lo = _parse_time_str(lo)
            hi = _parse_time_str(hi)
        return bool(lo <= valore_corsa <= hi)

    if op == "gte":
        rhs = valore_filtro
        if campo == "fascia_oraria":
            rhs = _parse_time_str(rhs)
        return bool(valore_corsa >= rhs)

    if op == "lte":
        rhs = valore_filtro
        if campo == "fascia_oraria":
            rhs = _parse_time_str(rhs)
        return bool(valore_corsa <= rhs)

    raise ValueError(f"operatore non supportato: {op!r}")


def matches_all(filtri: list[dict[str, Any]], corsa: _CorsaLike, giorno_tipo: str) -> bool:
    """Tutti i filtri devono matchare (AND).

    Lista vuota → ``True`` (regola di fallback: matcha tutto).
    """
    for f in filtri:
        if not matches_filtro(f, corsa, giorno_tipo):
            return False
    return True


# =====================================================================
# Risoluzione top-level
# =====================================================================


def _composizione_da_json(regola: _RegolaLike) -> tuple[ComposizioneItem, ...]:
    """Costruisce ``tuple[ComposizioneItem, ...]`` dal
    ``composizione_json`` (lista di dict) della regola.

    Il dato è validato a monte da Pydantic ``ComposizioneItem`` in
    ``schemas/programmi.py`` (n_pezzi >= 1, materiale_tipo_codice
    non vuoto, lista non vuota). Qui ci limitiamo al parsing.
    """
    items: list[ComposizioneItem] = []
    for entry in regola.composizione_json:
        items.append(
            ComposizioneItem(
                materiale_tipo_codice=str(entry["materiale_tipo_codice"]),
                n_pezzi=int(entry["n_pezzi"]),
            )
        )
    return tuple(items)


def _valida_accoppiamenti(
    regola_id: int,
    composizione: tuple[ComposizioneItem, ...],
    is_accoppiamento_ammesso: IsAccoppiamentoAmmesso,
) -> None:
    """Verifica che ogni coppia di materiali nella composizione sia
    in ``materiale_accoppiamento_ammesso`` (Sprint 5.5).

    Le coppie sono normalizzate lex (a <= b) per coerenza con il CHECK
    DB ``materiale_accoppiamento_normalizzato``.

    Logica:
    - Aggrega i pezzi per codice (somma se appare in più item).
    - Per ogni coppia di codici **distinti** (a, b): valida (a, b) lex.
    - Per ogni codice con ``n_pezzi >= 2``: valida self-pair (a, a)
      (es. composizione 526+526 doppia stessa famiglia richiede la
      coppia (526, 526) ammessa).
    """
    if len(composizione) < 2:
        return  # niente coppie da validare per regola single-material
    pezzi_per_tipo: dict[str, int] = {}
    for item in composizione:
        pezzi_per_tipo[item.materiale_tipo_codice] = (
            pezzi_per_tipo.get(item.materiale_tipo_codice, 0) + item.n_pezzi
        )
    codici = sorted(pezzi_per_tipo.keys())
    # Coppie di codici distinti (a, b) normalizzate lex
    for i in range(len(codici)):
        for j in range(i + 1, len(codici)):
            a, b = codici[i], codici[j]  # già lex per il sorted()
            if not is_accoppiamento_ammesso(a, b):
                raise ComposizioneNonAmmessaError(regola_id=regola_id, coppia_non_ammessa=(a, b))
    # Self-pair: solo se un codice appare 2+ volte nella composizione
    for codice, n_pezzi in pezzi_per_tipo.items():
        if n_pezzi >= 2 and not is_accoppiamento_ammesso(codice, codice):
            raise ComposizioneNonAmmessaError(
                regola_id=regola_id, coppia_non_ammessa=(codice, codice)
            )


def risolvi_corsa(
    corsa: _CorsaLike,
    regole: Sequence[_RegolaLike],
    data: date,
    is_accoppiamento_ammesso: IsAccoppiamentoAmmesso | None = None,
) -> AssegnazioneRisolta | None:
    """Risolve l'assegnazione di una corsa (composizione di rotabili)
    in una data.

    Algoritmo (vedi `PROGRAMMA-MATERIALE.md` §4.1 e
    `SPRINT-5-RIPENSAMENTO.md` §5.5):

    1. Determina `giorno_tipo` dalla `data`.
    2. Filtra le `regole` candidate (AND di tutti i filtri).
    3. Se nessuna candidata → `None`.
    4. Ordina per `(priorita DESC, specificita DESC)`.
    5. Se top-2 hanno priorità+specificità identiche → `RegolaAmbiguaError`.
    6. Costruisce ``composizione`` dalla ``composizione_json`` della top.
    7. **Sprint 5.5 — Validazione accoppiamento**: se la composizione
       ha 2+ materiali, ``is_composizione_manuale=False``, e il
       chiamante ha passato ``is_accoppiamento_ammesso``, ogni coppia
       (normalizzata lex) deve essere ammessa. Altrimenti
       ``ComposizioneNonAmmessaError``.
    8. Ritorna ``AssegnazioneRisolta`` con la composizione.

    Args:
        corsa: oggetto con i campi della corsa (vedi
            `schemas/programmi.CAMPI_AMMESSI`).
        regole: lista di regole del programma, **già caricata** (no lazy
            ORM). Tipicamente `programma.regole`.
        data: data per cui si risolve.
        is_accoppiamento_ammesso: callback opzionale che dato (a, b)
            ordinati lex ritorna True se la coppia è ammessa. Se
            ``None``, la validazione accoppiamento viene saltata
            (comportamento legacy / testing semplice).

    Returns:
        `AssegnazioneRisolta` con regola vincente, oppure `None` se
        nessuna regola matcha (corsa "residua" — vedi strict mode).

    Raises:
        RegolaAmbiguaError: se top-2 regole sono indistinguibili.
        ComposizioneNonAmmessaError: se la composizione viola gli
            accoppiamenti ammessi (Sprint 5.5).
        ValueError: se un filtro ha operatore sconosciuto.
    """
    giorno_tipo = determina_giorno_tipo(data)

    candidate = [r for r in regole if matches_all(r.filtri_json, corsa, giorno_tipo)]
    if not candidate:
        return None

    # Ordine: priorità più alta vince; a parità, più specifica (più filtri).
    candidate.sort(key=lambda r: (r.priorita, len(r.filtri_json)), reverse=True)

    top = candidate[0]
    if len(candidate) > 1:
        second = candidate[1]
        if top.priorita == second.priorita and len(top.filtri_json) == len(second.filtri_json):
            raise RegolaAmbiguaError(
                corsa_id=getattr(corsa, "numero_treno", None),
                regole_ids=[top.id, second.id],
            )

    composizione = _composizione_da_json(top)
    if not composizione:
        raise RuntimeError(
            f"Regola {top.id}: composizione_json vuota. "
            "Verifica integrità DB (Pydantic ComposizioneItem richiede "
            "lista non vuota)."
        )

    # Validazione accoppiamenti (Sprint 5.5). Skip se manuale o callback
    # non fornita.
    if not top.is_composizione_manuale and is_accoppiamento_ammesso is not None:
        _valida_accoppiamenti(top.id, composizione, is_accoppiamento_ammesso)

    return AssegnazioneRisolta(
        regola_id=top.id,
        composizione=composizione,
        is_composizione_manuale=top.is_composizione_manuale,
    )
