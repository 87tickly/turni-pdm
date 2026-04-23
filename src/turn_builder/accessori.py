"""
Modulo accessori — calcola ACCp (accessori in partenza) e ACCa
(accessori in arrivo) per ogni segmento di una giornata PdC.

Regola di business (richiesta utente 23/04/2026):

  Gli accessori NON si applicano automaticamente a inizio/fine giornata.
  Si applicano guardando il GIRO MATERIALE: un treno ottiene ACCp se il
  suo treno precedente nello stesso giro materiale lascia un gap
  >= 65 minuti; ottiene ACCa se il successivo lascia un gap >= 65 min.

Valori (default configurabili dopo generazione):

  ACCp condotta (preparazione mezzo)          : 40 min
  ACCp condotta con preriscaldo ● (dic-feb)   : 80 min
  ACCp vettura (passeggero)                   : 15 min
  ACCa condotta (spegnimento mezzo)           : 40 min
  ACCa vettura (scendo e basta)               : 10 min

I CVp / CVa (cambio volante) sono un caso diverso (gap < 65 min, treni
consecutivi, split tra due PdC): gestiti nel modulo cv_registry.py
(Step 5).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from ..validator.rules import _time_to_min
from .preheat_calendar import is_preheat_period


# Soglia del gap materiale oltre cui si applicano gli accessori pieni.
GAP_THRESHOLD_MIN = 65

# Valori di default accessori (richiesta utente 23/04/2026).
ACCP_CONDOTTA = 40
ACCA_CONDOTTA = 40
ACCP_VETTURA = 15
ACCA_VETTURA = 10
ACCP_PRERISCALDO = 80  # solo dic-feb, condotta con simbolo ●


def _time_with_overnight(dep_str: str, arr_str: str) -> tuple[int, int]:
    """Ritorna (dep_min, arr_min) con rollover +1440 se arr < dep."""
    dep = _time_to_min(dep_str)
    arr = _time_to_min(arr_str)
    if arr < dep:
        arr += 1440
    return dep, arr


def _seg_key(seg: dict):
    """Chiave stabile per riconoscere un segmento nella lista del giro
    materiale. Preferisce `id` (DB), altrimenti fallback triplo."""
    sid = seg.get("id")
    if sid is not None:
        return ("id", sid)
    return ("trip",
            seg.get("train_id", ""),
            seg.get("dep_time", ""),
            seg.get("from_station", ""))


def compute_material_gaps(material_segments: list,
                           target_segment: dict) -> tuple[Optional[int],
                                                          Optional[int]]:
    """
    Calcola i gap "prima" e "dopo" del segmento target dentro il suo
    giro materiale (stesso material_turn_id + day_index).

    Args:
        material_segments: lista dei segmenti dello stesso giro materiale
            per un giorno. Si ignorano i segmenti is_refezione (virtuali).
        target_segment: uno dei segmenti in material_segments.

    Returns:
        (gap_before_min, gap_after_min). None se il target e' il primo
        o l'ultimo del giorno (nessun confronto possibile, il chiamante
        interpreta None come "gap ampio" → accessori pieni applicati).
    """
    # Filtra fuori i segmenti virtuali (refezione). Ordino per `seq`
    # (ordine ufficiale dal parser del PDF) con fallback a dep_time.
    # Usare seq evita ambiguita' overnight (es. 22:00 -> 23:00 -> 01:00
    # del giorno dopo ma stesso day_index).
    real_segs = [s for s in material_segments
                 if not s.get("is_refezione", False)]
    real_segs = sorted(
        real_segs,
        key=lambda s: (s.get("seq", 0), _time_to_min(s.get("dep_time", "00:00"))),
    )

    target_key = _seg_key(target_segment)
    idx = next((i for i, s in enumerate(real_segs)
                if _seg_key(s) == target_key), None)
    if idx is None:
        return (None, None)

    target_dep, target_arr = _time_with_overnight(
        target_segment["dep_time"], target_segment["arr_time"])

    # gap_before: tra arr precedente e dep target
    if idx == 0:
        gap_before = None
    else:
        prev = real_segs[idx - 1]
        _, prev_arr = _time_with_overnight(prev["dep_time"], prev["arr_time"])
        gap_before = target_dep - prev_arr

    # gap_after: tra arr target e dep successivo
    if idx == len(real_segs) - 1:
        gap_after = None
    else:
        nxt = real_segs[idx + 1]
        nxt_dep = _time_to_min(nxt["dep_time"])
        if nxt_dep < target_arr:
            nxt_dep += 1440
        gap_after = nxt_dep - target_arr

    return (gap_before, gap_after)


def determine_accessori(segment: dict,
                         gap_before: Optional[int],
                         gap_after: Optional[int],
                         day_date: date) -> dict:
    """
    Determina ACCp e ACCa (in minuti) per il segmento in base a:
    - tipo segmento (condotta / vettura / preriscaldo)
    - gap materiale prima e dopo (None = gap ampio assunto)
    - data (per il periodo preriscaldo rinforzato)

    Ritorna {'accp_min': int, 'acca_min': int}. Se un gap e' sotto la
    soglia GAP_THRESHOLD_MIN, il corrispondente accessorio e' 0 (non
    c'e' tempo fisico per eseguirlo).
    """
    is_deadhead = bool(segment.get("is_deadhead", False))
    is_preheat = bool(segment.get("is_preheat", False))

    # ACCp: gap prima abbastanza ampio?
    if gap_before is None or gap_before >= GAP_THRESHOLD_MIN:
        if is_deadhead:
            accp = ACCP_VETTURA
        elif is_preheat and is_preheat_period(day_date):
            accp = ACCP_PRERISCALDO
        else:
            accp = ACCP_CONDOTTA
    else:
        accp = 0

    # ACCa: gap dopo abbastanza ampio?
    if gap_after is None or gap_after >= GAP_THRESHOLD_MIN:
        if is_deadhead:
            acca = ACCA_VETTURA
        else:
            acca = ACCA_CONDOTTA
    else:
        acca = 0

    return {"accp_min": accp, "acca_min": acca}


def apply_accessori(material_segments: list,
                     target_segment: dict,
                     day_date: date) -> dict:
    """
    Orchestratore: combina gap + accessori. Ritorna un dict con:
      - accp_min, acca_min: valori calcolati
      - gap_before, gap_after: gap grezzi (None se bordo)
    """
    gap_before, gap_after = compute_material_gaps(material_segments,
                                                    target_segment)
    accs = determine_accessori(target_segment, gap_before, gap_after, day_date)
    return {
        "accp_min": accs["accp_min"],
        "acca_min": accs["acca_min"],
        "gap_before": gap_before,
        "gap_after": gap_after,
    }
