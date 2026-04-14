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
)
