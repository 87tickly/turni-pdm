"""
Loader configurazione aziendale.
Carica la configurazione attiva (default: Trenord).
In futuro supporterà file JSON/YAML per switch dinamico.
"""

import os

from typing import Optional

from config.schema import CompanyConfig
from config.trenord import TRENORD_CONFIG

# Cache della configurazione attiva
_active_config: Optional[CompanyConfig] = None


def get_active_config() -> CompanyConfig:
    """Ritorna la configurazione aziendale attiva.

    Ordine di risoluzione:
    1. Env var COLAZIONE_COMPANY (es. "trenord") → seleziona preset
    2. Default: Trenord
    """
    global _active_config
    if _active_config is not None:
        return _active_config

    company = os.environ.get("COLAZIONE_COMPANY", "trenord").lower()

    configs = {
        "trenord": TRENORD_CONFIG,
        # Aggiungere qui future configurazioni:
        # "atm": ATM_CONFIG,
        # "trenitalia": TRENITALIA_CONFIG,
    }

    _active_config = configs.get(company, TRENORD_CONFIG)
    print(f"[CONFIG] Configurazione attiva: {_active_config.company_name}")
    return _active_config


def reset_config():
    """Reset della cache (utile per test)."""
    global _active_config
    _active_config = None
