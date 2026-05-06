"""Test detection impatto variazioni (Sub-MR 5.bis-impact, entry 179).

Smoke test sul helper ``calcola_impatto_su_programmi``: verifica
contratto + caso "no impatto" (corse_ids vuoto). Test del calcolo
reale (con giri/turni che referenziano corse impattate) è scope del
sub-MR fork (entry 180+) dove il setup completo sarà richiesto
comunque.

Test sull'estrattore ``estrai_corse_ids_da_risultato_pianificazione``:
puro Python, zero DB, copre i 4 tipi di operazione del modulo
``domain/variazioni_pde``.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.api.variazioni_impatto import (
    calcola_impatto_su_programmi,
    estrai_corse_ids_da_risultato_pianificazione,
)
from colazione.db import session_scope
from colazione.domain.variazioni_pde import (
    OpInsert,
    OpSoftCancella,
    OpUpdateOrari,
    OpUpdateValidoInDate,
    RisultatoPianificazione,
)

pytestmark = pytest.mark.skipif(
    os.getenv("SKIP_DB_TESTS") == "1",
    reason="DB not configured for tests",
)


# =====================================================================
# estrai_corse_ids_da_risultato_pianificazione (pure Python)
# =====================================================================


def test_estrai_corse_ids_risultato_vuoto() -> None:
    """RisultatoPianificazione vuoto → set vuoto."""
    res = RisultatoPianificazione()
    assert estrai_corse_ids_da_risultato_pianificazione(res) == set()


def test_estrai_corse_ids_solo_insert_zero_corse() -> None:
    """OpInsert non porta corsa_id (corsa nuova) → set vuoto, no impatto."""
    res = RisultatoPianificazione(
        insert=[OpInsert(parsed_index=0, row_hash="abc")],
    )
    assert estrai_corse_ids_da_risultato_pianificazione(res) == set()


def test_estrai_corse_ids_update_orari_e_cancellazioni() -> None:
    """Mix di update orari, update valido_in_date, cancellazioni."""
    from datetime import time

    res = RisultatoPianificazione(
        update_orari=[
            OpUpdateOrari(
                corsa_id=10,
                ora_partenza=time(7, 0),
                ora_arrivo=time(8, 0),
                ora_inizio_cds=None,
                ora_fine_cds=None,
                min_tratta=60,
                min_cds=None,
                km_tratta=None,
                km_cds=None,
            ),
        ],
        update_valido_in_date=[
            OpUpdateValidoInDate(corsa_id=20, valido_in_date_json=()),
        ],
        cancellazioni=[OpSoftCancella(corsa_id=30)],
    )
    assert estrai_corse_ids_da_risultato_pianificazione(res) == {10, 20, 30}


def test_estrai_corse_ids_dedupe() -> None:
    """Stessa corsa in più operazioni → un solo id nel set."""
    from datetime import time

    res = RisultatoPianificazione(
        update_orari=[
            OpUpdateOrari(
                corsa_id=42,
                ora_partenza=time(7, 0),
                ora_arrivo=time(8, 0),
                ora_inizio_cds=None,
                ora_fine_cds=None,
                min_tratta=None,
                min_cds=None,
                km_tratta=None,
                km_cds=None,
            ),
        ],
        cancellazioni=[OpSoftCancella(corsa_id=42)],
    )
    assert estrai_corse_ids_da_risultato_pianificazione(res) == {42}


# =====================================================================
# calcola_impatto_su_programmi (smoke con DB)
# =====================================================================


async def test_calcola_impatto_corse_vuote_ritorna_lista_vuota() -> None:
    """corse_ids vuoto → return [] senza query SQL (short-circuit)."""
    async with session_scope() as session:
        result = await calcola_impatto_su_programmi(
            session, corse_ids=set(), azienda_id=1
        )
        assert result == []


async def test_calcola_impatto_corse_inesistenti_ritorna_lista_vuota() -> None:
    """corse_ids con id che nessun giro referenzia → []."""
    async with session_scope() as session:
        result = await calcola_impatto_su_programmi(
            session, corse_ids={9_999_999_999}, azienda_id=1
        )
        assert result == []


async def test_calcola_impatto_segregazione_per_azienda() -> None:
    """Anche se ci sono corse impattanti, se l'azienda passata non è
    quella dei giri/turni → ritorna []. Test multi-tenant safety."""
    async with session_scope() as session:
        # Uso azienda_id altissimo (non esiste): garantisce 0 risultati
        # anche se per caso ci sono corse_ids match.
        result = await calcola_impatto_su_programmi(
            session, corse_ids={1, 2, 3}, azienda_id=99999
        )
        assert result == []
