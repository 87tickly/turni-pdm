"""Posizionamento catena su località manutenzione (Sprint 4.4.2 →
riscritto Sprint 5.3 con whitelist).

Funzione **pura** che, data una `Catena` (output di `catena.py`) + una
località manutenzione + una **whitelist di stazioni vicine ammesse**,
genera blocchi ``materiale_vuoto`` di **testa** e **coda** SOLO quando
la prima/ultima corsa cade dentro la whitelist (vuoti tecnici
intra-area-Milano).

Spec: ``docs/SPRINT-5-RIPENSAMENTO.md`` §3 e §5.3.

Modello operativo corretto (Sprint 5):

- I vuoti tecnici esistono **solo tra stazioni vicine alla sede
  manutentiva** (whitelist configurata in ``localita_stazione_vicina``,
  vedi script ``scripts/seed_whitelist_e_accoppiamenti.py``).
- Verso la periferia (Tirano, Asso, Laveno, ecc.) il convoglio si
  posiziona con **corse commerciali**: dorme in stazione la sera,
  riparte il mattino dopo.
- Una catena con prima/ultima corsa **fuori whitelist** non genera
  vuoti, e il giro chiude in modalità ``chiusa_a_localita=False`` —
  segnale a ``costruisci_giri_multigiornata`` che il giro continua il
  giorno dopo o si chiude in modo "non programmato".

Quando serve un materiale vuoto:

- **Testa**: se ``prima.codice_origine ∈ whitelist`` AND
  ``prima.codice_origine != stazione_collegata`` → vuoto da
  ``stazione_collegata`` → ``prima.codice_origine``,
  ``ora_arrivo = prima.ora_partenza - gap_min``. Se
  ``prima.codice_origine == stazione_collegata`` → niente vuoto
  (chiusura naturale). Se ``prima.codice_origine ∉ whitelist`` →
  niente vuoto, il treno è già lì da ieri.
- **Coda**: simmetrico, sull'ultima corsa.

Limiti residui:

- **Single-day rigido**: catena cross-notte (``ora_arrivo <
  ora_partenza``) → niente vuoto coda, ``chiusa_a_localita=False``.
  La chiusura è gestita da ``multi_giornata.py``.
- **Durata vuoto stimata**: parametro ``durata_vuoto_default_min``
  (default 30'). Niente matrice km/velocità reale qui.
- **Niente check capacità località**: la verifica pezzi/tipo è in
  ``composizione.py``.

Il modulo è **DB-agnostic**: accetta qualunque oggetto col duck-typing
giusto (Protocol ``_LocalitaLike``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Protocol

from colazione.domain.builder_giro.catena import Catena

# =====================================================================
# Errori
# =====================================================================


class LocalitaSenzaStazioneError(ValueError):
    """La località manutenzione non ha ``stazione_collegata_codice``.

    Senza la stazione collegata il builder non può generare materiali
    vuoti da/verso la località. Configura la località in anagrafica.
    """

    def __init__(self, codice_localita: str) -> None:
        super().__init__(
            f"Località manutenzione {codice_localita!r} non ha "
            "stazione_collegata_codice. Configura una stazione."
        )
        self.codice_localita = codice_localita


class PosizionamentoImpossibileError(ValueError):
    """Vuoto di testa partirebbe prima delle 00:00 (prima corsa troppo
    presto rispetto a ``durata_vuoto_default_min + gap_min``).

    In single-day non possiamo materializzare un vuoto che inizia "il
    giorno prima". 4.4.3 gestirà giri multi-giornata che ereditano la
    chiusura dalla giornata precedente.
    """


# =====================================================================
# Protocol — duck-typing input
# =====================================================================


class _LocalitaLike(Protocol):
    """Località manutenzione minima (ORM ``LocalitaManutenzione`` o test)."""

    codice: str
    stazione_collegata_codice: str | None


# =====================================================================
# Parametri + Output
# =====================================================================


@dataclass(frozen=True)
class ParamPosizionamento:
    """Parametri per il posizionamento.

    Attributi:
        durata_vuoto_default_min: durata stimata di un materiale vuoto
            (minuti). Default 30'. Stima conservativa, raffinabile
            quando avremo matrice km/velocità.
        gap_min: gap minimo tra vuoto e prima/ultima corsa (minuti).
            Default 5'. Stessa semantica di ``catena.ParamCatena.gap_min``.
    """

    durata_vuoto_default_min: int = 30
    gap_min: int = 5


_DEFAULT_PARAM = ParamPosizionamento()


@dataclass(frozen=True)
class BloccoMaterialeVuoto:
    """Posizionamento materiale vuoto generato dal builder.

    Si traduce poi in ``CorsaMaterialeVuoto`` ORM (Sprint 4.4.5
    persistenza), con ``origine='generato_da_giro_materiale'``.
    """

    codice_origine: str
    codice_destinazione: str
    ora_partenza: time
    ora_arrivo: time
    motivo: str  # 'testa' | 'coda' — per tracciabilità in metadata_json


@dataclass(frozen=True)
class CatenaPosizionata:
    """Catena chiusa (o aperta) su una località manutenzione.

    Attributi:
        localita_codice: codice località manutenzione di riferimento.
        stazione_collegata: codice stazione della località (denormalizzato
            per comodità del consumer).
        vuoto_testa: ``BloccoMaterialeVuoto`` se serve posizionamento
            iniziale (località → prima corsa). ``None`` se prima corsa
            parte già dalla stazione collegata.
        catena: la `Catena` originale (immutata).
        vuoto_coda: ``BloccoMaterialeVuoto`` se serve rientro (ultima
            corsa → località). ``None`` se l'ultima arriva già in
            stazione **oppure** la catena chiude cross-notte (in tal
            caso ``chiusa_a_localita=False``).
        chiusa_a_localita: ``True`` se il giro chiude in stazione
            collegata in questa giornata (naturalmente o via vuoto coda).
            ``False`` se cross-notte o se il vuoto di coda finirebbe
            oltre la mezzanotte.
    """

    localita_codice: str
    stazione_collegata: str
    vuoto_testa: BloccoMaterialeVuoto | None
    catena: Catena
    vuoto_coda: BloccoMaterialeVuoto | None
    chiusa_a_localita: bool


# =====================================================================
# Helpers interni
# =====================================================================


def _time_to_min(t: time) -> int:
    """``time`` → minuti dall'inizio giornata (0..1439)."""
    return t.hour * 60 + t.minute


def _min_to_time(m: int) -> time:
    """Minuti (0..1439) → ``time``."""
    return time(m // 60, m % 60)


def _attraversa_mezzanotte(ora_partenza: time, ora_arrivo: time) -> bool:
    return ora_arrivo < ora_partenza


# =====================================================================
# Algoritmo
# =====================================================================


def posiziona_su_localita(
    catena: Catena,
    localita: _LocalitaLike,
    whitelist_stazioni: frozenset[str],
    params: ParamPosizionamento = _DEFAULT_PARAM,
) -> CatenaPosizionata:
    """Posiziona una catena su una località manutenzione (Sprint 5.3).

    Algoritmo:

    1. Valida input (catena non vuota, località con stazione collegata).
    2. **Vuoto di testa** — generato SOLO se entrambe:
       - ``prima.codice_origine ∈ whitelist_stazioni``
       - ``prima.codice_origine != stazione_localita``
       Se ``prima.codice_origine == stazione_localita`` → niente vuoto
       (chiusura naturale). Se ``prima.codice_origine ∉ whitelist`` →
       niente vuoto, il treno è già nella stazione di partenza dalla
       sera precedente (multi-giornata).
       Se la partenza calcolata cade < 00:00, alza
       ``PosizionamentoImpossibileError``.
    3. **Vuoto di coda** — simmetrico, sull'ultima corsa: generato SOLO
       se NON cross-notte AND ``ultima.codice_destinazione ∈
       whitelist_stazioni`` AND ``ultima.codice_destinazione !=
       stazione_localita``. Se l'arrivo calcolato supera la mezzanotte,
       salta la generazione e marca ``chiusa_a_localita = False`` (la
       chiusura sarà gestita da ``multi_giornata.py``).
    4. ``chiusa_a_localita`` = True solo se l'ultima corsa arriva in
       ``stazione_localita`` (chiusura naturale) OPPURE è stato generato
       il vuoto di coda. Se ultima è fuori whitelist e ≠ stazione →
       False (treno dorme in linea).

    Args:
        catena: ``Catena`` non vuota (output di ``costruisci_catene``).
        localita: oggetto con ``codice`` e ``stazione_collegata_codice``
            non null.
        whitelist_stazioni: insieme di codici stazione "vicini" alla
            sede in cui sono ammessi i vuoti tecnici. Letto da
            ``localita_stazione_vicina`` (DB) — vedi loader in
            ``builder.py``. ``frozenset()`` vuoto = nessun vuoto mai
            generato.
        params: ``ParamPosizionamento``.

    Returns:
        ``CatenaPosizionata``: catena originale + 0/1/2 vuoti +
        flag chiusura.

    Raises:
        ValueError: catena vuota.
        LocalitaSenzaStazioneError: località senza stazione collegata.
        PosizionamentoImpossibileError: vuoto di testa partirebbe prima
            di 00:00.
    """
    if not catena.corse:
        raise ValueError("catena vuota: niente da posizionare")

    s = localita.stazione_collegata_codice
    if not s:
        raise LocalitaSenzaStazioneError(localita.codice)

    prima = catena.corse[0]
    ultima = catena.corse[-1]

    # ---- Vuoto di testa: solo se prima.origine ∈ whitelist e ≠ sede ----
    vuoto_testa: BloccoMaterialeVuoto | None = None
    if prima.codice_origine != s and prima.codice_origine in whitelist_stazioni:
        arrivo_min = _time_to_min(prima.ora_partenza) - params.gap_min
        partenza_min = arrivo_min - params.durata_vuoto_default_min
        if partenza_min < 0:
            raise PosizionamentoImpossibileError(
                f"Vuoto di testa per catena che inizia alle "
                f"{prima.ora_partenza.isoformat()} partirebbe prima delle "
                f"00:00 (durata stimata {params.durata_vuoto_default_min}' + "
                f"gap {params.gap_min}'). Riduci durata stimata o "
                "rimanda la chiusura a multi_giornata."
            )
        vuoto_testa = BloccoMaterialeVuoto(
            codice_origine=s,
            codice_destinazione=prima.codice_origine,
            ora_partenza=_min_to_time(partenza_min),
            ora_arrivo=_min_to_time(arrivo_min),
            motivo="testa",
        )

    # ---- Vuoto di coda: solo se ultima.dest ∈ whitelist e ≠ sede ----
    vuoto_coda: BloccoMaterialeVuoto | None = None
    cross_notte = _attraversa_mezzanotte(ultima.ora_partenza, ultima.ora_arrivo)
    coda_oltre_mezzanotte = False
    if (
        not cross_notte
        and ultima.codice_destinazione != s
        and ultima.codice_destinazione in whitelist_stazioni
    ):
        partenza_min = _time_to_min(ultima.ora_arrivo) + params.gap_min
        arrivo_min = partenza_min + params.durata_vuoto_default_min
        if arrivo_min > 24 * 60 - 1:
            # Vuoto finirebbe dopo le 23:59 → demando a multi_giornata.
            coda_oltre_mezzanotte = True
        else:
            vuoto_coda = BloccoMaterialeVuoto(
                codice_origine=ultima.codice_destinazione,
                codice_destinazione=s,
                ora_partenza=_min_to_time(partenza_min),
                ora_arrivo=_min_to_time(arrivo_min),
                motivo="coda",
            )

    # ---- Flag di chiusura ----
    # True solo se ultima corsa arriva alla sede (chiusura naturale)
    # oppure abbiamo generato il vuoto di coda. In ogni altro caso
    # (cross-notte, ultima fuori whitelist, coda oltre mezzanotte) →
    # False, il giro continua il giorno dopo (multi_giornata).
    chiusa = (
        not cross_notte
        and not coda_oltre_mezzanotte
        and (ultima.codice_destinazione == s or vuoto_coda is not None)
    )

    return CatenaPosizionata(
        localita_codice=localita.codice,
        stazione_collegata=s,
        vuoto_testa=vuoto_testa,
        catena=catena,
        vuoto_coda=vuoto_coda,
        chiusa_a_localita=chiusa,
    )
