"""Closure post-pass per giri aperti (Sprint 8.1 MR-A2).

Funzione pura ``chiudi_giri_aperti`` che opera DOPO
``costruisci_giri_multigiornata`` su una sequenza di ``Giro``. Per
ogni giro con ``motivo_chiusura == 'non_chiuso'`` (legacy: ciclo
aperto persistito senza tentativo di chiusura), tenta una chiusura
attiva con un **vuoto di rientro intra-area metropolitana**:

- Se l'ultima stazione del giro è già in ``whitelist_sede`` (caso
  tipico: ``costruisci_giri_multigiornata`` ha aggiunto un
  ``vuoto_coda`` di rientro upstream, oppure l'ultima corsa
  commerciale arriva direttamente "a casa") → marca
  ``motivo_chiusura='naturale'`` (MR-B1 entry 254: corregge il bug
  upstream che lasciava 'non_chiuso' nonostante il giro fosse
  effettivamente chiuso in sede).
- Altrimenti, se l'ultima stazione condivide un'area metropolitana
  con almeno una stazione della whitelist sede → genera
  ``BloccoMaterialeVuoto`` di coda, marca ``chiuso=True`` e
  ``motivo_chiusura='chiuso_con_vuoto'``.
- Altrimenti (es. arrivo a Tirano con sede FIO) → marca
  ``motivo_chiusura='ciclo_aperto_irrisolto'`` (decisione utente Q2=b
  2026-05-08: persistere ma marcare per intervento manuale).

**Strangler pattern**: il post-pass è opt-in via
``programma_materiale.builder_mode == 'esplorativo'`` (MR-A1
foundation). Programmi con ``builder_mode='rigido'`` mantengono il
comportamento legacy invariato.

**Scope MR-A2**: chiusura via vuoto **intra-area metropolitana**
soltanto. Riusa l'infrastruttura `area_metropolitana` /
`area_stazione_membri` (migration 0040, MR-E entry 236) già usata da
``catena.py`` per rilassare la continuità geografica. Non si tenta
chiusura su distanze arbitrarie (es. Alessandria → Milano = 90 km
fuori area Milano): quella richiede un grafo di tratti vuoti che è
scope MR-A4 / MR-A5.

**Risultato atteso sui sintomi reali (programma 17)**:
- Giri che terminano in stazioni Milano (Centrale, Cadorna, Garibaldi)
  con sede FIO whitelist Certosa → chiusi con vuoto di rientro
  intra-area (~10 min default, configurabile per AreaMetropolitana).
- Giri come G-FIO-026 (Alessandria → Milano Certosa, 93 km, fuori area
  Milano) → marker ``ciclo_aperto_irrisolto``: l'utente lo vede in
  rosso nell'UI invece di un giro silenziosamente sbagliato.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import time
from typing import cast

from colazione.domain.builder_giro.multi_giornata import (
    GiornataGiro,
    Giro,
)
from colazione.domain.builder_giro.posizionamento import (
    BloccoMaterialeVuoto,
    CatenaPosizionata,
)

# =====================================================================
# Parametri
# =====================================================================


@dataclass(frozen=True)
class ParamChiusuraPost:
    """Parametri per il closure post-pass (MR-A2).

    Tutti i campi sono dati di input al motore esplorativo: il modulo
    resta DB-agnostic come gli altri di ``builder_giro``. Il caller
    (``builder.py``) carica i mapping dal DB una sola volta per run e
    li passa a ``chiudi_giri_aperti``.

    Attributi:
        whitelist_sede: codici stazione "casa" della sede manutentiva
            del programma (set vuoto = nessuna whitelist, post-pass
            no-op).
        area_per_stazione: mapping ``stazione_codice → area_id`` per
            ogni stazione che appartiene a un'area metropolitana
            dell'azienda (popolato dalla join
            ``area_stazione_membri × area_metropolitana`` in
            ``builder.py``). Stazioni fuori da qualsiasi area non sono
            in questo dict.
        gap_vuoto_rientro_min: durata in minuti del vuoto di rientro
            generato. Default 10 (coerente con
            ``AreaMetropolitana.gap_intra_area_min`` server_default
            tipico Milano). Configurabile per programma in MR-A8.
    """

    whitelist_sede: frozenset[str]
    area_per_stazione: dict[str, int] = field(default_factory=dict)
    gap_vuoto_rientro_min: int = 10


# =====================================================================
# Helpers
# =====================================================================


def _ultima_stazione_giro(giro: Giro) -> str | None:
    """Ritorna il codice stazione di arrivo finale del giro.

    Priorità: ``vuoto_coda.codice_destinazione`` se presente
    (caso defensive: già chiuso con vuoto in upstream); altrimenti
    ``catena.corse[-1].codice_destinazione``. ``None`` se il giro non
    ha giornate o l'ultima giornata è vuota (non dovrebbe accadere,
    ``costruisci_giri_multigiornata`` garantisce almeno 1 corsa per
    giornata).
    """
    if not giro.giornate:
        return None
    ultima_giornata = giro.giornate[-1]
    cat_pos = ultima_giornata.catena_posizionata
    if cat_pos.vuoto_coda is not None:
        return cat_pos.vuoto_coda.codice_destinazione
    if not cat_pos.catena.corse:
        return None
    # Catena.corse è tipizzato tuple[Any, ...] per duck typing
    # (vedi catena.py:_CorsaLike Protocol). Cast esplicito.
    return cast(str, cat_pos.catena.corse[-1].codice_destinazione)


def _ultima_ora_arrivo(giro: Giro) -> time | None:
    """Ritorna l'ora di arrivo dell'ultimo blocco del giro (corsa o
    vuoto coda esistente).
    """
    if not giro.giornate:
        return None
    ultima_giornata = giro.giornate[-1]
    cat_pos = ultima_giornata.catena_posizionata
    if cat_pos.vuoto_coda is not None:
        return cat_pos.vuoto_coda.ora_arrivo
    if not cat_pos.catena.corse:
        return None
    return cast(time, cat_pos.catena.corse[-1].ora_arrivo)


def _trova_target_intra_area(
    staz_arrivo: str,
    whitelist_sede: frozenset[str],
    area_per_stazione: dict[str, int],
) -> str | None:
    """Cerca una stazione della whitelist sede che condivida un'area
    metropolitana con ``staz_arrivo``.

    Ritorna il codice della prima stazione whitelist trovata in stessa
    area, o ``None`` se nessuna intersezione (= chiusura impossibile
    per questo MR, marker ``ciclo_aperto_irrisolto``).

    Determinismo: se ci sono più stazioni whitelist nell'area, ritorna
    la prima in ordine alfabetico per garantire output stabile fra
    run.
    """
    area_arrivo = area_per_stazione.get(staz_arrivo)
    if area_arrivo is None:
        return None
    candidati = sorted(
        s
        for s in whitelist_sede
        if area_per_stazione.get(s) == area_arrivo
    )
    return candidati[0] if candidati else None


def _aggiungi_minuti(t: time, delta_min: int) -> tuple[time, bool]:
    """Somma ``delta_min`` minuti a ``t``. Ritorna ``(time_risultante,
    cross_notte)``. ``cross_notte=True`` se la somma sfora la
    mezzanotte.
    """
    totale_min = t.hour * 60 + t.minute + delta_min
    cross_notte = totale_min >= 1440
    totale_min %= 1440
    return time(totale_min // 60, totale_min % 60), cross_notte


# =====================================================================
# Algoritmo principale
# =====================================================================


def chiudi_giri_aperti(
    giri: Sequence[Giro],
    params: ParamChiusuraPost,
) -> list[Giro]:
    """Post-pass di chiusura attiva sui giri aperti.

    Per ogni giro con ``motivo_chiusura == 'non_chiuso'``:

    1. Calcola ``staz_arrivo`` (ultima stazione del giro).
    2. Se ``staz_arrivo`` è già in ``whitelist_sede``: defensive
       passa-through (situazione anomala, motivo_chiusura sarebbe
       dovuto essere 'naturale'; non sovrascriviamo per non mascherare
       il bug a monte).
    3. Cerca una stazione whitelist nella stessa area metropolitana
       di ``staz_arrivo`` (``_trova_target_intra_area``).
    4. Se trovata → genera ``BloccoMaterialeVuoto`` di coda
       (``staz_arrivo → target`` con durata
       ``gap_vuoto_rientro_min``) e ricostruisce l'ultima giornata
       con il vuoto coda. Marca ``chiuso=True``,
       ``motivo_chiusura='chiuso_con_vuoto'``.
    5. Se non trovata → solo aggiorna ``motivo_chiusura`` a
       ``'ciclo_aperto_irrisolto'`` (giro resta aperto, marker
       visibile per intervento manuale).

    Tutti gli altri giri (``naturale`` / ``max_giornate`` / ``km_cap``
    / ``sotto_min``) passano-through invariati.

    **Idempotente**: se chiamata su una lista che ha già subito il
    post-pass (motivi ``chiuso_con_vuoto`` o ``ciclo_aperto_irrisolto``
    già presenti), passa-through invariato.

    **Funzione pura**: input frozen dataclass, output nuova lista
    (``dataclasses.replace`` per ogni mutazione necessaria).
    """
    risultato: list[Giro] = []
    for giro in giri:
        if giro.motivo_chiusura != "non_chiuso":
            risultato.append(giro)
            continue

        staz_arrivo = _ultima_stazione_giro(giro)
        if staz_arrivo is None:
            # Defensive: giro senza giornate o senza corse — non
            # dovrebbe esistere. Marker per visibilità.
            risultato.append(
                dataclasses.replace(
                    giro, motivo_chiusura="ciclo_aperto_irrisolto"
                )
            )
            continue

        if staz_arrivo in params.whitelist_sede:
            # Sprint 8.1 MR-B1 (entry 254): il giro arriva in
            # whitelist sede — tipicamente perché
            # `costruisci_giri_multigiornata` ha già aggiunto un
            # `vuoto_coda` di rientro upstream, oppure l'ultima corsa
            # commerciale arriva direttamente "a casa". Il marker
            # upstream `'non_chiuso'` è un'anomalia da indagare a
            # parte (probabile fuori-stato del builder rispetto al
            # vuoto coda generato), MA il giro È DI FATTO CHIUSO in
            # stazione di sede. Marchiamolo `'naturale'` invece di
            # passthrough: l'utente vede la verità operativa, non
            # un falso "NON CHIUSO" generato dal bug a monte.
            risultato.append(
                dataclasses.replace(
                    giro, chiuso=True, motivo_chiusura="naturale"
                )
            )
            continue

        target = _trova_target_intra_area(
            staz_arrivo,
            params.whitelist_sede,
            params.area_per_stazione,
        )

        if target is None:
            risultato.append(
                dataclasses.replace(
                    giro, motivo_chiusura="ciclo_aperto_irrisolto"
                )
            )
            continue

        ora_partenza_vuoto = _ultima_ora_arrivo(giro)
        if ora_partenza_vuoto is None:
            risultato.append(
                dataclasses.replace(
                    giro, motivo_chiusura="ciclo_aperto_irrisolto"
                )
            )
            continue

        ora_arrivo_vuoto, _cross_notte = _aggiungi_minuti(
            ora_partenza_vuoto, params.gap_vuoto_rientro_min
        )
        vuoto_coda = BloccoMaterialeVuoto(
            codice_origine=staz_arrivo,
            codice_destinazione=target,
            ora_partenza=ora_partenza_vuoto,
            ora_arrivo=ora_arrivo_vuoto,
            motivo="coda",
            cross_notte_giorno_precedente=False,
        )

        ultima_giornata = giro.giornate[-1]
        cat_pos_aggiornata: CatenaPosizionata = dataclasses.replace(
            ultima_giornata.catena_posizionata,
            vuoto_coda=vuoto_coda,
            chiusa_a_localita=True,
        )
        giornata_aggiornata: GiornataGiro = dataclasses.replace(
            ultima_giornata, catena_posizionata=cat_pos_aggiornata
        )
        giornate_aggiornate = (
            *giro.giornate[:-1],
            giornata_aggiornata,
        )
        risultato.append(
            dataclasses.replace(
                giro,
                giornate=giornate_aggiornate,
                chiuso=True,
                motivo_chiusura="chiuso_con_vuoto",
            )
        )

    return risultato


__all__ = ["ParamChiusuraPost", "chiudi_giri_aperti"]
