"""
Servizio costruzione timeline giornaliera.
Genera i blocchi visivi per la rappresentazione del turno.
Estratto da server.py (~340 righe di logica).
"""

from src.validator.rules import _time_to_min, _min_to_time
from src.constants import (
    ACCESSORY_RULES,
    EXTRA_START_MIN,
    MEAL_MIN,
)
from services.segments import seg_get


def build_timeline_blocks(summary, deposito: str = "", db=None,
                          acc_start: int = None, acc_end: int = None) -> list[dict]:
    """
    Genera i blocchi timeline per una giornata di turno.
    Ogni blocco ha: type, label, detail, start (min), end (min),
    start_time (HH:MM), end_time (HH:MM), from_station, to_station, duration.

    Se deposito e db sono forniti, aggiunge:
    - blocco 'spostamento' (cyan) se il turno finisce fuori deposito
    - blocco 'dormita_fr' (indaco) se la stazione finale è FR
    """
    blocks = []
    segs = summary.segments
    if not segs or not summary.presentation_time or not summary.end_time:
        return blocks

    eff_acc_start = acc_start if acc_start is not None else ACCESSORY_RULES["default_start"]
    eff_acc_end = acc_end if acc_end is not None else ACCESSORY_RULES["default_end"]

    pres_m = _time_to_min(summary.presentation_time)
    end_m = _time_to_min(summary.end_time)
    if end_m <= pres_m:
        end_m += 24 * 60

    first_dep_str = seg_get(segs[0], "dep_time")
    last_arr_str = seg_get(segs[-1], "arr_time")
    first_from_st = seg_get(segs[0], "from_station", "")
    last_to_st = seg_get(segs[-1], "to_station", "")
    first_dep_m = _time_to_min(first_dep_str)
    last_arr_m = _time_to_min(last_arr_str)
    if first_dep_m < pres_m:
        first_dep_m += 24 * 60
    if last_arr_m < first_dep_m:
        last_arr_m += 24 * 60

    # 1. Extra Inizio
    extra_s_end = pres_m + EXTRA_START_MIN
    blocks.append({
        "type": "extra", "label": "Extra Inizio",
        "start": pres_m, "end": extra_s_end,
        "start_time": _min_to_time(pres_m), "end_time": _min_to_time(extra_s_end),
        "duration": EXTRA_START_MIN,
        "from_station": first_from_st, "to_station": first_from_st,
    })

    # 2. Accessori Inizio
    acc_start_dur = first_dep_m - extra_s_end
    blocks.append({
        "type": "accessori", "label": "Acc. Inizio" + (" (CVL)" if eff_acc_start == 5 else ""),
        "start": extra_s_end, "end": first_dep_m,
        "start_time": _min_to_time(extra_s_end), "end_time": first_dep_str,
        "duration": acc_start_dur,
        "from_station": first_from_st, "to_station": first_from_st,
    })

    # 3. Segmenti treno + gap + refezione
    meal_s_m = _time_to_min(summary.meal_start) if summary.meal_start else None
    meal_e_m = _time_to_min(summary.meal_end) if summary.meal_end else None
    if meal_s_m is not None and meal_s_m < pres_m:
        meal_s_m += 24 * 60
    if meal_e_m is not None and meal_e_m < pres_m:
        meal_e_m += 24 * 60

    meal_placed = False

    for i, seg in enumerate(segs):
        dep_m = _time_to_min(seg_get(seg, "dep_time"))
        arr_m = _time_to_min(seg_get(seg, "arr_time"))
        if dep_m < pres_m:
            dep_m += 24 * 60
        if arr_m <= dep_m:
            arr_m += 24 * 60

        train_id = seg_get(seg, "train_id", "?")
        from_st = seg_get(seg, "from_station", "")
        to_st = seg_get(seg, "to_station", "")
        seg_dur = arr_m - dep_m
        is_dh = seg_get(seg, "is_deadhead", False)

        blocks.append({
            "type": "deadhead" if is_dh else "train",
            "label": str(train_id) + (" [V]" if is_dh else ""),
            "detail": from_st + " → " + to_st,
            "train_id": str(train_id),
            "start": dep_m, "end": arr_m,
            "start_time": seg_get(seg, "dep_time"),
            "end_time": seg_get(seg, "arr_time"),
            "duration": seg_dur,
            "from_station": from_st,
            "to_station": to_st,
            "is_deadhead": bool(is_dh),
        })

        # Gap dopo questo segmento
        if i < len(segs) - 1:
            next_dep_str = seg_get(segs[i + 1], "dep_time")
            next_from_st = seg_get(segs[i + 1], "from_station", "")
            next_dep_m = _time_to_min(next_dep_str)
            if next_dep_m < pres_m:
                next_dep_m += 24 * 60

            if next_dep_m > arr_m:
                if (not meal_placed and meal_s_m is not None
                        and meal_s_m >= arr_m and meal_e_m <= next_dep_m):
                    if meal_s_m > arr_m:
                        blocks.append({
                            "type": "attesa", "label": "Attesa",
                            "start": arr_m, "end": meal_s_m,
                            "start_time": _min_to_time(arr_m),
                            "end_time": _min_to_time(meal_s_m),
                            "duration": meal_s_m - arr_m,
                            "from_station": to_st, "to_station": to_st,
                        })
                    blocks.append({
                        "type": "meal", "label": "Refezione",
                        "start": meal_s_m, "end": meal_e_m,
                        "start_time": summary.meal_start,
                        "end_time": summary.meal_end,
                        "duration": meal_e_m - meal_s_m,
                        "from_station": to_st, "to_station": to_st,
                    })
                    meal_placed = True
                    if meal_e_m < next_dep_m:
                        blocks.append({
                            "type": "attesa", "label": "Attesa",
                            "start": meal_e_m, "end": next_dep_m,
                            "start_time": _min_to_time(meal_e_m),
                            "end_time": next_dep_str,
                            "duration": next_dep_m - meal_e_m,
                            "from_station": to_st, "to_station": next_from_st,
                        })
                else:
                    blocks.append({
                        "type": "attesa", "label": "Attesa",
                        "start": arr_m, "end": next_dep_m,
                        "start_time": _min_to_time(arr_m),
                        "end_time": next_dep_str,
                        "duration": next_dep_m - arr_m,
                        "from_station": to_st, "to_station": next_from_st,
                    })

    # Refezione non piazzata → gap migliore
    if not meal_placed and meal_s_m is not None:
        best_gap = None
        best_gap_station = ""
        for i in range(len(segs) - 1):
            arr_str = seg_get(segs[i], "arr_time")
            dep_str = seg_get(segs[i + 1], "dep_time")
            arr_m_gap = _time_to_min(arr_str)
            dep_m_gap = _time_to_min(dep_str)
            if arr_m_gap < pres_m:
                arr_m_gap += 24 * 60
            if dep_m_gap < pres_m:
                dep_m_gap += 24 * 60
            gap_dur = dep_m_gap - arr_m_gap
            if gap_dur >= MEAL_MIN and (best_gap is None or gap_dur > best_gap[2]):
                best_gap = (arr_m_gap, dep_m_gap, gap_dur)
                best_gap_station = seg_get(segs[i], "to_station", "")
        if best_gap:
            meal_s_adj = best_gap[0]
            meal_e_adj = meal_s_adj + MEAL_MIN
            blocks.append({
                "type": "meal", "label": "Refezione",
                "start": meal_s_adj, "end": meal_e_adj,
                "start_time": _min_to_time(meal_s_adj),
                "end_time": _min_to_time(meal_e_adj),
                "duration": MEAL_MIN,
                "from_station": best_gap_station, "to_station": best_gap_station,
            })

    # 4. Accessori Fine
    acc_end_start = last_arr_m
    acc_end_end = last_arr_m + eff_acc_end
    blocks.append({
        "type": "accessori", "label": "Acc. Fine" + (" (CVL)" if eff_acc_end == 5 else ""),
        "start": acc_end_start, "end": acc_end_end,
        "start_time": last_arr_str,
        "end_time": _min_to_time(acc_end_end),
        "duration": eff_acc_end,
        "from_station": last_to_st, "to_station": last_to_st,
    })

    # 5. Extra Fine
    blocks.append({
        "type": "extra", "label": "Extra Fine",
        "start": acc_end_end, "end": end_m,
        "start_time": _min_to_time(acc_end_end),
        "end_time": _min_to_time(end_m),
        "duration": end_m - acc_end_end,
        "from_station": last_to_st, "to_station": last_to_st,
    })

    # 6. Rientro al deposito — Waterfall a 3 step
    if deposito and last_to_st.upper() != deposito.upper():
        if db:
            rientro_found = False
            last_train_id = seg_get(segs[-1], "train_id", "")

            # STEP 1: Controlla giro materiale
            if last_train_id:
                try:
                    giro_ctx = db.get_giro_chain_context(last_train_id)
                    if giro_ctx and giro_ctx.get("chain") and len(giro_ctx["chain"]) > 1:
                        pos = giro_ctx.get("position", -1)
                        chain = giro_ctx["chain"]
                        dep_upper = deposito.upper()
                        last_upper = last_to_st.upper()

                        for ci in range(pos + 1, len(chain)):
                            c = chain[ci]
                            c_from = (c.get("from") or "").upper().strip()
                            c_to = (c.get("to") or "").upper().strip()

                            from_match = c_from == last_upper or c_from.replace(" ", "") == last_upper.replace(" ", "")
                            to_match = c_to == dep_upper or c_to.replace(" ", "") == dep_upper.replace(" ", "")

                            if from_match and to_match:
                                n_dep_m = _time_to_min(c["dep"])
                                n_arr_m = _time_to_min(c["arr"])
                                if n_dep_m < last_arr_m:
                                    n_dep_m += 24 * 60
                                if n_arr_m < n_dep_m:
                                    n_arr_m += 24 * 60

                                if n_dep_m < last_arr_m:
                                    continue

                                if n_dep_m > end_m:
                                    blocks.append({
                                        "type": "attesa", "label": "Attesa rientro",
                                        "start": end_m, "end": n_dep_m,
                                        "start_time": _min_to_time(end_m),
                                        "end_time": c["dep"],
                                        "duration": n_dep_m - end_m,
                                        "from_station": last_to_st, "to_station": last_to_st,
                                    })

                                blocks.append({
                                    "type": "giro_return",
                                    "label": f"Giro {c['train_id']}",
                                    "detail": f"{last_to_st} → {deposito} (giro mat.)",
                                    "start": n_dep_m, "end": n_arr_m,
                                    "start_time": c["dep"],
                                    "end_time": c["arr"],
                                    "duration": n_arr_m - n_dep_m,
                                    "from_station": last_to_st,
                                    "to_station": deposito,
                                    "train_id": c["train_id"],
                                    "is_deadhead": c.get("is_deadhead", False),
                                })
                                rientro_found = True
                                break
                except Exception as e:
                    import traceback
                    print(f"[WARN] Giro materiale check failed for {last_train_id}: {e}")
                    traceback.print_exc()

            # STEP 2: Cerca nel DB treni di collegamento
            if not rientro_found:
                try:
                    connections = db.find_connecting_trains(
                        from_station=last_to_st,
                        after_time=_min_to_time(last_arr_m),
                        to_station=deposito,
                        limit=3,
                    )
                    if connections:
                        conn = connections[0]
                        c_dep_m = _time_to_min(conn["dep_time"])
                        c_arr_m = _time_to_min(conn["arr_time"])
                        if c_dep_m < last_arr_m:
                            c_dep_m += 24 * 60
                        if c_arr_m < c_dep_m:
                            c_arr_m += 24 * 60

                        if c_dep_m > end_m:
                            blocks.append({
                                "type": "attesa", "label": "Attesa spostamento",
                                "start": end_m, "end": c_dep_m,
                                "start_time": _min_to_time(end_m),
                                "end_time": conn["dep_time"],
                                "duration": c_dep_m - end_m,
                                "from_station": last_to_st, "to_station": last_to_st,
                            })

                        blocks.append({
                            "type": "spostamento",
                            "label": f"Spost. {conn.get('train_id', '?')}",
                            "detail": f"{last_to_st} → {deposito}",
                            "start": c_dep_m, "end": c_arr_m,
                            "start_time": conn["dep_time"],
                            "end_time": conn["arr_time"],
                            "duration": c_arr_m - c_dep_m,
                            "from_station": last_to_st,
                            "to_station": deposito,
                            "train_id": conn.get("train_id", ""),
                        })
                        rientro_found = True
                except Exception as e:
                    print(f"[WARN] find_connecting_trains failed: {e}")

            # STEP 3: Nessun rientro trovato
            if not rientro_found:
                blocks.append({
                    "type": "spostamento",
                    "label": "⚠ No rientro",
                    "detail": f"Nessun treno da {last_to_st} a {deposito}",
                    "start": end_m, "end": end_m + 15,
                    "start_time": _min_to_time(end_m),
                    "end_time": _min_to_time(end_m + 15),
                    "duration": 0,
                    "from_station": last_to_st, "to_station": last_to_st,
                })

    return blocks
