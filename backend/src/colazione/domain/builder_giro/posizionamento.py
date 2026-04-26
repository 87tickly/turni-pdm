"""Posizionamento catena su località manutenzione (Sprint 4.4.2).

Funzione **pura** che, data una `Catena` (output di `catena.py`) + una
località manutenzione + parametri, genera blocchi ``materiale_vuoto``
di **testa** e **coda** per chiudere il giro nella stazione collegata
alla località.

Spec: ``docs/LOGICA-COSTRUZIONE.md`` §3.2 (rami "posizionamento
iniziale" e "rientro a località" in ``costruisci_giri_da_localita``).

Quando serve un materiale vuoto:

- **Testa**: se la prima corsa NON parte dalla stazione collegata alla
  località → vuoto da ``stazione_collegata`` → ``prima.codice_origine``,
  che arriva in tempo per essere agganciato (``prima.ora_partenza -
  gap_min``).
- **Coda**: se l'ultima corsa NON arriva nella stazione collegata
  → vuoto da ``ultima.codice_destinazione`` →
  ``stazione_collegata``, partendo dopo l'arrivo dell'ultima
  (``ultima.ora_arrivo + gap_min``).

Limiti del sub-sprint 4.4.2:

- **Single-day rigido**: se la catena chiude cross-notte (ultima
  corsa con ``ora_arrivo < ora_partenza``) **NON** generiamo il vuoto
  di coda — la chiusura è demandata a Sprint 4.4.3 (multi-giornata).
  Indichiamo ``chiusa_a_localita=False``.
- **Durata vuoto stimata**: parametro ``durata_vuoto_default_min``
  (default 30'). Niente matrice km/velocità reale qui — raffinamento
  futuro quando servirà.
- **Niente check capacità località**: la verifica che la località
  abbia pezzi del tipo richiesto è in Sprint 4.4.4 (assegnazione).

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
    params: ParamPosizionamento = _DEFAULT_PARAM,
) -> CatenaPosizionata:
    """Posiziona una catena su una località manutenzione.

    Algoritmo:

    1. Valida input (catena non vuota, località con stazione collegata).
    2. **Vuoto di testa**: se ``prima.codice_origine != stazione_localita``,
       genera blocco vuoto che parte da ``stazione_localita`` e arriva in
       ``prima.codice_origine`` con ``ora_arrivo = prima.ora_partenza -
       gap_min``. Se la partenza calcolata è < 00:00, alza
       ``PosizionamentoImpossibileError``.
    3. **Vuoto di coda**: se la catena NON chiude cross-notte e
       ``ultima.codice_destinazione != stazione_localita``, genera
       blocco vuoto inverso. Se l'arrivo calcolato supera la
       mezzanotte, salta la generazione e marca ``chiusa_a_localita
       = False`` (la chiusura sarà gestita da 4.4.3).
    4. Calcola ``chiusa_a_localita`` finale.

    Args:
        catena: ``Catena`` non vuota (output di ``costruisci_catene``).
        localita: oggetto con ``codice`` e ``stazione_collegata_codice``
            non null.
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

    # ---- Vuoto di testa ----
    vuoto_testa: BloccoMaterialeVuoto | None = None
    if prima.codice_origine != s:
        arrivo_min = _time_to_min(prima.ora_partenza) - params.gap_min
        partenza_min = arrivo_min - params.durata_vuoto_default_min
        if partenza_min < 0:
            raise PosizionamentoImpossibileError(
                f"Vuoto di testa per catena che inizia alle "
                f"{prima.ora_partenza.isoformat()} partirebbe prima delle "
                f"00:00 (durata stimata {params.durata_vuoto_default_min}' + "
                f"gap {params.gap_min}'). Riduci durata stimata o "
                "rimanda la chiusura a 4.4.3 multi-giornata."
            )
        vuoto_testa = BloccoMaterialeVuoto(
            codice_origine=s,
            codice_destinazione=prima.codice_origine,
            ora_partenza=_min_to_time(partenza_min),
            ora_arrivo=_min_to_time(arrivo_min),
            motivo="testa",
        )

    # ---- Vuoto di coda ----
    vuoto_coda: BloccoMaterialeVuoto | None = None
    cross_notte = _attraversa_mezzanotte(ultima.ora_partenza, ultima.ora_arrivo)
    coda_oltre_mezzanotte = False
    if not cross_notte and ultima.codice_destinazione != s:
        partenza_min = _time_to_min(ultima.ora_arrivo) + params.gap_min
        arrivo_min = partenza_min + params.durata_vuoto_default_min
        if arrivo_min > 24 * 60 - 1:
            # Vuoto finirebbe dopo le 23:59 → demando a 4.4.3.
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
