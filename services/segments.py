"""
Servizi per manipolazione segmenti treno: dedup, serializzazione, helpers.
Estratto da server.py per riuso in più router.
"""

from collections import Counter


def seg_get(seg, key, default=""):
    """Helper: get field from segment (dict or object)."""
    if isinstance(seg, dict):
        return seg.get(key, default)
    return getattr(seg, key, default)


def dedup_segments(segments: list[dict]) -> list[dict]:
    """Deduplica segmenti: per ogni train_id, prende solo quelli del day_index
    piu' frequente (= LV, tipicamente). Rimuove anche segmenti identici."""
    if not segments:
        return segments

    day_idx_counts = Counter(s.get("day_index", 0) for s in segments)
    best_day_idx = day_idx_counts.most_common(1)[0][0]

    by_train: dict[str, dict[int, list]] = {}
    for s in segments:
        tid = s.get("train_id", "")
        di = s.get("day_index", 0)
        by_train.setdefault(tid, {}).setdefault(di, []).append(s)

    result = []
    seen = set()
    for tid, di_map in by_train.items():
        chosen_di = best_day_idx if best_day_idx in di_map else min(di_map.keys())
        for s in di_map[chosen_di]:
            key = (s.get("train_id"), s.get("dep_time"), s.get("arr_time"),
                   s.get("from_station"), s.get("to_station"))
            if key not in seen:
                seen.add(key)
                result.append(s)

    return result


def serialize_segments(segments) -> list[dict]:
    """Serializza segmenti in formato JSON-safe."""
    result = []
    for seg in segments:
        result.append({
            "train_id": seg_get(seg, "train_id", "?"),
            "from_station": seg_get(seg, "from_station", ""),
            "to_station": seg_get(seg, "to_station", ""),
            "dep_time": seg_get(seg, "dep_time", ""),
            "arr_time": seg_get(seg, "arr_time", ""),
            "is_deadhead": seg_get(seg, "is_deadhead", False),
        })
    return result
