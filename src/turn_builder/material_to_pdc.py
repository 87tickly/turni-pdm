"""
Builder turno materiale → turni PdC.

Implementa l'algoritmo in `docs/ALGORITMO-BUILDER.md` rispettando la
normativa in `docs/NORMATIVA-PDC.md`.

Contenuti:
- Tipi: Segment, EventoPdC, PdC, MaterialPool + utility tempo
- Logica: build_single_pdc, cover_material
- Validazione: validate_pdc, gap_rule

Convenzione tempi: tutti gli orari sono espressi in minuti dalla
mezzanotte (0-1439). Es. 04:10 = 250.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from src import constants as C


# ---------------------------------------------------------------------------
# Utility tempo
# ---------------------------------------------------------------------------


def hhmm_to_min(hhmm: str) -> int:
    """Converte stringa "HH:MM" in minuti dalla mezzanotte.

    >>> hhmm_to_min("04:10")
    250
    >>> hhmm_to_min("00:00")
    0
    >>> hhmm_to_min("23:59")
    1439
    """
    h_str, m_str = hhmm.strip().split(":")
    h, m = int(h_str), int(m_str)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f"orario fuori range: {hhmm}")
    return h * 60 + m


def min_to_hhmm(m: int) -> str:
    """Converte minuti in "HH:MM" normalizzando modulo 24h.

    Accetta anche valori negativi o > 1439: normalizza al giorno
    solare. Utile quando la presa servizio del PdC cade "tecnicamente"
    il giorno precedente (es. 23:45 = -15 rispetto alla mezzanotte del
    giorno principale).

    >>> min_to_hhmm(250)
    '04:10'
    >>> min_to_hhmm(0)
    '00:00'
    >>> min_to_hhmm(-15)
    '23:45'
    >>> min_to_hhmm(1440 + 30)
    '00:30'
    """
    m = m % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


# ---------------------------------------------------------------------------
# Segment — un treno (o materiale vuoto) del turno materiale
# NORMATIVA-PDC.md §1, §8, §13
# ---------------------------------------------------------------------------


class SegmentKind(str, Enum):
    """Tipo di segmento sul turno materiale."""

    COMMERCIALE = "commerciale"
    """Treno con passeggeri, traccia RFI. Orari su ARTURO."""

    VUOTO_I = "vuoto_i"
    """Treno senza passeggeri, traccia RFI con suffisso "i" (§1).
    Non presente su ARTURO. Orari leggibili dal PDF turno materiale.
    Esempi: 28335i, 28371i."""

    VUOTO_U = "vuoto_u"
    """Materiale vuoto con numero aziendale U**** (§8.7).
    Invisibile su PDF e ARTURO. Orari calcolati: es. FIOz→MiCertosa
    = 7 min dentro ACCp, partenza = arrivo_RFI − 7."""


@dataclass(frozen=True)
class Segment:
    """Un segmento del turno materiale.

    Il confronto/identità si basa su tutti i campi (dataclass default).
    Usabile come chiave dict / elemento set.
    """

    numero: str
    kind: SegmentKind
    da_stazione: str
    a_stazione: str
    partenza_min: int
    arrivo_min: int

    @property
    def durata_min(self) -> int:
        """Durata del segmento in minuti (può andare oltre mezzanotte;
        in tal caso il chiamante normalizza separatamente)."""
        return self.arrivo_min - self.partenza_min

    def __repr__(self) -> str:
        return (
            f"Segment({self.numero} {self.kind.value} "
            f"{self.da_stazione}→{self.a_stazione} "
            f"{min_to_hhmm(self.partenza_min)}→{min_to_hhmm(self.arrivo_min)})"
        )


# ---------------------------------------------------------------------------
# Pool di segmenti — §15 NORMATIVA (no doppioni)
# ---------------------------------------------------------------------------


@dataclass
class MaterialPool:
    """Pool dei segmenti non ancora assegnati a un PdC.

    Implementa il vincolo di unicità §15: ogni segmento usato da un
    PdC esce dalla pool. A fine costruzione la pool deve essere vuota.
    """

    segments: list[Segment] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.segments

    def first(self) -> Optional[Segment]:
        """Primo segmento disponibile, per orario di partenza crescente."""
        if not self.segments:
            return None
        return min(self.segments, key=lambda s: s.partenza_min)

    def remove(self, seg: Segment) -> None:
        """Rimuove il segmento dalla pool. KeyError se non presente."""
        self.segments.remove(seg)

    def remove_many(self, segs: list[Segment]) -> None:
        for s in segs:
            self.remove(s)

    def next_same_material(
        self, seg: Segment, max_gap_min: int = 300
    ) -> Optional[Segment]:
        """Prossimo segmento che continua logicamente dopo `seg`:
        - stessa stazione (`a_stazione == next.da_stazione`), oppure
          la partenza è nella stessa stazione con gap ragionevole.
        - partenza >= seg.arrivo_min
        - gap <= max_gap_min (default 5h).

        Il successivo ≠ `seg`.
        """
        candidates = [
            s
            for s in self.segments
            if s is not seg
            and s.da_stazione == seg.a_stazione
            and s.partenza_min >= seg.arrivo_min
            and (s.partenza_min - seg.arrivo_min) <= max_gap_min
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda s: s.partenza_min)


# ---------------------------------------------------------------------------
# EventoPdC — unità elementare della timeline di un PdC
# NORMATIVA-PDC.md §3, §4, §5, §6, §7, §8
# ---------------------------------------------------------------------------


class EventoKind(str, Enum):
    PRESA_SERVIZIO = "presa_servizio"   # §3.2: inizio turno
    FINE_SERVIZIO = "fine_servizio"     # §3.2: fine turno

    TAXI = "taxi"                        # §8.5.1: deposito ↔ impianto
    VETTURA = "vettura"                  # §7: passivo su treno commerciale
    MM = "mm"                            # §7.2: metropolitana

    ACCP = "accp"                        # §3.3: accessorio partenza
    ACCA = "acca"                        # §3.3: accessorio arrivo
    CONDOTTA = "condotta"                # tempo guida treno

    PK_ARRIVO = "pk_arrivo"              # §4.4: parking in arrivo (20')
    PK_PARTENZA = "pk_partenza"          # §4.4: parking in partenza (20')
    BUCO = "buco"                        # §4.2: gap utilizzabile
    REFEZ = "refez"                      # §4.1: refezione 30'

    CVA = "cva"                          # §5: cambio volante in arrivo
    CVP = "cvp"                          # §5: cambio volante in partenza


@dataclass(frozen=True)
class EventoPdC:
    """Singolo evento della timeline PdC.

    Un solo record per tutti i tipi; campi non applicabili restano ai
    default. Lo switch semantico si fa su `kind`.
    """

    kind: EventoKind
    inizio_min: int
    fine_min: int
    stazione: str = ""          # dove avviene (o stazione di partenza)
    stazione_a: str = ""         # destinazione (per taxi/vettura/condotta)
    segment: Optional[Segment] = None  # se condotta/vettura su un segmento
    treno: str = ""              # numero treno (ridondante con segment.numero)
    note: str = ""

    @property
    def durata_min(self) -> int:
        return self.fine_min - self.inizio_min


# ---------------------------------------------------------------------------
# PdC — un turno PdC completo
# ---------------------------------------------------------------------------


@dataclass
class PdC:
    """Un turno PdC: deposito di sede + timeline di eventi.

    La validazione contro la normativa (§14.2) avviene esternamente
    (`src/validator/rules.py::validate_pdc`, step 3).
    """

    deposito: str
    eventi: list[EventoPdC] = field(default_factory=list)

    # ── Proiezioni temporali ──────────────────────────────────────

    @property
    def presa_servizio_min(self) -> Optional[int]:
        """Orario presa servizio (primo evento PRESA_SERVIZIO)."""
        for e in self.eventi:
            if e.kind == EventoKind.PRESA_SERVIZIO:
                return e.inizio_min
        # Fallback: inizio del primo evento se PRESA_SERVIZIO non esplicito
        if self.eventi:
            return self.eventi[0].inizio_min
        return None

    @property
    def fine_servizio_min(self) -> Optional[int]:
        """Orario fine servizio (ultimo evento FINE_SERVIZIO o ultimo evento)."""
        for e in reversed(self.eventi):
            if e.kind == EventoKind.FINE_SERVIZIO:
                return e.fine_min
        if self.eventi:
            return self.eventi[-1].fine_min
        return None

    @property
    def prestazione_min(self) -> int:
        """Durata totale del turno in minuti (fine − inizio)."""
        s = self.presa_servizio_min
        e = self.fine_servizio_min
        if s is None or e is None:
            return 0
        return e - s

    @property
    def condotta_min(self) -> int:
        """Somma delle durate dei segmenti di condotta."""
        return sum(
            e.durata_min for e in self.eventi if e.kind == EventoKind.CONDOTTA
        )

    # ── Accesso ai segmenti usati (§15 unicità) ───────────────────

    @property
    def segmenti_condotta(self) -> list[Segment]:
        """Segmenti del materiale condotti dal PdC."""
        return [e.segment for e in self.eventi
                if e.kind == EventoKind.CONDOTTA and e.segment is not None]

    @property
    def segmenti_vettura(self) -> list[Segment]:
        """Segmenti su cui il PdC viaggia passivo."""
        return [e.segment for e in self.eventi
                if e.kind == EventoKind.VETTURA and e.segment is not None]

    @property
    def segmenti_usati(self) -> list[Segment]:
        """Tutti i segmenti consumati dal PdC (condotta + vettura).

        Questa è la lista da rimuovere dalla pool per §15.
        """
        return self.segmenti_condotta + self.segmenti_vettura

    # ── Refez / finestre ──────────────────────────────────────────

    @property
    def ha_refez(self) -> bool:
        return any(e.kind == EventoKind.REFEZ for e in self.eventi)

    def __repr__(self) -> str:
        s = self.presa_servizio_min
        e = self.fine_servizio_min
        start = min_to_hhmm(s) if s is not None else "??"
        end = min_to_hhmm(e) if e is not None else "??"
        return (
            f"PdC({self.deposito} "
            f"{start}→{end} "
            f"prestazione={self.prestazione_min}' "
            f"condotta={self.condotta_min}' "
            f"eventi={len(self.eventi)})"
        )


# ===========================================================================
# LOGICA DI COSTRUZIONE
# ===========================================================================


# Stazioni ammesse per CV §9.2 NORMATIVA-PDC
# 1. Sedi deposito PdC (dai DEPOSITI)
# 2. MORTARA (deroga)
# 3. Capolinea inversione (sottoinsieme aperto; per ora: TIRANO)
_CV_CAPOLINEA_INVERSIONE = {"TIRANO"}


def _cv_stations() -> set[str]:
    """Insieme delle stazioni in cui è ammesso un CV (§9.2)."""
    stations = set()
    # 1) sedi deposito (nome deposito = nome stazione ammessa)
    for depot in C.DEPOSITI:
        stations.add(depot)
    # 2) capolinea inversione
    stations.update(_CV_CAPOLINEA_INVERSIONE)
    return stations


# ---------------------------------------------------------------------------
# Callable plug: ricerca vettura di rientro (step futuro via ARTURO)
# ---------------------------------------------------------------------------


#: Ritorna (partenza_min, arrivo_min, numero_treno) del primo treno
#: passeggeri utile da `da` a `a` con partenza >= `after_min`.
#: None se nessuno disponibile.
VetturaLookup = Callable[[str, str, int], Optional[tuple[int, int, str]]]


def _fallback_vettura_lookup(
    da: str, a: str, after_min: int
) -> Optional[tuple[int, int, str]]:
    """Stub: nessuna vettura trovata. Il chiamante ripiega su taxi o
    stima. Usato di default quando non si passa un lookup reale."""
    return None


# ---------------------------------------------------------------------------
# Cap prestazione §11.8
# ---------------------------------------------------------------------------


def cap_prestazione(presa_servizio_min: int) -> int:
    """Ritorna il cap di prestazione in minuti per un turno che inizia
    all'orario dato. §11.8 NORMATIVA-PDC."""
    if (
        C.CAP_7H_WINDOW_START_MIN
        <= presa_servizio_min
        <= C.CAP_7H_WINDOW_END_MIN
    ):
        return C.CAP_7H_PRESTAZIONE_MIN
    return C.MAX_PRESTAZIONE_MIN


# ---------------------------------------------------------------------------
# Gap handling §6
# ---------------------------------------------------------------------------


class GapMode(str, Enum):
    """Modalità di gestione di un gap tra due segmenti condotta."""

    CV = "cv"     # Cambio Volante (§5) — richiede incontro 2 PdC
    PK = "pk"     # Parking (§4.4) — flessibile, no incontro
    ACC = "acc"   # ACCa + ACCp completi (§3.3) — 80 min totali


def gap_rule(gap_min: int) -> list[GapMode]:
    """Modalità ammesse per un gap, in ordine di preferenza §6."""
    if gap_min < 65:
        return [GapMode.CV, GapMode.PK]
    if gap_min <= 300:
        return [GapMode.ACC, GapMode.PK]
    # > 300: ACC default, PK opt-in
    return [GapMode.ACC, GapMode.PK]


# ---------------------------------------------------------------------------
# build_single_pdc — costruzione del singolo PdC
# ---------------------------------------------------------------------------


def build_single_pdc(
    primo_seg: Segment,
    pool: MaterialPool,
    deposito: str,
    vettura_lookup: VetturaLookup = _fallback_vettura_lookup,
) -> PdC:
    """Costruisce un PdC a partire da `primo_seg`, consumando segmenti
    dalla `pool`. Segue §3 ALGORITMO-BUILDER.md.

    **Non rimuove** i segmenti dalla pool (è compito del chiamante,
    tipicamente `cover_material`, dopo aver accettato il PdC).

    `vettura_lookup` è il callable per trovare la vettura di rientro
    (default stub: ripiega su TAXI).
    """
    eventi: list[EventoPdC] = []

    # 3.1 Presa servizio e posizionamento iniziale
    deposito_stazione = _stazione_deposito(deposito)
    origine_primo = primo_seg.da_stazione

    # Caso speciale FIOz (impianto aziendale §8.5/§8.5.1)
    if origine_primo in ("FIORENZA", "FIOZ") and primo_seg.kind in (
        SegmentKind.VUOTO_U, SegmentKind.VUOTO_I
    ):
        # Calcolo inverso: ACCp inizio = partenza_commerciale − 40'
        # (ACCp 40' §8.5, include 7' trasferimento U-numero dentro)
        accp_inizio = primo_seg.partenza_min - C.ACCP_STANDARD_MIN
        # Il primo segmento commerciale è preceduto dal U-numero; se
        # primo_seg è il VUOTO_U stesso, ACCp termina a seg.arrivo_min.
        if primo_seg.kind == SegmentKind.VUOTO_U:
            accp_fine = primo_seg.arrivo_min
            accp_inizio = accp_fine - C.ACCP_STANDARD_MIN
        else:
            # Primo è il VUOTO_I "i" sulla traccia RFI; ACCp finisce
            # all'inizio del "i" (il U-numero prima è implicito).
            accp_fine = primo_seg.partenza_min
            accp_inizio = accp_fine - C.ACCP_STANDARD_MIN

        # Taxi deposito → impianto (§8.5.1)
        taxi_fine = accp_inizio
        taxi_inizio = taxi_fine - C.DEPOT_TO_IMPIANTO_TAXI_MIN
        presa_servizio = taxi_inizio - C.PRE_VETTURA_MIN

        eventi.append(
            EventoPdC(
                EventoKind.PRESA_SERVIZIO, presa_servizio, presa_servizio,
                stazione=deposito_stazione,
            )
        )
        eventi.append(
            EventoPdC(
                EventoKind.TAXI, taxi_inizio, taxi_fine,
                stazione=deposito_stazione, stazione_a="FIORENZA",
                note=f"§8.5.1 stima {C.DEPOT_TO_IMPIANTO_TAXI_MIN}'",
            )
        )
        eventi.append(
            EventoPdC(
                EventoKind.ACCP, accp_inizio, accp_fine,
                stazione="FIORENZA",
                note=f"§8.5 ACCp {C.ACCP_STANDARD_MIN}' (include U-numero "
                f"{C.IMPIANTO_TO_RFI_TRANSFER_MIN}')",
            )
        )
    elif origine_primo == deposito_stazione:
        # Deposito = stazione partenza → presa servizio = ACCp start
        accp_inizio = primo_seg.partenza_min - C.ACCP_STANDARD_MIN
        accp_fine = primo_seg.partenza_min
        eventi.append(
            EventoPdC(
                EventoKind.PRESA_SERVIZIO, accp_inizio, accp_inizio,
                stazione=deposito_stazione,
            )
        )
        eventi.append(
            EventoPdC(
                EventoKind.ACCP, accp_inizio, accp_fine,
                stazione=deposito_stazione,
                note=f"§3.3 ACCp {C.ACCP_STANDARD_MIN}'",
            )
        )
    else:
        # Posizionamento: per ora sempre fallback TAXI (tempo fisso §8.5.1
        # esteso a qualunque coppia deposito→origine quando non esistono
        # tracce vettura affidabili — scelta conservativa v1).
        accp_fine = primo_seg.partenza_min
        accp_inizio = accp_fine - C.ACCP_STANDARD_MIN
        taxi_fine = accp_inizio
        taxi_inizio = taxi_fine - C.DEPOT_TO_IMPIANTO_TAXI_MIN
        presa_servizio = taxi_inizio - C.PRE_VETTURA_MIN
        eventi.append(
            EventoPdC(
                EventoKind.PRESA_SERVIZIO, presa_servizio, presa_servizio,
                stazione=deposito_stazione,
            )
        )
        eventi.append(
            EventoPdC(
                EventoKind.TAXI, taxi_inizio, taxi_fine,
                stazione=deposito_stazione, stazione_a=origine_primo,
                note=f"§7.2 fallback taxi {C.DEPOT_TO_IMPIANTO_TAXI_MIN}'",
            )
        )
        eventi.append(
            EventoPdC(
                EventoKind.ACCP, accp_inizio, accp_fine,
                stazione=origine_primo,
            )
        )

    # 3.2 Cap prestazione basato sulla presa servizio effettiva
    presa = eventi[0].inizio_min
    cap = cap_prestazione(presa)

    # 3.3 Loop condotta sui segmenti consecutivi stesso materiale
    segmenti_usati: list[Segment] = []
    seg = primo_seg
    cv_stations = _cv_stations()

    while True:
        # Aggiungi la condotta del segmento corrente
        eventi.append(
            EventoPdC(
                EventoKind.CONDOTTA, seg.partenza_min, seg.arrivo_min,
                stazione=seg.da_stazione, stazione_a=seg.a_stazione,
                segment=seg, treno=seg.numero,
            )
        )
        segmenti_usati.append(seg)

        # Proietta la chiusura se fermo qui
        proj = _proietta_fine(
            eventi, seg, deposito, cap, vettura_lookup
        )
        if proj is None:
            # Nessuna chiusura possibile, tronca catena
            break

        fine_min, chiusura_eventi, ok = proj

        # Verifica vincoli HARD (cap prestazione, condotta)
        condotta_fin = sum(
            e.durata_min for e in eventi
            if e.kind == EventoKind.CONDOTTA
        )
        prestazione_fin = fine_min - presa

        if prestazione_fin > cap:
            # Rimuovi ultimo segmento, chiudi prima
            eventi.pop()
            segmenti_usati.pop()
            seg_prev = segmenti_usati[-1] if segmenti_usati else None
            if seg_prev is None:
                # Nemmeno il primo segmento entra: PdC infattibile
                break
            seg = seg_prev
            break
        if condotta_fin > C.MAX_CONDOTTA_MIN:
            eventi.pop()
            segmenti_usati.pop()
            seg_prev = segmenti_usati[-1] if segmenti_usati else None
            if seg_prev is None:
                break
            seg = seg_prev
            break
        # v1: il builder non sa ancora inserire REFEZ. Tronco se la
        # prestazione proiettata supera la soglia di obbligo (§4.1)
        # e non abbiamo già una REFEZ valida negli eventi.
        if prestazione_fin > C.REFEZ_REQUIRED_ABOVE_MIN and not _has_valid_refez(eventi):
            eventi.pop()
            segmenti_usati.pop()
            seg_prev = segmenti_usati[-1] if segmenti_usati else None
            if seg_prev is None:
                break
            seg = seg_prev
            break

        # Valuta continuazione: c'è un segmento successivo stesso materiale?
        next_seg = pool.next_same_material(seg)
        if next_seg is None:
            break
        # `next_seg` non deve essere in segmenti_usati (non riuso)
        if next_seg in segmenti_usati:
            break
        # Gap fra arrivo attuale e partenza prossimo
        gap = next_seg.partenza_min - seg.arrivo_min
        if gap < 0:
            break

        # Accetta la continuazione: aggiungi evento gap + passa al successivo
        _append_gap_event(eventi, seg, next_seg, gap)
        seg = next_seg

    # 3.4 Chiusura del turno con rientro
    chiusura = _proietta_fine(eventi, seg, deposito, cap, vettura_lookup)
    if chiusura is not None:
        fine_min, chiusura_eventi, ok = chiusura
        eventi.extend(chiusura_eventi)

    pdc = PdC(deposito=deposito, eventi=eventi)
    return pdc


# ---------------------------------------------------------------------------
# Helper privati
# ---------------------------------------------------------------------------


def _stazione_deposito(deposito: str) -> str:
    """Nome canonico della stazione del deposito (via config depot_to_station
    se presente, altrimenti stesso nome)."""
    from config.loader import get_active_config
    cfg = get_active_config()
    mapping = getattr(cfg, "depot_to_station", {}) or {}
    return mapping.get(deposito, deposito)


def _has_valid_refez(eventi: list[EventoPdC]) -> bool:
    """True se esiste un evento REFEZ dentro finestra §4.1 con durata ≥ 30'."""
    for e in eventi:
        if e.kind != EventoKind.REFEZ:
            continue
        if e.durata_min < C.MEAL_MIN:
            continue
        if (C.MEAL_WINDOW_1_START <= e.inizio_min <= C.MEAL_WINDOW_1_END
                or C.MEAL_WINDOW_2_START <= e.inizio_min <= C.MEAL_WINDOW_2_END):
            return True
    return False


def _append_gap_event(
    eventi: list[EventoPdC],
    seg_prev: Segment,
    seg_next: Segment,
    gap_min: int,
) -> None:
    """Inserisce un evento di gestione gap (PK/BUCO) tra due condotte.
    §6 NORMATIVA-PDC: per gap < 65 con stesso PdC, PK è la scelta
    preferita (no incontro richiesto)."""
    if gap_min <= 0:
        return
    if gap_min <= 15:
        # Gap tecnico, troppo breve per essere "buco"; lo tralasciamo
        # come se i due treni fossero contigui.
        return
    # Scegli PK se stesso materiale (stesso PdC continua)
    eventi.append(
        EventoPdC(
            EventoKind.BUCO, seg_prev.arrivo_min, seg_next.partenza_min,
            stazione=seg_prev.a_stazione,
            note=f"gap {gap_min}' §4/§6",
        )
    )


def _proietta_fine(
    eventi: list[EventoPdC],
    ultimo_seg: Segment,
    deposito: str,
    cap: int,
    vettura_lookup: VetturaLookup,
) -> Optional[tuple[int, list[EventoPdC], bool]]:
    """Simula la chiusura del turno dopo `ultimo_seg`. Ritorna
    (fine_min, eventi_chiusura, ok_dentro_cap) oppure None se
    infattibile.

    Strategie, in ordine:
    1. CV se arrivo è §9.2 + rientro vettura passiva
    2. ACCa + rientro vettura passiva
    3. ACCa + rientro taxi
    """
    deposito_stazione = _stazione_deposito(deposito)
    arrivo_st = ultimo_seg.a_stazione
    arrivo_min = ultimo_seg.arrivo_min
    cv_stations = _cv_stations()

    presa = eventi[0].inizio_min if eventi else 0

    closing_events: list[EventoPdC] = []

    # 1) CV ammesso qui?
    cv_ammesso = arrivo_st in cv_stations and arrivo_st != deposito_stazione

    if cv_ammesso:
        # CVa immediato (durata 5' stima, §5.2 non fissa)
        cva_fine = arrivo_min + 5
        closing_events.append(
            EventoPdC(
                EventoKind.CVA, arrivo_min, cva_fine,
                stazione=arrivo_st,
                note="§5 consegna materiale",
            )
        )
        return _close_with_rientro(
            closing_events, arrivo_st, cva_fine, deposito_stazione,
            vettura_lookup, presa, cap
        )

    # 2) Siamo al deposito stesso?
    if arrivo_st == deposito_stazione:
        acca_fine = arrivo_min + C.ACCA_STANDARD_MIN
        closing_events.append(
            EventoPdC(
                EventoKind.ACCA, arrivo_min, acca_fine,
                stazione=arrivo_st,
                note=f"§3.3 ACCa {C.ACCA_STANDARD_MIN}'",
            )
        )
        closing_events.append(
            EventoPdC(
                EventoKind.FINE_SERVIZIO, acca_fine, acca_fine,
                stazione=deposito_stazione,
            )
        )
        return (acca_fine, closing_events, acca_fine - presa <= cap)

    # 3) ACCa + rientro
    acca_fine = arrivo_min + C.ACCA_STANDARD_MIN
    closing_events.append(
        EventoPdC(
            EventoKind.ACCA, arrivo_min, acca_fine,
            stazione=arrivo_st,
            note=f"§3.3 ACCa {C.ACCA_STANDARD_MIN}'",
        )
    )
    return _close_with_rientro(
        closing_events, arrivo_st, acca_fine, deposito_stazione,
        vettura_lookup, presa, cap
    )


def _close_with_rientro(
    closing_events: list[EventoPdC],
    da_stazione: str,
    dopo_min: int,
    deposito_stazione: str,
    vettura_lookup: VetturaLookup,
    presa: int,
    cap: int,
) -> tuple[int, list[EventoPdC], bool]:
    """Aggiunge rientro passivo al deposito + fine servizio."""
    vett = vettura_lookup(da_stazione, deposito_stazione, dopo_min)
    if vett is not None:
        v_part, v_arr, v_num = vett
        if v_part > dopo_min:
            closing_events.append(
                EventoPdC(
                    EventoKind.BUCO, dopo_min, v_part,
                    stazione=da_stazione,
                    note=f"attesa vettura {v_part - dopo_min}'",
                )
            )
        closing_events.append(
            EventoPdC(
                EventoKind.VETTURA, v_part, v_arr,
                stazione=da_stazione, stazione_a=deposito_stazione,
                treno=v_num, note="rientro §7.2",
            )
        )
        fine = v_arr + C.POST_VETTURA_MIN
        closing_events.append(
            EventoPdC(
                EventoKind.FINE_SERVIZIO, fine, fine,
                stazione=deposito_stazione,
            )
        )
        return (fine, closing_events, fine - presa <= cap)

    # Fallback taxi: stima tempo come posizionamento
    taxi_inizio = dopo_min
    taxi_fine = taxi_inizio + C.DEPOT_TO_IMPIANTO_TAXI_MIN
    closing_events.append(
        EventoPdC(
            EventoKind.TAXI, taxi_inizio, taxi_fine,
            stazione=da_stazione, stazione_a=deposito_stazione,
            note="§7.2 fallback taxi rientro",
        )
    )
    fine = taxi_fine + C.POST_VETTURA_MIN
    closing_events.append(
        EventoPdC(
            EventoKind.FINE_SERVIZIO, fine, fine,
            stazione=deposito_stazione,
        )
    )
    return (fine, closing_events, fine - presa <= cap)


# ---------------------------------------------------------------------------
# Validazione finale §5 ALGORITMO
# ---------------------------------------------------------------------------


def validate_pdc(pdc: PdC) -> list[str]:
    """Lista di violazioni di normativa. Vuota → PdC valido.

    Controlli implementati:
    - Prestazione ≤ cap (§11.8)
    - Condotta ≤ 330 (§14.2)
    - REFEZ richiesta se prestazione > 360 e non presente in finestra
      valida (§4.1)
    """
    violazioni: list[str] = []

    s = pdc.presa_servizio_min
    if s is None:
        violazioni.append("nessuna presa servizio")
        return violazioni

    cap = cap_prestazione(s)
    if pdc.prestazione_min > cap:
        violazioni.append(
            f"prestazione {pdc.prestazione_min}' > cap {cap}' "
            f"(§11.8, presa servizio {min_to_hhmm(s)})"
        )

    if pdc.condotta_min > C.MAX_CONDOTTA_MIN:
        violazioni.append(
            f"condotta {pdc.condotta_min}' > {C.MAX_CONDOTTA_MIN}' (§14.2)"
        )

    # REFEZ
    if pdc.prestazione_min > C.REFEZ_REQUIRED_ABOVE_MIN:
        refez = [e for e in pdc.eventi if e.kind == EventoKind.REFEZ]
        valid_refez = [
            e for e in refez
            if (C.MEAL_WINDOW_1_START <= e.inizio_min <= C.MEAL_WINDOW_1_END
                or C.MEAL_WINDOW_2_START <= e.inizio_min <= C.MEAL_WINDOW_2_END)
            and e.durata_min >= C.MEAL_MIN
        ]
        if not valid_refez:
            violazioni.append(
                f"REFEZ obbligatoria (prestazione {pdc.prestazione_min}' "
                f"> {C.REFEZ_REQUIRED_ABOVE_MIN}') mancante o fuori "
                f"finestra/durata (§4.1)"
            )

    return violazioni


# ---------------------------------------------------------------------------
# cover_material — algoritmo top-level §2
# ---------------------------------------------------------------------------


@dataclass
class CoverResult:
    pdc_list: list[PdC]
    residui: list[Segment]
    violazioni_totali: int


def cover_material(
    segments: list[Segment],
    scegli_deposito: Callable[[Segment], str],
    vettura_lookup: VetturaLookup = _fallback_vettura_lookup,
    max_pdc: int = 20,
) -> CoverResult:
    """Copre il turno materiale con una lista di PdC in regola.

    `scegli_deposito(primo_seg) -> nome_deposito` è il callable che
    decide quale deposito usare per il prossimo PdC. Signature
    intenzionalmente semplice: il chiamante può implementare strategie
    diverse (nearest, prefer list, ecc.).

    `max_pdc` è un safety: se supera, la pool residua viene restituita.
    """
    pool = MaterialPool(segments=list(segments))
    pdc_list: list[PdC] = []
    viol_tot = 0

    while not pool.is_empty() and len(pdc_list) < max_pdc:
        primo = pool.first()
        if primo is None:
            break
        deposito = scegli_deposito(primo)
        pdc = build_single_pdc(primo, pool, deposito, vettura_lookup)
        viol = validate_pdc(pdc)
        viol_tot += len(viol)
        # Rimuovi i segmenti usati dalla pool (§15). Tolleriamo che
        # alcuni segmenti spezzati siano parzialmente consumati: per
        # ora rimuoviamo quelli esattamente presenti.
        for seg in pdc.segmenti_usati:
            try:
                pool.remove(seg)
            except ValueError:
                pass
        # Se il builder non ha consumato nulla (PdC vuoto o senza
        # condotta), ferma per evitare loop infinito.
        if not pdc.segmenti_usati:
            pdc_list.append(pdc)
            break
        pdc_list.append(pdc)

    return CoverResult(
        pdc_list=pdc_list,
        residui=list(pool.segments),
        violazioni_totali=viol_tot,
    )
