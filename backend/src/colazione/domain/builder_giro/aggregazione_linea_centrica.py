"""Aggregazione TurnoConvoglio → Giro compatibile col persister
(Sprint 8.2 MR-D4).

Plan-D MR-D4: bridge fra il nuovo modello linea-centrico (output di
MR-D3 ``costruisci_turno_linea``) e il dataclass ``Giro`` legacy
consumato dal persister.

# Strategia di traduzione

Per ogni `TurnoConvoglio`:

1. Raggruppa le `GiornataServizio` per **chiave sequenza** (=
   tupla di numeri treno in ordine). Date con stessa sequenza
   diventano varianti calendariali di una stessa "giornata-tipo".
2. Ordina i gruppi per **data canonica crescente** (prima data
   alfabetica) — determinismo.
3. Per ogni gruppo crea una `GiornataGiro`:
   - ``data`` = data canonica del gruppo
   - ``dates_apply`` = tuple ordinata di tutte le date del gruppo
   - ``catena_posizionata`` = `CatenaPosizionata` sintetica con corse
     della sequenza
4. Aggrega in `Giro`:
   - ``localita_codice`` = `TurnoConvoglio.sede_codice`
   - ``giornate`` = tuple delle GiornataGiro create
   - ``chiuso`` = True se tutte le giornate finiscono in stazione
     collegata della sede (= ciclo chiuso a casa)
   - ``motivo_chiusura`` = ``'naturale'`` se chiuso, altrimenti
     ``'non_chiuso'``
   - ``km_cumulati`` = somma km del turno

# Cosa NON fa MR-D4

- Non aggrega più `TurnoConvoglio` in un singolo `Giro` (= scope
  futuro raffinamento; per ora 1 turno = 1 giro).
- Non gestisce vuoti tecnici fra giornate (= scope MR-D6).
- Non ricalcola le varianti calendariali oltre il raggruppamento
  per sequenza identica (= MR-D7 può raffinare se serve).

DB-agnostic. I `Giro` prodotti sono compatibili in lettura col
persister legacy (`persister.py`).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from colazione.domain.builder_giro.catena import Catena
from colazione.domain.builder_giro.costruisci_turno_linea import (
    GiornataServizio,
    TurnoConvoglio,
)
from colazione.domain.builder_giro.multi_giornata import (
    GiornataGiro,
    Giro,
    MotivoChiusura,
)
from colazione.domain.builder_giro.posizionamento import CatenaPosizionata

# =====================================================================
# Helpers
# =====================================================================


def _chiave_sequenza_giornata(giornata: GiornataServizio) -> tuple[Any, ...]:
    """Tupla deterministica delle corse della giornata.

    Due giornate con stessa sequenza (stessi numeri treno, stesse ore,
    stessa origine/destinazione) = stesso pattern operativo = stessa
    variante calendariale.

    Pattern allineato con `_chiave_a1_giornata` di multi_giornata.py
    (clustering A1 esistente).
    """
    return tuple(
        (
            c.numero_treno,
            c.ora_partenza,
            c.ora_arrivo,
            c.codice_origine,
            c.codice_destinazione,
        )
        for c in giornata.corse
    )


def _costruisci_catena_posizionata(
    giornata: GiornataServizio,
    *,
    sede_codice: str,
    stazione_collegata: str,
    regola_id: int | None,
) -> CatenaPosizionata:
    """Sintetizza una `CatenaPosizionata` da una `GiornataServizio`.

    Per MR-D4 baseline:
    - ``vuoto_testa``/``vuoto_coda`` = None (i vuoti tecnici sono
      scope MR-D6)
    - ``chiusa_a_localita`` = True se ``stazione_fine ==
      stazione_collegata``
    """
    catena = Catena(corse=giornata.corse)
    chiusa = giornata.stazione_fine == stazione_collegata
    return CatenaPosizionata(
        localita_codice=sede_codice,
        stazione_collegata=stazione_collegata,
        vuoto_testa=None,
        catena=catena,
        vuoto_coda=None,
        chiusa_a_localita=chiusa,
        regola_id=regola_id,
    )


def _raggruppa_per_chiave_sequenza(
    giornate: Sequence[GiornataServizio],
) -> list[tuple[tuple[Any, ...], list[GiornataServizio]]]:
    """Raggruppa giornate per chiave sequenza, ordina per data minima.

    Output: lista di (chiave, [giornate]) ordinata per data canonica
    (= prima data alfabetica del gruppo). Determinismo cross-run.
    """
    gruppi: dict[tuple[Any, ...], list[GiornataServizio]] = defaultdict(list)
    for g in giornate:
        gruppi[_chiave_sequenza_giornata(g)].append(g)

    out: list[tuple[tuple[Any, ...], list[GiornataServizio]]] = []
    for chiave, lista in gruppi.items():
        lista_ordinata = sorted(lista, key=lambda g: g.data)
        out.append((chiave, lista_ordinata))

    out.sort(key=lambda kg: kg[1][0].data)
    return out


# =====================================================================
# Algoritmo principale
# =====================================================================


def traduci_turno_in_giro(
    turno: TurnoConvoglio,
    *,
    stazione_collegata_per_sede: dict[str, str],
    regola_per_segmento: dict[str, int] | None = None,
) -> Giro | None:
    """Traduce un `TurnoConvoglio` in un `Giro` compatibile persister.

    Strategia:
    1. Raggruppa giornate del turno per chiave sequenza (= varianti).
    2. Per ogni gruppo: 1 `GiornataGiro` con `dates_apply` =
       tuple delle date del gruppo.
    3. Costruisce `Giro` con localita_codice = sede del turno,
       chiuso = tutte le giornate chiudono in stazione collegata.

    Args:
        turno: il `TurnoConvoglio` da tradurre.
        stazione_collegata_per_sede: mapping ``codice_sede →
            stazione_collegata``. Necessario per il check
            `chiusa_a_localita`.
        regola_per_segmento: opzionale, mapping ``segmento_codice →
            regola_id``. Se assente, regola_id=None (il post-pass
            backtracking dell'altro modello non agirà su questo giro).

    Returns:
        `Giro` compatibile, oppure `None` se il turno è vuoto
        (`giornate=()`).
    """
    if not turno.giornate:
        return None
    sede = turno.sede_codice
    stazione_collegata = stazione_collegata_per_sede.get(sede)
    if stazione_collegata is None:
        # Sede non mappata: defensive, ritorna None invece di crash
        return None

    regole = regola_per_segmento or {}
    regola_id = regole.get(turno.segmento_codice)

    gruppi = _raggruppa_per_chiave_sequenza(turno.giornate)

    giornate_giro: list[GiornataGiro] = []
    for _chiave, giornate_gruppo in gruppi:
        giornata_canonica = giornate_gruppo[0]
        cat_pos = _costruisci_catena_posizionata(
            giornata_canonica,
            sede_codice=sede,
            stazione_collegata=stazione_collegata,
            regola_id=regola_id,
        )
        dates_apply = tuple(g.data for g in giornate_gruppo)
        giornate_giro.append(
            GiornataGiro(
                data=giornata_canonica.data,
                catena_posizionata=cat_pos,
                dates_apply=dates_apply,
            )
        )

    chiuso = all(
        gg.catena_posizionata.chiusa_a_localita for gg in giornate_giro
    )
    motivo: MotivoChiusura = "naturale" if chiuso else "non_chiuso"

    return Giro(
        localita_codice=sede,
        giornate=tuple(giornate_giro),
        chiuso=chiuso,
        motivo_chiusura=motivo,
        km_cumulati=turno.km_totali,
    )


def traduci_turni_in_giri(
    turni: Sequence[TurnoConvoglio],
    *,
    stazione_collegata_per_sede: dict[str, str],
    regola_per_segmento: dict[str, int] | None = None,
) -> list[Giro]:
    """Wrapper multi-turno: traduce tutti i `TurnoConvoglio` validi
    in `Giro`. Skippa turni vuoti o con sede non mappata.

    Output ordinato per ``(localita_codice, giornate[0].data)`` per
    determinismo nei consumer downstream.
    """
    giri: list[Giro] = []
    for turno in turni:
        giro = traduci_turno_in_giro(
            turno,
            stazione_collegata_per_sede=stazione_collegata_per_sede,
            regola_per_segmento=regola_per_segmento,
        )
        if giro is not None:
            giri.append(giro)

    giri.sort(key=lambda g: (g.localita_codice, g.giornate[0].data))
    return giri


__all__ = [
    "traduci_turni_in_giri",
    "traduci_turno_in_giro",
]
