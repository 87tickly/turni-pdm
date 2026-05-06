"""Generazione varianti calendariali per giornata-tipo (MR-1110 Step 3 —
vedi ``docs/MR-1110-DESIGN.md`` §4.3).

Decisione utente 2026-05-06: dato un ``GiornataTipo`` (output del
sotto-MR 2 ``identifica_giornate_tipo``), raggruppa le sue istanze
(catena × data) per **sequenza di treni identica** in M
``VarianteCalendariale``. Ogni variante:

- Condivide la stessa "fase" (chiave 5-uple della giornata-tipo).
- Ha la propria sequenza concreta di corse (eventualmente molto
  diversa da altre varianti — vedi turno 1110 G6 variante 5
  ``"Si eff. 22/3, 12/4"`` con km=0 vs variante 1 ``"LV 1:5"``
  con km=131,57).
- Ha le proprie ``dates_apply`` (disgiunte da altre varianti).
- Ha etichetta calendariale parlante (chiama
  ``etichetta.genera_etichetta_parlante``).
- Ha ``prestazione_minuti`` e ``km_giornaliera`` calcolati dalla
  sequenza.

Algoritmo:

1. Per ogni ``CatenaIstanza`` della giornata-tipo, calcola
   chiave-sequenza ``tuple((numero_treno, ora_partenza_min,
   ora_arrivo_min) for corsa in catena)``.
2. Raggruppa per chiave-sequenza. Ogni gruppo è una variante.
3. Per ogni gruppo:
   - ``dates_apply`` = unione delle date delle istanze.
   - ``etichetta`` = ``genera_etichetta_parlante(dates_apply,
     periodo, festivita)``.
   - ``prestazione_minuti`` = durata totale del servizio (dal vuoto
     testa o prima corsa fino a vuoto coda o ultima corsa). Cross-
     mezzanotte: aggiunge 1440 al delta negativo.
   - ``km_giornaliera`` = somma ``km_tratta`` delle corse (i vuoti
     tecnici sono 0 km per default).

Output: ``GiornataTipoConVarianti`` con la giornata-tipo originale
+ tuple ordinata di varianti (per numero date apply desc, poi
sequenza-treni lessicografica per determinismo).

Il modulo è **DB-agnostic**.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, time

from colazione.domain.builder_giro.etichetta import genera_etichetta_parlante
from colazione.domain.builder_giro.giornata_tipo import (
    CatenaIstanza,
    GiornataTipo,
)
from colazione.domain.builder_giro.posizionamento import CatenaPosizionata

# =====================================================================
# Output dataclass
# =====================================================================


@dataclass(frozen=True)
class VarianteCalendariale:
    """Una variante calendariale di una giornata-tipo.

    Sprint MR-1110 sotto-MR Step 3. Sostituisce concettualmente
    ``aggregazione_a2.VarianteGiornata`` v1.

    Attributi:
        catena_canonica: la catena posizionata canonica della
            variante (= quella della prima istanza per data, scelta
            deterministica). Tutte le istanze del gruppo hanno
            sequenza-treni identica per costruzione, quindi la catena
            canonica è rappresentativa.
        dates_apply: frozenset di date in cui la variante si applica.
            Disgiunto dalle dates_apply delle altre varianti della
            stessa giornata-tipo.
        etichetta: stringa parlante stile PDF Trenord (vedi
            ``etichetta.genera_etichetta_parlante``). Es. ``"LV 1:5"``,
            ``"F escluso FpF ed escl. 22/3, 12/4"``,
            ``"Si eff. 22/3, 12/4"``.
        prestazione_minuti: durata totale del servizio in minuti
            (dal vuoto-testa o prima corsa fino al vuoto-coda o
            ultima corsa). Cross-mezzanotte gestito.
        km_giornaliera: somma km delle corse della catena (i vuoti
            tecnici contribuiscono 0).
    """

    catena_canonica: CatenaPosizionata
    dates_apply: frozenset[date]
    etichetta: str
    prestazione_minuti: int
    km_giornaliera: float


@dataclass(frozen=True)
class GiornataTipoConVarianti:
    """Giornata-tipo arricchita con M varianti calendariali (output
    Step 3).

    Wrapper attorno a ``GiornataTipo`` che aggiunge le varianti
    calendariali. La chiave 5-uple D1 resta invariata; le istanze
    originali sono raggruppate per sequenza-treni.

    Attributi:
        giornata: ``GiornataTipo`` originale (chiave 5-uple +
            istanze grezze).
        varianti: tuple ordinata per ``len(dates_apply) desc, etichetta
            asc`` (variante "principale" prima).
    """

    giornata: GiornataTipo
    varianti: tuple[VarianteCalendariale, ...]

    # Forwarder per leggibilità chiamante.
    @property
    def materiale_tipo_codice(self) -> str:
        return self.giornata.materiale_tipo_codice

    @property
    def localita_codice(self) -> str:
        return self.giornata.localita_codice

    @property
    def staz_inizio(self) -> str:
        return self.giornata.staz_inizio

    @property
    def staz_fine(self) -> str:
        return self.giornata.staz_fine

    @property
    def codice_servizio_dominante(self) -> str | None:
        return self.giornata.codice_servizio_dominante


# =====================================================================
# Helpers privati
# =====================================================================


def _time_to_min(t: time) -> int:
    return t.hour * 60 + t.minute


def _chiave_sequenza(
    cat_pos: CatenaPosizionata,
) -> tuple[tuple[str, int, int], ...]:
    """Chiave-sequenza per raggruppare istanze in varianti.

    = tuple ordinata di ``(numero_treno, ora_partenza_min,
    ora_arrivo_min)`` per ogni corsa della catena.

    I vuoti tecnici testa/coda **NON** sono inclusi nella chiave: sono
    inferenze del builder (posizionamento sede), non parte della
    sequenza commerciale che identifica la variante.
    """
    return tuple(
        (
            str(getattr(c, "numero_treno", "") or ""),
            _time_to_min(c.ora_partenza),
            _time_to_min(c.ora_arrivo),
        )
        for c in cat_pos.catena.corse
    )


def _km_catena(cat_pos: CatenaPosizionata) -> float:
    """Somma km_tratta delle corse della catena (vuoti = 0)."""
    total = 0.0
    for c in cat_pos.catena.corse:
        km = getattr(c, "km_tratta", None)
        if km is not None:
            total += float(km)
    return total


def _prestazione_minuti(cat_pos: CatenaPosizionata) -> int:
    """Durata totale servizio in minuti.

    Da ``vuoto_testa.ora_partenza`` (o prima corsa se nessun vuoto)
    a ``vuoto_coda.ora_arrivo`` (o ultima corsa). Cross-mezzanotte:
    se l'ora di arrivo finale è < ora di partenza iniziale, aggiunge
    1440 minuti (1 giorno).
    """
    if cat_pos.vuoto_testa is not None:
        partenza_min = _time_to_min(cat_pos.vuoto_testa.ora_partenza)
    else:
        partenza_min = _time_to_min(cat_pos.catena.corse[0].ora_partenza)

    if cat_pos.vuoto_coda is not None:
        arrivo_min = _time_to_min(cat_pos.vuoto_coda.ora_arrivo)
    else:
        arrivo_min = _time_to_min(cat_pos.catena.corse[-1].ora_arrivo)

    delta = arrivo_min - partenza_min
    if delta < 0:
        delta += 1440  # cross-mezzanotte
    return delta


# =====================================================================
# API pubblica
# =====================================================================


def genera_varianti_calendariali(
    giornata: GiornataTipo,
    festivita: frozenset[date],
    periodo: tuple[date, date],
) -> GiornataTipoConVarianti:
    """Raggruppa le istanze della giornata-tipo in varianti
    calendariali per sequenza-treni identica.

    Implementa lo Step 3 della pipeline MR-1110 (vedi
    ``docs/MR-1110-DESIGN.md`` §4.3).

    Args:
        giornata: ``GiornataTipo`` con istanze grezze.
        festivita: festività rilevanti per il periodo (vedi
            ``etichetta.genera_etichetta_parlante``).
        periodo: ``(inizio, fine)`` validità programma (D5).

    Returns:
        ``GiornataTipoConVarianti`` con la giornata-tipo originale +
        tuple delle varianti generate, ordinate per
        ``len(dates_apply) desc, etichetta asc``.

    Esempi:
        Giornata-tipo con istanze tutte stessa sequenza → 1 sola
        variante.
    """
    # Raggruppa le istanze per chiave-sequenza.
    per_sequenza: dict[
        tuple[tuple[str, int, int], ...], list[CatenaIstanza]
    ] = {}
    for ist in giornata.istanze:
        chiave = _chiave_sequenza(ist.catena_posizionata)
        per_sequenza.setdefault(chiave, []).append(ist)

    varianti: list[VarianteCalendariale] = []
    for _chiave, ist_gruppo in per_sequenza.items():
        # Ordina per data — la prima istanza è la canonica
        # (deterministico).
        ist_ordinate = sorted(ist_gruppo, key=lambda i: i.data)
        canonica = ist_ordinate[0].catena_posizionata

        dates_apply = frozenset(i.data for i in ist_ordinate)
        etichetta = genera_etichetta_parlante(
            dates_apply, periodo, festivita
        )
        prestazione = _prestazione_minuti(canonica)
        km = _km_catena(canonica)

        varianti.append(
            VarianteCalendariale(
                catena_canonica=canonica,
                dates_apply=dates_apply,
                etichetta=etichetta,
                prestazione_minuti=prestazione,
                km_giornaliera=km,
            )
        )

    # Ordinamento deterministico: numero date desc, etichetta asc.
    varianti.sort(key=lambda v: (-len(v.dates_apply), v.etichetta))

    return GiornataTipoConVarianti(
        giornata=giornata,
        varianti=tuple(varianti),
    )


def genera_varianti_per_lista(
    giornate: list[GiornataTipo],
    festivita: frozenset[date],
    periodo: tuple[date, date],
) -> list[GiornataTipoConVarianti]:
    """Convenience: applica ``genera_varianti_calendariali`` a una lista
    di giornate-tipo.

    Output preserva l'ordine dell'input.
    """
    return [
        genera_varianti_calendariali(g, festivita, periodo)
        for g in giornate
    ]


# Counter è importato ma non usato direttamente nel modulo (utile per
# eventuali estensioni future tipo "variante più frequente"); manteniamo
# l'import così è disponibile se il modulo viene esteso. Ruff potrebbe
# segnalarlo: lo mascheriamo qui sotto.
_ = Counter  # noqa: F841 — riservato per estensioni
