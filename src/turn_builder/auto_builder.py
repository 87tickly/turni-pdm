"""
Turn Builder Automatico — AI ENGINE v3

Architettura a 4 fasi:
  FASE 1 · POOL   — genera tutte le catene candidate (DFS branching)
  FASE 2 · BUILD  — multi-restart con rest-aware scheduling
  FASE 3 · EVOLVE — genetic crossover dei migliori turni
  FASE 4 · REFINE — simulated annealing (swap / replace locale)

Intelligenze attive:
  • Rest-aware: inizio giorno N+1 calcolato da fine giorno N (11h/14h/16h)
  • Meal-aware: catene con gap valido per refezione ricevono bonus
  • Diversità: alternanza mattina/pomeriggio/sera forzata
  • FR strategico: pianifica dormite FR per depositi con poche connessioni
  • Efficienza: rapporto condotta/prestazione nel punteggio
  • Anti-starvation: penalizza giornate con condotta < 2h
"""

import math
import random
from copy import deepcopy

from ..database.db import Database
from ..validator.rules import (
    TurnValidator, DaySummary, Violation,
    _time_to_min, _min_to_time, _fmt_min,
)
from ..constants import (
    MAX_PRESTAZIONE_MIN,
    MAX_CONDOTTA_MIN,
    MEAL_MIN,
    MEAL_WINDOW_1_START, MEAL_WINDOW_1_END,
    MEAL_WINDOW_2_START, MEAL_WINDOW_2_END,
    ACCESSORY_RULES, TEMPI_MEDI_RULES,
    EXTRA_START_MIN, EXTRA_END_MIN,
    WORK_BLOCK, REST_BLOCK,
    TARGET_CONDOTTA_MIN,
    REST_STANDARD_H, REST_AFTER_001_0100_H, REST_AFTER_NIGHT_H,
    FR_MAX_PRESTAZIONE_RIENTRO_MIN,
    WEEKLY_REST_MIN_H,
)

# ── Vincoli turno ──
FIRST_DAY_MIN_START_HOUR = 13    # primo giorno: partenza dopo le 13:00
LAST_DAY_MAX_END_HOUR = 15      # ultimo giorno: fine non dopo le 15:00
MIN_TOTAL_REST_H = 62           # riposo totale minimo nel ciclo 5+2

# ── Filtri segmento ──
MIN_SEG_DURATION = 10
MAX_SEG_DURATION = 300
MIN_CONFIDENCE = 0.5
MIN_DEP_HOUR = 4
MAX_DEP_HOUR = 23

# ── AI Engine params ──
NUM_RESTARTS     = 25       # fase 2: tentativi multi-restart
MAX_CHAINS       = 120      # fase 1: catene candidate max per pool
DFS_BRANCH       = 4        # fase 1: rami DFS per nodo
DFS_DEPTH        = 10       # fase 1: profondità max catena
MIN_COND_CHAIN   = 60       # scarta catene con condotta < 1h
MAX_GAP_MIN      = 180      # max attesa tra treni (3h)

# Genetic
POPULATION_SIZE  = 8        # fase 3: top turni da incrociare
CROSSOVER_ROUNDS = 15       # fase 3: round di crossover

# Simulated Annealing
SA_ITERATIONS    = 40       # fase 4: iterazioni SA
SA_TEMP_START    = 300.0    # fase 4: temperatura iniziale
SA_TEMP_END      = 10.0     # fase 4: temperatura finale


class AutoBuilder:
    """Builder automatico AI Engine v3 per turni PDM."""

    def __init__(self, db: Database, deposito: str = ""):
        self.db = db
        self.deposito = deposito.upper().strip()
        self.validator = TurnValidator(deposito=self.deposito)
        self._used_trains_global: set[str] = set()

        if self.deposito:
            self._reachable = set(
                s.upper() for s in self.db.get_reachable_stations(self.deposito)
            )
        else:
            self._reachable = set()

        # ── Cache abilitazioni del deposito ──
        # Carico le abilitazioni una volta sola; il filtro
        # is_segment_enabled() viene applicato solo se l'utente ha
        # almeno 1 linea configurata. Senza configurazione il builder
        # cade nel comportamento legacy (zero filtro abilitazioni).
        self._enabled_lines: set[tuple[str, str]] = set()
        self._enabled_materials: set[str] = set()
        if self.deposito:
            self._enabled_lines = set(self.db.get_enabled_lines(self.deposito))
            self._enabled_materials = set(self.db.get_enabled_materials(self.deposito))
        self._abilitazioni_active: bool = len(self._enabled_lines) > 0
        # Cache per evitare N query: material_turn_id -> endpoints + material_type
        self._endpoint_cache: dict = {}
        self._material_cache: dict = {}

        self._overhead = self._compute_overhead()

    # ═══════════════════════════════════════════════════════
    #  ABILITAZIONI (filtro + cache)
    # ═══════════════════════════════════════════════════════
    def _seg_abilitato(self, seg: dict) -> bool:
        """
        True se il segmento e' abilitato per il deposito (linea +
        materiale). Linea = coppia (from, to) normalizzata del segmento
        stesso (granulare: ogni tratta del giro materiale e' una linea
        a se'). Se l'utente non ha configurato abilitazioni, ritorna
        sempre True (compat retroattivita').
        """
        if not self._abilitazioni_active:
            return True
        from_st = (seg.get("from_station", "") if isinstance(seg, dict) else getattr(seg, "from_station", "")).upper().strip()
        to_st = (seg.get("to_station", "") if isinstance(seg, dict) else getattr(seg, "to_station", "")).upper().strip()
        if not from_st or not to_st or from_st == to_st:
            return False
        line = self.db._normalize_line_pair(from_st, to_st)
        if line not in self._enabled_lines:
            return False
        # Materiale (cache via material_turn_id)
        mat_turn_id = seg.get("material_turn_id") if isinstance(seg, dict) else getattr(seg, "material_turn_id", None)
        if not mat_turn_id:
            return True
        if mat_turn_id not in self._material_cache:
            cur = self.db._cursor()
            cur.execute(self.db._q("SELECT material_type FROM material_turn WHERE id = ?"),
                        (mat_turn_id,))
            row = cur.fetchone()
            mat = ""
            if row:
                d = self.db._dict(row)
                mat = (d.get("material_type") or "").upper().strip()
            self._material_cache[mat_turn_id] = mat
        mat = self._material_cache[mat_turn_id]
        if not mat:
            # Wildcard sul materiale: parser bug
            return True
        return mat in self._enabled_materials

    # ═══════════════════════════════════════════════════════
    #  UTILITÀ
    # ═══════════════════════════════════════════════════════
    def _compute_overhead(self) -> int:
        return (ACCESSORY_RULES["default_start"] + ACCESSORY_RULES["default_end"]
                + TEMPI_MEDI_RULES["default_extra"]
                + EXTRA_START_MIN + EXTRA_END_MIN + MEAL_MIN)

    @staticmethod
    def _seg_condotta(seg: dict) -> int:
        if seg.get("is_deadhead", False):
            return 0
        d = _time_to_min(seg["dep_time"])
        a = _time_to_min(seg["arr_time"])
        if a < d: a += 1440
        return a - d

    @staticmethod
    def _chain_condotta(chain: list[dict]) -> int:
        t = 0
        for s in chain:
            if s.get("is_deadhead", False): continue
            d = _time_to_min(s["dep_time"])
            a = _time_to_min(s["arr_time"])
            if a < d: a += 1440
            t += a - d
        return t

    @staticmethod
    def _chain_span(chain: list[dict]) -> int:
        f = _time_to_min(chain[0]["dep_time"])
        l = _time_to_min(chain[-1]["arr_time"])
        if l < f: l += 1440
        return l - f

    @staticmethod
    def _chain_end_min(chain: list[dict]) -> int:
        """Orario fine catena (con accessori) in minuti."""
        last_arr = _time_to_min(chain[-1]["arr_time"])
        return last_arr + ACCESSORY_RULES["default_end"] + EXTRA_END_MIN

    @staticmethod
    def _chain_start_min(chain: list[dict]) -> int:
        """Orario inizio catena (con accessori) in minuti."""
        first_dep = _time_to_min(chain[0]["dep_time"])
        return first_dep - ACCESSORY_RULES["default_start"] - EXTRA_START_MIN

    @staticmethod
    def _chain_train_ids(chain: list[dict]) -> set[str]:
        return {s.get("train_id", "") for s in chain}

    def _last_station(self, chain: list[dict]) -> str:
        return chain[-1].get("to_station", "").upper() if chain else ""

    def _returns_depot(self, chain: list[dict]) -> bool:
        return self._last_station(chain) == self.deposito

    def _required_rest_h(self, end_time_min: int) -> float:
        """Calcola ore di riposo minime basate sull'orario di fine turno."""
        end_mod = end_time_min % 1440
        # Controlla fascia 00:01 - 01:00
        if 1 <= end_mod <= 60:
            return REST_AFTER_001_0100_H
        # Controlla se era notturno (fine dopo mezzanotte sostanzialmente)
        if end_mod > 60 and end_mod < MIN_DEP_HOUR * 60:
            return REST_AFTER_NIGHT_H
        return REST_STANDARD_H

    # ═══════════════════════════════════════════════════════
    #  FILTRO SEGMENTI
    # ═══════════════════════════════════════════════════════
    def _filter_segments(self, segments: list, exclude_trains: set = None,
                         apply_zone_and_abilitazioni: bool = True) -> list:
        """
        Filtra segmenti per validita' generale (durata, ora, confidence)
        e opzionalmente per zona reachable + abilitazioni del deposito.

        apply_zone_and_abilitazioni=False usato per il pool di
        candidati di rientro: anche treni di linee non abilitate o fuori
        zona possono servire da rientro in vettura (deadhead).
        """
        excl = (exclude_trains or set()) | self._used_trains_global
        good = []
        for seg in segments:
            if seg.get("train_id", "") in excl: continue
            if seg.get("confidence", 0) < MIN_CONFIDENCE: continue
            dep_m = _time_to_min(seg["dep_time"])
            arr_m = _time_to_min(seg["arr_time"])
            if arr_m < dep_m: arr_m += 1440
            dur = arr_m - dep_m
            if dur < MIN_SEG_DURATION or dur > MAX_SEG_DURATION: continue
            if dep_m // 60 < MIN_DEP_HOUR or dep_m // 60 >= MAX_DEP_HOUR: continue
            if apply_zone_and_abilitazioni:
                if self._reachable:
                    if (seg.get("from_station", "").upper() not in self._reachable or
                        seg.get("to_station", "").upper() not in self._reachable):
                        continue
                if not self._seg_abilitato(seg):
                    continue
            good.append(seg)
        return good

    # ═══════════════════════════════════════════════════════
    #  RIENTRO AL DEPOSITO (in condotta o in vettura)
    # ═══════════════════════════════════════════════════════
    def _try_return_segment(self, all_day_segments: list, cur_st: str,
                             cur_arr: int, first_dep: int, used: set,
                             current_cond: int):
        """
        Cerca un treno cur_st -> deposito tra TUTTI i segmenti del giorno
        (non filtrati per zona/abilitazione). Se trovato e ammissibile:
        - Se abilitato per il deposito -> ritorna in CONDOTTA (segmento
          tale e quale, condotta contata)
        - Se non abilitato (linea o materiale) -> ritorna in VETTURA
          (copia del segmento marcata is_deadhead=True, condotta non
          contata, treno non consumato come "produttivo")

        Vincoli rientro:
          - dep >= cur_arr + 5 min (cambio treno minimo)
          - gap <= 300 min (5h finestra rientro, piu' larga del normale)
          - span totale + overhead <= MAX_PRESTAZIONE_MIN
          - condotta totale (se in condotta) <= MAX_CONDOTTA_MIN

        Sceglie il primo per gap crescente.
        """
        if not self.deposito or not all_day_segments:
            return None
        MIN_CHANGE_MIN = 5
        MAX_RETURN_GAP = 300
        candidates = []
        for seg in all_day_segments:
            tid = seg.get("train_id", "")
            if tid in used: continue
            if seg.get("from_station", "").upper() != cur_st: continue
            if seg.get("to_station", "").upper() != self.deposito: continue
            dep_m = _time_to_min(seg["dep_time"])
            if dep_m < cur_arr + MIN_CHANGE_MIN: continue
            gap = dep_m - cur_arr
            if gap > MAX_RETURN_GAP: continue
            arr_m = _time_to_min(seg["arr_time"])
            if arr_m < dep_m: arr_m += 1440
            span = arr_m - first_dep
            if span < 0: span += 1440
            if (span + self._overhead) > MAX_PRESTAZIONE_MIN: continue
            # In condotta solo se abilitato E condotta non sfora
            is_enabled = self._seg_abilitato(seg)
            seg_c = self._seg_condotta(seg)
            if is_enabled and (current_cond + seg_c) <= MAX_CONDOTTA_MIN:
                ret_seg = seg  # in condotta
            else:
                ret_seg = {**seg, "is_deadhead": True}  # in vettura
            candidates.append((gap, ret_seg))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]

    # ═══════════════════════════════════════════════════════
    #  FASE 1 · POOL — DFS BRANCHING
    # ═══════════════════════════════════════════════════════
    def _build_chain_pool(self, segments: list,
                          min_start: int = 0,
                          all_day_segments: list = None) -> list[list[dict]]:
        """
        Genera pool di catene candidate via DFS con branching.
        min_start: minuto minimo di partenza del primo treno.
        all_day_segments: TUTTI i segmenti del giorno (non filtrati per
            zona/abilitazione). Usato per cercare treni di rientro al
            deposito anche su linee non-abilitate (in tal caso il
            rientro viene marcato in vettura/deadhead).
        """
        if not self.deposito:
            return []

        deposito = self.deposito
        if all_day_segments is None:
            all_day_segments = segments
        departing = [s for s in segments
                     if (s.get("from_station", "").upper() == deposito
                         and _time_to_min(s["dep_time"]) >= min_start)]
        if not departing:
            return []

        pool: list[list[dict]] = []

        for start_seg in departing:
            s_cond = self._seg_condotta(start_seg)
            s_arr  = _time_to_min(start_seg["arr_time"])
            s_st   = start_seg.get("to_station", "").upper()
            s_dep  = _time_to_min(start_seg["dep_time"])

            if s_st == deposito:
                if s_cond >= MIN_COND_CHAIN:
                    pool.append([start_seg])
                continue

            # DFS: (chain, station, arr_m, condotta, used_ids, first_dep_m)
            stack = [([start_seg], s_st, s_arr, s_cond,
                      {start_seg.get("train_id", "")}, s_dep)]

            while stack and len(pool) < MAX_CHAINS:
                chain, cur_st, cur_arr, cur_cond, used, first_dep = stack.pop()

                if len(chain) >= DFS_DEPTH:
                    if cur_cond >= MIN_COND_CHAIN:
                        pool.append(list(chain))
                        # CVL: cerca sotto-catene che passano per il deposito
                        if cur_st != deposito:
                            # Iniezione rientro (in condotta o in vettura)
                            ret = self._try_return_segment(
                                all_day_segments, cur_st, cur_arr,
                                first_dep, used, cur_cond,
                            )
                            if ret is not None:
                                pool.append(list(chain) + [ret])
                            self._extract_cvl_subchains(chain, deposito, pool)
                    continue

                cands = []
                for seg in segments:
                    tid = seg.get("train_id", "")
                    if tid in used: continue
                    if seg.get("from_station", "").upper() != cur_st: continue
                    dep_m = _time_to_min(seg["dep_time"])
                    if dep_m < cur_arr and (cur_arr - dep_m) < 720: continue
                    gap = dep_m - cur_arr
                    if gap < 0: gap += 1440
                    if gap > MAX_GAP_MIN: continue
                    seg_c = self._seg_condotta(seg)
                    nc = cur_cond + seg_c
                    if nc > MAX_CONDOTTA_MIN: continue
                    arr_m = _time_to_min(seg["arr_time"])
                    if arr_m < dep_m: arr_m += 1440
                    span = arr_m - first_dep
                    if span < 0: span += 1440
                    if (span + self._overhead) > MAX_PRESTAZIONE_MIN: continue
                    cands.append((gap, seg, nc, arr_m))

                if not cands:
                    if cur_cond >= MIN_COND_CHAIN:
                        pool.append(list(chain))
                        # ── CVL: se la catena NON rientra al deposito,
                        # cerca un punto intermedio dove passa per il deposito
                        # e aggiungi anche la sotto-catena tagliata lì (cambio volante)
                        if cur_st != deposito:
                            # Iniezione rientro (in condotta o in vettura)
                            ret = self._try_return_segment(
                                all_day_segments, cur_st, cur_arr,
                                first_dep, used, cur_cond,
                            )
                            if ret is not None:
                                pool.append(list(chain) + [ret])
                            self._extract_cvl_subchains(chain, deposito, pool)
                    continue

                cands.sort(key=lambda x: x[0])
                for gap, seg, nc, arr_m in cands[:DFS_BRANCH]:
                    new_chain = chain + [seg]
                    new_st = seg.get("to_station", "").upper()
                    new_used = used | {seg.get("train_id", "")}

                    if new_st == deposito:
                        if nc >= MIN_COND_CHAIN:
                            pool.append(new_chain)
                        # Se condotta bassa, prova a ripartire dal deposito
                        if nc < TARGET_CONDOTTA_MIN:
                            stack.append((new_chain, new_st, arr_m, nc,
                                          new_used, first_dep))
                    else:
                        stack.append((new_chain, new_st, arr_m, nc,
                                      new_used, first_dep))

        return pool

    def _extract_cvl_subchains(self, chain: list[dict],
                                deposito: str,
                                pool: list[list[dict]]) -> None:
        """
        CVL (Cambio Volante): se una catena NON rientra al deposito,
        cerca punti intermedi dove un segmento arriva al deposito.
        In quel caso "taglia" la catena lì e aggiunge la sotto-catena
        al pool — il macchinista scende al deposito, il treno prosegue.

        Questo garantisce che il pool contenga sempre catene che rientrano
        al deposito, anche quando la catena completa proseguirebbe oltre.
        """
        for i, seg in enumerate(chain):
            to_st = seg.get("to_station", "").upper()
            if to_st == deposito and i > 0:
                # Sotto-catena: dal primo segmento fino a questo (incluso)
                sub = chain[:i + 1]
                sub_cond = self._chain_condotta(sub)
                if sub_cond >= MIN_COND_CHAIN:
                    # Evita duplicati esatti (controlla train_ids)
                    sub_ids = self._chain_train_ids(sub)
                    already = any(
                        self._chain_train_ids(p) == sub_ids for p in pool
                    )
                    if not already and len(pool) < MAX_CHAINS:
                        pool.append(sub)

    # ═══════════════════════════════════════════════════════
    #  SCORING CATENA (singola giornata)
    # ═══════════════════════════════════════════════════════
    def _score_chain(self, chain: list[dict]) -> float:
        cond = self._chain_condotta(chain)
        span = self._chain_span(chain)
        ret  = self._returns_depot(chain)

        score = 0.0

        # Condotta: puntare al TARGET (180min = 3h), non massimizzare
        # Parabola invertita centrata sul target: max score a 180min
        diff = abs(cond - TARGET_CONDOTTA_MIN)
        if cond >= TARGET_CONDOTTA_MIN:
            # Sopra target: penalità crescente ma meno severa (meglio avere di più che di meno)
            score += 500 - diff * 1.5
        else:
            # Sotto target: penalità più forte
            score += 500 - diff * 3.0

        # Rientro deposito: fondamentale (CVL — il turno DEVE finire al deposito)
        score += 1200 if ret else -800

        # Efficienza: condotta / span — meno tempo morto = meglio
        if span > 0:
            score += (cond / span) * 200

        # Penalità catene troppo corte (< 2h)
        if cond < 120:
            score -= (120 - cond) * 5

        # MEAL-AWARE: bonus se c'è un gap valido per refezione
        meal_ok = self._has_valid_meal_gap(chain)
        score += 200 if meal_ok else -100

        # Penalizza catene con attese lunghe (> 60 min tra treni)
        max_wait = self._max_wait_in_chain(chain)
        if max_wait > 60:
            score -= (max_wait - 60) * 1.5

        return score

    def _has_valid_meal_gap(self, chain: list[dict]) -> bool:
        """Verifica se la catena ha almeno un gap >= 30min in finestra refezione."""
        for i in range(len(chain) - 1):
            arr_m = _time_to_min(chain[i]["arr_time"])
            dep_m = _time_to_min(chain[i + 1]["dep_time"])
            if dep_m < arr_m: dep_m += 1440
            gap = dep_m - arr_m
            if gap < MEAL_MIN: continue
            # Check finestre
            for ws, we in [(MEAL_WINDOW_1_START, MEAL_WINDOW_1_END),
                           (MEAL_WINDOW_2_START, MEAL_WINDOW_2_END)]:
                slot_s = max(arr_m, ws)
                slot_e = slot_s + MEAL_MIN
                if slot_e <= min(dep_m, we):
                    return True
        return False

    def _max_wait_in_chain(self, chain: list[dict]) -> int:
        """Attesa massima tra treni consecutivi nella catena."""
        mx = 0
        for i in range(len(chain) - 1):
            arr_m = _time_to_min(chain[i]["arr_time"])
            dep_m = _time_to_min(chain[i + 1]["dep_time"])
            if dep_m < arr_m: dep_m += 1440
            mx = max(mx, dep_m - arr_m)
        return mx

    # ═══════════════════════════════════════════════════════
    #  SCORING GLOBALE TURNO
    # ═══════════════════════════════════════════════════════
    def _score_schedule(self, entries: list[dict]) -> float:
        """
        Punteggio globale di un turno completo.

        10 fattori pesati:
          1. Condotta totale
          2. Media condotta vs target
          3. Bilanciamento (std dev bassa)
          4. Giornata peggiore (anti-starvation)
          5. Rientri deposito
          6. Violazioni
          7. Giornate vuote
          8. Rispetto riposo tra turni
          9. Efficienza media (condotta/prestazione)
         10. Diversità fasce orarie
        """
        turns = [e for e in entries if e["type"] == "TURN"]
        conds, prest_list, start_hours_list = [], [], []
        violations = 0
        depot_ret = 0
        empty = 0
        rest_ok = 0
        rest_total = 0

        prev_end = None
        for e in turns:
            s = e.get("summary")
            if not s or not s.segments:
                empty += 1
                prev_end = None
                continue
            conds.append(s.condotta_min)
            prest_list.append(s.prestazione_min)
            violations += len(s.violations)

            last_seg = s.segments[-1]
            lt = (last_seg.get("to_station", "").upper()
                  if isinstance(last_seg, dict) else last_seg.to_station.upper())
            if lt == self.deposito:
                depot_ret += 1

            # Fascia oraria partenza
            first_dep = (s.segments[0].get("dep_time", "06:00")
                         if isinstance(s.segments[0], dict)
                         else s.segments[0].dep_time)
            start_hours_list.append(_time_to_min(first_dep) // 60)

            # Verifica rest con giorno precedente
            if prev_end is not None:
                pres_m = _time_to_min(s.presentation_time) if s.presentation_time else None
                if pres_m is not None:
                    rest_total += 1
                    rest_min = pres_m - prev_end
                    if rest_min <= 0: rest_min += 1440
                    req_h = self._required_rest_h(prev_end)
                    if rest_min >= req_h * 60:
                        rest_ok += 1

            if s.end_time:
                prev_end = _time_to_min(s.end_time)
            else:
                prev_end = None

        if not conds:
            return -100000

        n = len(conds)
        avg = sum(conds) / n
        total = sum(conds)
        std = (sum((c - avg) ** 2 for c in conds) / n) ** 0.5
        mn = min(conds)
        mx = max(conds)

        # Efficienza media
        eff_list = [c / p if p > 0 else 0 for c, p in zip(conds, prest_list)]
        avg_eff = sum(eff_list) / len(eff_list) if eff_list else 0

        # Diversità fasce orarie
        unique_hours = len(set(start_hours_list))

        score = 0.0

        # 1. Condotta: puntare al target, non massimizzare
        # Bonus per media vicina al target (180min), penalità se troppo alta o bassa
        avg_diff = abs(avg - TARGET_CONDOTTA_MIN)
        if avg_diff < 30:
            score += 600  # media perfetta (150-210 min)
        elif avg_diff < 60:
            score += 300  # buona (120-240 min)
        else:
            score -= avg_diff * 3  # troppo lontana dal target

        # 2. Penalità media troppo alta (>4h = 240min) — equità tra depositi
        if avg > 240:
            score -= (avg - 240) * 5

        # 3. Bilanciamento
        score -= std * 12.0

        # 4. Anti-starvation: giornata peggiore
        if mn < 90:
            score -= (90 - mn) * 15
        elif mn >= TARGET_CONDOTTA_MIN:
            score += 400  # tutte le giornate sopra target
        elif mn >= 120:
            score += 200

        # 5. Rientri deposito
        score += depot_ret * 350
        # Bonus tutti rientri
        if depot_ret == n:
            score += 500

        # 6. Violazioni (penalità forte)
        score -= violations * 250

        # 7. Giornate vuote
        score -= empty * 3000

        # 8. Rispetto riposo tra turni
        if rest_total > 0:
            rest_ratio = rest_ok / rest_total
            score += rest_ratio * 600
            if rest_ok == rest_total:
                score += 400  # bonus tutti ok

        # 9. Efficienza media
        score += avg_eff * 500

        # 10. Diversita fasce orarie
        score += unique_hours * 80

        # 11. Vincolo primo giorno dopo le 13:00
        if start_hours_list:
            first_hour = start_hours_list[0]
            if first_hour >= FIRST_DAY_MIN_START_HOUR:
                score += 400  # bonus primo giorno corretto
            else:
                score -= (FIRST_DAY_MIN_START_HOUR - first_hour) * 100  # penalita

        # 12. Vincolo ultimo giorno fine entro le 15:00 (HARD)
        if turns:
            last_t = turns[-1]
            ls = last_t.get("summary")
            if ls and ls.end_time:
                end_h = _time_to_min(ls.end_time) / 60
                if end_h <= LAST_DAY_MAX_END_HOUR:
                    score += 800  # bonus forte ultimo giorno corretto
                else:
                    # Penalita molto forte: -1000 per ora oltre le 15:00
                    score -= (end_h - LAST_DAY_MAX_END_HOUR) * 1000

        return score

    # ═══════════════════════════════════════════════════════
    #  FASE 2 · BUILD — REST-AWARE MULTI-RESTART
    # ═══════════════════════════════════════════════════════
    def _build_one_schedule(self, n_workdays: int, day_type: str,
                            base_excluded: set,
                            available_days: list[int],
                            randomize: bool = False) -> list[dict]:
        """
        Costruisce un turno completo con REST-AWARE scheduling.

        Per ogni giornata:
          1. Calcola earliest_start dal riposo obbligatorio
          2. Genera pool catene con min_start = earliest_start
          3. Filtra catene incompatibili (treni già usati)
          4. Seleziona catena (deterministica o randomizzata)
        """
        self._used_trains_global = set(base_excluded)
        calendar = self.validator.build_calendar(n_workdays)

        # ── VINCOLI PRIMO/ULTIMO GIORNO ──
        # Primo giorno: partenza dopo le 13:00
        # Ultimo giorno: fine non dopo le 15:00
        # Fasce intermedie: alternare mattina/pomeriggio per varieta
        n_turns = sum(1 for e in self.validator.build_calendar(n_workdays) if e["type"] == "TURN")

        if randomize:
            # Fasce intermedie randomizzate
            mid_slots = random.choice([
                [5, 6, 12],
                [6, 5, 13],
                [7, 12, 5],
                [5, 13, 6],
                [12, 6, 7],
            ])
            # Primo giorno: dopo le 13, ultimo giorno: mattina presto (per finire entro le 15)
            time_slots = [FIRST_DAY_MIN_START_HOUR]  # G1 = dopo le 13
            for i in range(1, n_turns - 1):
                time_slots.append(mid_slots[i % len(mid_slots)])
            if n_turns > 1:
                time_slots.append(5)  # Ultimo giorno = mattina presto (finire entro 15:00)
        else:
            time_slots = [FIRST_DAY_MIN_START_HOUR]  # G1 = dopo le 13
            mid = [5, 12, 6, 13]
            for i in range(1, n_turns - 1):
                time_slots.append(mid[i % len(mid)])
            if n_turns > 1:
                time_slots.append(5)  # Ultimo giorno = mattina presto

        prev_end_min = None  # fine turno precedente
        day_idx_cycle = 0
        is_last_day = False

        for entry in calendar:
            if entry["type"] == "REST":
                prev_end_min = None  # dopo riposo, nessun vincolo
                continue

            db_day = available_days[day_idx_cycle % len(available_days)]
            target_hour = time_slots[day_idx_cycle % len(time_slots)]
            is_last_day = (day_idx_cycle == n_turns - 1)

            # ── REST-AWARE: calcola partenza minima ──
            earliest_start_min = target_hour * 60
            if prev_end_min is not None:
                req_rest_h = self._required_rest_h(prev_end_min)
                forced_start = prev_end_min + int(req_rest_h * 60)
                # Sottrai accessori per avere l'orario del primo treno
                forced_train_start = (forced_start
                                      + ACCESSORY_RULES["default_start"]
                                      + EXTRA_START_MIN)
                # ── CAMBIO GIORNO: ogni entry TURN è un giorno diverso ──
                # Se il riposo porta al giorno successivo (>1440), sottrarre 1440
                if forced_train_start >= 1440:
                    forced_train_start -= 1440
                earliest_start_min = max(earliest_start_min, forced_train_start)

            day_idx_cycle += 1

            # ── ULTIMO GIORNO: prova TUTTI i day_index per trovare catene entro le 15 ──
            if is_last_day:
                days_to_try = [db_day] + [d for d in available_days if d != db_day]
            else:
                days_to_try = [db_day]

            pool = []
            filtered = []
            for try_day in days_to_try:
                # Carica segmenti unendo TUTTI i day_index validi (LV/SAB/DOM)
                # per dare al builder massima flessibilita': il deposito
                # piccolo come ALESSANDRIA ha solo 3 segmenti per day_index,
                # ma in union ne ha ~30, abbastanza per chiudere catene
                # con rientro. _used_trains_global previene il riuso.
                day_filtered = self._load_day_segments(
                    try_day, earliest_start_min // 60, available_days,
                    union_all_days=True,
                )
                if not day_filtered:
                    continue

                # Filtra ulteriormente per orario minimo esatto
                day_filtered = [s for s in day_filtered
                                if _time_to_min(s["dep_time"]) >= earliest_start_min]

                # Ultimo giorno: filtra segmenti che arrivano entro le 14:45
                if is_last_day:
                    max_arr = LAST_DAY_MAX_END_HOUR * 60 - 15  # 14:45 = 885 min
                    day_filtered_early = [s for s in day_filtered
                                          if _time_to_min(s["arr_time"]) <= max_arr]
                    if day_filtered_early:
                        day_filtered = day_filtered_early

                if not day_filtered:
                    continue

                filtered = day_filtered

                # Pool completo (no filtro zona/abilitazione) per cercare
                # treni di rientro al deposito anche su linee non abilitate
                # (in tal caso saranno marcati in vettura/deadhead).
                day_unfiltered = self._load_day_segments(
                    try_day, 0, available_days,
                    apply_zone_and_abilitazioni=False,
                    union_all_days=True,
                )

                # Genera pool catene
                day_pool = self._build_chain_pool(
                    day_filtered,
                    min_start=earliest_start_min,
                    all_day_segments=day_unfiltered,
                )
                if day_pool:
                    # Filtra catene con treni gia' usati
                    day_pool = [c for c in day_pool
                                if not (self._chain_train_ids(c) & self._used_trains_global)]
                if not day_pool:
                    continue

                # Ultimo giorno: solo catene che finiscono entro le 15:00
                if is_last_day:
                    max_end = LAST_DAY_MAX_END_HOUR * 60
                    acc_end = ACCESSORY_RULES.get("default_end", 8)
                    pool_early = [c for c in day_pool
                                  if (max(_time_to_min(s["arr_time"]) for s in c)
                                      + acc_end + EXTRA_END_MIN) <= max_end]
                    if pool_early:
                        pool = pool_early
                        break  # Trovate catene valide per l'ultimo giorno!
                    else:
                        pool.extend(day_pool)  # Aggiungi comunque come fallback
                else:
                    pool = day_pool
                    break  # Primo day_index ok

            if not filtered and not pool:
                entry["summary"] = DaySummary(segments=[])
                continue

            if pool:
                summary = self._select_from_pool(pool, randomize=randomize)
            else:
                # Fallback greedy
                sel = self._greedy_select(filtered)
                if sel:
                    summary = self.validator.validate_day(sel, deposito=self.deposito)
                    self._fix_meal_timing(summary)
                else:
                    summary = DaySummary(segments=[])

            entry["summary"] = summary

            # Registra treni usati e fine turno.
            # IMPORTANTE: i segmenti deadhead (rientro in vettura) NON
            # consumano il treno — il PdC e' passivo, quel treno ha il
            # suo macchinista titolare e resta disponibile per altri PdC
            # come treno produttivo.
            if summary.segments:
                for seg in summary.segments:
                    is_dh = (seg.get("is_deadhead", False)
                             if isinstance(seg, dict)
                             else getattr(seg, "is_deadhead", False))
                    if is_dh:
                        continue
                    tid = (seg.get("train_id", "")
                           if isinstance(seg, dict) else seg.train_id)
                    self._used_trains_global.add(tid)
                if summary.end_time:
                    prev_end_min = _time_to_min(summary.end_time)
                else:
                    prev_end_min = None
            else:
                prev_end_min = None

        # ── VINCOLO ULTIMO GIORNO: fine non dopo le 15:00 ──
        turn_entries = [e for e in calendar if e["type"] == "TURN"]
        if turn_entries:
            last_turn = turn_entries[-1]
            if last_turn.get("summary") and last_turn["summary"].segments:
                end_t = last_turn["summary"].end_time
                if end_t:
                    end_min = _time_to_min(end_t)
                    if end_min > LAST_DAY_MAX_END_HOUR * 60:
                        last_turn["summary"].violations.append(
                            Violation(
                                "LAST_DAY_LATE",
                                f"Ultimo giorno finisce alle {end_t}, "
                                f"max consentito {LAST_DAY_MAX_END_HOUR}:00",
                                severity="warning",
                            )
                        )

        # Valida riposo tra turni (per il log)
        self._validate_rest_chain(calendar)

        # ── VINCOLO 62H RIPOSO TOTALE ──
        self._validate_total_rest(calendar)

        return calendar

    def _select_from_pool(self, pool: list[list[dict]],
                          randomize: bool = False) -> DaySummary:
        """
        Seleziona catena dal pool con scoring.

        CVL enforcement: le catene che rientrano al deposito hanno SEMPRE
        priorità assoluta. Solo se non esistono catene depot-returning si
        usa la migliore catena non-depot come fallback (scenario FR).
        """
        scored = [(self._score_chain(c), c) for c in pool]
        scored.sort(key=lambda x: -x[0])

        # ── CVL: separa catene depot-returning da non-depot ──
        depot_chains = [(s, c) for s, c in scored if self._returns_depot(c)]
        non_depot_chains = [(s, c) for s, c in scored if not self._returns_depot(c)]

        # Usa SOLO catene depot-returning se ne esistono almeno una.
        # "il turno che finisce in un deposito viene chiamato CVL"
        if depot_chains:
            scored = depot_chains
        else:
            # Nessuna catena rientra al deposito — fallback (FR/emergenza)
            # Prendi solo la migliore catena non-depot
            scored = non_depot_chains[:1] if non_depot_chains else scored

        if randomize and len(scored) > 1:
            top = scored[:min(7, len(scored))]
            # Softmax-like selection
            max_s = top[0][0]
            weights = [math.exp((s - max_s) / 100.0) for s, _ in top]
            chosen = random.choices(top, weights=weights, k=1)[0]
            chain = chosen[1]
        else:
            chain = scored[0][1]

        summary = self.validator.validate_day(chain, deposito=self.deposito)
        self._fix_meal_timing(summary)
        return summary

    # ═══════════════════════════════════════════════════════
    #  FASE 3 · EVOLVE — GENETIC CROSSOVER
    # ═══════════════════════════════════════════════════════
    def _genetic_crossover(self, population: list[tuple[float, list[dict]]],
                           n_workdays: int, base_excluded: set,
                           available_days: list[int]) -> list[tuple[float, list[dict]]]:
        """
        Incrocia i migliori turni: prende giornate diverse da turni diversi.

        Es: Giorno 1 da turno A, Giorno 2 da turno B, Giorno 3 da turno A...
        Verifica compatibilità treni (no duplicati) e ricalcola score.
        """
        if len(population) < 2:
            return population

        new_pop = list(population)

        for _ in range(CROSSOVER_ROUNDS):
            # Scegli 2 genitori
            p1_idx, p2_idx = random.sample(range(len(population)), 2)
            p1_cal = population[p1_idx][1]
            p2_cal = population[p2_idx][1]

            p1_turns = [e for e in p1_cal if e["type"] == "TURN"]
            p2_turns = [e for e in p2_cal if e["type"] == "TURN"]

            if len(p1_turns) != len(p2_turns):
                continue

            # Crossover: per ogni giorno, scegli casualmente da p1 o p2
            child_cal = deepcopy(p1_cal)
            child_turns = [e for e in child_cal if e["type"] == "TURN"]
            used_trains: set[str] = set(base_excluded)
            valid = True

            for i, (ct, t1, t2) in enumerate(zip(child_turns, p1_turns, p2_turns)):
                # Scegli da quale genitore prendere
                source = random.choice([t1, t2])
                s = source.get("summary")
                if not s or not s.segments:
                    ct["summary"] = DaySummary(segments=[])
                    continue

                # Verifica conflitto treni
                day_trains = set()
                for seg in s.segments:
                    tid = (seg.get("train_id", "")
                           if isinstance(seg, dict) else seg.train_id)
                    day_trains.add(tid)

                if day_trains & used_trains:
                    # Conflitto: prova l'altro genitore
                    alt = t2 if source is t1 else t1
                    alt_s = alt.get("summary")
                    if alt_s and alt_s.segments:
                        alt_trains = set()
                        for seg in alt_s.segments:
                            tid = (seg.get("train_id", "")
                                   if isinstance(seg, dict) else seg.train_id)
                            alt_trains.add(tid)
                        if not (alt_trains & used_trains):
                            ct["summary"] = deepcopy(alt_s)
                            used_trains.update(alt_trains)
                            continue
                    # Entrambi in conflitto: segna vuoto
                    ct["summary"] = DaySummary(segments=[])
                    continue

                ct["summary"] = deepcopy(s)
                used_trains.update(day_trains)

            # Valida e score
            self._validate_rest_chain(child_cal)
            child_score = self._score_schedule(child_cal)
            new_pop.append((child_score, child_cal))

        # Tieni i migliori
        new_pop.sort(key=lambda x: -x[0])
        return new_pop[:POPULATION_SIZE]

    # ═══════════════════════════════════════════════════════
    #  FASE 4 · REFINE — SIMULATED ANNEALING
    # ═══════════════════════════════════════════════════════
    def _simulated_annealing(self, calendar: list[dict], score: float,
                             base_excluded: set,
                             available_days: list[int]) -> tuple[list[dict], float]:
        """
        Ottimizzazione locale: prova a sostituire singole giornate
        con catene alternative. Accetta peggioramenti con probabilità
        decrescente (temperatura).
        """
        best_cal = deepcopy(calendar)
        best_score = score
        current_cal = deepcopy(calendar)
        current_score = score

        turn_indices = [i for i, e in enumerate(current_cal) if e["type"] == "TURN"]
        if not turn_indices:
            return best_cal, best_score

        for iteration in range(SA_ITERATIONS):
            # Temperatura decrescente
            t = SA_TEMP_START * (SA_TEMP_END / SA_TEMP_START) ** (iteration / max(SA_ITERATIONS - 1, 1))

            # Scegli un giorno casuale da migliorare
            day_pos = random.choice(turn_indices)
            entry = current_cal[day_pos]
            old_summary = entry.get("summary")

            # Calcola treni usati ESCLUSO questo giorno
            used_except = set(base_excluded)
            for i, e in enumerate(current_cal):
                if i == day_pos: continue
                s = e.get("summary")
                if s and s.segments:
                    for seg in s.segments:
                        tid = (seg.get("train_id", "")
                               if isinstance(seg, dict) else seg.train_id)
                        used_except.add(tid)

            # Calcola earliest start dal giorno precedente
            earliest = MIN_DEP_HOUR * 60
            for i in range(day_pos - 1, -1, -1):
                pe = current_cal[i]
                if pe["type"] == "REST": break
                ps = pe.get("summary")
                if ps and ps.end_time:
                    prev_end = _time_to_min(ps.end_time)
                    req_h = self._required_rest_h(prev_end)
                    forced = (prev_end + int(req_h * 60)
                              + ACCESSORY_RULES["default_start"]
                              + EXTRA_START_MIN)
                    if forced >= 1440:
                        forced -= 1440
                    earliest = max(earliest, forced)
                    break

            # Genera alternative
            self._used_trains_global = used_except
            db_day = available_days[
                (day_pos % len(turn_indices)) % len(available_days)
            ]
            filtered = self._load_day_segments(db_day, earliest // 60, available_days)
            if filtered:
                filtered = [s for s in filtered
                            if _time_to_min(s["dep_time"]) >= earliest]
            if not filtered:
                continue

            pool = self._build_chain_pool(filtered, min_start=earliest)
            pool = [c for c in pool
                    if not (self._chain_train_ids(c) & used_except)]
            if not pool:
                continue

            # ── VINCOLO ULTIMO GIORNO nel SA ──
            is_last = (day_pos == turn_indices[-1])
            if is_last:
                max_end = LAST_DAY_MAX_END_HOUR * 60
                acc_end = ACCESSORY_RULES.get("default_end", 8)
                pool_early = [c for c in pool
                              if (max(_time_to_min(s["arr_time"]) for s in c)
                                  + acc_end + EXTRA_END_MIN) <= max_end]
                if pool_early:
                    pool = pool_early

            # Scegli catena random dal pool (non la migliore, per esplorare)
            scored = [(self._score_chain(c), c) for c in pool]
            scored.sort(key=lambda x: -x[0])
            top = scored[:min(5, len(scored))]
            chain = random.choice(top)[1]

            new_summary = self.validator.validate_day(chain, deposito=self.deposito)
            self._fix_meal_timing(new_summary)

            # Prova il swap
            trial_cal = deepcopy(current_cal)
            trial_cal[day_pos]["summary"] = new_summary
            self._validate_rest_chain(trial_cal)
            trial_score = self._score_schedule(trial_cal)

            delta = trial_score - current_score
            if delta > 0 or random.random() < math.exp(delta / max(t, 0.01)):
                current_cal = trial_cal
                current_score = trial_score
                if trial_score > best_score:
                    best_cal = deepcopy(trial_cal)
                    best_score = trial_score

        return best_cal, best_score

    # ═══════════════════════════════════════════════════════
    #  VALIDATE REST CHAIN
    # ═══════════════════════════════════════════════════════
    def _validate_rest_chain(self, calendar: list[dict]):
        """Valida e aggiunge violazioni riposo tra turni consecutivi."""
        turn_entries = [e for e in calendar
                        if e["type"] == "TURN" and e.get("summary")]
        for i in range(len(turn_entries) - 1):
            s1 = turn_entries[i]["summary"]
            s2 = turn_entries[i + 1]["summary"]
            if s1 and s2 and s1.segments and s2.segments:
                rest_v = self.validator.validate_rest_between(s1, s2)
                # Rimuovi vecchie violazioni REST se presenti
                s2.violations = [
                    v for v in s2.violations if v.rule != "MIN_REST"
                ]
                s2.violations.extend(rest_v)

    # ═══════════════════════════════════════════════════════
    #  VALIDATE TOTAL REST (62h minimo nel ciclo)
    # ═══════════════════════════════════════════════════════
    def _validate_total_rest(self, calendar: list[dict]):
        """
        Verifica che il riposo totale nel ciclo sia >= 62 ore.
        Calcola: (tempo totale ciclo) - (somma prestazioni).
        """
        turn_entries = [e for e in calendar
                        if e["type"] == "TURN" and e.get("summary")]
        if len(turn_entries) < 2:
            return

        # Calcola ore totali di prestazione
        total_prest_min = 0
        for e in turn_entries:
            s = e.get("summary")
            if s and s.segments:
                total_prest_min += s.prestazione_min

        # Tempo totale del ciclo (dal primo presentation_time all'ultimo end_time)
        first_pres = None
        last_end = None
        for e in turn_entries:
            s = e.get("summary")
            if s and s.segments:
                if s.presentation_time and first_pres is None:
                    first_pres = s.presentation_time
                if s.end_time:
                    last_end = s.end_time

        if first_pres and last_end:
            # Il ciclo 5+2 dura 7 giorni = 7*24*60 = 10080 minuti
            total_cycle_min = 7 * 24 * 60
            total_rest_min = total_cycle_min - total_prest_min
            total_rest_h = total_rest_min / 60

            if total_rest_h < MIN_TOTAL_REST_H:
                # Aggiungi violation al primo turno
                for e in turn_entries:
                    s = e.get("summary")
                    if s and s.segments:
                        s.violations.append(
                            Violation(
                                "RIPOSO_TOTALE_INSUFFICIENTE",
                                f"Riposo totale {total_rest_h:.0f}h, "
                                f"minimo richiesto {MIN_TOTAL_REST_H}h",
                                severity="error",
                            )
                        )
                        break  # Solo sul primo

    # ═══════════════════════════════════════════════════════
    #  DEDUP CHECK — Verifica treni non ripetuti
    # ═══════════════════════════════════════════════════════
    def _verify_no_duplicates(self, calendar: list[dict]) -> list[str]:
        """
        Verifica che nessun treno sia usato in piu di una giornata.
        Ritorna lista di treni duplicati (vuota = OK).
        """
        seen: dict[str, int] = {}  # train_id -> day number
        duplicates = []
        for e in calendar:
            if e["type"] != "TURN":
                continue
            s = e.get("summary")
            if not s or not s.segments:
                continue
            day_num = e.get("day", 0)
            for seg in s.segments:
                tid = (seg.get("train_id", "")
                       if isinstance(seg, dict) else seg.train_id)
                if tid in seen:
                    duplicates.append(tid)
                    # Rimuovi dalla giornata corrente per fix
                else:
                    seen[tid] = day_num
        return duplicates

    # ═══════════════════════════════════════════════════════
    #  BUILD SCHEDULE — ORCHESTRATORE PRINCIPALE
    # ═══════════════════════════════════════════════════════
    def build_schedule(self, n_workdays: int, day_type: str = "LV",
                       exclude_trains: list[str] = None) -> list[dict]:
        """
        Orchestratore AI a 4 fasi.

        FASE 1 · Pre-filtra segmenti e prepara zona raggiungibile
        FASE 2 · Multi-restart: genera NUM_RESTARTS turni completi
        FASE 3 · Genetic crossover: incrocia i migliori turni
        FASE 4 · Simulated annealing: ottimizza localmente il vincitore
        """
        print(f"\n{'='*60}")
        print(f"AI ENGINE v3 — {self.deposito or 'N/D'}")
        print(f"Giornate: {n_workdays} | Tipo: {day_type}")
        print(f"Zona: {len(self._reachable)} stazioni")
        print(f"{'='*60}")

        base_excluded = set(exclude_trains or [])

        try:
            available_days = self.db.get_day_indices_for_validity(day_type)
        except Exception:
            available_days = self.db.get_distinct_day_indices()
        if not available_days:
            available_days = [1]

        # ── FASE 2: Multi-restart ──
        print(f"\n  FASE 2 · Multi-restart ({NUM_RESTARTS} tentativi)...")
        population: list[tuple[float, list[dict]]] = []

        for attempt in range(NUM_RESTARTS):
            randomize = (attempt > 0)
            cal = self._build_one_schedule(
                n_workdays, day_type, base_excluded,
                available_days, randomize=randomize,
            )
            sc = self._score_schedule(cal)
            population.append((sc, cal))

        population.sort(key=lambda x: -x[0])
        print(f"    Top score: {population[0][0]:.0f}")

        # ── FASE 3: Genetic crossover ──
        print(f"  FASE 3 · Genetic crossover ({CROSSOVER_ROUNDS} round)...")
        top_pop = population[:POPULATION_SIZE]
        evolved = self._genetic_crossover(
            top_pop, n_workdays, base_excluded, available_days
        )
        print(f"    Top score dopo crossover: {evolved[0][0]:.0f}")

        # ── FASE 4: Simulated annealing ──
        print(f"  FASE 4 · Simulated annealing ({SA_ITERATIONS} iterazioni)...")
        best_score, best_cal = evolved[0]
        refined_cal, refined_score = self._simulated_annealing(
            best_cal, best_score, base_excluded, available_days
        )
        print(f"    Score finale: {refined_score:.0f} "
              f"({'migliorato!' if refined_score > best_score else 'invariato'})")

        final_cal = refined_cal if refined_score >= best_score else best_cal
        final_score = max(refined_score, best_score)

        # ── DEDUP CHECK ──
        dupes = self._verify_no_duplicates(final_cal)
        if dupes:
            print(f"  !! TRENI DUPLICATI RILEVATI: {dupes}")
            # Rimuovi duplicati dalle giornate successive
            seen_trains: set[str] = set()
            for entry in final_cal:
                if entry["type"] != "TURN":
                    continue
                s = entry.get("summary")
                if not s or not s.segments:
                    continue
                clean = []
                for seg in s.segments:
                    tid = (seg.get("train_id", "")
                           if isinstance(seg, dict) else seg.train_id)
                    if tid not in seen_trains:
                        seen_trains.add(tid)
                        clean.append(seg)
                if len(clean) < len(s.segments):
                    print(f"    -> Rimossi {len(s.segments)-len(clean)} duplicati da G{entry.get('day',0)}")
                    s.segments = clean
                    # Ricalcola validazione
                    new_sum = self.validator.validate_day(clean, deposito=self.deposito)
                    self._fix_meal_timing(new_sum)
                    entry["summary"] = new_sum
        else:
            print(f"  OK Nessun treno duplicato")

        # ── LOG RISULTATO ──
        all_violations = []
        condottas = []
        for entry in final_cal:
            if entry["type"] == "TURN" and entry.get("summary"):
                s = entry["summary"]
                if s.segments:
                    first_from = (s.segments[0].get("from_station", "?")
                                  if isinstance(s.segments[0], dict)
                                  else s.segments[0].from_station)
                    last_to = (s.segments[-1].get("to_station", "?")
                               if isinstance(s.segments[-1], dict)
                               else s.segments[-1].to_station)
                    cond = s.condotta_min
                    condottas.append(cond)
                    viol_str = f"! {len(s.violations)} viol" if s.violations else "OK"
                    print(f"  G{entry['day']}: {first_from} -> {last_to} "
                          f"({len(s.segments)} treni, cond={cond}min, "
                          f"prest={s.prestazione_min}min) {viol_str}")
                else:
                    print(f"  G{entry['day']}: VUOTO")
                all_violations.extend(s.violations)

        if condottas:
            avg = sum(condottas) / len(condottas)
            print(f"\n  MEDIA: {avg:.0f}min ({avg/60:.1f}h) | "
                  f"MIN: {min(condottas)}min | MAX: {max(condottas)}min | "
                  f"SCORE: {final_score:.0f}")

        print(f"  Violazioni totali: {len(all_violations)}\n")

        # ── VERIFICA POST-GENERAZIONE via cache live.arturo.travel ──
        # Per ogni segmento del turno finale, cerca conferma rotta reale
        # (cache hit = istantaneo; miss = chiamata API ~600ms).
        # Cresce il DB di rotte verificate. Aggiunge violazioni
        # WARN_DATA_MISMATCH se segmento non corrisponde a rotta reale.
        try:
            api_stats = self._verify_turn_via_api(final_cal)
            print(f"  API verify: {api_stats['ok']} ok, "
                  f"{api_stats['cache_hit']} cache, "
                  f"{api_stats['mismatch']} mismatch, "
                  f"{api_stats['not_found']} not_found, "
                  f"{api_stats['error']} errori")
        except Exception as e:
            print(f"  API verify saltato (errore: {e})")

        # Metadati
        if final_cal:
            final_cal[0]["_meta"] = {
                "deposito": self.deposito,
                "reachable_stations": sorted(self._reachable) if self._reachable else [],
                "total_violations": len(all_violations),
                "day_type": day_type,
                "ai_score": final_score,
                "ai_attempts": NUM_RESTARTS,
                "ai_version": "v3",
                "ai_phases": "restart+genetic+SA",
            }

        return final_cal

    def _verify_turn_via_api(self, calendar: list[dict]) -> dict:
        """
        Verifica i segmenti del turno generato chiamando live.arturo.travel
        (cache lazy). Aggiunge WARN_DATA_MISMATCH se la rotta reale non
        contiene il segmento (from -> to nell'ordine).
        """
        from services.train_route_cache import (
            get_or_fetch_train_route, fermate_segment,
        )
        from src.validator.rules import Violation
        stats = {"ok": 0, "cache_hit": 0, "mismatch": 0,
                 "not_found": 0, "error": 0}
        for entry in calendar:
            if entry.get("type") != "TURN":
                continue
            s = entry.get("summary")
            if not s or not s.segments:
                continue
            for seg in s.segments:
                tid = (seg.get("train_id", "") if isinstance(seg, dict)
                       else seg.train_id)
                from_st = (seg.get("from_station", "") if isinstance(seg, dict)
                           else seg.from_station)
                to_st = (seg.get("to_station", "") if isinstance(seg, dict)
                         else seg.to_station)
                if not tid:
                    continue
                route = get_or_fetch_train_route(self.db, tid, origine_hint=from_st)
                if route is None:
                    continue
                if route.get("from_cache"):
                    stats["cache_hit"] += 1
                status = route.get("api_status", "ok")
                if status == "not_found":
                    stats["not_found"] += 1
                    continue
                if status == "error_transient":
                    stats["error"] += 1
                    continue
                ferm = route.get("fermate", [])
                if not ferm:
                    continue
                check = fermate_segment(ferm, from_st, to_st)
                if check is None:
                    stats["mismatch"] += 1
                    s.violations.append(Violation(
                        "WARN_DATA_MISMATCH",
                        f"Treno {tid}: segmento {from_st}->{to_st} non "
                        f"corrisponde alla rotta reale "
                        f"({route.get('origine','?')}->{route.get('destinazione','?')}). "
                        f"Verifica via live.arturo.travel.",
                        severity="warning",
                    ))
                else:
                    stats["ok"] += 1
        return stats

    # ═══════════════════════════════════════════════════════
    #  WEEKLY SCHEDULE (turno settimanale unificato)
    # ═══════════════════════════════════════════════════════
    def build_weekly_schedule(self, n_workdays: int = 5,
                              exclude_trains: list[str] = None) -> dict:
        """
        Genera un turno settimanale unificato.
        Per ogni giornata produce varianti LMXGV / S / D.

        Logica:
        1. Genera LV (5 giornate) con build_schedule
        2. Per ogni giornata, cerca variante SAB nella stessa fascia oraria
        3. Per ogni giornata, cerca variante DOM (o S.COMP se nessun treno)
        4. Calcola ore pesate settimanali

        Returns:
            {
                "days": [
                    {
                        "day_number": 1,
                        "variants": {
                            "LMXGV": {summary, train_ids, ...},
                            "S": {summary, train_ids, ...} o {is_scomp: True},
                            "D": {summary, train_ids, ...} o {is_scomp: True},
                        }
                    }, ...
                ],
                "weekly_stats": {
                    "total_weighted_pres_min": ...,
                    "weighted_hours_per_day": ...,
                    "in_range": True/False,
                }
            }
        """
        from src.constants import (
            WEEKLY_HOURS_MIN, WEEKLY_HOURS_MAX, SCOMP_DURATION_MIN,
        )

        base_excluded = set(exclude_trains or [])

        # Step 1: Genera LV
        print(f"\n{'='*60}")
        print(f"WEEKLY BUILDER — {self.deposito}")
        print(f"{'='*60}")
        print(f"\n  Step 1: Generazione LV ({n_workdays} giornate)...")
        lv_cal = self.build_schedule(n_workdays, day_type="LV",
                                     exclude_trains=list(base_excluded))

        # Raccolta treni usati nel LV
        lv_used = set()
        for entry in lv_cal:
            if entry["type"] == "TURN" and entry.get("summary"):
                for seg in entry["summary"].segments:
                    tid = seg.get("train_id", "") if isinstance(seg, dict) else seg.train_id
                    lv_used.add(tid)

        # Step 2 & 3: Per ogni giornata LV, cerca varianti SAB e DOM
        print(f"\n  Step 2-3: Ricerca varianti SAB/DOM...")
        days = []
        for entry in lv_cal:
            if entry["type"] != "TURN":
                continue

            day_num = entry.get("day", 0)
            s = entry.get("summary")
            if not s or not s.segments:
                continue

            # Fascia oraria di questa giornata LV
            first_dep = s.segments[0].get("dep_time") if isinstance(s.segments[0], dict) else s.segments[0].dep_time
            lv_start_min = _time_to_min(first_dep)

            # Treni LV
            lv_train_ids = []
            for seg in s.segments:
                tid = seg.get("train_id", "") if isinstance(seg, dict) else seg.train_id
                lv_train_ids.append(tid)

            lv_variant = {
                "variant_type": "LMXGV",
                "day_type": "LV",
                "train_ids": lv_train_ids,
                "prestazione_min": s.prestazione_min,
                "condotta_min": s.condotta_min,
                "meal_min": s.meal_min,
                "is_fr": s.is_fr,
                "is_scomp": False,
                "scomp_duration_min": 0,
                "last_station": s.last_station,
                "violations": [{"rule": v.rule, "message": v.message} for v in s.violations],
            }

            # Variante SAB: cerca treni SAB nella stessa fascia oraria
            sab_variant = self._find_day_variant(
                "SAB", lv_start_min, lv_used | base_excluded, s
            )

            # Variante DOM: cerca treni DOM nella stessa fascia oraria
            dom_variant = self._find_day_variant(
                "DOM", lv_start_min, lv_used | base_excluded, s
            )

            days.append({
                "day_number": day_num,
                "variants": [lv_variant, sab_variant, dom_variant],
            })

        # Step 4: Calcola ore pesate
        total_weighted = 0
        freq_total = 0
        for day in days:
            for v in day["variants"]:
                freq = {"LMXGV": 5, "S": 1, "D": 1}.get(v["variant_type"], 1)
                pres = v.get("scomp_duration_min", 0) if v["is_scomp"] else v["prestazione_min"]
                total_weighted += pres * freq
                freq_total += freq

        weighted_per_day = total_weighted / freq_total if freq_total > 0 else 0
        weekly_pres = total_weighted / 7 * 7  # total across the week
        in_range = WEEKLY_HOURS_MIN <= total_weighted / 7 * 7 <= WEEKLY_HOURS_MAX

        print(f"\n  RIEPILOGO SETTIMANALE:")
        print(f"    Ore pesate/giorno: {weighted_per_day/60:.1f}h")
        print(f"    Totale settimanale: {total_weighted/60:.1f}h ({total_weighted}min)")
        print(f"    Range: {'OK' if in_range else 'FUORI RANGE'} "
              f"({WEEKLY_HOURS_MIN/60:.0f}h - {WEEKLY_HOURS_MAX/60:.0f}h)")

        return {
            "days": days,
            "weekly_stats": {
                "total_weighted_pres_min": total_weighted,
                "weighted_hours_per_day": round(weighted_per_day, 1),
                "weekly_hours": round(total_weighted / 60, 1),
                "in_range": in_range,
                "target_min": WEEKLY_HOURS_MIN,
                "target_max": WEEKLY_HOURS_MAX,
            },
            "deposito": self.deposito,
        }

    def _find_day_variant(self, day_type: str, lv_start_min: int,
                          exclude_trains: set, lv_summary) -> dict:
        """Cerca una variante SAB o DOM nella stessa fascia oraria della giornata LV.
        Se non trova treni, ritorna S.COMP."""
        from src.constants import SCOMP_DURATION_MIN, VARIANT_TO_DAY_TYPE

        vtype = "S" if day_type == "SAB" else "D"
        mapped_day_type = VARIANT_TO_DAY_TYPE.get(vtype, day_type)

        try:
            # Cerca treni che partono nella stessa fascia oraria (+/- 2 ore)
            window_start = max(0, lv_start_min - 120)
            window_end = lv_start_min + 120

            # Genera un piccolo turno per questo tipo giorno
            mini_cal = self.build_schedule(
                1, day_type=day_type,
                exclude_trains=list(exclude_trains),
            )

            for entry in mini_cal:
                if entry["type"] != "TURN":
                    continue
                s = entry.get("summary")
                if s and s.segments:
                    first_dep = s.segments[0].get("dep_time") if isinstance(s.segments[0], dict) else s.segments[0].dep_time
                    start_m = _time_to_min(first_dep)

                    # Check se è nella fascia oraria giusta (tolleranza 2h)
                    if abs(start_m - lv_start_min) <= 120:
                        train_ids = []
                        for seg in s.segments:
                            tid = seg.get("train_id", "") if isinstance(seg, dict) else seg.train_id
                            train_ids.append(tid)
                        return {
                            "variant_type": vtype,
                            "day_type": day_type,
                            "train_ids": train_ids,
                            "prestazione_min": s.prestazione_min,
                            "condotta_min": s.condotta_min,
                            "meal_min": s.meal_min,
                            "is_fr": s.is_fr,
                            "is_scomp": False,
                            "scomp_duration_min": 0,
                            "last_station": s.last_station,
                            "violations": [{"rule": v.rule, "message": v.message}
                                          for v in s.violations],
                        }
        except Exception as e:
            print(f"    Variante {vtype}: errore ricerca — {e}")

        # Nessun treno trovato → S.COMP (disponibilità)
        return {
            "variant_type": vtype,
            "day_type": day_type,
            "train_ids": [],
            "prestazione_min": 0,
            "condotta_min": 0,
            "meal_min": 0,
            "is_fr": False,
            "is_scomp": True,
            "scomp_duration_min": SCOMP_DURATION_MIN,
            "last_station": self.deposito,
            "violations": [],
        }

    # ═══════════════════════════════════════════════════════
    #  UTILITÀ LEGACY
    # ═══════════════════════════════════════════════════════
    def _load_day_segments(self, day_index: int, start_hour: int,
                           alt_day_indices: list[int] = None,
                           apply_zone_and_abilitazioni: bool = True,
                           union_all_days: bool = False) -> list:
        """
        Carica i segmenti di un giorno applicando i filtri di base.
        apply_zone_and_abilitazioni=False per ottenere il pool completo
        (usato per la ricerca del rientro: anche treni di linee non
        abilitate possono servire come rientro in vettura).
        union_all_days=True: carica e unisce i segmenti di TUTTI gli
        alt_day_indices (massima flessibilita' per il builder, evita di
        legare ogni giornata a un singolo day_index del materiale).
        """
        if union_all_days and alt_day_indices:
            # Union di tutti i day_index disponibili (deduplica via train_id+orario)
            seen = set()
            merged = []
            for idx in alt_day_indices:
                segs = self.db.get_all_segments(day_index=idx) or []
                for s in segs:
                    key = (s.get("train_id", ""), s.get("from_station", ""),
                           s.get("dep_time", ""), s.get("to_station", ""),
                           s.get("arr_time", ""))
                    if key in seen:
                        continue
                    seen.add(key)
                    merged.append(s)
            if not merged:
                merged = self.db.get_all_segments() or []
            filtered = self._filter_segments(
                merged,
                apply_zone_and_abilitazioni=apply_zone_and_abilitazioni,
            )
            filtered.sort(key=lambda s: _time_to_min(s["dep_time"]))
            if start_hour > 0:
                filtered = [s for s in filtered
                            if _time_to_min(s["dep_time"]) >= start_hour * 60]
            return filtered

        indices = [day_index]
        if alt_day_indices:
            indices.extend(i for i in alt_day_indices if i != day_index)
        for idx in indices:
            all_segments = self.db.get_all_segments(day_index=idx)
            if not all_segments:
                all_segments = self.db.get_all_segments()
            if not all_segments:
                continue
            filtered = self._filter_segments(
                all_segments,
                apply_zone_and_abilitazioni=apply_zone_and_abilitazioni,
            )
            filtered.sort(key=lambda s: _time_to_min(s["dep_time"]))
            if start_hour > 0:
                filtered = [s for s in filtered
                            if _time_to_min(s["dep_time"]) >= start_hour * 60]
            if filtered:
                return filtered
        return []

    def _greedy_select(self, filtered: list) -> list:
        selected, used, rc, oh = [], set(), 0, self._overhead
        for seg in filtered:
            tid = seg.get("train_id", "")
            if tid in used: continue
            if self.deposito and not selected:
                if seg.get("from_station", "").upper() != self.deposito: continue
            dep_m = _time_to_min(seg["dep_time"])
            arr_m = _time_to_min(seg["arr_time"])
            if arr_m < dep_m: arr_m += 1440
            dur = arr_m - dep_m
            if selected:
                la = _time_to_min(selected[-1]["arr_time"])
                if la > _time_to_min(selected[0]["dep_time"]): pass
                else: la += 1440
                if dep_m < la: continue
                lt = selected[-1].get("to_station", "").upper()
                tf = seg.get("from_station", "").upper()
                if lt and tf and lt != tf: continue
                if dep_m - la > MAX_GAP_MIN: continue
            is_dh = seg.get("is_deadhead", False)
            nc = rc + (dur if not is_dh else 0)
            fd = _time_to_min(selected[0]["dep_time"]) if selected else dep_m
            pp = (arr_m - fd) + oh
            if pp > MAX_PRESTAZIONE_MIN:
                if not selected: continue
                else: break
            if nc > MAX_CONDOTTA_MIN:
                if not selected: continue
                else: break
            selected.append(seg); used.add(tid)
            if not is_dh: rc = nc
        return selected

    def _fix_meal_timing(self, summary: DaySummary):
        if not summary.meal_start or not summary.meal_end: return
        ms = _time_to_min(summary.meal_start)
        me = _time_to_min(summary.meal_end)
        w1s, w1e = MEAL_WINDOW_1_START, MEAL_WINDOW_1_END
        w2s, w2e = MEAL_WINDOW_2_START, MEAL_WINDOW_2_END
        if (ms >= w1s and me <= w1e) or (ms >= w2s and me <= w2e): return
        segs = summary.segments
        if not segs: return
        best, bp = None, -1
        for i in range(len(segs) - 1):
            arr = segs[i].get("arr_time", "") if isinstance(segs[i], dict) else segs[i].arr_time
            dep = segs[i+1].get("dep_time", "") if isinstance(segs[i+1], dict) else segs[i+1].dep_time
            if not arr or not dep: continue
            am, dm = _time_to_min(arr), _time_to_min(dep)
            if dm < am: dm += 1440
            if dm - am < MEAL_MIN: continue
            for ws, we in [(w1s, w1e), (w2s, w2e)]:
                ss = max(am, ws)
                se = ss + MEAL_MIN
                if se <= min(dm, we):
                    pr = 100 - abs(ss - am)
                    if pr > bp: bp, best = pr, (ss, se)
        if best:
            summary.meal_start = _min_to_time(best[0])
            summary.meal_end = _min_to_time(best[1])
        else:
            fd = _time_to_min(segs[0].get("dep_time", "06:00") if isinstance(segs[0], dict) else segs[0].dep_time)
            if fd < 900:
                summary.meal_start, summary.meal_end = _min_to_time(w1s), _min_to_time(w1s + MEAL_MIN)
            else:
                summary.meal_start, summary.meal_end = _min_to_time(w2s), _min_to_time(w2s + MEAL_MIN)

    def build_day(self, day_index: int = 0, start_hour: int = 0,
                  alt_day_indices: list[int] = None) -> DaySummary:
        """Legacy interface per builder manuale."""
        filtered = self._load_day_segments(day_index, start_hour, alt_day_indices)
        if not filtered:
            return DaySummary(segments=[])
        if self.deposito:
            pool = self._build_chain_pool(filtered,
                                          min_start=start_hour * 60)
            if pool:
                summary = self._select_from_pool(pool, randomize=False)
                if summary.segments:
                    for seg in summary.segments:
                        tid = (seg.get("train_id", "")
                               if isinstance(seg, dict) else seg.train_id)
                        self._used_trains_global.add(tid)
                    return summary
        sel = self._greedy_select(filtered)
        if not sel: return DaySummary(segments=[])
        summary = self.validator.validate_day(sel, deposito=self.deposito)
        self._fix_meal_timing(summary)
        for seg in summary.segments:
            tid = (seg.get("train_id", "")
                   if isinstance(seg, dict) else seg.train_id)
            self._used_trains_global.add(tid)
        return summary
