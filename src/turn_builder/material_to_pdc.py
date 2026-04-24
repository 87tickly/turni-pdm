"""
Builder turno materiale → turni PdC — tipi base (step 2).

Questo modulo implementa l'algoritmo specificato in
`docs/ALGORITMO-BUILDER.md`, rispettando la normativa in
`docs/NORMATIVA-PDC.md`.

Step 2: solo strutture dati (Segment, EventoPdC, PdC, MaterialPool)
+ utility di conversione tempo. Nessuna logica di costruzione.
La logica arriva negli step successivi.

Convenzione tempi: tutti gli orari sono espressi in minuti dalla
mezzanotte (0-1439). Es. 04:10 = 250.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


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
    """Converte minuti dalla mezzanotte in "HH:MM".

    >>> min_to_hhmm(250)
    '04:10'
    >>> min_to_hhmm(0)
    '00:00'
    """
    if not (0 <= m < 24 * 60):
        raise ValueError(f"minuti fuori range: {m}")
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
