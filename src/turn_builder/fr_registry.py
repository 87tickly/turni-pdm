"""
FR Registry — gestione stazioni di Fuori Residenza (dormita) approvate
per ciascun PdC.

Flusso (Step 7 + Step 10):

  1. Durante la generazione, se la giornata non ha rientro e la stazione
     di fine NON e' in FR gia' approvate, viene marcata come
     `fr_candidate=True` + `fr_station=<stazione>`.
  2. Al termine della generazione, la UI mostra le FR candidate raggruppate
     per stazione (Step 10). L'utente approva una volta per stazione.
  3. Le stazioni approvate sono persistite nella tabella pdc_fr_approved
     e diventano FR valide per le prossime generazioni di quel PdC.

Questo modulo espone solo funzioni di read/write sulla tabella. La logica
di business (quando marcare candidata vs approvata) e' in day_assembler.
"""
from __future__ import annotations

import sqlite3
from typing import Iterable


def list_approved(conn: sqlite3.Connection, pdc_id: str) -> set[str]:
    """Ritorna il set di stazioni FR approvate per il PdC (uppercase)."""
    cur = conn.execute(
        "SELECT station FROM pdc_fr_approved WHERE pdc_id = ?",
        (pdc_id,),
    )
    return {(row[0] or "").upper().strip() for row in cur.fetchall()}


def approve(conn: sqlite3.Connection, pdc_id: str,
            station: str, notes: str = "") -> None:
    """Approva una stazione FR per il PdC. Idempotente."""
    conn.execute(
        "INSERT OR IGNORE INTO pdc_fr_approved (pdc_id, station, notes) "
        "VALUES (?, ?, ?)",
        (pdc_id, station.upper().strip(), notes),
    )
    conn.commit()


def revoke(conn: sqlite3.Connection, pdc_id: str, station: str) -> None:
    """Revoca l'approvazione di una stazione FR per il PdC."""
    conn.execute(
        "DELETE FROM pdc_fr_approved WHERE pdc_id = ? AND station = ?",
        (pdc_id, station.upper().strip()),
    )
    conn.commit()


def approve_batch(conn: sqlite3.Connection, pdc_id: str,
                   stations: Iterable[str]) -> int:
    """Approva N stazioni in una transazione. Ritorna il numero di nuove
    approvazioni effettivamente inserite."""
    before = len(list_approved(conn, pdc_id))
    for st in stations:
        approve(conn, pdc_id, st)
    return len(list_approved(conn, pdc_id)) - before
