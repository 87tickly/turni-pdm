"""
Costanti operative per il sistema di pianificazione turni PDM.

WRAPPER RETROCOMPATIBILE: tutte le costanti sono ora derivate dalla
configurazione aziendale attiva (config/). Questo file esporta gli stessi
nomi di prima, così validator, builder e gli altri consumer non cambiano.

Per aggiungere una nuova azienda: creare config/nomeazienda.py e registrarlo
in config/loader.py. Le costanti si aggiorneranno automaticamente.
"""

import os
from pathlib import Path

from config.loader import get_active_config

# Carica configurazione attiva
_cfg = get_active_config()

# ---------------------------------------------------------------------------
# LIMITI PRESTAZIONE E CONDOTTA
# ---------------------------------------------------------------------------
MAX_PRESTAZIONE_MIN = _cfg.max_prestazione_min
MAX_CONDOTTA_MIN = _cfg.max_condotta_min
MEAL_MIN = _cfg.meal_min

# NORMATIVA-PDC.md §11.8 — cap prestazione se presa servizio notte
CAP_7H_WINDOW_START_MIN = _cfg.cap_7h_window_start_min
CAP_7H_WINDOW_END_MIN = _cfg.cap_7h_window_end_min
CAP_7H_PRESTAZIONE_MIN = _cfg.cap_7h_prestazione_min

# NORMATIVA-PDC.md §4.1 — soglia REFEZ obbligatoria
REFEZ_REQUIRED_ABOVE_MIN = _cfg.refez_required_above_min

# Finestre orarie contrattuali per la refezione
MEAL_WINDOW_1_START = _cfg.meal_window_1_start
MEAL_WINDOW_1_END = _cfg.meal_window_1_end
MEAL_WINDOW_2_START = _cfg.meal_window_2_start
MEAL_WINDOW_2_END = _cfg.meal_window_2_end

# ---------------------------------------------------------------------------
# TEMPI AGGIUNTIVI (per ogni giornata con treni)
# ---------------------------------------------------------------------------
EXTRA_START_MIN = _cfg.extra_start_min
EXTRA_END_MIN = _cfg.extra_end_min
EXTRA_TOTAL_MIN = _cfg.extra_total_min

# ---------------------------------------------------------------------------
# NOTTURNO
# ---------------------------------------------------------------------------
MAX_NIGHT_MIN = _cfg.max_night_min
NIGHT_START = _cfg.night_start
NIGHT_END = _cfg.night_end

# ---------------------------------------------------------------------------
# RIPOSO TRA TURNI
# ---------------------------------------------------------------------------
REST_STANDARD_H = _cfg.rest_standard_h
REST_AFTER_001_0100_H = _cfg.rest_after_001_0100_h
REST_AFTER_NIGHT_H = _cfg.rest_after_night_h

# ---------------------------------------------------------------------------
# RIPOSO SETTIMANALE
# ---------------------------------------------------------------------------
WEEKLY_REST_MIN_H = _cfg.weekly_rest_min_h

# ---------------------------------------------------------------------------
# CICLO 5+2
# ---------------------------------------------------------------------------
WORK_BLOCK = _cfg.work_block
REST_BLOCK = _cfg.rest_block

# ---------------------------------------------------------------------------
# TEMPI ACCESSORI
# ---------------------------------------------------------------------------
ACCESSORY_RULES = _cfg.accessory_rules

# ---------------------------------------------------------------------------
# TEMPI MEDI (maggiorazione degli accessori)
# ---------------------------------------------------------------------------
TEMPI_MEDI_RULES = _cfg.tempi_medi_rules

# ---------------------------------------------------------------------------
# FUORI RESIDENZA - STAZIONI FR
# ---------------------------------------------------------------------------
ALLOWED_FR_STATIONS_DEFAULT = list(_cfg.fr_stations)
FR_STATIONS_FILE = _cfg.fr_stations_file

# ---------------------------------------------------------------------------
# CONDOTTA TARGET (media giornaliera)
# ---------------------------------------------------------------------------
TARGET_CONDOTTA_MIN = _cfg.target_condotta_min

# ---------------------------------------------------------------------------
# TURNO SETTIMANALE
# ---------------------------------------------------------------------------
WEEKLY_HOURS_MIN = _cfg.weekly_hours_min
WEEKLY_HOURS_MAX = _cfg.weekly_hours_max
WEEKLY_HOURS_TARGET = _cfg.weekly_hours_target
WEEKLY_DAYS = _cfg.weekly_days

# Mappatura tipo giorno → frequenza settimanale
DAY_FREQUENCY = dict(_cfg.day_frequency)

# Tipo variante → tipo giorno
VARIANT_TO_DAY_TYPE = dict(_cfg.variant_to_day_type)

# Durata minima per S.COMP (disponibilità)
SCOMP_DURATION_MIN = _cfg.scomp_duration_min

# ---------------------------------------------------------------------------
# FUORI RESIDENZA - REGOLE CONTRATTUALI
# ---------------------------------------------------------------------------
FR_MAX_PRESTAZIONE_ANDATA_MIN = _cfg.fr_max_prestazione_andata_min
FR_MIN_RIPOSO_H = _cfg.fr_min_riposo_h
FR_MAX_PRESTAZIONE_RIENTRO_MIN = _cfg.fr_max_prestazione_rientro_min
FR_MAX_PER_WEEK = _cfg.fr_max_per_week
FR_MAX_PER_28_DAYS = _cfg.fr_max_per_28_days

# ---------------------------------------------------------------------------
# OPZIONI ACCESSORI (standard + maggiorati)
# ---------------------------------------------------------------------------
ACCESSORY_OPTIONS = dict(_cfg.accessory_options)

# ---------------------------------------------------------------------------
# NORMATIVA-PDC.md §3.3 — valori contrattuali ACCp/ACCa su condotta
# ---------------------------------------------------------------------------
ACCP_STANDARD_MIN = _cfg.accp_standard_min
ACCA_STANDARD_MIN = _cfg.acca_standard_min
ACCP_PRERISCALDO_MIN = _cfg.accp_preriscaldo_min

# NORMATIVA-PDC.md §8.5 / §8.7 — trasferimento impianto ↔ stazione RFI
IMPIANTO_TO_RFI_TRANSFER_MIN = _cfg.impianto_to_rfi_transfer_min

# NORMATIVA-PDC.md §8.5.1 — taxi deposito ↔ impianto (no tracce)
DEPOT_TO_IMPIANTO_TAXI_MIN = _cfg.depot_to_impianto_taxi_min

# NORMATIVA-PDC.md §3.2 — finestre pre/post vettura
PRE_VETTURA_MIN = _cfg.pre_vettura_min
POST_VETTURA_MIN = _cfg.post_vettura_min

# ---------------------------------------------------------------------------
# TEMPI FISSI DI CONDOTTA (tratte a durata fissa, in minuti)
# ---------------------------------------------------------------------------
FIXED_TRAVEL_TIMES = dict(_cfg.fixed_travel_times)

# ---------------------------------------------------------------------------
# DEPOSITI (IMPIANTI)
# ---------------------------------------------------------------------------
DEPOSITI = list(_cfg.depots)

# ---------------------------------------------------------------------------
# VALIDITA CIRCOLAZIONE TRENI
# ---------------------------------------------------------------------------
VALIDITY_MAP = dict(_cfg.validity_map)

# Mappa giorno successivo per FR (dormita fuori residenza)
FR_NEXT_DAY_MAP = dict(_cfg.fr_next_day_map)


def load_fr_stations() -> list[str]:
    """Carica stazioni FR da file esterno oppure fallback dalla configurazione."""
    fr_path = Path(FR_STATIONS_FILE)
    if fr_path.exists():
        stations = [
            line.strip().upper()
            for line in fr_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        print(f"FR stations: caricata da file [{FR_STATIONS_FILE}] - {len(stations)} stazioni")
        return stations
    else:
        print(f"FR stations: da configurazione {_cfg.company_name} - {len(ALLOWED_FR_STATIONS_DEFAULT)} stazioni")
        return list(ALLOWED_FR_STATIONS_DEFAULT)
