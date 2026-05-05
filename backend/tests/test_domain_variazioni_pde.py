"""Pure unit test del modulo ``domain/variazioni_pde``.

Sprint 8.0 MR 5.bis (entry 173). Niente DB qui — solo dataclass +
funzioni pure di pianificazione. I test integration end-to-end stanno
in ``test_api_programmi_conferma.py`` sezione "Applica variazioni PdE".
"""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal

from colazione.domain.variazioni_pde import (
    CorsaEsistente,
    OpInsert,
    OpUpdateOrari,
    OpUpdateValidoInDate,
    ParsedTarget,
    pianifica_integrazione,
    pianifica_variazione_cancellazione,
    pianifica_variazione_interruzione,
    pianifica_variazione_orario,
)

# =====================================================================
# Helpers
# =====================================================================


def _esistente(
    *,
    id: int = 1,
    row_hash: str = "h_existing",
    numero_treno: str = "13",
    valido_da: date = date(2026, 1, 1),
    valido_a: date = date(2026, 12, 31),
    codice_origine: str = "S01",
    codice_destinazione: str = "S02",
    valido_in_date_json: tuple[str, ...] = (),
) -> CorsaEsistente:
    return CorsaEsistente(
        id=id,
        row_hash=row_hash,
        numero_treno=numero_treno,
        valido_da=valido_da,
        valido_a=valido_a,
        codice_origine=codice_origine,
        codice_destinazione=codice_destinazione,
        valido_in_date_json=valido_in_date_json,
    )


def _target(
    *,
    row_hash: str = "h_target",
    numero_treno: str = "13",
    valido_da: date = date(2026, 1, 1),
    valido_a: date = date(2026, 12, 31),
    codice_origine: str = "S01",
    codice_destinazione: str = "S02",
    ora_partenza: time = time(6, 39),
    ora_arrivo: time = time(7, 30),
    ora_inizio_cds: time | None = None,
    ora_fine_cds: time | None = None,
    min_tratta: int | None = 51,
    min_cds: int | None = None,
    km_tratta: Decimal | None = Decimal("45.5"),
    km_cds: Decimal | None = None,
    valido_in_date_json: tuple[str, ...] = (),
) -> ParsedTarget:
    return ParsedTarget(
        row_hash=row_hash,
        numero_treno=numero_treno,
        valido_da=valido_da,
        valido_a=valido_a,
        codice_origine=codice_origine,
        codice_destinazione=codice_destinazione,
        ora_partenza=ora_partenza,
        ora_arrivo=ora_arrivo,
        ora_inizio_cds=ora_inizio_cds,
        ora_fine_cds=ora_fine_cds,
        min_tratta=min_tratta,
        min_cds=min_cds,
        km_tratta=km_tratta,
        km_cds=km_cds,
        valido_in_date_json=valido_in_date_json,
    )


# =====================================================================
# INTEGRAZIONE
# =====================================================================


def test_integrazione_corsa_nuova_genera_op_insert() -> None:
    targets = [_target(row_hash="h_new")]
    result = pianifica_integrazione(targets, [])
    assert result.n_create == 1
    assert result.n_update == 0
    assert isinstance(result.insert[0], OpInsert)
    assert result.insert[0].parsed_index == 0
    assert result.insert[0].row_hash == "h_new"
    assert result.warnings == []


def test_integrazione_idempotente_se_hash_gia_esiste() -> None:
    """Re-applicare la stessa integrazione (stesso row_hash) → no INSERT."""
    targets = [_target(row_hash="h_dup")]
    esistenti = [_esistente(row_hash="h_dup")]
    result = pianifica_integrazione(targets, esistenti)
    assert result.n_create == 0
    # Warning informativo: tutte le corse erano già presenti.
    assert len(result.warnings) == 1
    assert "già presenti in DB" in result.warnings[0]


def test_integrazione_misto_nuove_e_duplicate() -> None:
    targets = [
        _target(row_hash="h1"),
        _target(row_hash="h2"),
        _target(row_hash="h3"),
    ]
    esistenti = [_esistente(row_hash="h2")]
    result = pianifica_integrazione(targets, esistenti)
    assert result.n_create == 2
    assert {op.row_hash for op in result.insert} == {"h1", "h3"}
    # Insert preserva l'ordine original (parsed_index ascending)
    assert [op.parsed_index for op in result.insert] == [0, 2]


def test_integrazione_duplicato_nel_file_preservato() -> None:
    """Stesso hash 2 volte nel file, 0 in DB → 2 OpInsert (no dedup)."""
    targets = [_target(row_hash="h_x"), _target(row_hash="h_x")]
    result = pianifica_integrazione(targets, [])
    assert result.n_create == 2


# =====================================================================
# VARIAZIONE_ORARIO
# =====================================================================


def test_orario_match_5_campi_genera_update() -> None:
    targets = [
        _target(
            numero_treno="42",
            valido_da=date(2026, 3, 1),
            valido_a=date(2026, 5, 31),
            codice_origine="A",
            codice_destinazione="B",
            ora_partenza=time(8, 15),
            ora_arrivo=time(9, 0),
        )
    ]
    esistenti = [
        _esistente(
            id=99,
            numero_treno="42",
            valido_da=date(2026, 3, 1),
            valido_a=date(2026, 5, 31),
            codice_origine="A",
            codice_destinazione="B",
        ),
    ]
    result = pianifica_variazione_orario(targets, esistenti)
    assert result.n_update == 1
    op = result.update_orari[0]
    assert isinstance(op, OpUpdateOrari)
    assert op.corsa_id == 99
    assert op.ora_partenza == time(8, 15)
    assert op.ora_arrivo == time(9, 0)
    assert result.warnings == []


def test_orario_no_match_emette_warning() -> None:
    """Corsa target non in DB → warning, niente update."""
    targets = [_target(numero_treno="999_inesistente")]
    esistenti = [_esistente(numero_treno="13")]
    result = pianifica_variazione_orario(targets, esistenti)
    assert result.n_update == 0
    assert len(result.warnings) == 1
    assert "corsa target non trovata" in result.warnings[0]


def test_orario_match_ambiguo_applica_a_tutti() -> None:
    """2 corse identiche per chiave a 5 → applica a entrambe + warning."""
    targets = [_target(numero_treno="13")]
    esistenti = [
        _esistente(id=1, numero_treno="13"),
        _esistente(id=2, numero_treno="13", row_hash="h_dup_2"),
    ]
    result = pianifica_variazione_orario(targets, esistenti)
    assert result.n_update == 2
    assert {op.corsa_id for op in result.update_orari} == {1, 2}
    assert any("match ambiguo" in w for w in result.warnings)


def test_orario_diverse_origini_no_match() -> None:
    """Stesso numero_treno + intervallo, ma origini diverse → no match."""
    targets = [_target(numero_treno="13", codice_origine="A")]
    esistenti = [_esistente(numero_treno="13", codice_origine="B")]
    result = pianifica_variazione_orario(targets, esistenti)
    assert result.n_update == 0
    assert len(result.warnings) == 1


# =====================================================================
# VARIAZIONE_INTERRUZIONE
# =====================================================================


def test_interruzione_intersezione_date() -> None:
    """Date esistenti = {1,2,3,4,5}, file dichiara {1,2,3} → DB → {1,2,3}."""
    targets = [
        _target(
            numero_treno="13",
            valido_in_date_json=(
                "2026-03-01",
                "2026-03-02",
                "2026-03-03",
            ),
        )
    ]
    esistenti = [
        _esistente(
            id=10,
            numero_treno="13",
            valido_in_date_json=(
                "2026-03-01",
                "2026-03-02",
                "2026-03-03",
                "2026-03-04",
                "2026-03-05",
            ),
        )
    ]
    result = pianifica_variazione_interruzione(targets, esistenti)
    assert result.n_update == 1
    op = result.update_valido_in_date[0]
    assert isinstance(op, OpUpdateValidoInDate)
    assert op.corsa_id == 10
    assert op.valido_in_date_json == (
        "2026-03-01",
        "2026-03-02",
        "2026-03-03",
    )


def test_interruzione_idempotente_se_nessuna_data_da_rimuovere() -> None:
    """File dichiara superset di esistente → niente da rimuovere."""
    targets = [
        _target(
            valido_in_date_json=("2026-03-01", "2026-03-02", "2026-03-03"),
        )
    ]
    esistenti = [_esistente(valido_in_date_json=("2026-03-01", "2026-03-02"))]
    result = pianifica_variazione_interruzione(targets, esistenti)
    assert result.n_update == 0
    # Warning informativo: il file dichiara date non in DB (extra ignorate).
    assert len(result.warnings) == 1
    assert "non presenti in DB" in result.warnings[0]


def test_interruzione_match_chiave_3_non_5() -> None:
    """Match deve trovare anche corse con origine/destinazione differenti."""
    targets = [
        _target(
            numero_treno="13",
            valido_da=date(2026, 1, 1),
            valido_a=date(2026, 12, 31),
            codice_origine="X",  # Diversa dall'esistente
            codice_destinazione="Y",
            valido_in_date_json=(),  # tutte le date interrotte
        )
    ]
    esistenti = [
        _esistente(
            id=10,
            numero_treno="13",
            valido_da=date(2026, 1, 1),
            valido_a=date(2026, 12, 31),
            codice_origine="A",  # Diversa dal target!
            codice_destinazione="B",
            valido_in_date_json=("2026-03-01",),
        )
    ]
    result = pianifica_variazione_interruzione(targets, esistenti)
    assert result.n_update == 1
    assert result.update_valido_in_date[0].valido_in_date_json == ()


def test_interruzione_target_vuoto_warning_cancellazione_totale() -> None:
    """Target con valido_in_date_json=() = interruzione totale,
    semanticamente vicina a CANCELLAZIONE. Warning informativo."""
    targets = [_target(numero_treno="13", valido_in_date_json=())]
    esistenti = [
        _esistente(
            numero_treno="13",
            valido_in_date_json=("2026-03-01", "2026-03-02"),
        )
    ]
    result = pianifica_variazione_interruzione(targets, esistenti)
    assert result.n_update == 1
    assert result.update_valido_in_date[0].valido_in_date_json == ()
    assert any("cancellazione totale" in w for w in result.warnings)


def test_interruzione_no_match_warning() -> None:
    targets = [_target(numero_treno="999_unknown")]
    esistenti = [_esistente(numero_treno="13")]
    result = pianifica_variazione_interruzione(targets, esistenti)
    assert result.n_update == 0
    assert len(result.warnings) == 1
    assert "corsa target non trovata" in result.warnings[0]


# =====================================================================
# VARIAZIONE_CANCELLAZIONE
# =====================================================================


def test_cancellazione_svuota_valido_in_date() -> None:
    targets = [_target(numero_treno="13")]
    esistenti = [
        _esistente(
            id=42,
            numero_treno="13",
            valido_in_date_json=("2026-03-01", "2026-03-02"),
        )
    ]
    result = pianifica_variazione_cancellazione(targets, esistenti)
    assert result.n_update == 1
    op = result.update_valido_in_date[0]
    assert op.corsa_id == 42
    assert op.valido_in_date_json == ()


def test_cancellazione_idempotente_se_gia_vuota() -> None:
    """Corsa già cancellata (lista vuota) → skip."""
    targets = [_target(numero_treno="13")]
    esistenti = [
        _esistente(numero_treno="13", valido_in_date_json=()),
    ]
    result = pianifica_variazione_cancellazione(targets, esistenti)
    assert result.n_update == 0


def test_cancellazione_match_ambiguo_applica_a_tutti() -> None:
    targets = [_target(numero_treno="13")]
    esistenti = [
        _esistente(id=1, numero_treno="13", valido_in_date_json=("2026-03-01",)),
        _esistente(
            id=2,
            numero_treno="13",
            row_hash="h_other",
            valido_in_date_json=("2026-03-02",),
        ),
    ]
    result = pianifica_variazione_cancellazione(targets, esistenti)
    assert result.n_update == 2
    assert all(op.valido_in_date_json == () for op in result.update_valido_in_date)
    assert any("match ambiguo" in w for w in result.warnings)


def test_cancellazione_no_match_warning() -> None:
    targets = [_target(numero_treno="999")]
    result = pianifica_variazione_cancellazione(targets, [])
    assert result.n_update == 0
    assert len(result.warnings) == 1


# =====================================================================
# Frozen dataclass invariants
# =====================================================================


def test_dataclass_op_insert_frozen() -> None:
    op = OpInsert(parsed_index=0, row_hash="x")
    assert op == OpInsert(parsed_index=0, row_hash="x")
    # Hashable (per uso in set)
    assert {op} == {OpInsert(parsed_index=0, row_hash="x")}


def test_dataclass_corsa_esistente_immutable_dates() -> None:
    """``valido_in_date_json`` deve essere tuple (non list) per freeze."""
    c = _esistente(valido_in_date_json=("2026-01-01",))
    assert isinstance(c.valido_in_date_json, tuple)


def test_risultato_n_create_n_update_aggregano() -> None:
    targets = [_target(row_hash="new_a"), _target(row_hash="new_b")]
    result = pianifica_integrazione(targets, [])
    assert result.n_create == 2
    assert result.n_update == 0
