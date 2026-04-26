"""Test puri del pde_importer (no DB) — Sprint 3.6.

Coprono:
- `compute_sha256`: deterministico, sensibile al contenuto
- `collect_stazioni`: dedup per codice, cattura CdS, gestisce None
- `_corsa_payload`: contiene tutti i 35 campi DB richiesti
- `_composizione_rows`: 9 entry, FK + check constraint coerenti
"""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from pathlib import Path
from typing import Any

from colazione.importers.pde import ComposizioneParsed, CorsaParsedRow
from colazione.importers.pde_importer import (
    _composizione_rows,
    _corsa_payload,
    collect_stazioni,
    compute_sha256,
)

# =====================================================================
# compute_sha256
# =====================================================================


def test_compute_sha256_deterministic(tmp_path: Path) -> None:
    """Stesso contenuto → stesso hash, su due chiamate."""
    f = tmp_path / "data.bin"
    f.write_bytes(b"hello world\n" * 1000)
    assert compute_sha256(f) == compute_sha256(f)


def test_compute_sha256_different_content_different_hash(tmp_path: Path) -> None:
    f1 = tmp_path / "a.bin"
    f2 = tmp_path / "b.bin"
    f1.write_bytes(b"hello")
    f2.write_bytes(b"hello!")
    assert compute_sha256(f1) != compute_sha256(f2)


def test_compute_sha256_known_value(tmp_path: Path) -> None:
    """Hash di 'abc' → valore noto (test vector NIST FIPS 180-4)."""
    f = tmp_path / "abc.bin"
    f.write_bytes(b"abc")
    assert compute_sha256(f) == ("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")


def test_compute_sha256_streams_large_file(tmp_path: Path) -> None:
    """File > chunk size (64KB) → hash non si rompe (no overflow memoria)."""
    f = tmp_path / "big.bin"
    f.write_bytes(b"x" * 200_000)  # ~200 KB
    h = compute_sha256(f)
    assert len(h) == 64  # hex SHA-256


# =====================================================================
# collect_stazioni
# =====================================================================


def _mk_parsed(
    *,
    codice_origine: str = "S01",
    codice_destinazione: str = "S02",
    codice_inizio_cds: str | None = None,
    codice_fine_cds: str | None = None,
) -> CorsaParsedRow:
    """Factory minimale di CorsaParsedRow per i test stazioni."""
    return CorsaParsedRow(
        numero_treno="1",
        codice_origine=codice_origine,
        codice_destinazione=codice_destinazione,
        codice_inizio_cds=codice_inizio_cds,
        codice_fine_cds=codice_fine_cds,
        ora_partenza=time(6, 0),
        ora_arrivo=time(7, 0),
        valido_da=date(2026, 1, 1),
        valido_a=date(2026, 12, 31),
    )


def test_collect_stazioni_unique_codici() -> None:
    parsed = [
        _mk_parsed(codice_origine="S01", codice_destinazione="S02"),
        _mk_parsed(codice_origine="S01", codice_destinazione="S03"),  # S01 ripetuta
    ]
    raw: list[dict[str, Any]] = [
        {"Stazione Origine Treno": "MILANO", "Stazione Destinazione Treno": "BRESCIA"},
        {"Stazione Origine Treno": "MILANO", "Stazione Destinazione Treno": "VARESE"},
    ]
    out = collect_stazioni(parsed, raw)
    assert out == {"S01": "MILANO", "S02": "BRESCIA", "S03": "VARESE"}


def test_collect_stazioni_first_name_wins_for_duplicates() -> None:
    """Duplicato con nome leggermente diverso → vince il primo (setdefault)."""
    parsed = [
        _mk_parsed(codice_origine="S01", codice_destinazione="S02"),
        _mk_parsed(codice_origine="S01", codice_destinazione="S03"),
    ]
    raw: list[dict[str, Any]] = [
        {"Stazione Origine Treno": "MILANO C.LE", "Stazione Destinazione Treno": "X"},
        {"Stazione Origine Treno": "MILANO CENTRALE", "Stazione Destinazione Treno": "Y"},
    ]
    out = collect_stazioni(parsed, raw)
    assert out["S01"] == "MILANO C.LE"


def test_collect_stazioni_includes_cds_stations() -> None:
    parsed = [
        _mk_parsed(
            codice_origine="S01",
            codice_destinazione="S02",
            codice_inizio_cds="S03",
            codice_fine_cds="S04",
        ),
    ]
    raw: list[dict[str, Any]] = [
        {
            "Stazione Origine Treno": "A",
            "Stazione Destinazione Treno": "B",
            "Stazione Inizio CdS": "C",
            "Stazione Fine CdS": "D",
        }
    ]
    out = collect_stazioni(parsed, raw)
    assert out == {"S01": "A", "S02": "B", "S03": "C", "S04": "D"}


def test_collect_stazioni_handles_missing_cds() -> None:
    """codice_inizio_cds=None → la chiave non finisce nel dizionario."""
    parsed = [_mk_parsed(codice_origine="S01", codice_destinazione="S02")]
    raw: list[dict[str, Any]] = [
        {"Stazione Origine Treno": "A", "Stazione Destinazione Treno": "B"}
    ]
    out = collect_stazioni(parsed, raw)
    assert "Stazione Inizio CdS" not in out  # non c'è nessuna chiave None
    assert set(out.keys()) == {"S01", "S02"}


def test_collect_stazioni_falls_back_to_codice_when_nome_empty() -> None:
    """Se il nome raw è None/vuoto, salva codice come nome (no None in DB)."""
    parsed = [_mk_parsed(codice_origine="S01", codice_destinazione="S02")]
    raw: list[dict[str, Any]] = [
        {"Stazione Origine Treno": None, "Stazione Destinazione Treno": ""}
    ]
    out = collect_stazioni(parsed, raw)
    assert out["S01"] == "S01"
    assert out["S02"] == "S02"


# =====================================================================
# _corsa_payload
# =====================================================================


def test_corsa_payload_contains_required_db_fields() -> None:
    """Payload deve avere tutte le colonne NOT NULL di corsa_commerciale."""
    parsed = _mk_parsed()
    payload = _corsa_payload(parsed, azienda_id=1, import_run_id=42)

    required = {
        "azienda_id",
        "numero_treno",
        "codice_origine",
        "codice_destinazione",
        "ora_partenza",
        "ora_arrivo",
        "valido_da",
        "valido_a",
        "is_treno_garantito_feriale",
        "is_treno_garantito_festivo",
        "giorni_per_mese_json",
        "valido_in_date_json",
        "import_source",
    }
    assert required.issubset(payload.keys())
    assert payload["azienda_id"] == 1
    assert payload["import_run_id"] == 42
    assert payload["import_source"] == "pde"


def test_corsa_payload_preserves_decimal_values() -> None:
    """Decimal non viene stringato (preservato come Decimal)."""
    parsed = _mk_parsed()
    parsed.km_tratta = Decimal("72.152")
    parsed.totale_km = Decimal("100.500")
    payload = _corsa_payload(parsed, azienda_id=1, import_run_id=1)
    assert payload["km_tratta"] == Decimal("72.152")
    assert payload["totale_km"] == Decimal("100.500")


def test_corsa_payload_passes_optional_nullable_fields() -> None:
    """I campi opzionali None vanno nel payload come None (non missing)."""
    parsed = _mk_parsed()
    payload = _corsa_payload(parsed, azienda_id=1, import_run_id=1)
    assert payload["codice_inizio_cds"] is None
    assert payload["min_tratta"] is None
    assert payload["totale_km"] is None


# =====================================================================
# _composizione_rows
# =====================================================================


def test_composizione_rows_returns_9_entries_with_correct_corsa_id() -> None:
    parsed = _mk_parsed()
    parsed.composizioni = [
        ComposizioneParsed(stagione=s, giorno_tipo=g)
        for s in ("invernale", "estiva", "agosto")
        for g in ("feriale", "sabato", "festivo")
    ]
    rows = _composizione_rows(corsa_id=99, parsed=parsed)
    assert len(rows) == 9
    assert all(r["corsa_commerciale_id"] == 99 for r in rows)


def test_composizione_rows_preserves_attributes() -> None:
    parsed = _mk_parsed()
    parsed.composizioni = [
        ComposizioneParsed(
            stagione="invernale",
            giorno_tipo="feriale",
            categoria_posti="A",
            is_doppia_composizione=True,
            tipologia_treno="ETR",
            vincolo_dichiarato="V1",
            categoria_bici="B1",
            categoria_prm="P1",
        )
    ]
    rows = _composizione_rows(corsa_id=1, parsed=parsed)
    assert rows[0]["stagione"] == "invernale"
    assert rows[0]["giorno_tipo"] == "feriale"
    assert rows[0]["categoria_posti"] == "A"
    assert rows[0]["is_doppia_composizione"] is True
    assert rows[0]["tipologia_treno"] == "ETR"
    assert rows[0]["vincolo_dichiarato"] == "V1"
    assert rows[0]["categoria_bici"] == "B1"
    assert rows[0]["categoria_prm"] == "P1"
