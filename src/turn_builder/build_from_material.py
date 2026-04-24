"""
Pipeline builder "normativa-first": dato deposito + n giornate, produce
un calendario di PdC usando `material_to_pdc.cover_material` — quindi
rispettando TUTTE le regole scritte in `docs/NORMATIVA-PDC.md`.

Sostituisce l'AutoBuilder genetico quando il chiamante imposta il
flag `use_normativa=True`. L'output è compatibile col formato atteso
da `/api/build-auto`: lista di dict `{type: TURN|REST, day, summary}`.

Classificazione segmenti dal DB → Segment kind:
  - train_id che inizia per "U" → VUOTO_U (materiale aziendale)
  - train_id che termina per "i" → VUOTO_I (vuoto traccia RFI)
  - altrimenti → COMMERCIALE

Se il parser PDF non ha popolato questi marker (dataset attuale),
tutto finisce come COMMERCIALE: la normativa si applica comunque,
solo le regole FIOz (§8.5, §8.5.1) restano inerti.

Strategia V1 (semplice e deterministica):
  1. Per ogni giornata lavorativa, fetch segmenti del day_index
  2. Raggruppa per material_turn_id
  3. Per ogni materiale: Segment[] ordinati → cover_material()
  4. Scegli il primo PdC risultante con deposito == richiesto
  5. Se nessun PdC del deposito, prendi il primo PdC qualsiasi
  6. Conversione PdC → lista segmenti dict → TurnValidator.validate_day
     per ottenere DaySummary compatibile
  7. 5 (o N) giornate lavorative + 2 giorni di riposo

Non ottimale: non esplora alternative multiple, non ottimizza il
carico settimanale. Ma è conforme alla normativa — può essere
migliorato in step successivi.
"""

from __future__ import annotations

from typing import Optional

from ..constants import DEPOSITI
from ..database.db import Database
from ..validator.rules import TurnValidator
from .material_to_pdc import (
    EventoKind,
    EventoPdC,
    MaterialPool,
    PdC,
    Segment,
    SegmentKind,
    cover_material,
    hhmm_to_min,
    min_to_hhmm,
)


# ---------------------------------------------------------------------------
# Classificazione segmenti DB → Segment kind
# ---------------------------------------------------------------------------


def _classify_kind(train_id: str) -> SegmentKind:
    if not train_id:
        return SegmentKind.COMMERCIALE
    tid = str(train_id).strip()
    if tid.upper().startswith("U"):
        return SegmentKind.VUOTO_U
    # Suffisso "i" minuscolo conserva, ma non confondo con sigle tipo "PI"
    if len(tid) > 1 and tid.endswith("i") and tid[-2].isdigit():
        return SegmentKind.VUOTO_I
    return SegmentKind.COMMERCIALE


def _db_segment_to_segment(db_row: dict) -> Optional[Segment]:
    """Converte una riga DB train_segment in un `Segment` del builder
    normativa. Ritorna None se mancano campi obbligatori."""
    train_id = db_row.get("train_id") or ""
    frm = (db_row.get("from_station") or "").strip().upper()
    to = (db_row.get("to_station") or "").strip().upper()
    dep = db_row.get("dep_time")
    arr = db_row.get("arr_time")
    if not (train_id and frm and to and dep and arr):
        return None
    try:
        dep_m = hhmm_to_min(dep)
        arr_m = hhmm_to_min(arr)
    except ValueError:
        return None
    return Segment(
        numero=train_id,
        kind=_classify_kind(train_id),
        da_stazione=frm,
        a_stazione=to,
        partenza_min=dep_m,
        arrivo_min=arr_m,
    )


# ---------------------------------------------------------------------------
# Strategia deposito e vettura lookup
# ---------------------------------------------------------------------------


def _make_scegli_deposito(deposito_richiesto: str):
    """Per la pipeline V1 il deposito è fisso (quello richiesto nella request).
    Ogni PdC del giorno sarà assegnato a `deposito_richiesto`."""
    def scegli(_seg: Segment) -> str:
        return deposito_richiesto
    return scegli


def _make_vettura_lookup(db: Database):
    """Vettura lookup via DB: cerca tra i segmenti un treno passeggeri
    commerciale da A a B con partenza >= `after_min`.

    Fallback semplice: scansione linear dei segmenti di tutte le
    giornate col nome stazione `a` come origine. In produzione questa
    chiamata dovrebbe passare da ARTURO Live (§12.1), ma il dataset DB
    è sufficiente per una prima implementazione.
    """
    def lookup(da: str, a: str, after_min: int):
        da_u = da.upper().strip()
        a_u = a.upper().strip()
        try:
            segs = db.query_station_departures(da_u)
        except Exception:
            return None
        # Filtra per destinazione e orario
        candidates = []
        for s in segs:
            if (s.get("to_station") or "").strip().upper() != a_u:
                continue
            dep = s.get("dep_time")
            arr = s.get("arr_time")
            if not dep or not arr:
                continue
            try:
                dep_m = hhmm_to_min(dep)
                arr_m = hhmm_to_min(arr)
            except ValueError:
                continue
            if dep_m < after_min:
                continue
            candidates.append((dep_m, arr_m, s.get("train_id") or ""))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0])
        return candidates[0]
    return lookup


# ---------------------------------------------------------------------------
# Conversione PdC → list[dict] per TurnValidator
# ---------------------------------------------------------------------------


def _pdc_to_db_segments(pdc: PdC) -> list[dict]:
    """Estrae dai PdC-events i segmenti (condotta + vettura) nel formato
    dict atteso da TurnValidator/serialize_segments.

    Campi attesi dal formato RFI: train_id, from_station, to_station,
    dep_time, arr_time, is_deadhead. Aggiungiamo anche `material_turn_id`
    e `day_index` quando disponibili dal Segment originario (non sempre).
    """
    out: list[dict] = []
    for ev in pdc.eventi:
        if ev.kind not in (EventoKind.CONDOTTA, EventoKind.VETTURA):
            continue
        seg = ev.segment
        if seg is None:
            continue
        out.append({
            "train_id": seg.numero,
            "from_station": seg.da_stazione,
            "to_station": seg.a_stazione,
            "dep_time": min_to_hhmm(seg.partenza_min),
            "arr_time": min_to_hhmm(seg.arrivo_min),
            "is_deadhead": 1 if ev.kind == EventoKind.VETTURA else 0,
            "is_accessory": 0,
            "segment_kind": seg.kind.value,
        })
    return out


# ---------------------------------------------------------------------------
# Entry point — build schedule conforme alla normativa
# ---------------------------------------------------------------------------


def build_schedule_from_material(
    db: Database,
    deposito: str,
    n_workdays: int = 5,
    day_type: str = "LV",
    exclude_trains: Optional[set[str]] = None,
) -> list[dict]:
    """Costruisce un calendario settimanale (5+2) per `deposito` usando
    la pipeline conforme alla NORMATIVA-PDC.md.

    Ritorna una lista di dict compatibile con l'endpoint /api/build-auto:
        [{type: "TURN"|"REST", day, week_day_type, summary: DaySummary?}, ...]

    Se per una giornata non riesce a trovare alcun PdC, la entry
    ha `summary=None` e un marker di violazione nel DaySummary
    (gestito dal chiamante via `Violation`).
    """
    exclude_trains = exclude_trains or set()
    validator = TurnValidator(deposito=deposito)
    scegli_deposito = _make_scegli_deposito(deposito)
    vettura_lookup = _make_vettura_lookup(db)

    calendar: list[dict] = []
    train_ids_used: set[str] = set(exclude_trains)

    for day in range(1, n_workdays + 1):
        # day_index nel DB corrisponde generalmente al numero giornata del ciclo
        db_rows = db.get_all_segments(day_index=day)
        # Classifica segmenti e raggruppa per material_turn_id
        by_mat: dict[int, list[Segment]] = {}
        for row in db_rows:
            tid = row.get("train_id")
            if not tid or tid in train_ids_used:
                continue
            mat_id = row.get("material_turn_id")
            if mat_id is None:
                continue
            seg = _db_segment_to_segment(row)
            if seg is None:
                continue
            by_mat.setdefault(mat_id, []).append(seg)

        chosen_summary = None
        for mat_id, segments in by_mat.items():
            # Ordina per partenza
            segments.sort(key=lambda s: s.partenza_min)
            # cover_material applica §11.8, §4.1, §9.2, §15 e costruisce PdC
            try:
                result = cover_material(
                    segments,
                    scegli_deposito=scegli_deposito,
                    vettura_lookup=vettura_lookup,
                )
            except Exception:
                continue
            for pdc in result.pdc_list:
                if pdc.deposito != deposito:
                    continue
                db_segs = _pdc_to_db_segments(pdc)
                if not db_segs:
                    continue
                # Valida: il validator applica a sua volta §11.8 cap variabile,
                # §4.1 REFEZ > 6h, etc.
                summary = validator.validate_day(db_segs, deposito=deposito)
                # Accetta solo se non sfora nessun vincolo rigido
                has_hard_violation = any(
                    v.rule in ("MAX_PRESTAZIONE", "MAX_CONDOTTA")
                    for v in summary.violations
                )
                if has_hard_violation:
                    continue
                # Blocca i treni usati per evitare doppioni (§15 cross-day)
                for db_seg in db_segs:
                    train_ids_used.add(db_seg["train_id"])
                chosen_summary = summary
                break
            if chosen_summary is not None:
                break

        calendar.append({
            "type": "TURN",
            "day": day,
            "week_day_type": day_type,
            "summary": chosen_summary,
        })

    # Riposo: ciclo 5+2
    calendar.append({"type": "REST", "day": None, "summary": None})
    calendar.append({"type": "REST", "day": None, "summary": None})

    # Metadata (compatibilità con _meta del vecchio builder)
    if calendar and calendar[0].get("summary"):
        calendar[0]["_meta"] = {
            "deposito": deposito,
            "reachable_stations": sorted(set(DEPOSITI)),
            "total_violations": sum(
                len(e["summary"].violations)
                for e in calendar
                if e.get("summary") and hasattr(e["summary"], "violations")
            ),
        }
    return calendar
