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
from datetime import time
from typing import Any

from colazione.domain.builder_giro.catena import Catena
from colazione.domain.builder_giro.costruisci_turno_linea import (
    GiornataServizio,
    TurnoConvoglio,
)
from colazione.domain.builder_giro.durata_vuoto import (
    DURATA_VUOTO_DEFAULT_MIN,
    calcola_durata_vuoto_min,
)
from colazione.domain.builder_giro.multi_giornata import (
    GiornataGiro,
    Giro,
    MotivoChiusura,
)
from colazione.domain.builder_giro.posizionamento import (
    BloccoMaterialeVuoto,
    CatenaPosizionata,
)

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


def _costruisci_vuoto_rientro_target(
    giornata: GiornataServizio,
    stazione_target: str,
    *,
    durata_min: int,
) -> BloccoMaterialeVuoto | None:
    """Sprint 8.2 MR-D6 + Sprint 8.3 MR-S2: costruisce un blocco vuoto
    di rientro dall'ultima stazione operativa della giornata alla
    stazione target (= sede regola, dato utente).

    Necessario per chiudere i giri quando ``sede_target !=
    sede_operativa`` (= MR-D2 ottimizzazione geometrica ha scelto
    sede diversa dalla regola dichiarata). Pattern memoria
    ``project_rientro_sede_9XXXX``: numerazione vuoti =
    ``9{numero_treno_commerciale_di_confine}``.

    **Sprint 8.3 MR-S2 (chiude S2 HIGH critica entry 284 + S1 HIGH
    critica piano entry 285)**: la durata del vuoto NON è più hardcoded
    a 60 min — il chiamante la calcola via
    ``durata_vuoto.calcola_durata_vuoto_min`` con strategia 4-livelli
    (hit diretto → speculare → baseline geometrico → 60 fallback) e
    la passa via parametro ``durata_min``.

    Heuristic:
    - ``ora_partenza`` = ora_arrivo dell'ultima corsa.
    - ``ora_arrivo`` = ora_partenza + ``durata_min``.
    - ``motivo='coda'`` per tracciabilità nei metadata.
    - ``cross_notte_giorno_precedente=False`` (= rientro nello
      stesso giorno operativo, non valido per "uscita serale K-1").

    Args:
        giornata: ultima giornata del turno.
        stazione_target: codice stazione collegata alla sede target.
        durata_min: durata stimata del vuoto rientro in minuti
            (calcolata dal chiamante con dati reali del programma o
            fallback geometrico/default).

    Returns:
        ``BloccoMaterialeVuoto`` se serve rientro
        (``stazione_fine != stazione_target``), ``None`` altrimenti.
    """
    if not giornata.corse:
        return None
    if giornata.stazione_fine == stazione_target:
        # Già a target, no rientro necessario
        return None
    ultima = giornata.corse[-1]
    arrivo_min = ultima.ora_arrivo.hour * 60 + ultima.ora_arrivo.minute
    fine_rientro_min = arrivo_min + durata_min
    # Cross-mezzanotte: cap a 23:59 per non finire oltre il giorno
    # solare. Il "giro" potrebbe quindi non chiudere se il rientro
    # finisce dopo mezzanotte. Lasciamo `chiusa_a_localita` decisa
    # dal chiamante.
    if fine_rientro_min >= 24 * 60:
        fine_rientro_min = 24 * 60 - 1
    return BloccoMaterialeVuoto(
        codice_origine=giornata.stazione_fine,
        codice_destinazione=stazione_target,
        ora_partenza=ultima.ora_arrivo,
        ora_arrivo=time(fine_rientro_min // 60, fine_rientro_min % 60),
        motivo="coda",
        cross_notte_giorno_precedente=False,
    )


def _costruisci_catena_posizionata(
    giornata: GiornataServizio,
    *,
    sede_codice: str,
    stazione_collegata: str,
    regola_id: int | None,
    aggiungi_vuoto_rientro_a: str | None = None,
    durata_min_vuoto_rientro: int = DURATA_VUOTO_DEFAULT_MIN,
) -> CatenaPosizionata:
    """Sintetizza una `CatenaPosizionata` da una `GiornataServizio`.

    Per MR-D4 baseline:
    - ``vuoto_testa``/``vuoto_coda`` = None (i vuoti tecnici sono
      scope MR-D6)
    - ``chiusa_a_localita`` = True se ``stazione_fine ==
      stazione_collegata``

    **Sprint 8.2 MR-D6 (entry 279)**: se ``aggiungi_vuoto_rientro_a``
    è valorizzato (= stazione target diversa da sede operativa),
    costruisce un ``BloccoMaterialeVuoto`` di coda da
    ``giornata.stazione_fine`` a ``aggiungi_vuoto_rientro_a`` e
    setta ``chiusa_a_localita=True`` (giro chiude a target via
    vuoto coda).

    **Sprint 8.3 MR-S2**: la durata del vuoto rientro è ora calcolata
    dal chiamante via ``calcola_durata_vuoto_min`` (data-driven con
    fallback geometrico) e passata via ``durata_min_vuoto_rientro``.
    Default ``DURATA_VUOTO_DEFAULT_MIN`` (= 60) preserva backward-compat
    quando il chiamante non passa nulla.
    """
    catena = Catena(corse=giornata.corse)
    vuoto_coda: BloccoMaterialeVuoto | None = None
    if aggiungi_vuoto_rientro_a is not None:
        vuoto_coda = _costruisci_vuoto_rientro_target(
            giornata,
            aggiungi_vuoto_rientro_a,
            durata_min=durata_min_vuoto_rientro,
        )
        # Se serve rientro E il vuoto è stato costruito, il giro
        # chiude a target via vuoto coda.
        if vuoto_coda is not None:
            chiusa = True
        else:
            # `_costruisci_vuoto_rientro_target` ha ritornato None →
            # già a target, chiusa per stazione_fine == target.
            chiusa = giornata.stazione_fine == aggiungi_vuoto_rientro_a
    else:
        chiusa = giornata.stazione_fine == stazione_collegata
    return CatenaPosizionata(
        localita_codice=sede_codice,
        stazione_collegata=stazione_collegata,
        vuoto_testa=None,
        catena=catena,
        vuoto_coda=vuoto_coda,
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
    sede_target_per_regola: dict[int, str] | None = None,
    durata_vuoto_per_coppia: dict[tuple[str, str], int] | None = None,
    baseline_durata_per_stazione: dict[str, int] | None = None,
) -> Giro | None:
    """Traduce un `TurnoConvoglio` in un `Giro` compatibile persister.

    Strategia:
    1. Raggruppa giornate del turno per chiave sequenza (= varianti).
    2. Per ogni gruppo: 1 `GiornataGiro` con `dates_apply` =
       tuple delle date del gruppo.
    3. Costruisce `Giro` con sede target dichiarata dalla regola
       (Sprint 8.2 MR-D5h-DUAL entry 276) e ``sede_operativa_codice``
       = sede scelta da MR-D2 ottimizzazione geometrica.

    Args:
        turno: il `TurnoConvoglio` da tradurre.
        stazione_collegata_per_sede: mapping ``codice_sede →
            stazione_collegata``. Necessario per il check
            `chiusa_a_localita`.
        regola_per_segmento: opzionale, mapping ``segmento_codice →
            regola_id``. Se assente, regola_id=None (il post-pass
            backtracking dell'altro modello non agirà su questo giro).
        sede_target_per_regola: Sprint 8.2 MR-D5h-DUAL — opzionale,
            mapping ``regola_id → sede_target_codice``. Se presente
            E la regola ha sede_target, ``Giro.localita_codice``
            diventa la sede TARGET (regola.localita_codice, dato
            utente) e ``Giro.sede_operativa_codice`` diventa la sede
            geometrica (turno.sede_codice). Se assente o regola
            non in mapping, mantiene comportamento legacy
            (``localita_codice = turno.sede_codice``,
            ``sede_operativa_codice = None``).
        durata_vuoto_per_coppia: Sprint 8.3 MR-S2 — opzionale, mapping
            ``(origine, destinazione) → mediana_durata_min`` calcolato
            sui dati reali del programma. Usato per stimare durata
            vuoto rientro target invece del 60 hardcoded.
        baseline_durata_per_stazione: Sprint 8.3 MR-S2 — opzionale,
            mapping ``stazione → mediana_durata_min`` per fallback
            geometrico quando la coppia non è in
            ``durata_vuoto_per_coppia``.

    Returns:
        `Giro` compatibile, oppure `None` se il turno è vuoto
        (`giornate=()`).
    """
    if not turno.giornate:
        return None
    sede_operativa = turno.sede_codice
    stazione_collegata = stazione_collegata_per_sede.get(sede_operativa)
    if stazione_collegata is None:
        # Sede non mappata: defensive, ritorna None invece di crash
        return None

    regole = regola_per_segmento or {}
    regola_id = regole.get(turno.segmento_codice)
    if regola_id is None:
        # Sprint 8.2 MR-D5f S2 follow-up: il chiamante (builder.py)
        # popola ``regola_per_segmento`` solo con chiavi
        # ``{linea}_completo`` (1 sola variante per linea). MR-D1
        # produce anche ``{linea}_tronco_X`` e ``{linea}_isolato_X_Y``
        # per linee multi-tronco. Senza fallback, tutti i giri di
        # tronchi finiscono con regola_id=None → scartati downstream
        # da `_traduce_e_filtra_giri_linea_centrica`. Risolto via
        # estrazione prefisso linea (split sul primo '_'): per ogni
        # segmento `_tronco_X`/`_isolato_X_Y` ricaviamo `{linea}` e
        # ricado su ``{linea}_completo`` come "regola madre".
        prefisso_linea = turno.segmento_codice.split("_", 1)[0]
        regola_id = regole.get(f"{prefisso_linea}_completo")

    # Sprint 8.2 MR-D5h-DUAL entry 276 — risoluzione sede target/operativa.
    sede_target_map = sede_target_per_regola or {}
    sede_target = (
        sede_target_map.get(regola_id) if regola_id is not None else None
    )
    if sede_target is None:
        # Comportamento legacy / fallback: target = operativa, niente
        # divergenza segnalabile.
        localita_codice_giro = sede_operativa
        sede_operativa_codice_giro: str | None = None
    else:
        localita_codice_giro = sede_target
        # Espone sede_operativa solo se DIFFERISCE da target (= MR-D2
        # ha scelto sede diversa dal dato utente).
        sede_operativa_codice_giro = (
            sede_operativa if sede_operativa != sede_target else None
        )

    # Sprint 8.2 MR-D6 (entry 279) — vuoto rientro target.
    # Calcola la stazione TARGET (= stazione collegata della sede regola).
    # Se sede_target != sede_operativa, l'ultima giornata del giro
    # avrà un `vuoto_coda` da capolinea operativo a stazione target
    # per chiudere il giro alla sede dichiarata dall'utente.
    stazione_target_codice: str | None = None
    if sede_target is not None and sede_target != sede_operativa:
        stazione_target_codice = stazione_collegata_per_sede.get(sede_target)

    gruppi = _raggruppa_per_chiave_sequenza(turno.giornate)
    n_giornate = len(gruppi)

    giornate_giro: list[GiornataGiro] = []
    for idx, (_chiave, giornate_gruppo) in enumerate(gruppi):
        giornata_canonica = giornate_gruppo[0]
        # MR-D6: aggiungi vuoto rientro SOLO sull'ULTIMA giornata
        # (= il convoglio rientra a sede target a fine giro, non
        # inter-giornata).
        is_ultima = idx == n_giornate - 1
        aggiungi_vuoto = (
            stazione_target_codice if is_ultima else None
        )
        # MR-S2: calcola durata vuoto data-driven via lookup
        # (hit diretto → speculare → baseline geometrico → 60).
        # Se aggiungi_vuoto è None, il param non viene usato dal
        # sub-helper ma lo passiamo comunque per signature-compat.
        if aggiungi_vuoto is not None:
            durata_min_vuoto = calcola_durata_vuoto_min(
                giornata_canonica.stazione_fine,
                aggiungi_vuoto,
                durata_lookup=durata_vuoto_per_coppia,
                baseline_per_stazione=baseline_durata_per_stazione,
            )
        else:
            durata_min_vuoto = DURATA_VUOTO_DEFAULT_MIN
        cat_pos = _costruisci_catena_posizionata(
            giornata_canonica,
            sede_codice=sede_operativa,
            stazione_collegata=stazione_collegata,
            regola_id=regola_id,
            aggiungi_vuoto_rientro_a=aggiungi_vuoto,
            durata_min_vuoto_rientro=durata_min_vuoto,
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
        localita_codice=localita_codice_giro,
        giornate=tuple(giornate_giro),
        chiuso=chiuso,
        motivo_chiusura=motivo,
        km_cumulati=turno.km_totali,
        sede_operativa_codice=sede_operativa_codice_giro,
    )


def traduci_turni_in_giri(
    turni: Sequence[TurnoConvoglio],
    *,
    stazione_collegata_per_sede: dict[str, str],
    regola_per_segmento: dict[str, int] | None = None,
    sede_target_per_regola: dict[int, str] | None = None,
    durata_vuoto_per_coppia: dict[tuple[str, str], int] | None = None,
    baseline_durata_per_stazione: dict[str, int] | None = None,
) -> list[Giro]:
    """Wrapper multi-turno: traduce tutti i `TurnoConvoglio` validi
    in `Giro`. Skippa turni vuoti o con sede non mappata.

    Output ordinato per ``(localita_codice, giornate[0].data)`` per
    determinismo nei consumer downstream. ``localita_codice`` post
    MR-D5h-DUAL può essere la sede TARGET (da regola) invece della
    sede operativa: il sort cambia coerentemente.

    Sprint 8.3 MR-S2: i 2 nuovi parametri ``durata_vuoto_per_coppia``
    e ``baseline_durata_per_stazione`` propagano i lookup data-driven
    a ``traduci_turno_in_giro`` per stima vuoto rientro target reale.
    """
    giri: list[Giro] = []
    for turno in turni:
        giro = traduci_turno_in_giro(
            turno,
            stazione_collegata_per_sede=stazione_collegata_per_sede,
            regola_per_segmento=regola_per_segmento,
            sede_target_per_regola=sede_target_per_regola,
            durata_vuoto_per_coppia=durata_vuoto_per_coppia,
            baseline_durata_per_stazione=baseline_durata_per_stazione,
        )
        if giro is not None:
            giri.append(giro)

    giri.sort(key=lambda g: (g.localita_codice, g.giornate[0].data))
    return giri


__all__ = [
    "traduci_turni_in_giri",
    "traduci_turno_in_giro",
]
