"""
Validator per regole operative turni PDM.
Tutte le regole sono implementate direttamente nel codice.
"""

from dataclasses import dataclass, field
from typing import Optional

from ..constants import (
    MAX_PRESTAZIONE_MIN,
    MAX_CONDOTTA_MIN,
    MEAL_MIN,
    MEAL_WINDOW_1_START,
    MEAL_WINDOW_1_END,
    MEAL_WINDOW_2_START,
    MEAL_WINDOW_2_END,
    EXTRA_START_MIN,
    EXTRA_END_MIN,
    MAX_NIGHT_MIN,
    NIGHT_START,
    NIGHT_END,
    REST_STANDARD_H,
    REST_AFTER_001_0100_H,
    REST_AFTER_NIGHT_H,
    WEEKLY_REST_MIN_H,
    WORK_BLOCK,
    REST_BLOCK,
    ACCESSORY_RULES,
    TEMPI_MEDI_RULES,
    FIXED_TRAVEL_TIMES,
    load_fr_stations,
)


@dataclass
class Violation:
    rule: str
    message: str
    severity: str = "ERROR"  # ERROR, WARNING


@dataclass
class DaySummary:
    """Riepilogo di una giornata di turno."""
    segments: list  # list of TrainSegment-like dicts
    presentation_time: str = ""   # HH:MM
    end_time: str = ""            # HH:MM
    prestazione_min: int = 0
    condotta_min: int = 0
    accessori_min: int = 0
    tempi_medi_min: int = 0
    extra_min: int = 0
    meal_min: int = MEAL_MIN
    night_minutes: int = 0
    day_type: str = "DIURNA"      # DIURNA / NOTTURNA
    violations: list = field(default_factory=list)
    deposito: str = ""
    last_station: str = ""
    is_fr: bool = False
    meal_start: str = ""
    meal_end: str = ""

    def format_output(self) -> str:
        lines = []
        lines.append(f"  Prestazione totale: {_fmt_min(self.prestazione_min)} / limite {_fmt_min(MAX_PRESTAZIONE_MIN)}")
        lines.append(f"  Condotta: {_fmt_min(self.condotta_min)} / limite {_fmt_min(MAX_CONDOTTA_MIN)}")
        lines.append(f"  Refezione: {_fmt_min(self.meal_min)}")
        lines.append(f"  Accessori: {_fmt_min(self.accessori_min)}")
        lines.append(f"  Tempi medi: {_fmt_min(self.tempi_medi_min)}")
        lines.append(f"  Tempi aggiuntivi: {_fmt_min(self.extra_min)}")
        lines.append(f"  Night minutes: {self.night_minutes}")
        lines.append(f"  Tipo giornata: {self.day_type}")
        if self.is_fr:
            lines.append(f"  Fuori Residenza: SI ({self.last_station})")
        if self.violations:
            lines.append(f"  --- VIOLATIONS ---")
            for v in self.violations:
                lines.append(f"  [{v.severity}] {v.rule}: {v.message}")
        return "\n".join(lines)


def _fmt_min(minutes: int) -> str:
    """Formatta minuti come Xh XX."""
    h = minutes // 60
    m = minutes % 60
    return f"{h}h{m:02d}"


def _time_to_min(t: str) -> int:
    """Converte HH:MM in minuti dalla mezzanotte."""
    parts = t.split(":")
    return int(parts[0]) * 60 + int(parts[1])


def _min_to_time(m: int) -> str:
    """Converte minuti in HH:MM."""
    m = m % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def validate_weekly_hours(days: list[dict]) -> list:
    """Valida le ore settimanali pesate per un turno settimanale.

    days = [{
        "day_number": 1,
        "variants": [
            {"variant_type": "LMXGV", "prestazione_min": 480, "is_scomp": False, ...},
            {"variant_type": "S", "prestazione_min": 0, "is_scomp": True,
             "scomp_duration_min": 360, ...},
            {"variant_type": "D", ...},
        ]
    }, ...]

    Returns: list of Violation
    """
    from ..constants import (
        WEEKLY_HOURS_MIN, WEEKLY_HOURS_MAX, WEEKLY_HOURS_TARGET,
        SCOMP_DURATION_MIN, DAY_FREQUENCY,
    )

    violations = []
    total_weighted = 0
    freq_total = 0

    for day in days:
        for v in day.get("variants", []):
            freq = DAY_FREQUENCY.get(v.get("variant_type", "LMXGV"), 1)
            if v.get("is_scomp"):
                pres = v.get("scomp_duration_min", SCOMP_DURATION_MIN)
            else:
                pres = v.get("prestazione_min", 0)
            total_weighted += pres * freq
            freq_total += freq

    # ore settimanali = sum pesata
    weekly_min = total_weighted
    weekly_hours = weekly_min / 60

    if weekly_min < WEEKLY_HOURS_MIN:
        violations.append(Violation(
            rule="WEEKLY_HOURS_MIN",
            message=f"Ore settimanali {weekly_hours:.1f}h sotto il minimo "
                    f"({WEEKLY_HOURS_MIN/60:.0f}h)",
            severity="ERROR",
        ))
    elif weekly_min > WEEKLY_HOURS_MAX:
        violations.append(Violation(
            rule="WEEKLY_HOURS_MAX",
            message=f"Ore settimanali {weekly_hours:.1f}h sopra il massimo "
                    f"({WEEKLY_HOURS_MAX/60:.0f}h)",
            severity="ERROR",
        ))

    return violations


class TurnValidator:
    def __init__(self, deposito: str = ""):
        self.deposito = deposito.upper()
        self.fr_stations = load_fr_stations()

    def compute_condotta(self, segments: list) -> int:
        """Calcola condotta totale (solo segmenti non deadhead).
        Per tratte con tempo fisso (FIXED_TRAVEL_TIMES), usa il valore fisso."""
        total = 0
        for seg in segments:
            is_dh = seg.get("is_deadhead", False) if isinstance(seg, dict) else getattr(seg, "is_deadhead", False)
            if is_dh:
                continue
            dep = seg.get("dep_time", "") if isinstance(seg, dict) else seg.dep_time
            arr = seg.get("arr_time", "") if isinstance(seg, dict) else seg.arr_time
            from_st = (seg.get("from_station", "") if isinstance(seg, dict) else getattr(seg, "from_station", "")).upper()
            to_st = (seg.get("to_station", "") if isinstance(seg, dict) else getattr(seg, "to_station", "")).upper()
            # Controlla tempo fisso per questa tratta
            fixed = FIXED_TRAVEL_TIMES.get((from_st, to_st))
            if fixed is not None:
                total += fixed
            elif dep and arr:
                dep_m = _time_to_min(dep)
                arr_m = _time_to_min(arr)
                if arr_m < dep_m:
                    arr_m += 24 * 60
                total += arr_m - dep_m
        return total

    def compute_accessori(self, start: int = None, end: int = None) -> int:
        """Calcola tempi accessori base.
        Se start/end forniti, usa quelli; altrimenti usa i default (10+8)."""
        s = start if start is not None else ACCESSORY_RULES["default_start"]
        e = end if end is not None else ACCESSORY_RULES["default_end"]
        return s + e

    def compute_tempi_medi(self) -> int:
        """Calcola tempi medi (maggiorazione accessori)."""
        return TEMPI_MEDI_RULES["default_extra"]

    def compute_extra(self) -> int:
        """Calcola tempi aggiuntivi."""
        return EXTRA_START_MIN + EXTRA_END_MIN

    def compute_night_minutes(self, start_time: str, end_time: str) -> int:
        """Calcola overlap del turno con fascia notturna 00:01 - 01:00."""
        night_start_m = _time_to_min(NIGHT_START)  # 1
        night_end_m = _time_to_min(NIGHT_END)      # 60

        turno_start = _time_to_min(start_time)
        turno_end = _time_to_min(end_time)

        # Gestisci turno che attraversa la mezzanotte
        if turno_end <= turno_start:
            turno_end += 24 * 60

        # La fascia notturna 00:01-01:00 potrebbe cadere oggi o domani
        total_night = 0
        for offset in [0, 24 * 60]:
            ns = night_start_m + offset
            ne = night_end_m + offset
            overlap_start = max(turno_start, ns)
            overlap_end = min(turno_end, ne)
            if overlap_start < overlap_end:
                total_night += overlap_end - overlap_start

        return min(total_night, MAX_NIGHT_MIN)

    def find_meal_slot(self, segments: list) -> tuple[str, str]:
        """
        Trova slot per refezione tra gap dei treni.

        La refezione è consentita SOLO in queste finestre contrattuali:
        - Finestra 1: 11:30 - 15:30
        - Finestra 2: 18:30 - 22:30

        Se nessun gap cade in una finestra valida, posiziona comunque
        all'inizio della finestra più vicina (il macchinista dovrà gestire).
        """
        windows = [
            (MEAL_WINDOW_1_START, MEAL_WINDOW_1_END),
            (MEAL_WINDOW_2_START, MEAL_WINDOW_2_END),
        ]

        if len(segments) < 2:
            return self._meal_in_window(segments, windows)

        # Cerca gap >= 30 min tra segmenti consecutivi che cada in una finestra
        best_slot = None
        best_priority = -1

        for i in range(len(segments) - 1):
            arr = segments[i].get("arr_time", "") if isinstance(segments[i], dict) else segments[i].arr_time
            dep = segments[i + 1].get("dep_time", "") if isinstance(segments[i + 1], dict) else segments[i + 1].dep_time
            if not arr or not dep:
                continue

            arr_m = _time_to_min(arr)
            dep_m = _time_to_min(dep)
            if dep_m < arr_m:
                dep_m += 24 * 60
            gap = dep_m - arr_m

            if gap < MEAL_MIN:
                continue

            # Prova a piazzare la refezione in una finestra valida
            for w_start, w_end in windows:
                slot_start = max(arr_m, w_start)
                slot_end = slot_start + MEAL_MIN

                if slot_end <= min(dep_m, w_end):
                    # Slot valido nella finestra!
                    priority = 100 - abs(slot_start - arr_m)
                    if priority > best_priority:
                        best_priority = priority
                        best_slot = (slot_start, slot_end)

        if best_slot:
            return _min_to_time(best_slot[0]), _min_to_time(best_slot[1])

        # Fallback: posiziona all'inizio della finestra più vicina
        return self._meal_in_window(segments, windows)

    def _meal_in_window(self, segments: list, windows: list) -> tuple[str, str]:
        """Posiziona refezione nella finestra contrattuale più vicina."""
        if not segments:
            return _min_to_time(MEAL_WINDOW_1_START), _min_to_time(MEAL_WINDOW_1_START + MEAL_MIN)

        first_dep = segments[0].get("dep_time", "06:00") if isinstance(segments[0], dict) else segments[0].dep_time
        first_m = _time_to_min(first_dep)

        # Scegli la finestra in base all'ora del turno
        if first_m < 15 * 60:
            # Turno mattutino/pomeridiano → finestra 1 (11:30-15:30)
            return _min_to_time(MEAL_WINDOW_1_START), _min_to_time(MEAL_WINDOW_1_START + MEAL_MIN)
        else:
            # Turno serale → finestra 2 (18:30-22:30)
            return _min_to_time(MEAL_WINDOW_2_START), _min_to_time(MEAL_WINDOW_2_START + MEAL_MIN)

    def compute_prestazione(self, segments: list,
                             acc_start: int = None,
                             acc_end: int = None) -> tuple[int, str, str]:
        """
        Calcola prestazione totale e orari presentazione/fine.
        acc_start/acc_end: valori accessori custom (es. CVL=5, ACC=40).
        Ritorna (prestazione_min, presentation_time, end_time).
        """
        if not segments:
            return 0, "", ""

        first_dep = segments[0].get("dep_time", "") if isinstance(segments[0], dict) else segments[0].dep_time
        last_arr = segments[-1].get("arr_time", "") if isinstance(segments[-1], dict) else segments[-1].arr_time

        if not first_dep or not last_arr:
            return 0, "", ""

        actual_acc_start = acc_start if acc_start is not None else ACCESSORY_RULES["default_start"]
        actual_acc_end = acc_end if acc_end is not None else ACCESSORY_RULES["default_end"]

        # Presentazione = primo dep - accessori_start - extra_start
        pres_min = _time_to_min(first_dep) - actual_acc_start - EXTRA_START_MIN
        # Fine = ultimo arr + accessori_end + extra_end
        fine_min = _time_to_min(last_arr) + actual_acc_end + EXTRA_END_MIN

        if fine_min < pres_min:
            fine_min += 24 * 60

        prestazione = fine_min - pres_min
        # La prestazione include tutto: condotta, accessori, medi, extra, meal

        return prestazione, _min_to_time(pres_min), _min_to_time(fine_min)

    def validate_day(self, segments: list, deposito: str = "",
                     is_fr_override: bool = False,
                     acc_start: int = None, acc_end: int = None) -> DaySummary:
        """Valida una giornata di turno completa.
        is_fr_override: se True, il turno e marcato come FR dall'utente
        e non genera violation NO_RIENTRO_BASE.
        acc_start/acc_end: valori accessori custom (es. CVL=5, standard=10/8, maggiorato, ecc.)
        """
        dep = deposito.upper() or self.deposito
        violations = []

        if not segments:
            return DaySummary(
                segments=segments,
                violations=[Violation("EMPTY_DAY", "Nessun segmento nella giornata")],
            )

        # Calcoli
        condotta = self.compute_condotta(segments)
        accessori = self.compute_accessori(start=acc_start, end=acc_end)
        tempi_medi = self.compute_tempi_medi()
        extra = self.compute_extra()
        prestazione, pres_time, end_time = self.compute_prestazione(
            segments, acc_start=acc_start, acc_end=acc_end)

        # Refezione: obbligatoria solo se condotta > 6h OPPURE se il turno
        # copre le fasce 12:00-15:00 o 19:00-21:00
        meal_required = False
        if condotta > 360:  # > 6 ore
            meal_required = True
        else:
            # Controlla se i treni coprono le fasce orarie dei pasti
            for seg in segments:
                dep_str = seg.get("dep_time", "") if isinstance(seg, dict) else seg.dep_time
                arr_str = seg.get("arr_time", "") if isinstance(seg, dict) else seg.arr_time
                dep_m = _time_to_min(dep_str) if dep_str else 0
                arr_m = _time_to_min(arr_str) if arr_str else 0
                if arr_m < dep_m:
                    arr_m += 24 * 60
                # Fascia pranzo 12:00-15:00
                if dep_m < 15 * 60 and arr_m > 12 * 60:
                    meal_required = True
                    break
                # Fascia cena 19:00-21:00
                if dep_m < 21 * 60 and arr_m > 19 * 60:
                    meal_required = True
                    break

        if meal_required:
            meal_start, meal_end = self.find_meal_slot(segments)
            actual_meal_min = MEAL_MIN
        else:
            meal_start, meal_end = "", ""
            actual_meal_min = 0

        # Night
        night_min = 0
        if pres_time and end_time:
            night_min = self.compute_night_minutes(pres_time, end_time)

        day_type = "NOTTURNA" if night_min > 0 else "DIURNA"

        # Ultima stazione
        last_seg = segments[-1]
        last_station = (
            last_seg.get("to_station", "") if isinstance(last_seg, dict)
            else last_seg.to_station
        )

        # Fuori residenza
        # Il FR ha senso SOLO se il turno termina in fascia serale/notturna
        # (17:00 - 04:00 del giorno successivo). Un turno che termina alle
        # 06:17 o alle 14:00 in stazione FR autorizzata NON e' FR: il PdC
        # ha tempo per tornare al deposito, va contato come NO_RIENTRO.
        FR_MIN_END_HOUR = 17  # Fine >= 17:00 OPPURE <= 04:00
        FR_MAX_END_HOUR = 4
        is_fr = False
        if dep and last_station.upper() != dep:
            # Verifica orario: end_time deve essere in fascia FR-valida
            end_in_fr_window = False
            if end_time:
                end_hour = _time_to_min(end_time) / 60
                end_in_fr_window = (end_hour >= FR_MIN_END_HOUR
                                    or end_hour <= FR_MAX_END_HOUR)
            if is_fr_override:
                # L'utente ha esplicitamente marcato come FR - nessuna violation
                is_fr = True
            elif (last_station.upper() in [s.upper() for s in self.fr_stations]
                  and end_in_fr_window):
                is_fr = True
            elif (last_station.upper() in [s.upper() for s in self.fr_stations]
                  and not end_in_fr_window):
                # Stazione e' FR autorizzata MA orario fuori finestra serale
                # -> non e' FR vera, e' un mancato rientro
                violations.append(
                    Violation(
                        "NO_RIENTRO_BASE",
                        f"Turno termina a {last_station} alle {end_time}: "
                        f"FR ammesso solo per turni serali/notturni "
                        f"(fine >= {FR_MIN_END_HOUR}:00 o <= {FR_MAX_END_HOUR}:00). "
                        f"Il PdC dovrebbe rientrare al deposito {dep}.",
                    )
                )
            else:
                violations.append(
                    Violation(
                        "NO_RIENTRO_BASE",
                        f"Turno termina a {last_station}, non nel deposito "
                        f"{dep} e non in stazione FR autorizzata.",
                    )
                )

        # Vincoli
        if prestazione > MAX_PRESTAZIONE_MIN:
            violations.append(
                Violation(
                    "MAX_PRESTAZIONE",
                    f"Prestazione {_fmt_min(prestazione)} supera limite "
                    f"{_fmt_min(MAX_PRESTAZIONE_MIN)}",
                )
            )

        if condotta > MAX_CONDOTTA_MIN:
            violations.append(
                Violation(
                    "MAX_CONDOTTA",
                    f"Condotta {_fmt_min(condotta)} supera limite "
                    f"{_fmt_min(MAX_CONDOTTA_MIN)}",
                )
            )

        if night_min > MAX_NIGHT_MIN:
            violations.append(
                Violation(
                    "MAX_NIGHT",
                    f"Notturno {night_min} min supera limite {MAX_NIGHT_MIN} min",
                )
            )

        return DaySummary(
            segments=segments,
            presentation_time=pres_time,
            end_time=end_time,
            prestazione_min=prestazione,
            condotta_min=condotta,
            accessori_min=accessori,
            tempi_medi_min=tempi_medi,
            extra_min=extra,
            meal_min=actual_meal_min,
            night_minutes=night_min,
            day_type=day_type,
            violations=violations,
            deposito=dep,
            last_station=last_station,
            is_fr=is_fr,
            meal_start=meal_start,
            meal_end=meal_end,
        )

    def validate_rest_between(
        self, day_i_summary: DaySummary, day_j_summary: DaySummary
    ) -> list[Violation]:
        """Valida il riposo tra due giornate consecutive."""
        violations = []

        if not day_i_summary.end_time or not day_j_summary.presentation_time:
            return violations

        end_m = _time_to_min(day_i_summary.end_time)
        start_m = _time_to_min(day_j_summary.presentation_time)

        # Se il giorno successivo inizia "prima", assumiamo giorno dopo
        if start_m <= end_m:
            start_m += 24 * 60

        rest_min = start_m - end_m
        rest_h = rest_min / 60.0

        # Determina il riposo minimo richiesto
        required_h = REST_STANDARD_H

        # Se fine turno tra 00:01 e 01:00
        end_time_m = _time_to_min(day_i_summary.end_time)
        night_start_m = _time_to_min(NIGHT_START)
        night_end_m = _time_to_min(NIGHT_END)
        if night_start_m <= end_time_m <= night_end_m:
            required_h = REST_AFTER_001_0100_H

        # Se giornata notturna
        if day_i_summary.day_type == "NOTTURNA":
            required_h = max(required_h, REST_AFTER_NIGHT_H)

        if rest_h < required_h:
            violations.append(
                Violation(
                    "MIN_REST",
                    f"Riposo {rest_h:.1f}h insufficiente, "
                    f"richiesto minimo {required_h}h "
                    f"(fine: {day_i_summary.end_time}, "
                    f"inizio: {day_j_summary.presentation_time})",
                )
            )

        return violations

    def validate_weekly_rest(self, calendar: list[dict]) -> list[Violation]:
        """
        Verifica che il calendario contenga almeno 62h consecutive di riposo.
        calendar: lista di dict con 'type' (TURN/REST) e opzionalmente
                  'summary' (DaySummary) per i turni.
        """
        violations = []

        # Cerca blocchi REST consecutivi
        max_rest_h = 0
        current_rest_h = 0
        last_end_time = None

        for entry in calendar:
            if entry["type"] == "REST":
                current_rest_h += 24  # un giorno di riposo = 24h
            else:
                if current_rest_h > 0:
                    max_rest_h = max(max_rest_h, current_rest_h)
                current_rest_h = 0

        max_rest_h = max(max_rest_h, current_rest_h)

        if max_rest_h < WEEKLY_REST_MIN_H:
            violations.append(
                Violation(
                    "WEEKLY_REST_MISSING",
                    f"Riposo settimanale massimo trovato: {max_rest_h}h, "
                    f"richiesto minimo {WEEKLY_REST_MIN_H}h",
                )
            )

        return violations

    def build_calendar(self, n_workdays: int) -> list[dict]:
        """
        Genera calendario con ciclo 5+2.
        N = numero giornate di turno (i REST non contano).
        """
        calendar = []
        work_count = 0
        block_count = 0

        while work_count < n_workdays:
            # Blocco di lavoro
            for _ in range(WORK_BLOCK):
                if work_count >= n_workdays:
                    break
                calendar.append({"type": "TURN", "day": work_count + 1, "summary": None})
                work_count += 1
                block_count += 1

            # Blocco di riposo (solo se ci sono ancora turni o per completare il ciclo)
            if work_count <= n_workdays:
                for _ in range(REST_BLOCK):
                    calendar.append({"type": "REST", "day": None, "summary": None})

        return calendar
