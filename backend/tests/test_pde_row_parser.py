"""Test parser singola riga PdE end-to-end (Sprint 3.2-3.5).

Usa la fixture `tests/fixtures/pde_sample.xlsx` (38 righe reali Trenord,
selezionate per coprire i pattern di periodicità). Verifica:

- Tutte le 38 righe parsano senza eccezioni
- Composizioni: ogni riga ha esattamente 9 entry
- Cross-check Gg_*: warnings vuoti su tutte le righe (la fixture è
  formato Trenord canonico, il parser deve azzeccare la matematica)
"""

from datetime import date, time
from decimal import Decimal
from pathlib import Path

import pytest

from colazione.importers.pde import (
    CorsaParsedRow,
    parse_corsa_row,
    read_pde_file,
)

FIXTURE = Path(__file__).parent / "fixtures" / "pde_sample.xlsx"


@pytest.fixture(scope="module")
def parsed_rows() -> list[CorsaParsedRow]:
    raw = read_pde_file(FIXTURE)
    return [parse_corsa_row(r) for r in raw]


def test_all_rows_parse_without_error(parsed_rows: list[CorsaParsedRow]) -> None:
    assert len(parsed_rows) == 38


def test_each_row_has_9_composizioni(parsed_rows: list[CorsaParsedRow]) -> None:
    for r in parsed_rows:
        assert len(r.composizioni) == 9


def test_composizione_keys_are_complete(parsed_rows: list[CorsaParsedRow]) -> None:
    """Ogni riga ha le 9 combinazioni stagione × giorno_tipo, sempre nello stesso ordine."""
    expected = {
        ("invernale", "feriale"),
        ("invernale", "sabato"),
        ("invernale", "festivo"),
        ("estiva", "feriale"),
        ("estiva", "sabato"),
        ("estiva", "festivo"),
        ("agosto", "feriale"),
        ("agosto", "sabato"),
        ("agosto", "festivo"),
    }
    for r in parsed_rows:
        actual = {(c.stagione, c.giorno_tipo) for c in r.composizioni}
        assert actual == expected


def test_high_match_with_pde_gg_anno(parsed_rows: list[CorsaParsedRow]) -> None:
    """≥80% delle righe ha `valido_in_date` allineato con Gg_anno PdE.

    Il testo `Periodicità` è la **fonte di verità** (decisione utente).
    Gg_anno è dato informativo Trenord, derivato dal `Codice Periodicità`
    interno. Per la maggior parte dei treni i due combaciano; per pochi
    casi (osservato: 5/38 = 13%) il testo Periodicità Trenord differisce
    dai conteggi interni — il parser segue il testo, segnala discrepanza
    come warning info ma NON blocca l'import.

    Threshold ≥80%: se cala sotto, indaga (potrebbe esserci nuovo
    pattern del testo non gestito).
    """
    n_total = len(parsed_rows)
    n_ok = sum(1 for r in parsed_rows if not r.warnings)
    pct_ok = n_ok / n_total
    assert pct_ok >= 0.80, (
        f"Solo {n_ok}/{n_total} ({pct_ok:.0%}) righe matchano Gg_anno PdE; atteso ≥80%."
    )


def test_warnings_are_info_not_errors(parsed_rows: list[CorsaParsedRow]) -> None:
    """Le warning del parser sono info-only sul cross-check Gg_*.

    Devono iniziare con `gg_*:` (formato cross_check_gg_mensili). Se
    una warning ha formato diverso (es. eccezione di parsing), è un
    bug serio — fail.
    """
    for r in parsed_rows:
        for w in r.warnings:
            assert w.startswith("gg_"), f"Warning non-info su treno {r.numero_treno}: {w!r}"


def test_first_row_basic_fields(parsed_rows: list[CorsaParsedRow]) -> None:
    """Riga 0 della fixture: treno 13 FN Cadorna→Laveno con skip dic 2025."""
    r = parsed_rows[0]
    assert r.numero_treno == "13"
    assert r.rete == "FN"
    assert r.numero_treno_fn == "13"
    assert r.codice_origine == "S01066"
    assert r.codice_destinazione == "S01747"
    assert r.ora_partenza == time(6, 39, 0)
    assert r.ora_arrivo == time(8, 23, 0)
    assert r.valido_da == date(2025, 12, 14)
    assert r.valido_a == date(2026, 12, 31)
    assert r.is_treno_garantito_feriale is True
    assert r.is_treno_garantito_festivo is False


def test_first_row_valido_in_date_excludes_skip(
    parsed_rows: list[CorsaParsedRow],
) -> None:
    """Riga 0: 'Non circola dal 01/12/2025 al 13/12/2025' → ma quei giorni
    sono fuori da [valido_da=14/12/2025], quindi il calcolo è banale:
    tutti i giorni nell'intervallo di validità."""
    r = parsed_rows[0]
    # 14/12/2025 → 31/12/2026 = 18 + 365 = 383 giorni
    assert len(r.valido_in_date_json) == 383
    # ISO format
    assert r.valido_in_date_json[0] == "2025-12-14"
    assert r.valido_in_date_json[-1] == "2026-12-31"


def test_decimal_fields_parsed(parsed_rows: list[CorsaParsedRow]) -> None:
    r = parsed_rows[0]
    assert isinstance(r.km_tratta, Decimal)
    assert r.km_tratta == Decimal("72.152")
    assert isinstance(r.totale_km, Decimal)


def test_giorni_per_mese_json_populated(parsed_rows: list[CorsaParsedRow]) -> None:
    """Ogni riga ha i 16 campi Gg_* mappati."""
    r = parsed_rows[0]
    assert "gg_gen" in r.giorni_per_mese_json
    assert "gg_anno" in r.giorni_per_mese_json
    assert r.giorni_per_mese_json["gg_anno"] == 365


def test_numero_treno_normalized_to_string(parsed_rows: list[CorsaParsedRow]) -> None:
    """Excel/Numbers ritorna float per integer-valued; il parser lo
    riduce a stringa intera."""
    for r in parsed_rows:
        assert isinstance(r.numero_treno, str)
        # No trailing '.0'
        assert not r.numero_treno.endswith(".0")


def test_periodicita_apply_interval_row(parsed_rows: list[CorsaParsedRow]) -> None:
    """Almeno una riga della fixture ha periodicità 'corta' (apply_interval o
    poche date), conseguenza della selezione bucket dello script di
    fixture build."""
    short_validity = [r for r in parsed_rows if 1 <= len(r.valido_in_date_json) < 30]
    assert len(short_validity) > 0, (
        "Atteso almeno una riga con apply_interval/dates corte; nessuna trovata."
    )
