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

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.domain.builder_pdc.builder import (
    CONDOTTA_MAX_MIN,
    PRESTAZIONE_MAX_NOTTURNO,
    PRESTAZIONE_MAX_STANDARD,
    BuilderTurnoPdcResult,
    DepositoPdcNonTrovatoError,
    GiroNonTrovatoError,
    GiroVuotoError,
    _build_giornata_pdc,
    _GiornataPdcDraft,
    _persisti_un_turno_pdc,
)
from colazione.domain.builder_pdc.split_cv import lista_stazioni_cv_ammesse
from colazione.models.anagrafica import Depot
from colazione.models.giri import (
    GiroBlocco,
    GiroGiornata,
    GiroMateriale,
    GiroVariante,
)
from colazione.models.turni_pdc import TurnoPdc

# Penalty enorme per soluzioni invalide nel DP (cap superato senza
# alternative). Usato come "infinito" — un singolo step di violazione
# ha più peso di un'intera giornata coperta da turni puliti.
_INVALIDO = 10**9


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


def _scegli_deposito_per_segmento(
    blocchi_segmento: list[GiroBlocco],
    depositi: list[Depot],
) -> Depot | None:
    """Heuristic post-DP: scegli il miglior deposito per il segmento.

    Strategia (in ordine di preferenza):

    1. Deposito la cui ``stazione_principale_codice`` coincide con la
       ``stazione_da_codice`` del primo blocco del segmento. È il
       caso ideale: il PdC inizia da casa.
    2. Deposito con stazione_principale = stazione_a del primo blocco
       o stazione_da/a di un blocco intermedio. Sempre nessun FR
       perché tocca il deposito durante il segmento.
    3. Deposito con stazione_principale = stazione_a dell'ultimo blocco
       del segmento. Il PdC parte da deposito X, ma chiude in casa Y.
       FR per X (notte fuori), casa per Y al mattino successivo.
    4. Fallback: il primo deposito con stazione_principale popolata
       (= almeno il calcolo FR sarà sensato a posteriori).
    5. Fallback finale: ``None`` (legacy, sede = stazione del materiale).

    Per il MVP α.2 limito alla strategia 1+2+3+5 (skip 4): se nessun
    deposito sta lungo la tratta del segmento, ritorno None — il
    builder usa il fallback legacy e l'utente vedrà che quel turno
    ha "Sede PdC: legacy", segnale che la copertura CV è incompleta
    su quella tratta.
    """
    if not blocchi_segmento or not depositi:
        return None

    # Raccogli tutte le stazioni "toccate" dal segmento (ordine: from
    # del primo > a di tutti i blocchi).
    stazioni_toccate: list[str] = []
    primo = blocchi_segmento[0]
    if primo.stazione_da_codice is not None:
        stazioni_toccate.append(primo.stazione_da_codice)
    for b in blocchi_segmento:
        if b.stazione_a_codice is not None and b.stazione_a_codice not in stazioni_toccate:
            stazioni_toccate.append(b.stazione_a_codice)

    # Indice deposit by stazione_principale_codice per lookup O(1).
    by_stazione: dict[str, Depot] = {
        d.stazione_principale_codice: d
        for d in depositi
        if d.stazione_principale_codice is not None
    }

    # Strategia 1: stazione_da del primo blocco (= avvio "in casa").
    if primo.stazione_da_codice is not None and primo.stazione_da_codice in by_stazione:
        return by_stazione[primo.stazione_da_codice]

    # Strategia 2+3: una qualsiasi stazione toccata corrisponde a un depot.
    for s in stazioni_toccate:
        if s in by_stazione:
            return by_stazione[s]

    # Nessun match — il segmento non passa da alcun deposito popolato.
    return None


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

        for idx_start, idx_end in ranges:
            seg_blocchi = blocchi[idx_start : idx_end + 1]
            depot = _scegli_deposito_per_segmento(seg_blocchi, depositi)
            segmenti_globali.append(
                _SegmentoTurno(
                    giornata_giro_id=gg.id,
                    numero_giornata=gg.numero_giornata,
                    variante_calendario=validita,
                    blocchi=seg_blocchi,
                    idx_start=idx_start,
                    idx_end=idx_end,
                    deposito_assegnato=depot,
                )
            )

    if not segmenti_globali:
        raise GiroVuotoError(f"Giro {giro_id} non ha blocchi validi")

    # Persiste ogni segmento come 1 TurnoPdc autonomo (1 giornata, ciclo=1).
    risultati: list[BuilderTurnoPdcResult] = await _persisti_segmenti(
        session=session,
        azienda_id=azienda_id,
        giro=giro,
        segmenti=segmenti_globali,
        valido_da_eff=valido_da_eff,
        giornate_ids_giro=giornata_ids,
    )

    await session.commit()
    return risultati


async def _persisti_segmenti(
    *,
    session: AsyncSession,
    azienda_id: int,
    giro: GiroMateriale,
    segmenti: list[_SegmentoTurno],
    valido_da_eff: date,
    giornate_ids_giro: list[int],
) -> list[BuilderTurnoPdcResult]:
    """Persiste 1 TurnoPdc per ogni segmento.

    Codice turno: ``T-{depot.codice}-{giro.numero_turno}-G{n_giornata}-S{seq}``
    (con depot) oppure ``T-{giro.numero_turno}-G{n_giornata}-S{seq}`` (legacy
    senza depot).

    Riusa ``_persisti_un_turno_pdc`` esistente (Sprint 7.4) passando
    una lista di drafts di 1 elemento per ogni segmento → ogni
    turno_pdc ha 1 giornata sola (ciclo=1) → modello "PdC fa quel
    turno una sola volta nel ciclo del materiale".
    """
    risultati: list[BuilderTurnoPdcResult] = []
    # Conteggio sotto-segmenti per giornata, per il suffisso S{seq}.
    seq_per_giornata: dict[int, int] = {}

    for seg in segmenti:
        seq_per_giornata[seg.numero_giornata] = (
            seq_per_giornata.get(seg.numero_giornata, 0) + 1
        )
        seq_idx = seq_per_giornata[seg.numero_giornata]
        depot = seg.deposito_assegnato

        # Costruisco il draft sul segmento, rinumerando giornata=1
        # (il TurnoPdc ha 1 sola giornata, ciclo=1).
        draft = _build_giornata_pdc(
            numero_giornata=1,
            variante_calendario=seg.variante_calendario,
            blocchi_giro=seg.blocchi,
        )
        if draft is None:
            continue

        codice_pieces = ["T"]
        if depot is not None:
            codice_pieces.append(depot.codice)
        codice_pieces.append(giro.numero_turno or f"GIRO{giro.id}")
        codice_pieces.append(f"G{seg.numero_giornata:02d}")
        codice_pieces.append(f"S{seq_idx}")
        codice = "-".join(codice_pieces)[:50]

        # Stazione sede effettiva: se ho depot con stazione popolata,
        # uso quella; altrimenti la stazione di partenza del segmento
        # (legacy fallback, NORMATIVA-PDC §10 dice che ogni PdC ha
        # una sede di residenza).
        stazione_sede = (
            depot.stazione_principale_codice
            if depot is not None and depot.stazione_principale_codice is not None
            else draft.stazione_inizio
        )

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
                "multi_turno_seq": seq_idx,
                "builder_strategy": "multi_turno_dp_alpha2",
            },
            depot_target=depot,
            violazioni_ciclo_extra=[],
        )
        risultati.append(risultato)

    return risultati


__all__ = [
    "DepositoPdcNonTrovatoError",
    "GiroNonTrovatoError",
    "GiroVuotoError",
    "genera_turni_pdc_multi",
]
