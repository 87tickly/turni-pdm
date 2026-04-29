"""Test Sprint 4.1 — programma materiale: filtri Pydantic + ORM smoke.

Coverage:
- `FiltroRegola`: validazione completa di campi/op/valori, con casi
  positivi e negativi.
- `ProgrammaMaterialeCreate`: validazione date, strict_options default,
  regole nested.
- ORM `ProgrammaMateriale` + `ProgrammaRegolaAssegnazione`: registrazione
  su `Base.metadata`.

I test sono **puri** (no DB) — il round-trip DB sarà nel test
integration di Sub 4.3 (API CRUD).
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from colazione.db import Base
from colazione.models.programmi import (
    ProgrammaMateriale,
    ProgrammaRegolaAssegnazione,
)
from colazione.schemas.programmi import (
    ComposizioneItem,
    FiltroRegola,
    ProgrammaMaterialeCreate,
    ProgrammaRegolaAssegnazioneCreate,
    StrictOptions,
)

# =====================================================================
# FiltroRegola — casi positivi
# =====================================================================


def test_filtro_codice_linea_eq_valido() -> None:
    f = FiltroRegola(campo="codice_linea", op="eq", valore="S5")
    assert f.campo == "codice_linea"
    assert f.op == "eq"
    assert f.valore == "S5"


def test_filtro_categoria_in_lista_valido() -> None:
    f = FiltroRegola(campo="categoria", op="in", valore=["RE", "R"])
    assert f.valore == ["RE", "R"]


def test_filtro_fascia_oraria_between_valido() -> None:
    f = FiltroRegola(
        campo="fascia_oraria",
        op="between",
        valore=["04:00", "15:59"],
    )
    assert f.valore == ["04:00", "15:59"]


def test_filtro_fascia_oraria_between_con_secondi() -> None:
    """Formato HH:MM:SS accettato."""
    f = FiltroRegola(
        campo="fascia_oraria",
        op="between",
        valore=["04:00:00", "15:59:59"],
    )
    assert f.valore == ["04:00:00", "15:59:59"]


def test_filtro_giorno_tipo_in_valido() -> None:
    f = FiltroRegola(campo="giorno_tipo", op="in", valore=["feriale", "sabato"])
    assert f.valore == ["feriale", "sabato"]


def test_filtro_treno_garantito_eq_bool() -> None:
    f = FiltroRegola(campo="is_treno_garantito_feriale", op="eq", valore=True)
    assert f.valore is True


# =====================================================================
# FiltroRegola — casi negativi (errori di validazione)
# =====================================================================


def test_filtro_campo_non_supportato_raises() -> None:
    with pytest.raises(ValidationError, match="non supportato"):
        FiltroRegola(campo="campo_inesistente", op="eq", valore="x")


def test_filtro_op_non_supportato_raises() -> None:
    with pytest.raises(ValidationError, match="non supportato"):
        FiltroRegola(campo="codice_linea", op="like", valore="S%")


def test_filtro_op_incompatibile_con_campo_raises() -> None:
    """`fascia_oraria` non accetta `eq` (solo between/gte/lte)."""
    with pytest.raises(ValidationError, match="non compatibile"):
        FiltroRegola(campo="fascia_oraria", op="eq", valore="04:00")


def test_filtro_eq_con_lista_raises() -> None:
    """op `eq` richiede valore scalare, non lista."""
    with pytest.raises(ValidationError, match="scalare"):
        FiltroRegola(campo="codice_linea", op="eq", valore=["S5", "S6"])


def test_filtro_in_con_lista_vuota_raises() -> None:
    with pytest.raises(ValidationError, match="lista non vuota"):
        FiltroRegola(campo="categoria", op="in", valore=[])


def test_filtro_between_con_un_solo_elemento_raises() -> None:
    with pytest.raises(ValidationError, match="esattamente 2"):
        FiltroRegola(campo="fascia_oraria", op="between", valore=["04:00"])


def test_filtro_giorno_tipo_valore_invalido_raises() -> None:
    with pytest.raises(ValidationError, match="non valido"):
        FiltroRegola(campo="giorno_tipo", op="in", valore=["domenica"])


def test_filtro_fascia_oraria_formato_errato_raises() -> None:
    with pytest.raises(ValidationError, match="non in formato"):
        FiltroRegola(campo="fascia_oraria", op="between", valore=["04AM", "16PM"])


def test_filtro_extra_field_raises() -> None:
    """Pydantic `extra=forbid`: campi extra non ammessi."""
    with pytest.raises(ValidationError):
        FiltroRegola.model_validate(
            {"campo": "codice_linea", "op": "eq", "valore": "S5", "extra": "x"}
        )


# =====================================================================
# StrictOptions
# =====================================================================


def test_strict_options_default_tutto_false() -> None:
    s = StrictOptions()
    assert s.no_corse_residue is False
    assert s.no_overcapacity is False
    assert s.no_aggancio_non_validato is False
    assert s.no_orphan_blocks is False
    assert s.no_giro_appeso is False
    assert s.no_km_eccesso is False


def test_strict_options_personalizzata() -> None:
    s = StrictOptions(no_corse_residue=True, no_overcapacity=True)
    assert s.no_corse_residue is True
    assert s.no_overcapacity is True
    assert s.no_aggancio_non_validato is False  # gli altri restano default


def test_strict_options_extra_field_raises() -> None:
    with pytest.raises(ValidationError):
        StrictOptions.model_validate({"no_invalid_flag": True})


# =====================================================================
# ProgrammaMaterialeCreate
# =====================================================================


def test_programma_create_minimo_valido() -> None:
    p = ProgrammaMaterialeCreate(
        nome="Test",
        valido_da=date(2026, 1, 1),
        valido_a=date(2026, 12, 31),
    )
    assert p.nome == "Test"
    assert p.n_giornate_default == 1
    assert p.fascia_oraria_tolerance_min == 30
    assert p.regole == []


def test_programma_create_validita_invertita_raises() -> None:
    with pytest.raises(ValidationError, match="valido_a deve essere"):
        ProgrammaMaterialeCreate(
            nome="X",
            valido_da=date(2026, 12, 31),
            valido_a=date(2026, 1, 1),
        )


def test_programma_create_con_regole_nested() -> None:
    """Una regola annidata viene validata in cascata."""
    p = ProgrammaMaterialeCreate(
        nome="Trenord 2025-2026",
        valido_da=date(2025, 12, 14),
        valido_a=date(2026, 4, 30),
        km_max_giornaliero=800,
        km_max_ciclo=5000,
        n_giornate_default=5,
        regole=[
            ProgrammaRegolaAssegnazioneCreate(
                filtri_json=[
                    FiltroRegola(campo="codice_linea", op="eq", valore="S5"),
                    FiltroRegola(
                        campo="fascia_oraria",
                        op="between",
                        valore=["04:00", "15:59"],
                    ),
                ],
                composizione=[ComposizioneItem(materiale_tipo_codice="ALe711", n_pezzi=3)],
                priorita=80,
            ),
        ],
    )
    assert p.km_max_ciclo == 5000
    assert len(p.regole) == 1
    assert p.regole[0].composizione[0].n_pezzi == 3
    assert p.regole[0].composizione[0].materiale_tipo_codice == "ALe711"
    assert p.regole[0].is_composizione_manuale is False
    assert len(p.regole[0].filtri_json) == 2


def test_programma_create_regola_filtri_invalidi_propagano_errore() -> None:
    """Errori dentro filtri_json di una regola fanno fallire il programma."""
    with pytest.raises(ValidationError, match="non supportato"):
        ProgrammaMaterialeCreate.model_validate(
            {
                "nome": "X",
                "valido_da": "2026-01-01",
                "valido_a": "2026-12-31",
                "regole": [
                    {
                        "filtri_json": [
                            {
                                "campo": "campo_inesistente",
                                "op": "eq",
                                "valore": "x",
                            }
                        ],
                        "composizione": [{"materiale_tipo_codice": "ALe711", "n_pezzi": 1}],
                    }
                ],
            }
        )


def test_regola_create_n_pezzi_zero_raises() -> None:
    with pytest.raises(ValidationError):
        ProgrammaRegolaAssegnazioneCreate(
            composizione=[ComposizioneItem(materiale_tipo_codice="ALe711", n_pezzi=0)]
        )


def test_regola_create_composizione_vuota_raises() -> None:
    with pytest.raises(ValidationError):
        ProgrammaRegolaAssegnazioneCreate(composizione=[])


def test_regola_create_priorita_oltre_100_raises() -> None:
    with pytest.raises(ValidationError):
        ProgrammaRegolaAssegnazioneCreate(
            composizione=[ComposizioneItem(materiale_tipo_codice="ALe711", n_pezzi=1)],
            priorita=150,
        )


def test_regola_create_composizione_mista_ok() -> None:
    """Composizione di 2+ elementi (es. ETR526+ETR425 per Tirano)."""
    r = ProgrammaRegolaAssegnazioneCreate(
        composizione=[
            ComposizioneItem(materiale_tipo_codice="ETR526", n_pezzi=1),
            ComposizioneItem(materiale_tipo_codice="ETR425", n_pezzi=1),
        ],
        is_composizione_manuale=False,
    )
    assert len(r.composizione) == 2
    assert r.composizione[0].materiale_tipo_codice == "ETR526"
    assert r.composizione[1].materiale_tipo_codice == "ETR425"


# =====================================================================
# ORM smoke (no DB)
# =====================================================================


def test_programma_materiale_registrato_su_metadata() -> None:
    """`ProgrammaMateriale` esiste su `Base.metadata.tables`."""
    assert "programma_materiale" in Base.metadata.tables
    assert "programma_regola_assegnazione" in Base.metadata.tables


def test_programma_materiale_columns_attese() -> None:
    """Schema ORM ha i campi attesi (verifica nomi colonne)."""
    cols = {c.name for c in Base.metadata.tables["programma_materiale"].columns}
    expected = {
        "id",
        "azienda_id",
        "nome",
        "valido_da",
        "valido_a",
        "stato",
        "km_max_giornaliero",
        "km_max_ciclo",
        "n_giornate_default",
        "fascia_oraria_tolerance_min",
        "strict_options_json",
        "created_by_user_id",
        "created_at",
        "updated_at",
    }
    assert expected.issubset(cols)


def test_regola_columns_attese() -> None:
    cols = {c.name for c in Base.metadata.tables["programma_regola_assegnazione"].columns}
    expected = {
        "id",
        "programma_id",
        "filtri_json",
        "composizione_json",
        "is_composizione_manuale",
        "materiale_tipo_codice",
        "numero_pezzi",
        "priorita",
        "note",
        "created_at",
    }
    assert expected.issubset(cols)


def test_programma_orm_instanziabile() -> None:
    """L'ORM si può istanziare (no DB)."""
    p = ProgrammaMateriale(
        azienda_id=1,
        nome="Test",
        valido_da=date(2026, 1, 1),
        valido_a=date(2026, 12, 31),
        strict_options_json={"no_corse_residue": False},
    )
    assert p.nome == "Test"
    assert p.azienda_id == 1


def test_regola_orm_instanziabile() -> None:
    r = ProgrammaRegolaAssegnazione(
        programma_id=1,
        filtri_json=[
            {"campo": "codice_linea", "op": "eq", "valore": "S5"},
        ],
        materiale_tipo_codice="ALe711",
        numero_pezzi=3,
        priorita=80,
    )
    assert r.numero_pezzi == 3
    assert r.filtri_json[0]["campo"] == "codice_linea"


def test_giro_blocco_ha_nuovi_campi() -> None:
    """Sprint 4.1 alter: GiroBlocco ha is_validato_utente + metadata_json."""
    cols = {c.name for c in Base.metadata.tables["giro_blocco"].columns}
    assert "is_validato_utente" in cols
    assert "metadata_json" in cols


# =====================================================================
# Sprint 5.1: ComposizioneItem + tabelle nuove + materiale.localita_default
# =====================================================================


def test_composizione_item_valido() -> None:
    c = ComposizioneItem(materiale_tipo_codice="ETR526", n_pezzi=2)
    assert c.materiale_tipo_codice == "ETR526"
    assert c.n_pezzi == 2


def test_composizione_item_n_pezzi_zero_raises() -> None:
    with pytest.raises(ValidationError):
        ComposizioneItem(materiale_tipo_codice="ETR526", n_pezzi=0)


def test_composizione_item_n_pezzi_negativo_raises() -> None:
    with pytest.raises(ValidationError):
        ComposizioneItem(materiale_tipo_codice="ETR526", n_pezzi=-1)


def test_composizione_item_materiale_codice_vuoto_raises() -> None:
    with pytest.raises(ValidationError):
        ComposizioneItem(materiale_tipo_codice="", n_pezzi=1)


def test_composizione_item_extra_field_raises() -> None:
    with pytest.raises(ValidationError):
        ComposizioneItem.model_validate(
            {"materiale_tipo_codice": "ETR526", "n_pezzi": 1, "garbage": "x"}
        )


def test_localita_stazione_vicina_registrato() -> None:
    """Sprint 5.1: tabella whitelist M:N stazioni-sede."""
    assert "localita_stazione_vicina" in Base.metadata.tables
    cols = {c.name for c in Base.metadata.tables["localita_stazione_vicina"].columns}
    expected = {"id", "localita_manutenzione_id", "stazione_codice", "created_at"}
    assert expected.issubset(cols)


def test_materiale_accoppiamento_ammesso_registrato() -> None:
    """Sprint 5.1: tabella vincoli accoppiamento materiali."""
    assert "materiale_accoppiamento_ammesso" in Base.metadata.tables
    cols = {c.name for c in Base.metadata.tables["materiale_accoppiamento_ammesso"].columns}
    expected = {
        "id",
        "materiale_a_codice",
        "materiale_b_codice",
        "note",
        "created_at",
    }
    assert expected.issubset(cols)


def test_materiale_tipo_ha_localita_default() -> None:
    """Sprint 5.1: materiale_tipo.localita_manutenzione_default_id (nullable)."""
    cols = {c.name for c in Base.metadata.tables["materiale_tipo"].columns}
    assert "localita_manutenzione_default_id" in cols


def test_regola_orm_con_composizione_completa() -> None:
    """ORM accetta sia composizione_json che legacy (post-migration 0007)."""
    r = ProgrammaRegolaAssegnazione(
        programma_id=1,
        filtri_json=[],
        composizione_json=[
            {"materiale_tipo_codice": "ETR526", "n_pezzi": 1},
            {"materiale_tipo_codice": "ETR425", "n_pezzi": 1},
        ],
        is_composizione_manuale=False,
        # Legacy popolati dal primo elemento (per retrocompat fino a Sub 5.5)
        materiale_tipo_codice="ETR526",
        numero_pezzi=1,
        priorita=80,
    )
    assert len(r.composizione_json) == 2
    assert r.is_composizione_manuale is False


def test_programma_materiale_orm_con_km_max_ciclo() -> None:
    """ORM accetta km_max_ciclo (Sprint 5.1)."""
    p = ProgrammaMateriale(
        azienda_id=1,
        nome="Test ciclo",
        valido_da=date(2026, 1, 1),
        valido_a=date(2026, 12, 31),
        km_max_ciclo=10000,
        strict_options_json={"no_giro_appeso": False},
    )
    assert p.km_max_ciclo == 10000
