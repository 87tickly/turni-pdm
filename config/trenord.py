"""
Configurazione specifica Trenord.
Override solo dei valori che differiscono dai default normativi.
"""

from config.schema import CompanyConfig

TRENORD_CONFIG = CompanyConfig(
    company_name="Trenord",
    company_code="TRENORD",

    depots=[
        "ALESSANDRIA",
        "ARONA",
        "BERGAMO",
        "BRESCIA",
        "COLICO",
        "COMO",
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
    ],

    fr_stations=[
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
    ],

    fixed_travel_times={
        ("ALESSANDRIA", "PAVIA"): 79,
        ("PAVIA", "ALESSANDRIA"): 79,
        ("ALESSANDRIA", "MILANO ROGOREDO"): 105,
        ("MILANO ROGOREDO", "ALESSANDRIA"): 105,
    },

    # CVL è specifico Trenord
    accessory_options={
        "standard": {"label": "Standard (10+8)", "start": 10, "end": 8},
        "maggiorato_1": {"label": "Maggiorato 1 (15+10)", "start": 15, "end": 10},
        "maggiorato_2": {"label": "Maggiorato 2 (20+15)", "start": 20, "end": 15},
        "maggiorato_3": {"label": "Maggiorato 3 (25+20)", "start": 25, "end": 20},
        "cvl": {"label": "CVL - Cambio Volante (5+5)", "start": 5, "end": 5},
    },

    depot_to_station={
        "GARIBALDI_ALE": "MILANO PORTA GARIBALDI",
        "GARIBALDI_CADETTI": "MILANO PORTA GARIBALDI",
        "GARIBALDI_TE": "MILANO PORTA GARIBALDI",
        "GRECO_TE": "MILANO GRECO PIRELLI",
        "GRECO_S9": "MILANO GRECO PIRELLI",
        "FIORENZA": "MILANO CADORNA",
        "COMO": "COMO SAN GIOVANNI",
    },

    # ── Normativa PdC esplicitamente dichiarata per Trenord ──────
    # (valori identici ai default schema; qui per tracciabilità).
    # NORMATIVA-PDC.md §11.8 — prestazione max variabile
    cap_7h_window_start_min=60,            # 01:00
    cap_7h_window_end_min=4 * 60 + 59,     # 04:59
    cap_7h_prestazione_min=420,            # 7h
    # §4.1 — soglia REFEZ obbligatoria
    refez_required_above_min=360,          # 6h
    # §3.3 — accessori contrattuali condotta
    accp_standard_min=40,
    acca_standard_min=40,
    accp_preriscaldo_min=80,               # ● dic-feb
    # §8.5 / §8.7 — trasferimento impianto ↔ stazione RFI (U-numero)
    impianto_to_rfi_transfer_min=7,        # FIOz → Mi.Certosa
    # §8.5.1 — taxi deposito ↔ impianto (no tracce pubbliche)
    depot_to_impianto_taxi_min=20,         # MI.PG ↔ FIOz
    # §3.2 — finestre pre/post vettura
    pre_vettura_min=15,
    post_vettura_min=15,
)
