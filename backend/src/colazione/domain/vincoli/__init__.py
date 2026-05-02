"""Vincoli inviolabili a livello tipo materiale.

Vedi `data/vincoli_materiale_inviolabili.json` (Single Source of Truth)
e `inviolabili.py` per il validator.
"""

from colazione.domain.vincoli.inviolabili import (
    Violazione,
    carica_vincoli,
    valida_regola,
)

__all__ = [
    "Violazione",
    "carica_vincoli",
    "valida_regola",
]
