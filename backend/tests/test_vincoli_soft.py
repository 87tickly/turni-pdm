"""Test per ``domain/builder_giro/vincoli_soft.py`` (Sprint 8.1 MR-A1).

Foundation del refactor builder esplora-e-rilassa. Questi test verificano
che le strutture dati siano:
- Immutabili (dataclass frozen)
- Validate al costruttore (peso, livello)
- La factory ``tier_vincoli_default`` ritorni una sequenza coerente
  con la decisione utente Q1=b (5 tier ordinati con pesi crescenti).
"""

from __future__ import annotations

import dataclasses

import pytest

from colazione.domain.builder_giro.vincoli_soft import (
    Tier,
    TipoRilassamento,
    TipoVincoloSoft,
    VincoloSoft,
    tier_vincoli_default,
)

# =====================================================================
# Enum
# =====================================================================


def test_tipo_vincolo_soft_valori() -> None:
    """Gli enum corrispondono ai vincoli del programma materiale."""
    assert TipoVincoloSoft.LINEA.value == "linea"
    assert TipoVincoloSoft.MATERIALE.value == "materiale"
    assert TipoVincoloSoft.SEDE_CHIUSURA.value == "sede_chiusura"
    assert TipoVincoloSoft.DURATA_GIORNATE.value == "durata_giornate"
    assert TipoVincoloSoft.SOSTA_DIURNA.value == "sosta_diurna"
    assert TipoVincoloSoft.SERVIZIO_GIORNATA.value == "servizio_giornata"


def test_tipo_rilassamento_valori() -> None:
    assert TipoRilassamento.PREFERENZA.value == "preferenza"
    assert TipoRilassamento.FALLBACK_GOVERNATO.value == "fallback_governato"
    assert TipoRilassamento.HARD_BLOCK.value == "hard_block"


# =====================================================================
# VincoloSoft
# =====================================================================


def test_vincolo_soft_default_peso_e_rilassamento() -> None:
    v = VincoloSoft(tipo=TipoVincoloSoft.LINEA, valore_target="R11")
    assert v.peso == 50
    assert v.rilassamento == TipoRilassamento.FALLBACK_GOVERNATO
    assert v.metadata == {}


def test_vincolo_soft_frozen() -> None:
    v = VincoloSoft(tipo=TipoVincoloSoft.LINEA, valore_target="R11")
    with pytest.raises(dataclasses.FrozenInstanceError):
        v.peso = 99  # type: ignore[misc]


@pytest.mark.parametrize("peso_invalido", [-1, 101, -100, 200])
def test_vincolo_soft_peso_fuori_range_solleva(peso_invalido: int) -> None:
    with pytest.raises(ValueError, match="VincoloSoft.peso"):
        VincoloSoft(
            tipo=TipoVincoloSoft.LINEA,
            valore_target="R11",
            peso=peso_invalido,
        )


@pytest.mark.parametrize("peso_valido", [0, 1, 50, 100])
def test_vincolo_soft_peso_in_range_accettato(peso_valido: int) -> None:
    v = VincoloSoft(
        tipo=TipoVincoloSoft.LINEA, valore_target="R11", peso=peso_valido
    )
    assert v.peso == peso_valido


# =====================================================================
# Tier
# =====================================================================


def test_tier_frozen() -> None:
    t = Tier(livello=0, nome="esatto")
    with pytest.raises(dataclasses.FrozenInstanceError):
        t.livello = 1  # type: ignore[misc]


def test_tier_livello_negativo_solleva() -> None:
    with pytest.raises(ValueError, match="Tier.livello"):
        Tier(livello=-1, nome="invalido")


def test_tier_default_vincoli_e_descrizione_vuoti() -> None:
    t = Tier(livello=0, nome="esatto")
    assert t.vincoli == ()
    assert t.descrizione == ""


# =====================================================================
# Factory tier_vincoli_default
# =====================================================================


def test_tier_default_ritorna_5_tier() -> None:
    """5 tier (0..4) come da decisione utente Q1=b 2026-05-08."""
    tiers = tier_vincoli_default()
    assert len(tiers) == 5


def test_tier_default_ordinati_per_livello_crescente() -> None:
    tiers = tier_vincoli_default()
    livelli = [t.livello for t in tiers]
    assert livelli == [0, 1, 2, 3, 4]


def test_tier_default_nomi_attesi() -> None:
    tiers = tier_vincoli_default()
    nomi = [t.nome for t in tiers]
    assert nomi == [
        "esatto",
        "materiale_compatibile",
        "linea_adiacente",
        "qualsiasi_con_vuoto",
        "marker",
    ]


def test_tier_default_nomi_unici() -> None:
    tiers = tier_vincoli_default()
    nomi = {t.nome for t in tiers}
    assert len(nomi) == len(tiers)


def test_tier_default_esatto_non_ha_vincoli() -> None:
    """Il tier 0 (esatto) replica il comportamento legacy 'rigido':
    nessun rilassamento applicato.
    """
    tiers = tier_vincoli_default()
    tier_esatto = tiers[0]
    assert tier_esatto.livello == 0
    assert tier_esatto.nome == "esatto"
    assert tier_esatto.vincoli == ()


def test_tier_default_marker_ha_hard_block() -> None:
    """Il tier 4 (marker) usa HARD_BLOCK: oltre questo, ciclo aperto
    irrisolto persistito per intervento manuale (decisione utente Q2=b).
    """
    tiers = tier_vincoli_default()
    tier_marker = tiers[-1]
    assert tier_marker.nome == "marker"
    assert len(tier_marker.vincoli) >= 1
    assert all(
        v.rilassamento == TipoRilassamento.HARD_BLOCK
        for v in tier_marker.vincoli
    )


def test_tier_default_pesi_crescono_con_livello() -> None:
    """I pesi del vincolo LINEA crescono lungo i tier 1→4 (penalty
    cumulativa: il motore preferisce soluzioni a tier basso).
    """
    tiers = tier_vincoli_default()
    pesi_linea: list[int] = []
    for t in tiers[1:]:  # skip tier 0 (no vincoli)
        for v in t.vincoli:
            if v.tipo == TipoVincoloSoft.LINEA:
                pesi_linea.append(v.peso)
                break
    assert pesi_linea == sorted(pesi_linea)
    assert pesi_linea[0] < pesi_linea[-1]


def test_tier_default_deterministic() -> None:
    """La factory è deterministica: due chiamate restituiscono tier
    uguali (struttura immutabile, ricostruita ogni volta ma identica).
    """
    a = tier_vincoli_default()
    b = tier_vincoli_default()
    assert a == b


# =====================================================================
# Re-export builder_giro/__init__.py
# =====================================================================


def test_re_export_da_builder_giro_init() -> None:
    """Le strutture sono raggiungibili dal package builder_giro."""
    from colazione.domain import builder_giro

    assert builder_giro.Tier is Tier
    assert builder_giro.TipoVincoloSoft is TipoVincoloSoft
    assert builder_giro.TipoRilassamento is TipoRilassamento
    assert builder_giro.VincoloSoft is VincoloSoft
    assert builder_giro.tier_vincoli_default is tier_vincoli_default
