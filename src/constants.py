"""
Costanti operative per il sistema di pianificazione turni PDM.
Tutte le regole operative sono implementate direttamente nel codice.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# LIMITI PRESTAZIONE E CONDOTTA
# ---------------------------------------------------------------------------
MAX_PRESTAZIONE_MIN = 510        # 8h30
MAX_CONDOTTA_MIN = 330           # 5h30
MEAL_MIN = 30                    # refezione inclusa nella prestazione

# Finestre orarie contrattuali per la refezione
MEAL_WINDOW_1_START = 11 * 60 + 30   # 11:30
MEAL_WINDOW_1_END = 15 * 60 + 30     # 15:30
MEAL_WINDOW_2_START = 18 * 60 + 30   # 18:30
MEAL_WINDOW_2_END = 22 * 60 + 30     # 22:30

# ---------------------------------------------------------------------------
# TEMPI AGGIUNTIVI (per ogni giornata con treni)
# ---------------------------------------------------------------------------
EXTRA_START_MIN = 5
EXTRA_END_MIN = 5
EXTRA_TOTAL_MIN = EXTRA_START_MIN + EXTRA_END_MIN  # 10

# ---------------------------------------------------------------------------
# NOTTURNO
# ---------------------------------------------------------------------------
MAX_NIGHT_MIN = 420              # massimo notturno (7 ore)
NIGHT_START = "00:01"
NIGHT_END = "01:00"

# ---------------------------------------------------------------------------
# RIPOSO TRA TURNI
# ---------------------------------------------------------------------------
REST_STANDARD_H = 11
REST_AFTER_001_0100_H = 14       # fine turno tra 00:01 e 01:00
REST_AFTER_NIGHT_H = 16          # giornata notturna

# ---------------------------------------------------------------------------
# RIPOSO SETTIMANALE
# ---------------------------------------------------------------------------
WEEKLY_REST_MIN_H = 62

# ---------------------------------------------------------------------------
# CICLO 5+2
# ---------------------------------------------------------------------------
WORK_BLOCK = 5
REST_BLOCK = 2

# ---------------------------------------------------------------------------
# TEMPI ACCESSORI
# ---------------------------------------------------------------------------
ACCESSORY_RULES = {
    "default_start": 10,
    "default_end": 8,
}

# ---------------------------------------------------------------------------
# TEMPI MEDI (maggiorazione degli accessori)
# ---------------------------------------------------------------------------
TEMPI_MEDI_RULES = {
    "default_extra": 4,
}

# ---------------------------------------------------------------------------
# FUORI RESIDENZA - STAZIONI FR
# ---------------------------------------------------------------------------
ALLOWED_FR_STATIONS_DEFAULT = [
    "MILANO CENTRALE",
    "MILANO PORTA GARIBALDI",
    "MILANO ROGOREDO",
    "BERGAMO",
    "BRESCIA",
    "CREMONA",
    "MANTOVA",
    "LECCO",
    "COMO SAN GIOVANNI",
    "VARESE",
    "GALLARATE",
    "BUSTO ARSIZIO",
    "SARONNO",
    "MONZA",
    "TORINO PORTA NUOVA",
    "TORINO PORTA SUSA",
    "NOVARA",
    "ALESSANDRIA",
    "CASELLE AEROPORTO",
]

FR_STATIONS_FILE = "fr_stations.txt"

# ---------------------------------------------------------------------------
# CONDOTTA TARGET (media giornaliera)
# ---------------------------------------------------------------------------
TARGET_CONDOTTA_MIN = 180            # 3 ore condotta media giornaliera

# ---------------------------------------------------------------------------
# TURNO SETTIMANALE
# ---------------------------------------------------------------------------
WEEKLY_HOURS_MIN = 33 * 60           # 33 ore settimanali minime (1980 min)
WEEKLY_HOURS_MAX = 38 * 60           # 38 ore settimanali massime (2280 min)
WEEKLY_HOURS_TARGET = 35.5 * 60      # 35h30 target ottimale (2130 min)
WEEKLY_DAYS = 5                       # numero giornate lavorative nel turno

# Mappatura tipo giorno → frequenza settimanale
DAY_FREQUENCY = {
    "LMXGV": 5,   # Lun-Mar-Mer-Gio-Ven
    "S": 1,        # Sabato
    "D": 1,        # Domenica
}

# Tipo variante → tipo giorno
VARIANT_TO_DAY_TYPE = {
    "LMXGV": "LV",
    "S": "SAB",
    "D": "DOM",
}

# Durata minima per S.COMP (disponibilità)
SCOMP_DURATION_MIN = 360             # 6 ore (360 min)

# ---------------------------------------------------------------------------
# FUORI RESIDENZA - REGOLE CONTRATTUALI
# ---------------------------------------------------------------------------
FR_MAX_PRESTAZIONE_ANDATA_MIN = 510  # 8h30 giorno di andata (come normale)
FR_MIN_RIPOSO_H = 6                  # minimo 6 ore riposo in FR
FR_MAX_PRESTAZIONE_RIENTRO_MIN = 420 # 7h max giorno rientro (compreso viaggio)
FR_MAX_PER_WEEK = 1                  # max 1 dormita FR a settimana
FR_MAX_PER_28_DAYS = 3               # max 3 dormite FR su 28 giorni

# ---------------------------------------------------------------------------
# OPZIONI ACCESSORI (standard + maggiorati)
# ---------------------------------------------------------------------------
ACCESSORY_OPTIONS = {
    "standard": {"label": "Standard (10+8)", "start": 10, "end": 8},
    "maggiorato_1": {"label": "Maggiorato 1 (15+10)", "start": 15, "end": 10},
    "maggiorato_2": {"label": "Maggiorato 2 (20+15)", "start": 20, "end": 15},
    "maggiorato_3": {"label": "Maggiorato 3 (25+20)", "start": 25, "end": 20},
    "cvl": {"label": "CVL - Cambio Volante (5+5)", "start": 5, "end": 5},
}

# ---------------------------------------------------------------------------
# TEMPI FISSI DI CONDOTTA (tratte a durata fissa, in minuti)
# ---------------------------------------------------------------------------
FIXED_TRAVEL_TIMES = {
    ("ALESSANDRIA", "PAVIA"): 79,            # 1h 19min
    ("PAVIA", "ALESSANDRIA"): 79,            # 1h 19min
    ("ALESSANDRIA", "MILANO ROGOREDO"): 105,  # 1h 45min
    ("MILANO ROGOREDO", "ALESSANDRIA"): 105,  # 1h 45min
}

# ---------------------------------------------------------------------------
# DEPOSITI (IMPIANTI) TRENORD
# ---------------------------------------------------------------------------
DEPOSITI = [
    "ALESSANDRIA",
    "ARONA",
    "BERGAMO",
    "BRESCIA",
    "COLICO",
    "CREMONA",
    "DOMODOSSOLA",
    "FIORENZA",
    "GALLARATE",
    "GARIBALDI_ALE",
    "GARIBALDI_CADETTI",
    "GARIBALDI_TE",
    "GRECO_TE",
    "GRECO_S9",
    "LECCO",
    "LUINO",
    "MANTOVA",
    "MORTARA",
    "PAVIA",
    "PIACENZA",
    "SONDRIO",
    "TREVIGLIO",
    "VERONA",
    "VOGHERA",
]

# ---------------------------------------------------------------------------
# VALIDITA CIRCOLAZIONE TRENI
# ---------------------------------------------------------------------------
VALIDITY_MAP = {
    "LV":   ["LV", "LS", "GG"],       # Lun-Ven
    "SAB":  ["SAB", "LS", "GG"],       # Sabato
    "DOM":  ["DOM", "GG", "FEST"],     # Domenica
    "FEST": ["FEST", "DOM", "GG"],     # Festivi
}

# Mappa giorno successivo per FR (dormita fuori residenza)
# LV Lun-Ven: il giorno dopo è ancora LV (tranne venerdì → SAB)
# SAB: il giorno dopo è DOM
# DOM: il giorno dopo è LV (lunedì)
FR_NEXT_DAY_MAP = {
    "LV":   ["LV", "SAB"],   # Lun→Mar...Gio→Ven ok, Ven→Sab possibile
    "SAB":  ["DOM"],          # Sabato → Domenica
    "DOM":  ["LV"],           # Domenica → Lunedì
    "FEST": ["LV"],           # Festivo → Lunedì (tipicamente)
}


def load_fr_stations() -> list[str]:
    """Carica stazioni FR da file esterno oppure fallback hardcoded."""
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
        print(f"FR stations: fallback hardcoded - {len(ALLOWED_FR_STATIONS_DEFAULT)} stazioni")
        return list(ALLOWED_FR_STATIONS_DEFAULT)
