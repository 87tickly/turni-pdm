"""
Schema configurazione aziendale.
I valori di default riflettono la normativa ferroviaria italiana generica.
Ogni azienda può override solo ciò che è diverso.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CompanyConfig:
    """Configurazione completa per un'azienda di trasporto ferroviario."""

    # ── Identità azienda ──────────────────────────────────────────
    company_name: str = ""
    company_code: str = ""  # codice identificativo (es. "TRENORD")

    # ── Depositi / Impianti ───────────────────────────────────────
    depots: list[str] = field(default_factory=list)

    # ── Stazioni Fuori Residenza ──────────────────────────────────
    fr_stations: list[str] = field(default_factory=list)
    fr_stations_file: str = "fr_stations.txt"

    # ── Tempi fissi di condotta (tratte a durata fissa, minuti) ───
    # Chiave: tupla (stazione_a, stazione_b), valore: minuti
    fixed_travel_times: dict = field(default_factory=dict)

    # ── Opzioni accessori ─────────────────────────────────────────
    accessory_options: dict = field(default_factory=lambda: {
        "standard": {"label": "Standard (10+8)", "start": 10, "end": 8},
        "maggiorato_1": {"label": "Maggiorato 1 (15+10)", "start": 15, "end": 10},
        "maggiorato_2": {"label": "Maggiorato 2 (20+15)", "start": 20, "end": 15},
        "maggiorato_3": {"label": "Maggiorato 3 (25+20)", "start": 25, "end": 20},
    })

    # ── Mapping deposito → stazione reale (per VT/ARTURO) ────────
    depot_to_station: dict = field(default_factory=dict)

    # ── Validità circolazione ─────────────────────────────────────
    validity_map: dict = field(default_factory=lambda: {
        "LV":   ["LV", "LS", "GG"],
        "SAB":  ["SAB", "LS", "GG"],
        "DOM":  ["DOM", "GG", "FEST"],
        "FEST": ["FEST", "DOM", "GG"],
    })

    # Mappa giorno successivo per FR (dormita)
    fr_next_day_map: dict = field(default_factory=lambda: {
        "LV":   ["LV", "SAB"],
        "SAB":  ["DOM"],
        "DOM":  ["LV"],
        "FEST": ["LV"],
    })

    # ── Limiti prestazione e condotta (normativa italiana) ────────
    max_prestazione_min: int = 510       # 8h30
    max_condotta_min: int = 330          # 5h30
    meal_min: int = 30                   # refezione inclusa nella prestazione

    # Finestre orarie refezione
    meal_window_1_start: int = 11 * 60 + 30   # 11:30
    meal_window_1_end: int = 15 * 60 + 30     # 15:30
    meal_window_2_start: int = 18 * 60 + 30   # 18:30
    meal_window_2_end: int = 22 * 60 + 30     # 22:30

    # ── Tempi aggiuntivi ──────────────────────────────────────────
    extra_start_min: int = 5
    extra_end_min: int = 5

    # ── Regole accessori ──────────────────────────────────────────
    accessory_default_start: int = 10
    accessory_default_end: int = 8

    # ── Tempi medi (maggiorazione) ────────────────────────────────
    tempi_medi_default_extra: int = 4

    # ── Notturno ──────────────────────────────────────────────────
    max_night_min: int = 420             # 7 ore
    night_start: str = "00:01"
    night_end: str = "01:00"

    # ── Riposo tra turni ──────────────────────────────────────────
    rest_standard_h: int = 11
    rest_after_001_0100_h: int = 14      # fine turno tra 00:01 e 01:00
    rest_after_night_h: int = 16         # giornata notturna

    # ── Riposo settimanale ────────────────────────────────────────
    weekly_rest_min_h: int = 62

    # ── Ciclo lavorativo ──────────────────────────────────────────
    work_block: int = 5
    rest_block: int = 2

    # ── Condotta target ───────────────────────────────────────────
    # 4h di condotta media giornaliera: feedback utente 22/04/2026
    # "possiamo arrivare tranquillamente anche a 4h oppure 5h max".
    # Max contrattuale resta 5h30' (max_condotta_min=330).
    target_condotta_min: int = 240       # 4h

    # ── Turno settimanale ─────────────────────────────────────────
    weekly_hours_min: int = 33 * 60      # 1980 min
    weekly_hours_max: int = 38 * 60      # 2280 min
    weekly_hours_target: int = int(35.5 * 60)  # 2130 min
    weekly_days: int = 5

    # Frequenza tipo giorno
    day_frequency: dict = field(default_factory=lambda: {
        "LMXGV": 5,
        "S": 1,
        "D": 1,
    })

    # Tipo variante → tipo giorno
    variant_to_day_type: dict = field(default_factory=lambda: {
        "LMXGV": "LV",
        "S": "SAB",
        "D": "DOM",
    })

    # ── S.COMP (disponibilità) ────────────────────────────────────
    scomp_duration_min: int = 360        # 6 ore

    # ── Fuori Residenza - Regole contrattuali ─────────────────────
    fr_max_prestazione_andata_min: int = 510   # 8h30 (come normale)
    fr_min_riposo_h: int = 6
    fr_max_prestazione_rientro_min: int = 420  # 7h max giorno rientro
    fr_max_per_week: int = 1
    fr_max_per_28_days: int = 3

    @property
    def extra_total_min(self) -> int:
        return self.extra_start_min + self.extra_end_min

    @property
    def accessory_rules(self) -> dict:
        return {
            "default_start": self.accessory_default_start,
            "default_end": self.accessory_default_end,
        }

    @property
    def tempi_medi_rules(self) -> dict:
        return {
            "default_extra": self.tempi_medi_default_extra,
        }
