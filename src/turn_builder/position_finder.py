"""
Position Finder — cerca percorsi in vettura (deadhead) per posizionamento
o rientro del PdC.

Il PdC sale come passeggero (vettura) su 1-3 treni concatenati per
raggiungere la stazione di inizio del seed produttivo (posizionamento)
o per tornare al deposito dopo il seed (rientro).

Richiesta utente: max 3 hop (1 hop = 1 treno vettura, 2 = 2 treni
concatenati, 3 = 3 treni).

Algoritmo: BFS sui segmenti del giorno, con vincoli:
- arrivo a destinazione entro time_target
- gap tra treni >= MIN_CHANGE_MIN (5')
- gap tra treni <= MAX_HOP_WAIT (60') per evitare catene troppo lunghe
- max N hop

Output: lista di opzioni ordinate per arrivo crescente (prima opzione =
percorso che arriva prima).
"""
from __future__ import annotations

from ..validator.rules import _time_to_min


# Parametri (richiesta utente: max 3 hop)
MAX_HOPS = 3
MIN_CHANGE_MIN = 5  # 5' min tra un treno e il successivo
MAX_HOP_WAIT = 60   # 60' max attesa tra 2 hop consecutivi
MAX_POSITIONING_DURATION = 240  # 4h max totali di posizionamento


def find_position_path(
    all_day_segments: list,
    from_station: str,
    to_station: str,
    arrive_by_min: int,
    depart_after_min: int = 0,
    max_hops: int = MAX_HOPS,
    exclude_train_ids: set = None,
) -> list:
    """
    Cerca percorsi in vettura (from_station -> to_station) che arrivino
    entro 'arrive_by_min' e partano dopo 'depart_after_min'.

    Args:
        all_day_segments: tutti i segmenti candidati del giorno
        from_station: stazione di partenza (es. deposito)
        to_station: stazione di arrivo (es. inizio seed)
        arrive_by_min: orario massimo di arrivo (minuti dalla mezzanotte)
        depart_after_min: orario minimo di partenza (default 0)
        max_hops: max numero di treni concatenati (default 3)
        exclude_train_ids: train_id da NON usare (gia' bloccati)

    Returns:
        Lista di percorsi. Ogni percorso = lista di segmenti marcati
        is_deadhead=True. Ordinati per arrivo crescente (prima = prima).
        Vuota se nessun percorso trovato.
    """
    from_u = (from_station or "").upper().strip()
    to_u = (to_station or "").upper().strip()
    if not from_u or not to_u or from_u == to_u:
        return []
    exclude = set(exclude_train_ids or [])

    # Indice segmenti per from_station
    by_from: dict = {}
    for seg in all_day_segments:
        key = (seg.get("from_station", "") or "").upper().strip()
        by_from.setdefault(key, []).append(seg)

    # BFS: (current_chain, current_station, current_arr_min,
    #       first_dep_min, used_ids)
    results = []
    initial = [(
        [], from_u, depart_after_min, None, set(),
    )]
    stack = list(initial)

    while stack:
        chain, cur_st, cur_arr, first_dep, used = stack.pop()
        if len(chain) >= max_hops:
            continue
        for seg in by_from.get(cur_st, []):
            tid = seg.get("train_id", "")
            if tid in exclude or tid in used:
                continue
            dep_m = _time_to_min(seg["dep_time"])
            if dep_m < cur_arr + MIN_CHANGE_MIN:
                continue
            gap = dep_m - cur_arr
            if gap > MAX_HOP_WAIT and len(chain) > 0:
                continue
            arr_m = _time_to_min(seg["arr_time"])
            if arr_m < dep_m:
                arr_m += 1440
            if arr_m > arrive_by_min:
                continue
            # Durata totale dal primo dep
            fd = first_dep if first_dep is not None else dep_m
            total_dur = arr_m - fd
            if total_dur > MAX_POSITIONING_DURATION:
                continue

            new_seg = {**seg, "is_deadhead": True}
            new_chain = chain + [new_seg]
            new_used = used | {tid}
            new_st = (seg.get("to_station", "") or "").upper().strip()

            # Se arrivati a destinazione: aggiungi ai risultati
            if new_st == to_u:
                results.append(new_chain)
                continue  # non estendere oltre

            # Altrimenti estendi se hop residui
            if len(new_chain) < max_hops:
                stack.append((new_chain, new_st, arr_m, fd, new_used))

    # Ordina per arrivo (minore arrivo = migliore posizionamento)
    results.sort(key=lambda c: _time_to_min(c[-1]["arr_time"]) if c else 0,
                 reverse=False)
    return results


def find_return_path(
    all_day_segments: list,
    from_station: str,
    deposito: str,
    depart_after_min: int,
    max_hops: int = MAX_HOPS,
    exclude_train_ids: set = None,
) -> list:
    """
    Cerca percorsi di rientro al deposito dopo il seed produttivo.
    Wrapper di find_position_path senza vincolo arrive_by (arriva
    quando possibile).
    """
    # "arrive_by" = fine giornata (es. 26:00 per coprire anche notturni)
    ARRIVE_BY_END_OF_DAY = 1440 + 360  # 06:00 del giorno dopo = 30:00
    return find_position_path(
        all_day_segments=all_day_segments,
        from_station=from_station,
        to_station=deposito,
        arrive_by_min=ARRIVE_BY_END_OF_DAY,
        depart_after_min=depart_after_min,
        max_hops=max_hops,
        exclude_train_ids=exclude_train_ids,
    )
