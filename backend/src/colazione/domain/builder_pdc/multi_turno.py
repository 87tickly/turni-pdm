"""Builder PdC multi-turno con programmazione dinamica — Sprint 7.10 MR α.2.

Risolve il problema diagnosticato dall'utente nel screenshot smoke
2026-05-05: il builder MVP precedente costruiva **1 turno PdC monolitico
per giornata-giro**, con prestazione totale di 20+ ore e 6/6 giornate
fuori cap normativi.

Questo modulo costruisce invece **N turni PdC autonomi distinti** per
ogni giro materiale, ognuno:

- coperto da 1 PdC che parte e torna al SUO deposito (o FR controllato);
- entro cap prestazione (510min standard, 420min notturno);
- entro cap condotta (330min);
- con scambio PdC permesso SOLO in stazioni CV ammesse (depositi +
  deroghe TIRANO/MORTARA — vedi `split_cv.lista_stazioni_cv_ammesse`);
- assegnato al miglior deposito disponibile (heuristic post-DP che
  preferisce il deposito = stazione di partenza del segmento).

Algoritmo (MVP α.2 — la singola giornata-giro è il sub-problema DP):

1. Per ogni giornata-giro indipendentemente:
   a. Estraggo i blocchi ordinati cronologicamente.
   b. Marco i "punti di taglio possibili": gli indici `i` per cui
      `blocchi[i].stazione_da_codice` è in `stazioni_cv`.
   c. DP `T[i]` = costo minimo per coprire i blocchi [0..i] partendo
      da un PdC qualsiasi che inizia dal blocco 0 o da un punto CV.
      Recurrenza:
      ``T[i] = min over j ∈ {-1, split_points[<i+1]}: T[j] + 1``
      condizionato a che il segmento [j+1..i] sia entro cap
      prestazione+condotta.
   d. Backtrack da T[n-1] → sequenza ordinata di split points.
2. Per ogni segmento risultante, **scelgo il deposito ottimale**:
   preferenza al deposito con `stazione_principale_codice` =
   stazione_partenza del segmento; fallback a deposito più vicino
   (= stessa città / nome simile); fallback finale a NULL (legacy).
3. Persiste gli N segmenti come N TurnoPdc autonomi distinti.

NB sull'inter-giornata: nel MVP α.2 ogni giornata-giro è risolta
indipendentemente (DP locale). Lo scambio inter-giornata (PdC che
fa metà G1 + metà G2) richiederebbe DP globale sullo "spaghetto"
intero del giro — scope MR α.2.bis se serve. Oggi: bug del singolo
turno fuori-cap risolto, sequenze di N turni autonomi all'interno
di ogni giornata-giro.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.config import get_settings
from colazione.domain.builder_pdc.builder import (
    ACCESSORI_MIN_STANDARD,
    CONDOTTA_MAX_MIN,
    FINE_SERVIZIO_MIN,
    PRESA_SERVIZIO_MIN,
    PRESTAZIONE_MAX_NOTTURNO,
    PRESTAZIONE_MAX_STANDARD,
    BuilderTurnoPdcResult,
    DepositoPdcNonTrovatoError,
    GiroNonTrovatoError,
    GiroVuotoError,
    _BloccoPdcDraft,
    _build_giornata_pdc,
    _from_min,
    _GiornataPdcDraft,
    _persisti_un_turno_pdc,
    _t,
)
from colazione.domain.builder_pdc.split_cv import lista_stazioni_cv_ammesse
from colazione.integrations.live_arturo import (
    TrenoVettura,
    trova_treno_vettura,
)
from colazione.models.anagrafica import Depot
from colazione.models.giri import (
    GiroBlocco,
    GiroGiornata,
    GiroMateriale,
    GiroVariante,
)
from colazione.models.turni_pdc import TurnoPdc

logger = logging.getLogger(__name__)

# Penalty enorme per soluzioni invalide nel DP (cap superato senza
# alternative). Usato come "infinito" — un singolo step di violazione
# ha più peso di un'intera giornata coperta da turni puliti.
_INVALIDO = 10**9

# Sprint 7.10 MR α.5: gap minimo dopo ACCa prima che il PdC possa
# salire sulla vettura. 5 min di "buffer" per uscire dal mezzo,
# raggiungere il binario, salire come passeggero. Configurabile in
# futuro via Settings se serve.
VETTURA_GAP_PRE_MIN = 5
# Attesa massima accettabile fra ora_fine_servizio e partenza vettura.
# Sopra questo valore il PdC sta troppo "fermo" e il rientro non è
# competitivo (= meglio FR).
VETTURA_ATTESA_MAX_MIN = 120


@dataclass
class _SegmentoTurno:
    """Un sotto-segmento di una giornata-giro che diventerà 1 TurnoPdc.

    Rappresenta i blocchi `[idx_start..idx_end]` (estremi inclusi) di
    una giornata-giro coperti da un singolo PdC. ``deposito_assegnato``
    è il Depot scelto post-DP (può essere None se nessun deposito
    matcha la stazione di partenza/arrivo).
    """

    giornata_giro_id: int
    numero_giornata: int
    variante_calendario: str
    blocchi: list[GiroBlocco]
    idx_start: int
    idx_end: int
    deposito_assegnato: Depot | None
    # Sprint 7.10 MR α.5.fix: vettura RIENTRO pre-calcolata dalla
    # heuristic (= già verificata via API live durante la scelta
    # deposito).
    vettura_pre: TrenoVettura | None = None
    # Sprint 7.10 MR α.8: vettura PARTENZA pre-calcolata + flag
    # DORMITA. Decisione utente 2026-05-05: il PdC che inizia in
    # stazione ≠ depot deve avere vettura mattutina O DORMITA la
    # sera prima.
    vettura_pre_partenza: TrenoVettura | None = None
    dormita_partenza: bool = False
    dormita_rientro: bool = False


def _eccede_cap_prestazione(draft: _GiornataPdcDraft) -> bool:
    """True se prestazione del draft eccede il cap applicabile."""
    cap = (
        PRESTAZIONE_MAX_NOTTURNO if draft.is_notturno else PRESTAZIONE_MAX_STANDARD
    )
    return draft.prestazione_min > cap


def _segmento_valido(blocchi: list[GiroBlocco]) -> _GiornataPdcDraft | None:
    """Costruisce il draft del segmento; ritorna None se non valido.

    Validità = il draft esiste E non eccede cap prestazione/condotta.
    Refezione mancante NON invalida il segmento (è gestita a sub-livello
    dal builder MVP nello stesso modo del split CV intermedio Sprint 7.4).
    """
    draft = _build_giornata_pdc(
        numero_giornata=1,  # placeholder: rinumerato a livello segmento
        variante_calendario="GG",
        blocchi_giro=blocchi,
    )
    if draft is None:
        return None
    if _eccede_cap_prestazione(draft):
        return None
    if draft.condotta_min > CONDOTTA_MAX_MIN:
        return None
    return draft


def _dp_segmenta_giornata(
    blocchi: list[GiroBlocco],
    stazioni_cv: set[str],
) -> list[tuple[int, int]] | None:
    """DP che produce la sequenza ottima di split per UNA giornata-giro.

    Output: lista `[(start, end), ...]` con coppie di indici inclusivi
    nei blocchi della giornata. Ogni coppia rappresenta un segmento
    coperto da 1 PdC distinto. Garantito: copertura completa,
    nessuna sovrapposizione, ogni segmento entro cap normativi.

    Ritorna `None` se non esiste alcuna segmentazione valida (es.
    nessuna stazione CV ammessa lungo la tratta E la giornata
    monolitica eccede già cap → impossibile da coprire correttamente).

    Recurrenza:
        T[i] = costo minimo per coprire blocchi [0..i]
             = min over j ∈ split_anchors_le(i):
                   T[j-1] + 1 (= 1 turno aggiuntivo)
                 condizionato a [j..i] entro cap.

        split_anchors_le(i) = {j : 0 ≤ j ≤ i E blocchi[j] inizia
                              in stazione CV ammessa OR j = 0}

        Condizione iniziale: T[-1] = 0 (nessun turno per coprire
        il vuoto).

    Backtrack: parto da T[n-1], scelgo il `j` che ha realizzato il
    minimo, e ricostruisco a ritroso fino a coprire [0..n-1].
    """
    n = len(blocchi)
    if n == 0:
        return []

    # Anchors di taglio: i blocchi che possono essere "primo blocco"
    # di un segmento (= la stazione di INIZIO del blocco è in CV).
    # Il blocco 0 è sempre anchor (è l'inizio della giornata).
    anchors: set[int] = {0}
    for i, b in enumerate(blocchi):
        if i > 0 and b.stazione_da_codice is not None and b.stazione_da_codice in stazioni_cv:
            anchors.add(i)

    # T[i] = costo minimo per coprire [0..i]; dp_prev[i] = j scelto
    # come anchor del segmento finale di [0..i] (per backtrack).
    T: list[int] = [_INVALIDO] * n
    dp_prev: list[int] = [-1] * n

    for i in range(n):
        for j in anchors:
            if j > i:
                continue
            # Considera il segmento blocchi[j..i].
            seg_blocchi = blocchi[j : i + 1]
            if _segmento_valido(seg_blocchi) is None:
                continue
            # Costo: T[j-1] + 1 (1 turno aggiuntivo).
            base = 0 if j == 0 else T[j - 1]
            if base >= _INVALIDO:
                continue
            cand = base + 1
            if cand < T[i]:
                T[i] = cand
                dp_prev[i] = j

    if T[n - 1] >= _INVALIDO:
        # Nessuna segmentazione valida — la giornata richiederà
        # fallback (= 1 turno monolitico fuori cap, come pre-MR α.2).
        return None

    # Backtrack.
    segmenti: list[tuple[int, int]] = []
    i = n - 1
    while i >= 0:
        j = dp_prev[i]
        segmenti.append((j, i))
        i = j - 1
    segmenti.reverse()
    return segmenti


@dataclass
class _RisultatoHeuristic:
    """Sprint 7.10 MR α.8: esito completo della scelta deposito.

    Quattro bit di stato indipendenti:
    - ``vettura_partenza``: treno per portare il PdC dal depot alla
      stazione di apertura (None se apertura == depot O dormita_partenza
      è True).
    - ``vettura_rientro``: treno per riportare il PdC alla chiusura
      (None se chiusura == depot O dormita_rientro è True).
    - ``dormita_partenza``: True se il PdC deve dormire la notte prima
      vicino alla stazione di apertura (= nessuna vettura mattutina
      utile).
    - ``dormita_rientro``: True se il PdC deve fare FR alla fine del
      turno (= nessuna vettura serale utile).
    """

    depot: Depot
    vettura_partenza: TrenoVettura | None
    vettura_rientro: TrenoVettura | None
    dormita_partenza: bool
    dormita_rientro: bool


async def _scegli_deposito_per_segmento(
    blocchi_segmento: list[GiroBlocco],
    depositi: list[Depot],
    *,
    ora_apertura_min: int,
    ora_chiusura_min: int,
    live_client: httpx.AsyncClient,
) -> _RisultatoHeuristic | None:
    """Heuristic post-DP con quality gate VETTURA + DORMITA — Sprint 7.10 MR α.8.

    Decisioni utente cumulativa 2026-05-05:
    - α.5.fix: *"non è giusto inserire SONDRIO se il PdC chiude a
      LECCO e non c'è vettura"* → quality gate vettura rientro.
    - α.8: *"non si assegnano mai giornate ad un deposito quando
      queste non possono essere raggiunte con le vetture e la
      giornata inizia in una località dove esiste il deposito.
      Cremona è deposito. Vercelli non è deposito quindi crei una
      DORMITA"*. → quality gate vettura PARTENZA + DORMITA fallback.

    Per ogni candidato depot la funzione valuta in 4 scenari:

    1. **Casa-Casa**: depot = apertura = chiusura. Niente vetture
       né dormite serve. Vincitore preferenziale.
    2. **Casa-Lontano**: depot = apertura, chiusura ≠ depot. Vettura
       RIENTRO richiesta; se manca → DORMITA finale (FR).
    3. **Lontano-Casa**: chiusura = depot, apertura ≠ depot. Vettura
       PARTENZA richiesta; se manca → DORMITA iniziale.
    4. **Lontano-Lontano**: depot ≠ apertura ≠ chiusura. Vettura
       PARTENZA + RIENTRO; se manca una delle due → DORMITA al lato.

    Il candidato vince **se e solo se è internamente coerente**: ogni
    spostamento PdC↔stazione del lavoro è risolto via vettura O
    dormita esplicita. Niente "buchi" silenti.

    Ritorna ``None`` solo se non c'è nemmeno un depot popolato che
    matcha apertura/chiusura/intermedie (= fallback FT nel chiamante).
    """
    if not blocchi_segmento or not depositi:
        return None

    primo = blocchi_segmento[0]
    ultimo = blocchi_segmento[-1]
    stazione_apertura = primo.stazione_da_codice
    stazione_chiusura = ultimo.stazione_a_codice

    # Indice depot by stazione_principale_codice per lookup O(1).
    by_stazione: dict[str, Depot] = {
        d.stazione_principale_codice: d
        for d in depositi
        if d.stazione_principale_codice is not None
    }

    # Lista candidati in ordine di preferenza:
    # 1. depot = apertura = chiusura (casa-casa, idempotente)
    # 2. depot = apertura (casa-lontano)
    # 3. depot = chiusura (lontano-casa)
    # 4. depot = stazione intermedia (lontano-lontano)
    candidati_ordinati: list[str] = []
    seen: set[str] = set()

    def _aggiungi(s: str | None) -> None:
        if s is not None and s in by_stazione and s not in seen:
            candidati_ordinati.append(s)
            seen.add(s)

    if (
        stazione_apertura is not None
        and stazione_apertura == stazione_chiusura
    ):
        _aggiungi(stazione_apertura)  # casa-casa
    _aggiungi(stazione_apertura)  # casa-lontano (se diverso)
    _aggiungi(stazione_chiusura)  # lontano-casa
    for b in blocchi_segmento:
        _aggiungi(b.stazione_da_codice)
        _aggiungi(b.stazione_a_codice)

    # Per ogni candidato, valuta lo scenario e cerca vetture
    # richieste con fallback DORMITA.
    for codice_depot in candidati_ordinati:
        depot = by_stazione[codice_depot]
        risultato = await _valuta_candidato(
            depot=depot,
            stazione_apertura=stazione_apertura,
            stazione_chiusura=stazione_chiusura,
            ora_apertura_min=ora_apertura_min,
            ora_chiusura_min=ora_chiusura_min,
            live_client=live_client,
        )
        if risultato is not None:
            return risultato
        logger.info(
            "Depot %s scartato per segmento (apertura=%s, chiusura=%s): "
            "scenario non risolvibile",
            codice_depot,
            stazione_apertura,
            stazione_chiusura,
        )

    return None


# Sprint 7.10 MR α.8: tempo minimo che la vettura mattutina deve
# arrivare PRIMA dell'inizio prestazione del PdC.
# inizio_prestazione = primo_treno_orario - ACCESSORI_MIN_STANDARD - PRESA_SERVIZIO_MIN
# Quindi la vettura deve arrivare a `stazione_apertura` entro
# `ora_apertura_min - VETTURA_GAP_POST_ARRIVO_MIN`.
VETTURA_GAP_POST_ARRIVO_MIN = 5


async def _valuta_candidato(
    *,
    depot: Depot,
    stazione_apertura: str | None,
    stazione_chiusura: str | None,
    ora_apertura_min: int,
    ora_chiusura_min: int,
    live_client: httpx.AsyncClient,
) -> _RisultatoHeuristic | None:
    """Valuta se il `depot` è ammissibile per il segmento.

    Restituisce un ``_RisultatoHeuristic`` valorizzato se il
    PdC del depot può:
    - raggiungere la stazione di apertura (vettura mattutina O
      dormita la sera prima)
    - tornare al depot dalla chiusura (vettura serale O FR)

    Se il depot non ha ``stazione_principale_codice`` popolata,
    ritorna ``None`` (lo skippiamo).
    """
    sede = depot.stazione_principale_codice
    if sede is None:
        return None

    # Lato PARTENZA: serve vettura sede → apertura?
    serve_vettura_partenza = stazione_apertura is not None and stazione_apertura != sede
    vettura_partenza: TrenoVettura | None = None
    dormita_partenza = False

    if serve_vettura_partenza:
        assert stazione_apertura is not None
        # La vettura deve ARRIVARE a stazione_apertura entro:
        # ora_apertura_min (= inizio_prestazione) meno un buffer
        # per scendere dal treno e prendere servizio.
        # Cerco una vettura che parta dalla sede entro le 6h prima
        # dell'apertura (sliding window ampio per coprire treni mattutini).
        ora_min_partenza_vettura = (
            ora_apertura_min - 6 * 60
        ) % (24 * 60)
        vettura_partenza = await trova_treno_vettura(
            stazione_partenza_codice=sede,
            stazione_arrivo_codice=stazione_apertura,
            ora_min_partenza=ora_min_partenza_vettura,
            max_attesa_min=6 * 60,
            client=live_client,
        )
        if vettura_partenza is not None:
            # Verifica che il treno arrivi PRIMA dell'apertura
            # con buffer.
            arrivo_min_vettura = vettura_partenza.arrivo_min
            margine = (ora_apertura_min - arrivo_min_vettura) % (24 * 60)
            # Se il margine è > 6h (= treno arriva troppo presto) o
            # troppo piccolo (< buffer) il treno non è utile.
            if (
                margine < VETTURA_GAP_POST_ARRIVO_MIN
                or margine > 6 * 60
            ):
                vettura_partenza = None
        if vettura_partenza is None:
            # Fallback: DORMITA la sera prima vicino alla stazione di
            # apertura. Decisione utente 2026-05-05: *"se non ci sono
            # vetture mattutine per raggiungerlo, questa è una
            # dormita"*.
            dormita_partenza = True

    # Lato RIENTRO: serve vettura chiusura → sede?
    serve_vettura_rientro = stazione_chiusura is not None and stazione_chiusura != sede
    vettura_rientro: TrenoVettura | None = None
    dormita_rientro = False

    if serve_vettura_rientro:
        assert stazione_chiusura is not None
        vettura_rientro = await trova_treno_vettura(
            stazione_partenza_codice=stazione_chiusura,
            stazione_arrivo_codice=sede,
            ora_min_partenza=ora_chiusura_min + VETTURA_GAP_PRE_MIN,
            max_attesa_min=VETTURA_ATTESA_MAX_MIN,
            client=live_client,
        )
        if vettura_rientro is None:
            dormita_rientro = True

    return _RisultatoHeuristic(
        depot=depot,
        vettura_partenza=vettura_partenza,
        vettura_rientro=vettura_rientro,
        dormita_partenza=dormita_partenza,
        dormita_rientro=dormita_rientro,
    )


async def genera_turni_pdc_multi(
    *,
    session: AsyncSession,
    azienda_id: int,
    giro_id: int,
    valido_da: date | None = None,
    force: bool = False,
) -> list[BuilderTurnoPdcResult]:
    """Entry point: costruisce N turni PdC autonomi per il giro.

    Per ogni giornata-giro applica DP locale per la segmentazione e
    persiste N TurnoPdc, ognuno con il suo ``deposito_pdc_id``.

    Anti-rigenerazione: se esistono già turni per il giro e
    ``force=False`` solleva ``GiriEsistentiError`` (riusa la stessa
    eccezione del builder monolitico per coerenza API). Con
    ``force=True`` cancella tutti i turni del giro indipendentemente
    dal deposito e ricrea da zero.

    Raises:
        GiroNonTrovatoError, GiroVuotoError, GiriEsistentiError.
    """
    giro = (
        await session.execute(
            select(GiroMateriale).where(
                GiroMateriale.id == giro_id,
                GiroMateriale.azienda_id == azienda_id,
            )
        )
    ).scalar_one_or_none()
    if giro is None:
        raise GiroNonTrovatoError(
            f"Giro {giro_id} non trovato per azienda {azienda_id}"
        )

    giornate_giro = list(
        (
            await session.execute(
                select(GiroGiornata)
                .where(GiroGiornata.giro_materiale_id == giro_id)
                .order_by(GiroGiornata.numero_giornata)
            )
        ).scalars()
    )
    if not giornate_giro:
        raise GiroVuotoError(f"Giro {giro_id} non ha giornate")

    giornata_ids = [gg.id for gg in giornate_giro]

    canonica_per_giornata: dict[int, GiroVariante] = {}
    for v in (
        await session.execute(
            select(GiroVariante)
            .where(GiroVariante.giro_giornata_id.in_(giornata_ids))
            .order_by(GiroVariante.giro_giornata_id, GiroVariante.variant_index)
        )
    ).scalars():
        canonica_per_giornata.setdefault(v.giro_giornata_id, v)

    canonica_ids = [v.id for v in canonica_per_giornata.values()]
    blocchi_per_giornata: dict[int, list[GiroBlocco]] = {}
    if canonica_ids:
        var_to_gg = {v.id: v.giro_giornata_id for v in canonica_per_giornata.values()}
        for b in (
            await session.execute(
                select(GiroBlocco)
                .where(GiroBlocco.giro_variante_id.in_(canonica_ids))
                .order_by(GiroBlocco.giro_variante_id, GiroBlocco.seq)
            )
        ).scalars():
            gg_id = var_to_gg[b.giro_variante_id]
            blocchi_per_giornata.setdefault(gg_id, []).append(b)

    depositi = list(
        (
            await session.execute(
                select(Depot)
                .where(
                    Depot.azienda_id == azienda_id,
                    Depot.is_attivo,
                    Depot.tipi_personale_ammessi == "PdC",
                )
                .order_by(Depot.codice)
            )
        ).scalars()
    )
    stazioni_cv = await lista_stazioni_cv_ammesse(session, azienda_id)

    # Anti-rigenerazione: cancella TUTTI i turni del giro (qualsiasi
    # deposito) se force, altrimenti raise. Match più aggressivo del
    # builder monolitico perché il multi-turno produce turni multipli
    # che semanticamente sono "il piano PdC del giro".
    existing = list(
        (
            await session.execute(
                select(TurnoPdc).where(TurnoPdc.azienda_id == azienda_id)
            )
        ).scalars()
    )
    legati = [
        t for t in existing
        if (t.generation_metadata_json or {}).get("giro_materiale_id") == giro_id
    ]
    if legati and not force:
        # Lancia la stessa eccezione del builder monolitico per
        # coerenza API; il chiamante sa già gestirla con 409.
        from colazione.domain.builder_pdc.builder import GiriEsistentiError
        raise GiriEsistentiError(
            f"Esistono già {len(legati)} turno/i PdC per giro {giro_id}: "
            f"{legati[0].codice}"
            + (f" ... +{len(legati)-1} altri" if len(legati) > 1 else "")
        )
    for t in legati:
        await session.delete(t)
    if legati:
        await session.flush()

    valido_da_eff = valido_da or date.today()

    # Costruisci tutti i segmenti DP per tutte le giornate-giro.
    segmenti_globali: list[_SegmentoTurno] = []
    # Pre-step (sync, no API): calcola i ranges DP per ogni giornata.
    # La heuristic deposito (async, con API live) viene poi applicata
    # in un secondo loop con il client live_arturo aperto una sola volta.
    ranges_per_giornata: list[
        tuple[GiroGiornata, str, list[GiroBlocco], list[tuple[int, int]]]
    ] = []
    for gg in giornate_giro:
        blocchi = blocchi_per_giornata.get(gg.id, [])
        if not blocchi:
            continue
        canonica = canonica_per_giornata.get(gg.id)
        validita = (canonica.validita_testo if canonica is not None else None) or "GG"

        ranges = _dp_segmenta_giornata(blocchi, stazioni_cv)
        if ranges is None:
            # Fallback: nessuna segmentazione valida → 1 turno monolitico
            # per quella giornata. L'utente vedrà violazioni cap, segnale
            # che serve un punto CV addizionale o un giro più corto.
            ranges = [(0, len(blocchi) - 1)]
        ranges_per_giornata.append((gg, validita, blocchi, ranges))

    # Sprint 7.10 MR α.5.fix: client httpx condiviso fra heuristic
    # deposito (quality gate vettura) e persistenza (assegnazione
    # vettura al draft). Una sola connessione TLS, ammortizzata sui
    # ~3-5 depositi tipici × N segmenti.
    settings = get_settings()
    live_client = httpx.AsyncClient(timeout=settings.live_arturo_timeout_sec)

    try:
        for gg, validita, blocchi_gg, ranges in ranges_per_giornata:
            for idx_start, idx_end in ranges:
                seg_blocchi = blocchi_gg[idx_start : idx_end + 1]
                primo_blocco = seg_blocchi[0]
                ultimo_blocco = seg_blocchi[-1]
                # Sprint 7.10 MR α.8: stima `ora_apertura_min` (= inizio
                # prestazione del PdC) e `ora_chiusura_min` (= fine
                # servizio) per i quality gate vettura PARTENZA + RIENTRO.
                if primo_blocco.ora_inizio is None:
                    ora_apertura_min = 0
                else:
                    ora_apertura_min = (
                        _t(primo_blocco.ora_inizio)
                        - ACCESSORI_MIN_STANDARD
                        - PRESA_SERVIZIO_MIN
                    ) % (24 * 60)
                if ultimo_blocco.ora_fine is None:
                    ora_chiusura_min = 0
                else:
                    ora_chiusura_min = (
                        _t(ultimo_blocco.ora_fine)
                        + ACCESSORI_MIN_STANDARD
                        + FINE_SERVIZIO_MIN
                    ) % (24 * 60)
                heur = await _scegli_deposito_per_segmento(
                    seg_blocchi,
                    depositi,
                    ora_apertura_min=ora_apertura_min,
                    ora_chiusura_min=ora_chiusura_min,
                    live_client=live_client,
                )
                segmenti_globali.append(
                    _SegmentoTurno(
                        giornata_giro_id=gg.id,
                        numero_giornata=gg.numero_giornata,
                        variante_calendario=validita,
                        blocchi=seg_blocchi,
                        idx_start=idx_start,
                        idx_end=idx_end,
                        deposito_assegnato=heur.depot if heur is not None else None,
                        vettura_pre=heur.vettura_rientro if heur is not None else None,
                        vettura_pre_partenza=(
                            heur.vettura_partenza if heur is not None else None
                        ),
                        dormita_partenza=(
                            heur.dormita_partenza if heur is not None else False
                        ),
                        dormita_rientro=(
                            heur.dormita_rientro if heur is not None else False
                        ),
                    )
                )

        if not segmenti_globali:
            raise GiroVuotoError(f"Giro {giro_id} non ha blocchi validi")

        # Persiste i segmenti come N TurnoPdc accorpati per deposito.
        # Riusa lo stesso live_client per la vettura sull'ultima
        # giornata di ogni TurnoPdc (se vettura_pre già nota viene
        # riusata).
        risultati: list[BuilderTurnoPdcResult] = await _persisti_segmenti(
            session=session,
            azienda_id=azienda_id,
            giro=giro,
            segmenti=segmenti_globali,
            valido_da_eff=valido_da_eff,
            giornate_ids_giro=giornata_ids,
            live_client=live_client,
        )
    finally:
        await live_client.aclose()

    await session.commit()
    return risultati


async def _aggiungi_vettura_partenza(
    *,
    draft: _GiornataPdcDraft,
    depot: Depot,
    treno_pre_calcolato: TrenoVettura | None,
) -> _GiornataPdcDraft:
    """Sprint 7.10 MR α.8: prepende un blocco VETTURA all'inizio del
    primo draft del ciclo per portare il PdC dal depot alla stazione
    di apertura.

    Decisione utente 2026-05-05: *"da Alessandria come posso
    raggiungere VC se il treno parte alle 5? Serve una vettura
    mattutina o una dormita la sera prima"*.

    Algoritmo (idempotente):
    1. Se nessun treno pre-calcolato → ritorna draft invariato (il
       chiamante usa il flag `dormita_partenza` per segnalare che
       il PdC è arrivato la sera prima).
    2. Altrimenti, prepende un blocco ``VETTURA`` PRIMA della
       PRESA, aggiorna ``inizio_prestazione`` alla partenza della
       vettura, e aggiorna ``prestazione_min`` corrispondentemente.

    Niente verifica cap prestazione qui: la vettura partenza è
    "tempo passivo" pre-presa, e il cap si misura da PRESA in poi.
    Lascia gestione cap al builder principale.
    """
    if treno_pre_calcolato is None:
        return draft

    # Costruisci il blocco VETTURA "in partenza" (prima della PRESA).
    blocco_vettura = _BloccoPdcDraft(
        seq=0,  # rinumerato a fine pipeline
        tipo_evento="VETTURA",
        ora_inizio=_from_min(treno_pre_calcolato.partenza_min),
        ora_fine=_from_min(treno_pre_calcolato.arrivo_min),
        durata_min=treno_pre_calcolato.durata_min,
        stazione_da_codice=treno_pre_calcolato.stazione_partenza_codice,
        stazione_a_codice=treno_pre_calcolato.stazione_arrivo_codice,
        accessori_note=(
            f"Vettura partenza dal deposito {depot.codice}: "
            f"treno {treno_pre_calcolato.categoria} "
            f"{treno_pre_calcolato.numero} "
            f"({treno_pre_calcolato.operatore or '—'})"
        ),
    )

    # La PRESA SERVIZIO ora avviene dopo l'arrivo della vettura.
    # `inizio_prestazione` resta quello calcolato dal builder MVP
    # (= primo_treno - ACCp - PRESA), perché la vettura è "viaggio
    # passivo" antecedente. Cambiamo solo l'orario del blocco PRESA
    # se necessario, e aggiorniamo prestazione/blocchi totali.
    nuovi_blocchi = [blocco_vettura, *list(draft.blocchi)]

    # Renumera seq.
    for i, b in enumerate(nuovi_blocchi, start=1):
        b.seq = i

    # `inizio_prestazione` rimane invariato (la vettura è prima della
    # presa, quindi è prestazione "extra" notional). Ma per visibilità
    # operativa, alcune aziende contano il PdC "in turno" già dalla
    # vettura. Per ora teniamo `inizio_prestazione` invariato (= ora
    # presa originale) — il blocco VETTURA è visibile prima nel Gantt.

    return _GiornataPdcDraft(
        numero_giornata=draft.numero_giornata,
        variante_calendario=draft.variante_calendario,
        blocchi=nuovi_blocchi,
        # La stazione di INIZIO del turno è ora il deposito (= dove
        # parte la vettura), perché è da lì che il PdC inizia il
        # tragitto.
        stazione_inizio=treno_pre_calcolato.stazione_partenza_codice,
        stazione_fine=draft.stazione_fine,
        inizio_prestazione=draft.inizio_prestazione,
        fine_prestazione=draft.fine_prestazione,
        prestazione_min=draft.prestazione_min,
        condotta_min=draft.condotta_min,
        refezione_min=draft.refezione_min,
        is_notturno=draft.is_notturno,
        violazioni=draft.violazioni,
    )


async def _aggiungi_vettura_rientro(
    *,
    draft: _GiornataPdcDraft,
    depot: Depot,
    client: httpx.AsyncClient,
    treno_pre_calcolato: TrenoVettura | None = None,
) -> tuple[_GiornataPdcDraft, TrenoVettura | None]:
    """Sprint 7.10 MR α.5: estende l'ultima giornata del turno con un
    blocco VETTURA per riportare il PdC al deposito.

    Algoritmo:
    1. Se ``draft.stazione_fine == depot.stazione_principale_codice``
       → niente vettura serve (PdC chiude in casa). Ritorna
       ``(draft, None)``.
    2. Altrimenti, chiama ``trova_treno_vettura(stazione_fine,
       depot.stazione_principale, ora_fine + buffer)``.
    3. Se trovato un treno → aggiunge un blocco ``VETTURA`` al
       ``draft.blocchi`` (dopo il blocco FINE), aggiorna
       ``fine_prestazione`` all'arrivo della vettura, e
       ``prestazione_min += vettura.durata_min + (attesa)``.
    4. Se NON trovato (API down, nessun passante in finestra,
       depot senza stazione popolata) → ritorna ``(draft, None)``.
       Il chiamante può marcarlo come "vettura mancante" nei
       metadata per visibilità del problema.

    NB sul cap prestazione: l'aggiunta della vettura può portare la
    prestazione totale OLTRE il cap normativo (510min std). In tal
    caso aggiunge un'entry alle ``violazioni`` del draft anziché
    rifiutare la vettura — meglio mostrare al pianificatore un
    rientro reale fuori-cap che lasciare il PdC senza rientro.
    """
    if depot.stazione_principale_codice is None:
        return draft, None
    if draft.stazione_fine == depot.stazione_principale_codice:
        # Già a casa, no vettura.
        return draft, None
    if draft.stazione_fine is None:
        return draft, None

    # Sprint 7.10 MR α.5.fix: se il treno è già stato pre-calcolato
    # dalla heuristic deposito (quality gate vettura), riusalo
    # direttamente senza una seconda chiamata API.
    if treno_pre_calcolato is not None:
        treno: TrenoVettura | None = treno_pre_calcolato
    else:
        ora_fine_min = _t(draft.fine_prestazione)
        treno = await trova_treno_vettura(
            stazione_partenza_codice=draft.stazione_fine,
            stazione_arrivo_codice=depot.stazione_principale_codice,
            ora_min_partenza=ora_fine_min + VETTURA_GAP_PRE_MIN,
            max_attesa_min=VETTURA_ATTESA_MAX_MIN,
            client=client,
        )
    if treno is None:
        return draft, None

    # Costruisci il blocco VETTURA. La sequenza delle stazioni nel
    # blocco è (stazione_chiusura_PdC → deposito), il PdC viaggia
    # come passeggero.
    blocco_vettura = _BloccoPdcDraft(
        seq=draft.blocchi[-1].seq + 1 if draft.blocchi else 1,
        tipo_evento="VETTURA",
        ora_inizio=_from_min(treno.partenza_min),
        ora_fine=_from_min(treno.arrivo_min),
        durata_min=treno.durata_min,
        stazione_da_codice=treno.stazione_partenza_codice,
        stazione_a_codice=treno.stazione_arrivo_codice,
        accessori_note=(
            f"Rientro deposito {depot.codice}: treno {treno.categoria} "
            f"{treno.numero} ({treno.operatore or '—'})"
        ),
    )
    nuovi_blocchi = list(draft.blocchi) + [blocco_vettura]

    # Aggiorna prestazione e fine_prestazione del draft.
    # Prestazione = (treno.arrivo_min - inizio_prestazione) gestendo
    # wrap-mezzanotte. Approssimazione: se arrivo > inizio, ok; se
    # arrivo < inizio (cross-mezzanotte) aggiungi 24h.
    inizio_prest_min = _t(draft.inizio_prestazione)
    nuova_fine_min = treno.arrivo_min
    if nuova_fine_min < inizio_prest_min:
        nuova_prest = (24 * 60 - inizio_prest_min) + nuova_fine_min
    else:
        nuova_prest = nuova_fine_min - inizio_prest_min

    nuove_violazioni = list(draft.violazioni)
    cap_prest = (
        PRESTAZIONE_MAX_NOTTURNO if draft.is_notturno else PRESTAZIONE_MAX_STANDARD
    )
    if nuova_prest > cap_prest and not any(
        v.startswith("prestazione_max") for v in nuove_violazioni
    ):
        nuove_violazioni.append(
            f"prestazione_max:{nuova_prest}>{cap_prest}min(con_vettura_rientro)"
        )

    nuovo_draft = _GiornataPdcDraft(
        numero_giornata=draft.numero_giornata,
        variante_calendario=draft.variante_calendario,
        blocchi=nuovi_blocchi,
        stazione_inizio=draft.stazione_inizio,
        # La stazione di chiusura ora è il deposito.
        stazione_fine=depot.stazione_principale_codice,
        inizio_prestazione=draft.inizio_prestazione,
        fine_prestazione=_from_min(treno.arrivo_min),
        prestazione_min=nuova_prest,
        condotta_min=draft.condotta_min,  # vettura non è condotta
        refezione_min=draft.refezione_min,
        is_notturno=draft.is_notturno,
        violazioni=nuove_violazioni,
    )
    return nuovo_draft, treno


async def _prossimo_progressivo_per_deposito(
    session: AsyncSession,
    azienda_id: int,
    deposito_pdc_id: int,
) -> int:
    """Sprint 7.10 MR α.4 (entry 154): prossimo NNN del codice turno.

    Restituisce ``count(turni_pdc esistenti del deposito) + 1``.
    Idempotente nei limiti della sessione: il chiamante ha già
    cancellato i turni del giro corrente prima di questa funzione,
    quindi il count non li include.

    Numerazione progressiva *non riciclata*: se un deposito ha mai
    avuto 50 turni e ne sono stati cancellati 10, il prossimo è 51.
    Evita ambiguità di codici riassegnati nel tempo.
    """
    from sqlalchemy import func

    count = (
        await session.execute(
            select(func.count(TurnoPdc.id)).where(
                TurnoPdc.azienda_id == azienda_id,
                TurnoPdc.deposito_pdc_id == deposito_pdc_id,
            )
        )
    ).scalar_one()
    return int(count) + 1


async def _persisti_segmenti(
    *,
    session: AsyncSession,
    azienda_id: int,
    giro: GiroMateriale,
    segmenti: list[_SegmentoTurno],
    valido_da_eff: date,
    giornate_ids_giro: list[int],
    live_client: httpx.AsyncClient,
) -> list[BuilderTurnoPdcResult]:
    """Sprint 7.10 MR α.4 (entry 154): accorpa per deposito + codice nuovo.

    Decisione utente 2026-05-05: *"il deposito è solo uno per ogni
    località, crea un unico file"* + *"non serve riportare il nome
    del turno materiale, sono due cose separate"*.

    Quindi:
    - N segmenti DP con lo stesso deposito → **1 TurnoPdc** con N
      giornate (ciclo N), non N TurnoPdc indipendenti.
    - Codice: ``T-{depot.codice}-{NNN:03d}`` con NNN progressivo
      *globale* per (azienda, deposito). Niente più riferimento al
      numero turno del giro materiale.

    Segmenti SENZA deposito (la tratta non passa da alcun depot
    popolato) restano persistiti uno per uno con codice
    ``T-LEGACY-{giro_id}-{seq:02d}`` — segnale visibile al
    pianificatore che la tratta non ha copertura CV soddisfacente.
    """
    # 1. Costruisco i drafts in memoria, raggruppandoli per deposito.
    drafts_per_deposito: dict[
        int | None, list[tuple[_SegmentoTurno, _GiornataPdcDraft]]
    ] = {}
    for seg in segmenti:
        depot_key = (
            seg.deposito_assegnato.id if seg.deposito_assegnato is not None else None
        )
        draft = _build_giornata_pdc(
            numero_giornata=1,  # placeholder, rinumerato sotto
            variante_calendario=seg.variante_calendario,
            blocchi_giro=seg.blocchi,
        )
        if draft is None:
            continue
        drafts_per_deposito.setdefault(depot_key, []).append((seg, draft))

    risultati: list[BuilderTurnoPdcResult] = []

    # Indice depot by stazione_principale_codice — riusato per
    # ri-assegnare i segmenti "FT" al depot della stazione di partenza.
    by_stazione: dict[str, Depot] = {}
    for d_iter in (s.deposito_assegnato for s in segmenti if s.deposito_assegnato is not None):
        if d_iter.stazione_principale_codice is not None:
            by_stazione[d_iter.stazione_principale_codice] = d_iter
    # Carica tutti i depositi attivi (la heuristic ne aveva la lista
    # piena ma qui abbiamo solo quelli vincenti). Ne servono di più
    # per il match FT su stazione di partenza.
    all_depots = list(
        (
            await session.execute(
                select(Depot).where(
                    Depot.azienda_id == azienda_id,
                    Depot.is_attivo,
                    Depot.tipi_personale_ammessi == "PdC",
                )
            )
        ).scalars()
    )
    for d_iter in all_depots:
        if d_iter.stazione_principale_codice is not None:
            by_stazione.setdefault(d_iter.stazione_principale_codice, d_iter)

    # 2. Per ogni deposito, persisti 1 TurnoPdc aggregando le sue
    #    giornate. Per `None` (= heuristic non ha trovato depot
    #    adatto) faccio 1 turno "Fuori Turno" (T-FT) per segmento
    #    assegnato al depot della stazione di partenza, se esiste.
    # Il `live_client` è ora passato dal chiamante (genera_turni_pdc_multi),
    # così la heuristic deposito (che ne ha già fatto uso per il
    # quality gate vettura) e la persistenza condividono la stessa
    # connessione TLS.
    for depot_key, lista in drafts_per_deposito.items():
        if depot_key is None:
            # Sprint 7.10 MR α.8: T-LEGACY → T-FT (Fuori Turno).
            # Decisione utente 2026-05-05: *"non creare mai LEGACY,
            # rinominalo come FUORI TURNO (FT) e assegnalo al deposito
            # di appartenenza dove inizia il treno"*.
            for idx, (seg, draft) in enumerate(lista, start=1):
                draft.numero_giornata = 1
                # Cerca il depot della stazione di PARTENZA del primo
                # blocco del segmento. Se non popolato come depot,
                # fallback a codice senza depot.
                stazione_partenza = (
                    seg.blocchi[0].stazione_da_codice if seg.blocchi else None
                )
                depot_partenza = (
                    by_stazione.get(stazione_partenza)
                    if stazione_partenza is not None
                    else None
                )
                if depot_partenza is not None:
                    nnn_ft = await _prossimo_progressivo_per_deposito(
                        session, azienda_id, depot_partenza.id
                    )
                    codice = f"T-FT-{depot_partenza.codice}-{nnn_ft:03d}"[:50]
                    stazione_sede = (
                        depot_partenza.stazione_principale_codice
                        if depot_partenza.stazione_principale_codice is not None
                        else draft.stazione_inizio
                    )
                else:
                    codice = f"T-FT-{giro.id}-{idx:02d}"[:50]
                    stazione_sede = draft.stazione_inizio
                risultato = await _persisti_un_turno_pdc(
                    session=session,
                    azienda_id=azienda_id,
                    giro=giro,
                    drafts=[draft],
                    codice=codice,
                    stazione_sede=stazione_sede,
                    valido_da_eff=valido_da_eff,
                    giornate_ids=giornate_ids_giro,
                    extra_metadata={
                        "fr_giornate": [],
                        "is_ramo_split": False,
                        "fr_cap_violazioni": [],
                        "multi_turno_giornata_origine": seg.numero_giornata,
                        "multi_turno_idx_start": seg.idx_start,
                        "multi_turno_idx_end": seg.idx_end,
                        "multi_turno_seq": idx,
                        "is_fuori_turno": True,
                        "fuori_turno_motivo": (
                            "tratta_non_coperta_da_vetture: nessun depot ha "
                            "rientro fattibile via API live arturo entro "
                            f"{VETTURA_ATTESA_MAX_MIN}min. Pianificatore deve "
                            "decidere FR / dormita / assegnazione manuale."
                        ),
                        "builder_strategy": "multi_turno_dp_alpha8_ft",
                    },
                    depot_target=depot_partenza,
                    violazioni_ciclo_extra=[],
                )
                risultati.append(risultato)
            continue

        # Deposito reale: accorpa N segmenti in 1 TurnoPdc.
        depot = lista[0][0].deposito_assegnato
        assert depot is not None and depot.id == depot_key

        nnn = await _prossimo_progressivo_per_deposito(
            session, azienda_id, depot_key
        )
        codice = f"T-{depot.codice}-{nnn:03d}"[:50]

        # Ordina per (giornata-giro origine, idx_start) → giornate
        # del TurnoPdc in ordine cronologico del giro.
        lista.sort(key=lambda x: (x[0].numero_giornata, x[0].idx_start))

        # Rinumera giornata=1..N nel ciclo del TurnoPdc.
        drafts_finali: list[_GiornataPdcDraft] = []
        meta_giornate: list[dict[str, int]] = []
        for i, (seg, draft) in enumerate(lista, start=1):
            draft.numero_giornata = i
            drafts_finali.append(draft)
            meta_giornate.append(
                {
                    "numero_giornata_pdc": i,
                    "giornata_giro_origine": seg.numero_giornata,
                    "idx_start": seg.idx_start,
                    "idx_end": seg.idx_end,
                }
            )

        # Sprint 7.10 MR α.5: VETTURA passiva sull'ultima giornata del
        # ciclo (= dove il PdC chiude prima del riposo settimanale). Se
        # l'ultima giornata chiude in stazione ≠ deposito, prova a
        # cercare un treno passante via API live arturo. Aggiunge un
        # blocco VETTURA al draft, oppure flagga "vettura non trovata"
        # nei metadata se non c'è alcun passante in finestra.
        vettura_meta: dict[str, object] | None = None
        vettura_partenza_meta: dict[str, object] | None = None
        # Sprint 7.10 MR α.8: VETTURA PARTENZA sul PRIMO draft del
        # ciclo (= prima giornata operativa). Se la heuristic ha
        # trovato un treno mattutino dal depot alla stazione di
        # apertura, lo prependiamo prima della PRESA del draft.
        primo_seg = lista[0][0]
        if drafts_finali and primo_seg.vettura_pre_partenza is not None:
            primo_draft_v = await _aggiungi_vettura_partenza(
                draft=drafts_finali[0],
                depot=depot,
                treno_pre_calcolato=primo_seg.vettura_pre_partenza,
            )
            drafts_finali[0] = primo_draft_v
            tp = primo_seg.vettura_pre_partenza
            vettura_partenza_meta = {
                "treno_numero": tp.numero,
                "treno_categoria": tp.categoria,
                "operatore": tp.operatore,
                "stazione_partenza": tp.stazione_partenza_codice,
                "stazione_arrivo": tp.stazione_arrivo_codice,
                "partenza_min": tp.partenza_min,
                "arrivo_min": tp.arrivo_min,
                "durata_min": tp.durata_min,
            }
        elif primo_seg.dormita_partenza:
            vettura_partenza_meta = {
                "treno_numero": None,
                "motivo": (
                    "dormita_partenza: nessuna vettura mattutina dal "
                    f"deposito {depot.codice} alla stazione di apertura. "
                    "Il PdC è arrivato la sera prima (FR)."
                ),
            }

        if drafts_finali:
            ultimo_idx = len(drafts_finali) - 1
            ultimo_draft = drafts_finali[ultimo_idx]
            # Sprint 7.10 MR α.5.fix: se la heuristic deposito ha già
            # pre-calcolato la vettura per questo segmento (quality gate),
            # riusala direttamente. La vettura è quella dell'ULTIMO
            # segmento del deposito (= quello che chiude il ciclo).
            ultimo_seg = lista[-1][0]
            treno_pre = ultimo_seg.vettura_pre
            ultimo_aggiornato, treno = await _aggiungi_vettura_rientro(
                draft=ultimo_draft,
                depot=depot,
                client=live_client,
                treno_pre_calcolato=treno_pre,
            )
            drafts_finali[ultimo_idx] = ultimo_aggiornato
            if treno is not None:
                vettura_meta = {
                    "treno_numero": treno.numero,
                    "treno_categoria": treno.categoria,
                    "operatore": treno.operatore,
                    "stazione_partenza": treno.stazione_partenza_codice,
                    "stazione_arrivo": treno.stazione_arrivo_codice,
                    "partenza_min": treno.partenza_min,
                    "arrivo_min": treno.arrivo_min,
                    "durata_min": treno.durata_min,
                }
            elif ultimo_seg.dormita_rientro:
                # Sprint 7.10 MR α.8: dormita finale (FR) — PdC dorme
                # in stazione di chiusura, rientro il giorno dopo o
                # nel ciclo successivo.
                vettura_meta = {
                    "treno_numero": None,
                    "stazione_partenza": ultimo_draft.stazione_fine,
                    "stazione_arrivo": depot.stazione_principale_codice,
                    "motivo": (
                        "dormita_rientro: nessun treno passante in "
                        f"finestra {VETTURA_ATTESA_MAX_MIN}min. "
                        "Il PdC fa FR, rientra il giorno dopo."
                    ),
                }
            elif (
                ultimo_draft.stazione_fine != depot.stazione_principale_codice
                and depot.stazione_principale_codice is not None
            ):
                # Edge case: heuristic non ha pre-calcolato vettura E
                # nemmeno dormita (caso raro, e.g. depot scelto da
                # logica non quality-gated). Fallback informativo.
                vettura_meta = {
                    "treno_numero": None,
                    "stazione_partenza": ultimo_draft.stazione_fine,
                    "stazione_arrivo": depot.stazione_principale_codice,
                    "motivo": (
                        "vettura_non_trovata: nessun treno passante in "
                        f"finestra {VETTURA_ATTESA_MAX_MIN}min, FR consigliato"
                    ),
                }

        stazione_sede = (
            depot.stazione_principale_codice
            if depot.stazione_principale_codice is not None
            else drafts_finali[0].stazione_inizio
        )

        risultato = await _persisti_un_turno_pdc(
            session=session,
            azienda_id=azienda_id,
            giro=giro,
            drafts=drafts_finali,
            codice=codice,
            stazione_sede=stazione_sede,
            valido_da_eff=valido_da_eff,
            giornate_ids=giornate_ids_giro,
            extra_metadata={
                "fr_giornate": [],
                "is_ramo_split": False,
                "fr_cap_violazioni": [],
                "multi_turno_progressivo": nnn,
                "multi_turno_giornate": meta_giornate,
                "vettura_rientro": vettura_meta,
                "vettura_partenza": vettura_partenza_meta,
                "builder_strategy": "multi_turno_dp_alpha8",
            },
            depot_target=depot,
            violazioni_ciclo_extra=[],
        )
        risultati.append(risultato)

    # NB: il `live_client` è chiuso dal chiamante (genera_turni_pdc_multi)
    # nel suo blocco `finally`. Non chiuderlo qui o lo si renderebbe
    # inutilizzabile per altre chiamate.
    return risultati


__all__ = [
    "DepositoPdcNonTrovatoError",
    "GiroNonTrovatoError",
    "GiroVuotoError",
    "genera_turni_pdc_multi",
]
