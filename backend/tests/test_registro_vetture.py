"""Test unit RegistroVettureAssegnate — Sprint 8.2 MR-PD-FIX-SEVERO 3b A1.

Verifica il vincolo §15 cross-PdC: assegna/is_assegnata, wild card
match, chiave (numero, operatore), data_operativa isolation.

Test ``from_db`` integration con DB reale è in ``test_a1_cross_pdc.py``
(integration end-to-end con turno PdC esistente).
"""

from __future__ import annotations

from datetime import date

import pytest

from colazione.domain.builder_pdc.registro_vetture import (
    RegistroVettureAssegnate,
)


class TestRegistroBase:
    """Comportamento di base: assegna/is_assegnata, conteggio."""

    def test_registro_vuoto_nessuna_vettura(self) -> None:
        r = RegistroVettureAssegnate()
        assert r.n_assegnate == 0
        assert not r.is_assegnata(
            numero_treno="2425",
            operatore="TN",
            data_operativa=date(2026, 3, 15),
        )

    def test_assegna_e_query_match(self) -> None:
        r = RegistroVettureAssegnate()
        r.assegna(
            numero_treno="2425",
            operatore="TN",
            data_operativa=date(2026, 3, 15),
        )
        assert r.n_assegnate == 1
        assert r.is_assegnata(
            numero_treno="2425",
            operatore="TN",
            data_operativa=date(2026, 3, 15),
        )

    def test_assegna_idempotente(self) -> None:
        """Stessa chiave + stessa data: 2 assegna() = 1 entry sola."""
        r = RegistroVettureAssegnate()
        r.assegna(numero_treno="2425", operatore="TN", data_operativa=date(2026, 3, 15))
        r.assegna(numero_treno="2425", operatore="TN", data_operativa=date(2026, 3, 15))
        assert r.n_assegnate == 1


class TestChiaveOperatore:
    """S3 SEVERO: chiave (numero, operatore) — operatori distinti = chiavi
    distinte (no falso positivo doppione su numerazioni cross-azienda)."""

    def test_stesso_numero_operatori_diversi_no_match(self) -> None:
        r = RegistroVettureAssegnate()
        r.assegna(numero_treno="100", operatore="TN", data_operativa=date(2026, 3, 15))
        # TILO con stesso numero non collide
        assert not r.is_assegnata(
            numero_treno="100",
            operatore="TILO",
            data_operativa=date(2026, 3, 15),
        )

    def test_stesso_numero_operatore_none_no_match_strict(self) -> None:
        """None matcha solo None: TN registrato ≠ None (operatore ignoto)."""
        r = RegistroVettureAssegnate()
        r.assegna(numero_treno="100", operatore="TN", data_operativa=date(2026, 3, 15))
        assert not r.is_assegnata(
            numero_treno="100",
            operatore=None,
            data_operativa=date(2026, 3, 15),
        )

    def test_operatore_none_match_se_registrato_none(self) -> None:
        r = RegistroVettureAssegnate()
        r.assegna(numero_treno="100", operatore=None, data_operativa=date(2026, 3, 15))
        assert r.is_assegnata(
            numero_treno="100",
            operatore=None,
            data_operativa=date(2026, 3, 15),
        )


class TestDataIsolation:
    """Date diverse = entries indipendenti."""

    def test_data_diversa_no_match(self) -> None:
        r = RegistroVettureAssegnate()
        r.assegna(numero_treno="2425", operatore="TN", data_operativa=date(2026, 3, 15))
        assert not r.is_assegnata(
            numero_treno="2425",
            operatore="TN",
            data_operativa=date(2026, 3, 16),
        )

    def test_assegna_2_date_2_entries(self) -> None:
        r = RegistroVettureAssegnate()
        r.assegna(numero_treno="2425", operatore="TN", data_operativa=date(2026, 3, 15))
        r.assegna(numero_treno="2425", operatore="TN", data_operativa=date(2026, 3, 16))
        assert r.n_assegnate == 2
        assert r.is_assegnata(
            numero_treno="2425",
            operatore="TN",
            data_operativa=date(2026, 3, 15),
        )
        assert r.is_assegnata(
            numero_treno="2425",
            operatore="TN",
            data_operativa=date(2026, 3, 16),
        )


class TestWildCardMatch:
    """S4 SEVERO MVP: data_operativa=None nel registro = wild card,
    matcha qualsiasi data."""

    def test_wild_card_matcha_qualsiasi_data(self) -> None:
        r = RegistroVettureAssegnate()
        r.assegna(numero_treno="2425", operatore="TN", data_operativa=None)
        # 3 date diverse: tutte matchano
        assert r.is_assegnata(
            numero_treno="2425",
            operatore="TN",
            data_operativa=date(2026, 3, 15),
        )
        assert r.is_assegnata(
            numero_treno="2425",
            operatore="TN",
            data_operativa=date(2026, 12, 31),
        )
        assert r.is_assegnata(
            numero_treno="2425",
            operatore="TN",
            data_operativa=date(2027, 1, 1),
        )

    def test_wild_card_solo_su_chiave_corrispondente(self) -> None:
        """Wild card non spara su chiavi diverse."""
        r = RegistroVettureAssegnate()
        r.assegna(numero_treno="2425", operatore="TN", data_operativa=None)
        # Numero diverso: no match anche con wild card
        assert not r.is_assegnata(
            numero_treno="999",
            operatore="TN",
            data_operativa=date(2026, 3, 15),
        )


class TestNumeriDaEscludere:
    """Set di esclusi per propagazione al filtro `trova_treno_vettura`."""

    def test_set_vuoto_se_nessuna_assegnata(self) -> None:
        r = RegistroVettureAssegnate()
        assert r.numeri_da_escludere(data_operativa=date(2026, 3, 15)) == frozenset()

    def test_set_include_data_concreta(self) -> None:
        r = RegistroVettureAssegnate()
        r.assegna(numero_treno="2425", operatore="TN", data_operativa=date(2026, 3, 15))
        r.assegna(numero_treno="2426", operatore="TN", data_operativa=date(2026, 3, 15))
        # Altra data: non inclusa
        r.assegna(numero_treno="3000", operatore="TN", data_operativa=date(2026, 3, 16))
        out = r.numeri_da_escludere(data_operativa=date(2026, 3, 15))
        assert ("2425", "TN") in out
        assert ("2426", "TN") in out
        assert ("3000", "TN") not in out

    def test_set_include_wild_card(self) -> None:
        r = RegistroVettureAssegnate()
        r.assegna(numero_treno="2425", operatore="TN", data_operativa=None)  # wild
        r.assegna(numero_treno="2426", operatore="TN", data_operativa=date(2026, 3, 15))
        out = r.numeri_da_escludere(data_operativa=date(2026, 3, 15))
        assert ("2425", "TN") in out  # wild card
        assert ("2426", "TN") in out  # data concreta


@pytest.mark.asyncio
async def test_from_db_registro_vuoto_se_no_turni() -> None:
    """from_db con DB vuoto ritorna registro vuoto. Test smoke a livello
    factory (non integration con DB reale: vedi test_a1_cross_pdc.py)."""
    # Mock minimale di AsyncSession con execute() che ritorna result vuoto.
    from unittest.mock import AsyncMock, MagicMock

    fake_result = MagicMock()
    fake_result.all.return_value = []
    fake_session = AsyncMock()
    fake_session.execute = AsyncMock(return_value=fake_result)

    r = await RegistroVettureAssegnate.from_db(fake_session, programma_id=42)
    assert r.n_assegnate == 0
    fake_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_from_db_carica_numeri_treno_come_wild_card() -> None:
    """from_db legge numero_treno_vettura dei blocchi VETTURA e li
    registra come wild card (data=None)."""
    from unittest.mock import AsyncMock, MagicMock

    fake_result = MagicMock()
    # Simula 3 righe: 3 numeri treno distinti
    fake_result.all.return_value = [("2425",), ("2426",), ("28335i",)]
    fake_session = AsyncMock()
    fake_session.execute = AsyncMock(return_value=fake_result)

    r = await RegistroVettureAssegnate.from_db(fake_session, programma_id=42)
    assert r.n_assegnate == 3
    # Tutti registrati come wild card → matchano qualsiasi data
    for numero in ("2425", "2426", "28335i"):
        assert r.is_assegnata(
            numero_treno=numero,
            operatore=None,  # wild operatore
            data_operativa=date(2026, 3, 15),
        )
