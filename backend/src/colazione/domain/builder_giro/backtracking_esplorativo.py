"""Backtracking esplorativo per estendere giri corti (Sprint 8.1 MR-A4).

Funzione pura ``tenta_estensione_giri_corti`` che opera DOPO
``costruisci_giri_multigiornata``. Per ogni giro con
``motivo_chiusura in {'sotto_min', 'non_chiuso'}`` E
``len(giornate) < n_giornate_min``, applica un **beam search con
backtracking limitato** per cercare estensioni cross-notte che il
greedy legacy ha mancato.

**Decisione architettura V4 Pro 2026-05-08**: V4 Pro ha dissentito dalla
proposta NINO iniziale ``beam=3 / depth=1`` come "troppo debole per
150 corse non coperte + redistribuzione giri 1g". Decisione utente:
seguire V4 Pro = backtracking PROFONDO + parametrizzato.

**Strangler pattern**: opt-in via ``programma.builder_mode == 'esplorativo'``.
Programmi con ``'rigido'`` mantengono il comportamento legacy
(``costruisci_giri_multigiornata`` greedy stretto + Fix C2 troncamento).

**Algoritmo**:

1. Filtra i giri "corti" (sotto ``n_giornate_min``, motivi che indicano
   chiusura subottimale).
2. Per ogni giro corto: ricostruisce lo stato (giornate visitate,
   km cumulati) e lancia ``_estendi_ricorsivo`` con beam search.
3. Beam search: per ogni giornata in coda, considera **top-k
   continuazioni** (default 8) ordinate per ora di partenza crescente
   (deterministico). Pruning: scarta branch che sforerebbero
   ``km_max_ciclo`` oltre il 10% di tolleranza.
4. Depth dinamico: ``depth_max = (n_giornate_min - len(giornate)) +
   depth_max_oltre_min``, capped da ``n_giornate_max`` (no overflow).
5. Score di ogni stato finale raggiunto: bilanciamento km coperti +
   n_corse coperte + bonus chiusura geografica + bonus raggiungimento
   ``n_giornate_min``. Sceglie il migliore.
6. Se nessun branch migliora il giro originale, lo lascia invariato.

**Logging**: ritorna ``StatBacktracking`` con metriche per tuning
empirico in MR-A7 (giri processati, estesi, branches esplorati,
depth media raggiunta).

**Costo computazionale**: nel worst case ``beam_k^depth_max`` nodi
per giro corto. Default ``beam=8, depth=4`` → 4096 nodi per giro,
~10ms in Python puro. Su 50 giri corti per programma = ~500ms.
Pruning km_cap riduce ulteriormente.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import cast

from colazione.domain.builder_giro.multi_giornata import (
    GiornataGiro,
    Giro,
    MotivoChiusura,
    ParamMultiGiornata,
    _km_giornata,
    _minuti_diurni_sosta_intergiornata,
    _pct_servizio_catena,
    _time_to_min,
)
from colazione.domain.builder_giro.posizionamento import CatenaPosizionata

# =====================================================================
# Parametri + Stato
# =====================================================================


@dataclass(frozen=True)
class ParamBacktracking:
    """Parametri del backtracking esplorativo.

    Tutti i valori scelti seguendo il dissenso V4 Pro 2026-05-08
    rispetto alla proposta iniziale ``beam=3, depth=1`` di NINO. V4 Pro:
    "troppo debole per 150 corse non coperte + redistribuzione giri 1g".

    Attributi:
        beam_k: numero di continuazioni candidate considerate per
            giornata. Default 8 (vs 3 originale = 2.7x). Configurabile
            per programma in MR-A8 se i numeri di MR-A7 lo richiedono.
        depth_max_oltre_min: oltre il gap a ``n_giornate_min``, quanti
            step in più di backtracking concedere. Default 2 (giro
            corto a 2 giornate, n_min=4 → depth=4 step). Limitato da
            ``n_giornate_max`` (hard cap).
        tolleranza_km_cap_pct: % di tolleranza sul km_max_ciclo per
            scartare branch sub-ottimali. Default 10% (es. cap=5000 →
            branch oltre 5500 scartato). Più stretto = meno esplorazione,
            più rapido. Più largo = più ramificazione.
        log_level: ``'silent'`` | ``'info'`` | ``'debug'``. Default
            ``'info'`` (statistiche aggregate). ``'debug'`` per tuning
            empirico (per-giro branches).
    """

    beam_k: int = 8
    depth_max_oltre_min: int = 2
    tolleranza_km_cap_pct: float = 10.0
    log_level: str = "info"
    # MR-A4-bis (entry 247) HIGH-1 fix: hard cap sui nodi visitati
    # nell'intero run del backtracking. Previene esplosione 8^11 worst
    # case su programmi con n_giornate_max alto. Default 100k = ~1s
    # CPU Python su nodo medio. Quando raggiunto, abort + warning.
    n_branches_max: int = 100_000
    # MR-A4-bis (entry 247) MED-NINO-1 fix: pesi score parametrizzati.
    # MR-B2 (entry 255): peso_chiude_sede 50 → 500 dopo verifica empirica
    # prog 17 produzione. Razionale: per giri 6g km cumulati ~1800 → score
    # km = 900 (peso_km=0.5). Il vecchio peso_chiude_sede=50 era
    # sproporzionato (18:1 vs km), il backtracking sceglieva spesso il
    # branch con più km invece del branch che chiude in sede. Con 500,
    # ratio chiusura:km ≈ 0.55 — confrontabile, lo score privilegia
    # chiusura quando entrambi sono "buoni".
    peso_km: float = 0.5
    peso_corse: float = 1.0
    peso_chiude_sede: float = 500.0
    peso_raggiunge_min: float = 30.0
    peso_n_giornate: float = -0.5

    def __post_init__(self) -> None:
        if self.beam_k < 1:
            raise ValueError(
                f"ParamBacktracking.beam_k deve essere >= 1, ricevuto {self.beam_k}"
            )
        if self.depth_max_oltre_min < 0:
            raise ValueError(
                f"ParamBacktracking.depth_max_oltre_min deve essere >= 0, "
                f"ricevuto {self.depth_max_oltre_min}"
            )
        if self.tolleranza_km_cap_pct < 0:
            raise ValueError(
                f"ParamBacktracking.tolleranza_km_cap_pct deve essere >= 0, "
                f"ricevuto {self.tolleranza_km_cap_pct}"
            )
        if self.log_level not in ("silent", "info", "debug"):
            raise ValueError(
                f"ParamBacktracking.log_level deve essere "
                f"'silent'|'info'|'debug', ricevuto {self.log_level!r}"
            )
        if self.n_branches_max < 1:
            raise ValueError(
                f"ParamBacktracking.n_branches_max deve essere >= 1, "
                f"ricevuto {self.n_branches_max}"
            )


@dataclass(frozen=True)
class _StatoBacktracking:
    """Stato corrente di una catena di giri durante il backtracking.

    Privato al modulo: il caller riceve direttamente ``Giro``.
    """

    giornate: tuple[GiornataGiro, ...]
    visitate: frozenset[int]  # id() di catene già usate
    km_cumulati: float


@dataclass(frozen=True)
class StatBacktracking:
    """Statistiche di una run del backtracking, per logging A7."""

    n_giri_processati: int
    n_giri_estesi: int
    n_branches_esplorati: int
    avg_depth_raggiunta: float
    warnings: tuple[str, ...] = field(default_factory=tuple)


# =====================================================================
# Helpers
# =====================================================================


def _trova_continuazioni_top_k(
    catene_data: list[CatenaPosizionata],
    visitate: frozenset[int],
    staz_arrivo: str,
    localita_codice: str,
    k: int,
) -> list[CatenaPosizionata]:
    """Versione esplorativa di ``_trova_continuazione`` di multi_giornata.py:
    ritorna fino a ``k`` candidati ordinati per ora_partenza crescente
    (deterministico).

    Vincoli identici al legacy:
    - non già visitata (id() non in ``visitate``)
    - stessa località manutenzione (= stesso convoglio fisico)
    - prima corsa parte da ``staz_arrivo``
    """
    candidati = [
        c
        for c in catene_data
        if id(c) not in visitate
        and c.localita_codice == localita_codice
        and c.catena.corse[0].codice_origine == staz_arrivo
    ]
    candidati.sort(
        key=lambda c: _time_to_min(c.catena.corse[0].ora_partenza)
    )
    return candidati[:k]


def _score_stato(
    stato: _StatoBacktracking,
    params_mg: ParamMultiGiornata,
    params_back: ParamBacktracking,
) -> float:
    """Score di uno stato: più alto = giro migliore.

    Componenti (pesi parametrizzati in ``ParamBacktracking`` da
    MR-A4-bis entry 247):
    - ``km_cumulati × peso_km`` (default 0.5): km coperti.
    - ``n_corse × peso_corse`` (default 1.0): corse PdE coperte.
    - ``peso_chiude_sede`` (default 500, MR-B2 entry 255) se ultima
      stazione in ``whitelist_sede`` (chiusura geografica, vincolo
      principale).
    - ``peso_raggiunge_min`` (default 30) se ``len(giornate) >=
      n_giornate_min`` (raggiunge soft floor).
    - ``peso_n_giornate × n_giornate`` (default -0.5): piccola
      penalità per preferire giri compatti a parità di copertura.
    """
    n_giornate = len(stato.giornate)
    if n_giornate == 0:
        return 0.0
    n_corse = sum(
        len(gg.catena_posizionata.catena.corse) for gg in stato.giornate
    )
    ultima_staz = (
        stato.giornate[-1].catena_posizionata.catena.corse[-1].codice_destinazione
        if stato.giornate[-1].catena_posizionata.catena.corse
        else ""
    )
    chiude_in_sede = ultima_staz in params_mg.whitelist_sede
    raggiunge_min = n_giornate >= params_mg.n_giornate_min
    return (
        stato.km_cumulati * params_back.peso_km
        + n_corse * params_back.peso_corse
        + (params_back.peso_chiude_sede if chiude_in_sede else 0.0)
        + (params_back.peso_raggiunge_min if raggiunge_min else 0.0)
        + n_giornate * params_back.peso_n_giornate
    )


def _estendi_ricorsivo(
    stato: _StatoBacktracking,
    catene_per_data: dict[date, list[CatenaPosizionata]],
    d_inizio: date,
    params_mg: ParamMultiGiornata,
    params_back: ParamBacktracking,
    depth_remaining: int,
    n_branches: list[int],
) -> list[_StatoBacktracking]:
    """Backtracking ricorsivo. Esplora top-k continuazioni della
    giornata successiva fino a ``depth_remaining`` giornate addizionali.

    Pruning: scarta branch che sforerebbero ``km_max_ciclo`` oltre la
    tolleranza percentuale.

    Ritorna lista di stati raggiunti (uno per branch terminato). Il
    chiamante seleziona il migliore via ``_score_stato``.
    """
    n_branches[0] += 1

    # MR-A4-bis (entry 247) HIGH-1 fix: hard cap globale sui nodi
    # visitati. Quando raggiunto, abort qualsiasi ulteriore esplorazione
    # (lo stato corrente viene comunque restituito come terminale).
    # Il caller logga warning quando il cap è stato hittato.
    if n_branches[0] >= params_back.n_branches_max:
        return [stato]

    # Stop condition: depth esaurita o n_giornate_max raggiunto.
    if depth_remaining <= 0:
        return [stato]
    if len(stato.giornate) >= params_mg.n_giornate_max:
        return [stato]

    # Estrai punto di continuazione
    ultima_giornata = stato.giornate[-1]
    cat_pos = ultima_giornata.catena_posizionata
    if not cat_pos.catena.corse:
        return [stato]
    ultima_corsa = cat_pos.catena.corse[-1]
    staz_arrivo = cast(str, ultima_corsa.codice_destinazione)
    localita = cat_pos.localita_codice

    d_prossima = d_inizio + timedelta(days=len(stato.giornate))
    if d_prossima not in catene_per_data:
        return [stato]

    continuazioni = _trova_continuazioni_top_k(
        catene_per_data[d_prossima],
        stato.visitate,
        staz_arrivo,
        localita,
        params_back.beam_k,
    )
    if not continuazioni:
        return [stato]

    # Pruning km_cap (con tolleranza)
    km_cap = float(params_mg.km_max_ciclo or 0.0)
    km_cap_max = (
        km_cap * (1.0 + params_back.tolleranza_km_cap_pct / 100.0)
        if km_cap > 0
        else float("inf")
    )

    risultati: list[_StatoBacktracking] = [stato]  # include stato corrente come opzione di stop
    for prossima in continuazioni:
        km_extra = _km_giornata(prossima)
        nuovo_km = stato.km_cumulati + km_extra
        if km_cap > 0 and nuovo_km > km_cap_max:
            # Sforerebbe la tolleranza, skip questo branch.
            continue

        # MR-A4-bis (entry 247) HIGH-2 fix: replicare i vincoli
        # MR-4 (entry 224) che il greedy legacy in
        # multi_giornata.py:601-623 rispetta. Senza questi check, il
        # backtracking estendeva giri violando max_sosta_diurna_min e
        # min_servizio_giornata_pct configurati dal pianificatore.
        # **Regressione di vincolo identificata da SEVERO critica
        # MR-A4 (voto 2/10)**.
        if not cat_pos.catena.corse:
            # Già gestito sopra (return [stato]) ma defensive
            continue
        ultima_corsa_orig = cat_pos.catena.corse[-1]
        prima_corsa_prossima = prossima.catena.corse[0]

        if params_mg.max_sosta_diurna_min is not None:
            diurno_sosta = _minuti_diurni_sosta_intergiornata(
                ultima_corsa_orig.ora_arrivo,
                prima_corsa_prossima.ora_partenza,
            )
            if diurno_sosta > params_mg.max_sosta_diurna_min:
                continue

        if params_mg.min_servizio_giornata_pct is not None:
            pct = _pct_servizio_catena(prossima)
            if pct < params_mg.min_servizio_giornata_pct:
                continue

        nuova_giornata = GiornataGiro(
            data=d_prossima, catena_posizionata=prossima
        )
        nuovo_stato = _StatoBacktracking(
            giornate=(*stato.giornate, nuova_giornata),
            visitate=stato.visitate | {id(prossima)},
            km_cumulati=nuovo_km,
        )
        # Recurse
        ramo = _estendi_ricorsivo(
            nuovo_stato,
            catene_per_data,
            d_inizio,
            params_mg,
            params_back,
            depth_remaining - 1,
            n_branches,
        )
        risultati.extend(ramo)
    return risultati


def _ricalcola_motivo(
    stato: _StatoBacktracking, params_mg: ParamMultiGiornata
) -> tuple[bool, MotivoChiusura]:
    """Ricalcola ``(chiuso, motivo_chiusura)`` per un nuovo stato.

    Logica identica a multi_giornata.py righe 644-669, applicata a
    posteriori sullo stato esteso.
    """
    if not stato.giornate:
        return False, "non_chiuso"
    ultima_corsa_finale = (
        stato.giornate[-1].catena_posizionata.catena.corse[-1]
    )
    staz_arrivo_finale = cast(str, ultima_corsa_finale.codice_destinazione)
    sotto_min = len(stato.giornate) < params_mg.n_giornate_min

    if params_mg.km_max_ciclo is not None:
        km_cap_raggiunto = stato.km_cumulati >= float(params_mg.km_max_ciclo)
        vicino_sede = staz_arrivo_finale in params_mg.whitelist_sede
        if km_cap_raggiunto and vicino_sede:
            return True, "naturale"
        if km_cap_raggiunto:
            return False, "km_cap"
        if len(stato.giornate) >= params_mg.n_giornate_max:
            return False, "max_giornate"
        if sotto_min:
            return False, "sotto_min"
        return False, "non_chiuso"
    # Modo legacy: fallback se km_max_ciclo non definito
    chiusa_geo = stato.giornate[-1].catena_posizionata.chiusa_a_localita
    if chiusa_geo:
        return True, "naturale"
    if len(stato.giornate) >= params_mg.n_giornate_max:
        return False, "max_giornate"
    return False, "non_chiuso"


# =====================================================================
# Algoritmo principale
# =====================================================================


def tenta_estensione_giri_corti(
    giri: Sequence[Giro],
    catene_per_data_per_materiale: dict[str, dict[date, list[CatenaPosizionata]]],
    materiale_per_giro_idx: dict[int, str],
    params_mg: ParamMultiGiornata,
    params_back: ParamBacktracking | None = None,
) -> tuple[list[Giro], StatBacktracking]:
    """Per ogni giro estendibile (``motivo_chiusura ∈ {'sotto_min',
    'non_chiuso'}`` e ``len(giornate) < n_giornate_max``), tenta
    estensione via beam search con backtracking profondo.

    MR-B2 (entry 255): l'eligibilità si è allargata da
    ``len < n_giornate_min`` a ``len < n_giornate_max``. Il backtracking
    ora processa anche giri che hanno raggiunto la soglia minima ma sono
    ancora aperti (tipico: giri 6-11g che terminano fuori area-Milano).
    Lo score `_score_stato` con `peso_chiude_sede=500` privilegia branch
    che riportano in whitelist sede.

    Args:
        giri: lista giri prodotti da ``costruisci_giri_multigiornata``.
        catene_per_data_per_materiale: mapping ``materiale_codice →
            data → lista catene posizionate``. Stesso pool che ha
            generato i giri (passato dal builder.py).
        materiale_per_giro_idx: mapping ``idx_giro → materiale_codice``.
            Il caller (``builder.py``) lo costruisce dalla regola
            dominante della prima corsa di ogni giro.
        params_mg: parametri multi-giornata (whitelist_sede, km_max_ciclo,
            n_giornate_min/max, ecc.). Riusa i parametri della run.
        params_back: parametri backtracking. Se ``None``, usa default
            V4 Pro (beam_k=8, depth_max_oltre_min=2, tolleranza 10%).

    Returns:
        ``(giri_estesi, stat)``: lista nuova (input non mutato, pure
        function) + statistiche per logging A7.

    Idempotenza: chiamare 2 volte sullo stesso input produce stesso
    output (giri già "lunghi" passa-through).
    """
    if params_back is None:
        params_back = ParamBacktracking()

    n_processati = 0
    n_estesi = 0
    n_branches_total = 0
    depth_total = 0.0
    warnings: list[str] = []

    risultato: list[Giro] = []

    for idx, giro in enumerate(giri):
        # Filtri eligibilità
        if giro.motivo_chiusura not in {"sotto_min", "non_chiuso"}:
            risultato.append(giro)
            continue
        # MR-B2 (entry 255): in MR-A4 originale qui c'era
        # `len(giornate) >= n_giornate_min`: il backtracking si applicava
        # SOLO ai giri sotto-min. Verifica empirica prog 17 (post entry
        # 254): 19/23 giri non_chiuso terminavano fuori area-Milano
        # (PAVIA, MORTARA, ALESSANDRIA, ASTI, ecc.) con
        # `len(giornate) >= n_giornate_min` (=4). Non venivano mai
        # processati. Estendiamo l'eligibilità a giri "non chiusi" fino
        # a `n_giornate_max`: il backtracking cerca catene di estensione
        # che possano chiudere il giro in sede (score peso_chiude_sede
        # alzato a 500 per privilegiare chiusura geografica).
        if len(giro.giornate) >= params_mg.n_giornate_max:
            risultato.append(giro)
            continue
        if not giro.giornate:
            risultato.append(giro)
            continue

        # Materiale + d_inizio del giro (derivati)
        materiale = materiale_per_giro_idx.get(idx)
        if materiale is None:
            warnings.append(
                f"giro idx={idx}: materiale non mappato, skip backtracking"
            )
            risultato.append(giro)
            continue
        catene_per_data = catene_per_data_per_materiale.get(materiale, {})
        if not catene_per_data:
            risultato.append(giro)
            continue
        d_inizio = giro.giornate[0].data

        # Stato iniziale
        visitate_init = frozenset(
            id(g.catena_posizionata) for g in giro.giornate
        )
        stato_init = _StatoBacktracking(
            giornate=giro.giornate,
            visitate=visitate_init,
            km_cumulati=giro.km_cumulati,
        )

        # Depth dinamico: gap a n_min + bonus, capped da n_max
        gap_a_min = max(0, params_mg.n_giornate_min - len(giro.giornate))
        depth_max = gap_a_min + params_back.depth_max_oltre_min
        depth_max = min(depth_max, params_mg.n_giornate_max - len(giro.giornate))

        if depth_max <= 0:
            risultato.append(giro)
            continue

        n_processati += 1
        n_branches_local = [0]

        stati_finali = _estendi_ricorsivo(
            stato_init,
            catene_per_data,
            d_inizio,
            params_mg,
            params_back,
            depth_max,
            n_branches_local,
        )
        n_branches_total += n_branches_local[0]

        # MR-A4-bis (entry 247) HIGH-1 fix: log warning quando il cap
        # n_branches_max è stato hittato per questo giro. Indica
        # che il backtracking è stato troncato prematuramente; il
        # giro potrebbe essere migliorabile aumentando n_branches_max
        # in ParamBacktracking ma a costo di runtime. Dato per A7
        # tuning empirico.
        if n_branches_local[0] >= params_back.n_branches_max:
            warnings.append(
                f"giro idx={idx}: backtracking abortito al cap "
                f"n_branches_max={params_back.n_branches_max} "
                f"(esplorazione troncata, possibile soluzione migliore "
                f"con cap più alto)"
            )

        # Seleziona miglior stato per score
        miglior_stato = stato_init
        miglior_score = _score_stato(stato_init, params_mg, params_back)
        for s in stati_finali:
            sc = _score_stato(s, params_mg, params_back)
            if sc > miglior_score:
                miglior_score = sc
                miglior_stato = s

        if miglior_stato is stato_init:
            risultato.append(giro)
            continue

        # Costruisce nuovo Giro con stato migliore + ricalcola motivo
        chiuso, motivo = _ricalcola_motivo(miglior_stato, params_mg)
        n_estesi += 1
        depth_total += float(
            len(miglior_stato.giornate) - len(giro.giornate)
        )

        risultato.append(
            dataclasses.replace(
                giro,
                giornate=miglior_stato.giornate,
                km_cumulati=miglior_stato.km_cumulati,
                chiuso=chiuso,
                motivo_chiusura=motivo,
            )
        )

    avg_depth = depth_total / n_estesi if n_estesi > 0 else 0.0
    return risultato, StatBacktracking(
        n_giri_processati=n_processati,
        n_giri_estesi=n_estesi,
        n_branches_esplorati=n_branches_total,
        avg_depth_raggiunta=avg_depth,
        warnings=tuple(warnings),
    )


__all__ = [
    "ParamBacktracking",
    "StatBacktracking",
    "tenta_estensione_giri_corti",
]
