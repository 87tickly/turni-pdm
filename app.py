#!/usr/bin/env python3
"""
Sistema Pianificazione Turni PDM - Personale di Macchina.

Uso:
    python app.py import <percorso_pdf>
    python app.py train <numero_treno>
    python app.py station "<nome_stazione>"
    python app.py build-auto --deposito "STAZIONE" --days 10
    python app.py build-manual --deposito "STAZIONE"
    python app.py info
    python app.py clear
"""

from src.cli import run_cli

if __name__ == "__main__":
    run_cli()
