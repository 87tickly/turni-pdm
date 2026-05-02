"""Vincoli inviolabili a livello tipo materiale.

Vedi `data/vincoli_materiale_inviolabili.json` (Single Source of Truth)
e `inviolabili.py` per il validator.
"""

from colazione.domain.vincoli.inviolabili import (
    Vincolo,
    Violazione,
    carica_vincoli,
    corsa_ammessa_per_materiale,
    valida_regola,
)

__all__ = [
    "Vincolo",
    "Violazione",
    "carica_vincoli",
    "corsa_ammessa_per_materiale",
    "valida_regola",
]
