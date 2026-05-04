"""Capacity-aware routing dei cluster A1 (Sprint 7.9 MR 11B Step 2,
entry 121).

Ribilancia i ``GiroAssegnato`` (cluster A1 post-clustering A1) in base
alla dotazione fisica di pezzi disponibili per materiale per
quell'azienda. Un cluster A1 = un convoglio fisico con composizione
(es. ETR526×2 = 2 pezzi ETR526 occupati per tutto il ciclo).

Algoritmo greedy:

1. Raggruppa cluster per materiale principale (= primo elemento della
   composizione del primo blocco assegnato).
2. Per ogni materiale con dotazione finita:
   a. Ordina cluster per ``km_cumulati`` DESC. I cluster più produttivi
      (= più km totali nel ciclo) tengono la regola originale; i meno
      produttivi vengono spostati per primi.
   b. Tieni cluster finché la capacity disponibile è sufficiente.
   c. Per i cluster in surplus: tenta riassegnazione a una regola
      alternativa con materiale che ha ancora capacity disponibile.
   d. Se nessuna regola alternativa cattura tutte le corse del cluster
      o ha capacity sufficiente → cluster scartato (le sue corse
      diventano residue).
3. Se ``dotazione[materiale] is None`` (= capacity illimitata, es.
   FLIRT TILO) tutti i cluster di quel materiale passano senza check.

Decisione utente 2026-05-04: criterio di scelta del cluster da
spostare = ``km_cumulati`` ASC (= cluster con MENO km totali spostato
per primo, preserva i cicli più produttivi).

Il modulo è **DB-agnostic**: opera solo su `GiroAssegnato` + regole
+ dotazione (dict).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import date
from typing import Any

from colazione.domain.builder_giro.composizione import (
    BloccoAssegnato,
    GiornataAssegnata,
    GiroAssegnato,
)
from colazione.domain.builder_giro.risolvi_corsa import (
    AssegnazioneRisolta,
    ComposizioneItem,
    IsAccoppiamentoAmmesso,
    _RegolaLike,
    risolvi_corsa,
)


# =====================================================================
# Helpers
# =====================================================================


def _composizione_principale(giro: GiroAssegnato) -> tuple[ComposizioneItem, ...] | None:
    """Composizione del primo blocco assegnato del cluster.

    Per un cluster A1 chiuso da composizione coerente, tutti i blocchi
    di tutte le giornate hanno la stessa ``assegnazione.composizione``
    (= il convoglio fisico ha una composizione sola per tutto il
    ciclo). Restituisce ``None`` se nessun blocco è assegnato (giro
    orfano).
    """
    for giornata in giro.giornate:
        for blocco in giornata.blocchi_assegnati:
            return blocco.assegnazione.composizione
    return None


def _materiale_principale(giro: GiroAssegnato) -> str | None:
    """Codice del materiale principale del cluster (primo della composizione)."""
    comp = _composizione_principale(giro)
    if comp is None:
        return None
    return comp[0].materiale_tipo_codice


def _regola_id_principale(giro: GiroAssegnato) -> int | None:
    """Id della regola che ha generato il cluster (dal primo blocco)."""
    for giornata in giro.giornate:
        for blocco in giornata.blocchi_assegnati:
            return blocco.assegnazione.regola_id
    return None


def _pezzi_consumati_per_giro(comp: tuple[ComposizioneItem, ...]) -> dict[str, int]:
    """Pezzi consumati per materiale dal cluster (1 cluster = 1 convoglio).

    Esempio: composizione ``(ETR526×2, ETR425×1)`` → ``{ETR526: 2,
    ETR425: 1}``.
    """
    out: dict[str, int] = defaultdict(int)
    for item in comp:
        out[item.materiale_tipo_codice] += item.n_pezzi
    return dict(out)


# =====================================================================
# Riassegnazione a regola alternativa
# =====================================================================


def _ricostruisci_cluster_con_regola(
    cluster: GiroAssegnato,
    nuova_regola: _RegolaLike,
    is_accoppiamento_ammesso: IsAccoppiamentoAmmesso | None = None,
) -> GiroAssegnato | None:
    """Riassegna tutte le corse del cluster a ``nuova_regola``.

    Strategia: per ogni blocco invoca ``risolvi_corsa(corsa,
    [nuova_regola], data, ...)``. Se la regola non cattura la corsa
    (filtri non match), restituisce ``None`` — il cluster non è
    ricomponibile su questa regola.

    Se la regola cattura tutte le corse, ritorna un nuovo
    ``GiroAssegnato`` con ``BloccoAssegnato.assegnazione`` aggiornata
    (nuova composizione + nuovo regola_id) per ogni blocco di ogni
    giornata.
    """
    nuove_giornate: list[GiornataAssegnata] = []
    for giornata in cluster.giornate:
        nuovi_blocchi: list[BloccoAssegnato] = []
        for blocco in giornata.blocchi_assegnati:
            nuova_assegn = risolvi_corsa(
                blocco.corsa,
                [nuova_regola],
                giornata.data,
                is_accoppiamento_ammesso=is_accoppiamento_ammesso,
            )
            if nuova_assegn is None:
                # Regola non cattura questa corsa → cluster non
                # ricomponibile.
                return None
            nuovi_blocchi.append(replace(blocco, assegnazione=nuova_assegn))

        nuove_giornate.append(
            replace(giornata, blocchi_assegnati=tuple(nuovi_blocchi))
        )

    return replace(cluster, giornate=tuple(nuove_giornate))


def _trova_regola_alternativa(
    cluster: GiroAssegnato,
    regole: list[_RegolaLike],
    regola_corrente_id: int,
    pezzi_residui: dict[str, int | None],
    is_accoppiamento_ammesso: IsAccoppiamentoAmmesso | None,
) -> tuple[_RegolaLike, GiroAssegnato] | None:
    """Cerca una regola alternativa (escludendo ``regola_corrente_id``)
    che catturi TUTTE le corse del cluster e abbia capacity disponibile
    per la propria composizione.

    Strategia: prova le regole in ordine di "capacity disponibile DESC"
    (dotazione_residua / pezzi_per_convoglio = quanti convogli ancora
    possibili). La prima regola che ricostruisce il cluster e ha
    capacity vince.

    Returns:
        ``(regola, cluster_ricostruito)`` o ``None`` se nessuna
        alternativa è valida.
    """
    candidate = [r for r in regole if r.id != regola_corrente_id]

    def _score_capacity(regola: _RegolaLike) -> float:
        """Quanti convogli rimanenti questa regola può ancora produrre."""
        comp_items = [
            ComposizioneItem(str(d["materiale_tipo_codice"]), int(d["n_pezzi"]))
            for d in regola.composizione_json
        ]
        if not comp_items:
            return -1.0
        consumo = _pezzi_consumati_per_giro(tuple(comp_items))
        slot_min = float("inf")
        for materiale, n_pezzi in consumo.items():
            disponibili = pezzi_residui.get(materiale)
            if disponibili is None:
                # Capacity illimitata → infinito slot
                continue
            if n_pezzi <= 0:
                continue
            slots = disponibili / n_pezzi
            if slots < slot_min:
                slot_min = slots
        return slot_min if slot_min != float("inf") else 1e18

    # Ordina candidate per score capacity DESC; tie-break id ASC.
    candidate.sort(key=lambda r: (-_score_capacity(r), r.id))

    for regola in candidate:
        if _score_capacity(regola) < 1.0:
            # Nemmeno 1 convoglio entra: skippa
            continue
        ricostruito = _ricostruisci_cluster_con_regola(
            cluster, regola, is_accoppiamento_ammesso
        )
        if ricostruito is not None:
            return regola, ricostruito

    return None


# =====================================================================
# API pubblica
# =====================================================================


def ribilancia_per_capacity(
    giri_a1: list[GiroAssegnato],
    regole: list[_RegolaLike],
    dotazione: dict[str, int | None],
    is_accoppiamento_ammesso: IsAccoppiamentoAmmesso | None = None,
) -> tuple[list[GiroAssegnato], list[GiroAssegnato], list[str]]:
    """Ribilancia cluster A1 in base alla dotazione fisica.

    Args:
        giri_a1: cluster prodotti dal pipeline post-composizione.
        regole: regole del programma (tutte, anche quelle non vincenti
            in ``risolvi_corsa``).
        dotazione: ``{materiale_codice: pezzi_disponibili | None}``.
            ``None`` = capacity illimitata. ``0`` o assente = nessun
            consumo permesso (e cluster scartato a meno di alternativa).
        is_accoppiamento_ammesso: callback per validazione accoppiamento
            quando la riassegnazione tocca composizioni multi-materiale.

    Returns:
        Tupla ``(giri_tenuti, giri_scartati, warnings)``:
        - ``giri_tenuti``: cluster da passare ad aggregazione A2.
        - ``giri_scartati``: cluster eliminati per capacity esaurita;
          le loro corse cadono come ``corse_residue`` (il caller
          aggrega).
        - ``warnings``: messaggi diagnostici per l'utente.
    """
    if not giri_a1:
        return [], [], []

    pezzi_residui: dict[str, int | None] = dict(dotazione)
    giri_orfani: list[GiroAssegnato] = []
    per_materiale: dict[str, list[GiroAssegnato]] = defaultdict(list)
    for g in giri_a1:
        m = _materiale_principale(g)
        if m is None:
            giri_orfani.append(g)
            continue
        per_materiale[m].append(g)

    output: list[GiroAssegnato] = []
    scartati: list[GiroAssegnato] = []
    warnings: list[str] = []

    # Per ogni materiale, ordina cluster per km_cumulati DESC: i più
    # produttivi tengono la regola originale.
    for materiale, lista in per_materiale.items():
        lista.sort(key=lambda g: -g.km_cumulati)

        for cluster in lista:
            comp = _composizione_principale(cluster)
            if comp is None:
                output.append(cluster)
                continue

            consumo = _pezzi_consumati_per_giro(comp)
            disponibile = all(
                _ha_capacity(pezzi_residui.get(m), n) for m, n in consumo.items()
            )

            if disponibile:
                # OK, tieni cluster e consuma capacity.
                for m, n in consumo.items():
                    if pezzi_residui.get(m) is not None:
                        pezzi_residui[m] = (pezzi_residui[m] or 0) - n
                output.append(cluster)
                continue

            # Surplus: tenta riassegnazione a regola alternativa.
            regola_corrente_id = _regola_id_principale(cluster)
            if regola_corrente_id is None:
                output.append(cluster)
                continue

            alt = _trova_regola_alternativa(
                cluster,
                regole,
                regola_corrente_id,
                pezzi_residui,
                is_accoppiamento_ammesso,
            )
            if alt is None:
                # Cluster scartato.
                scartati.append(cluster)
                n_corse = sum(len(g.blocchi_assegnati) for g in cluster.giornate)
                warnings.append(
                    f"Cluster materiale={materiale} km={cluster.km_cumulati:.0f} "
                    f"scartato per capacity esaurita (dotazione "
                    f"{dotazione.get(materiale)}, no regola alternativa). "
                    f"{n_corse} corse → residue."
                )
                continue

            # Riassegnato: consuma capacity della NUOVA regola.
            nuova_regola, cluster_nuovo = alt
            nuova_comp = _composizione_principale(cluster_nuovo)
            assert nuova_comp is not None  # garantito da _ricostruisci_cluster_con_regola
            nuovo_consumo = _pezzi_consumati_per_giro(nuova_comp)
            for m, n in nuovo_consumo.items():
                if pezzi_residui.get(m) is not None:
                    pezzi_residui[m] = (pezzi_residui[m] or 0) - n
            output.append(cluster_nuovo)
            warnings.append(
                f"Cluster originariamente regola={regola_corrente_id} "
                f"({materiale}) riassegnato a regola={nuova_regola.id} "
                f"(km={cluster.km_cumulati:.0f}) per capacity."
            )

    output.extend(giri_orfani)
    return output, scartati, warnings


def _ha_capacity(disponibile: int | None, richiesto: int) -> bool:
    """``True`` se ci sono almeno ``richiesto`` pezzi disponibili.

    ``disponibile is None`` = capacity illimitata.
    """
    if disponibile is None:
        return True
    return disponibile >= richiesto


# =====================================================================
# Caricamento dotazione da DB (helper async per builder)
# =====================================================================


async def carica_dotazione_per_azienda(
    session: Any,
    azienda_id: int,
) -> dict[str, int | None]:
    """Carica `materiale_dotazione_azienda` come dict
    ``{materiale_codice: pezzi_disponibili}``.

    Materiali NON registrati in tabella → assenti dal dict (= capacity
    illimitata di default per non bloccare flussi storici prima della
    seed dotazione).
    """
    from sqlalchemy import select

    from colazione.models.anagrafica import MaterialeDotazioneAzienda

    stmt = select(MaterialeDotazioneAzienda).where(
        MaterialeDotazioneAzienda.azienda_id == azienda_id
    )
    rows = (await session.execute(stmt)).scalars().all()
    return {row.materiale_codice: row.pezzi_disponibili for row in rows}


def aggrega_corse_residue_da_scartati(
    scartati: list[GiroAssegnato],
) -> list[date]:
    """Helper informativo: date di applicazione coperte dai cluster
    scartati (il caller può loggare quante corse / quali date sono
    perse).
    """
    date_perse: set[date] = set()
    for g in scartati:
        for giornata in g.giornate:
            date_perse.update(giornata.dates_apply_or_data)
    return sorted(date_perse)
