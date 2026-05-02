"""Test unit del validator vincoli inviolabili (`domain/vincoli/inviolabili.py`).

Test puri (no DB): mockano `CorsaCommerciale` con dataclass minimi e
chiamano direttamente ``valida_regola()``.

Coverage dei 2 vincoli HARD del JSON `data/vincoli_materiale_inviolabili.json`:
1. tecnico_elettrico_no_linee_diesel (blacklist)
2. contrattuale_tilo_flirt_524 (whitelist)

Entry 92: i 5 vincoli operativi (ATR803, ATR125, ATR115, ALn668, D520)
sono stati eliminati perché ingestibili (ogni linea ha decine di
sub-tratte, falsi positivi sui pattern bidir capolinea-capolinea).
La responsabilità sulle scelte operative torna al pianificatore.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

import pytest

from colazione.domain.vincoli import carica_vincoli, valida_regola
from colazione.domain.vincoli.inviolabili import Vincolo


# =====================================================================
# Fixtures
# =====================================================================


@dataclass
class CorsaMock:
    """Minimo CorsaLike per i test (campi referenziati dai filtri + dal validator)."""

    numero_treno: str
    codice_origine: str
    codice_destinazione: str
    codice_linea: str | None = None
    direttrice: str | None = None
    categoria: str | None = None
    rete: str | None = None
    is_treno_garantito_feriale: bool = False
    is_treno_garantito_festivo: bool = False
    fascia_oraria: str | None = None
    ora_partenza: time = time(8, 0)
    ora_arrivo: time = time(9, 0)
    codice_origine_cds: str | None = None
    codice_destinazione_cds: str | None = None


# Lookup stazioni: codice → nome (i pattern dei vincoli matchano sui nomi).
_STAZIONI = {
    # Linea Brescia-Iseo-Edolo (NON elettrificata)
    "ST_BS": "BRESCIA",
    "ST_ISEO": "ISEO",
    "ST_PISOGNE": "PISOGNE",
    "ST_EDOLO": "EDOLO",
    # Linea TILO Como-Chiasso
    "ST_COMO": "COMO S.GIOVANNI",
    "ST_CHIASSO": "CHIASSO",
    # Linea Malpensa
    "ST_MXP_T1": "MALPENSA AEROPORTO T1",
    "ST_MXP_T2": "MALPENSA AEROPORTO T2",
    "ST_VARESE": "VARESE",
    "ST_LUINO": "LUINO",
    "ST_GALLARATE": "GALLARATE",
    # Linea Tirano (elettrificata, NO TILO)
    "ST_MICLE": "MILANO CENTRALE",
    "ST_TIRANO": "TIRANO",
    "ST_SONDRIO": "SONDRIO",
    # Linea Bergamo (elettrificata)
    "ST_BERGAMO": "BERGAMO",
    "ST_TREVIGLIO": "TREVIGLIO",
}


@pytest.fixture(scope="module")
def vincoli() -> list[Vincolo]:
    """Carica i 2 vincoli reali dal JSON canonico."""
    return carica_vincoli()


# =====================================================================
# 1. Vincolo tecnico_elettrico_no_linee_diesel (blacklist)
# =====================================================================


def test_elettrico_su_linea_elettrificata_ok(vincoli: list[Vincolo]) -> None:
    """Caravaggio (ETR421) su Bergamo-Treviglio → nessuna violazione."""
    corse = [
        CorsaMock("R3-001", "ST_BERGAMO", "ST_TREVIGLIO"),
        CorsaMock("R3-002", "ST_TREVIGLIO", "ST_BERGAMO"),
    ]
    violazioni = valida_regola(
        corse_programma=corse,
        stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "ETR421", "n_pezzi": 1}],
        filtri=[],
        vincoli=vincoli,
    )
    assert violazioni == []


def test_elettrico_su_brescia_iseo_violazione(vincoli: list[Vincolo]) -> None:
    """ETR421 (elettrico) su Brescia-Iseo (non elettrificata) → 1 violazione."""
    corse = [
        CorsaMock("R5-001", "ST_BS", "ST_EDOLO"),
        CorsaMock("R5-002", "ST_BS", "ST_ISEO"),
    ]
    violazioni = valida_regola(
        corse_programma=corse,
        stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "ETR421", "n_pezzi": 1}],
        filtri=[],
        vincoli=vincoli,
    )
    assert len(violazioni) == 1
    v = violazioni[0]
    assert v.vincolo_id == "tecnico_elettrico_no_linee_diesel"
    assert v.materiale_tipo_codice == "ETR421"
    assert len(v.corse_problematiche) == 2


def test_diesel_atr803_su_brescia_iseo_ok(vincoli: list[Vincolo]) -> None:
    """ATR803 (esente: ibrido) su Brescia-Iseo → nessuna violazione.

    Entry 92: rimosso il vincolo HARD operativo ATR803, ATR803 può
    andare ovunque (responsabilità del pianificatore)."""
    corse = [CorsaMock("R5-100", "ST_BS", "ST_EDOLO")]
    violazioni = valida_regola(
        corse_programma=corse,
        stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "ATR803", "n_pezzi": 1}],
        filtri=[],
        vincoli=vincoli,
    )
    assert violazioni == []


def test_diesel_atr125_libero_ovunque(vincoli: list[Vincolo]) -> None:
    """ATR125 (esente dal vincolo elettrico) può andare ovunque dopo
    l'eliminazione dei vincoli operativi (entry 92)."""
    corse = [
        CorsaMock("R-100", "ST_BS", "ST_EDOLO"),  # Brescia-Iseo
        CorsaMock("R-101", "ST_BERGAMO", "ST_TREVIGLIO"),  # Bergamo (elettrificata)
        CorsaMock("R-102", "ST_MICLE", "ST_TIRANO"),  # Tirano
    ]
    violazioni = valida_regola(
        corse_programma=corse,
        stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "ATR125", "n_pezzi": 1}],
        filtri=[],
        vincoli=vincoli,
    )
    assert violazioni == []


# =====================================================================
# 2. Vincolo contrattuale_tilo_flirt_524 (whitelist)
# =====================================================================


def test_tilo_su_chiasso_ok(vincoli: list[Vincolo]) -> None:
    """ETR524 TILO su Como-Chiasso → linea ammessa, nessuna violazione."""
    corse = [
        CorsaMock("S10-001", "ST_COMO", "ST_CHIASSO"),
        CorsaMock("S10-002", "ST_CHIASSO", "ST_COMO"),
    ]
    violazioni = valida_regola(
        corse_programma=corse,
        stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "ETR524", "n_pezzi": 1}],
        filtri=[],
        vincoli=vincoli,
    )
    assert violazioni == []


def test_tilo_su_malpensa_varese_ok(vincoli: list[Vincolo]) -> None:
    """ETR524 TILO su Malpensa-Varese → linea ammessa."""
    corse = [CorsaMock("MXP-001", "ST_MXP_T1", "ST_VARESE")]
    violazioni = valida_regola(
        corse_programma=corse,
        stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "ETR524", "n_pezzi": 1}],
        filtri=[],
        vincoli=vincoli,
    )
    assert violazioni == []


def test_tilo_su_tirano_violazione(vincoli: list[Vincolo]) -> None:
    """ETR524 TILO su Mi.Centrale-Tirano → linea NON ammessa (whitelist TILO)."""
    corse = [
        CorsaMock("R7-001", "ST_MICLE", "ST_TIRANO"),
        CorsaMock("R7-002", "ST_TIRANO", "ST_SONDRIO"),
    ]
    violazioni = valida_regola(
        corse_programma=corse,
        stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "ETR524", "n_pezzi": 1}],
        filtri=[],
        vincoli=vincoli,
    )
    tilo_v = [v for v in violazioni if v.vincolo_id == "contrattuale_tilo_flirt_524"]
    assert len(tilo_v) == 1
    assert tilo_v[0].materiale_tipo_codice == "ETR524"
    assert len(tilo_v[0].corse_problematiche) == 2


def test_tilo_su_brescia_iseo_doppia_violazione(vincoli: list[Vincolo]) -> None:
    """ETR524 su Brescia-Iseo → viola SIA elettrico (linea non elettrif.) SIA TILO (whitelist)."""
    corse = [CorsaMock("R5-001", "ST_BS", "ST_EDOLO")]
    violazioni = valida_regola(
        corse_programma=corse,
        stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "ETR524", "n_pezzi": 1}],
        filtri=[],
        vincoli=vincoli,
    )
    assert len(violazioni) == 2
    ids = {v.vincolo_id for v in violazioni}
    assert ids == {
        "tecnico_elettrico_no_linee_diesel",
        "contrattuale_tilo_flirt_524",
    }


# =====================================================================
# Edge cases
# =====================================================================


def test_filtri_giorno_tipo_ignorati(vincoli: list[Vincolo]) -> None:
    """Il filtro `giorno_tipo` viene rimosso dalla validation: il vincolo
    geografico vale per tutti i giorni della settimana."""
    corse = [CorsaMock("R5-001", "ST_BS", "ST_EDOLO")]
    violazioni = valida_regola(
        corse_programma=corse,
        stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "ETR421", "n_pezzi": 1}],
        filtri=[{"campo": "giorno_tipo", "op": "in", "valore": ["sabato"]}],
        vincoli=vincoli,
    )
    assert len(violazioni) == 1
    assert violazioni[0].vincolo_id == "tecnico_elettrico_no_linee_diesel"


def test_filtri_codice_linea_riducono_corse(vincoli: list[Vincolo]) -> None:
    """Un filtro `codice_linea` riduce il subset di corse considerate."""
    corse = [
        CorsaMock("R5-001", "ST_BS", "ST_EDOLO", codice_linea="R5"),
        CorsaMock("R3-001", "ST_BERGAMO", "ST_TREVIGLIO", codice_linea="R3"),
    ]
    violazioni = valida_regola(
        corse_programma=corse,
        stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "ETR421", "n_pezzi": 1}],
        filtri=[{"campo": "codice_linea", "op": "eq", "valore": "R3"}],
        vincoli=vincoli,
    )
    assert violazioni == []


def test_lookup_stazione_mancante_usa_codice_grezzo(
    vincoli: list[Vincolo],
) -> None:
    """Se un codice stazione non è nel lookup, fallback al codice grezzo:
    il pattern matcha sul codice se il nome non c'è."""
    corse = [
        CorsaMock("R5-X", "ISEO", "EDOLO"),
    ]
    violazioni = valida_regola(
        corse_programma=corse,
        stazioni_lookup={},
        composizione=[{"materiale_tipo_codice": "ETR421", "n_pezzi": 1}],
        filtri=[],
        vincoli=vincoli,
    )
    assert len(violazioni) == 1
    assert violazioni[0].vincolo_id == "tecnico_elettrico_no_linee_diesel"


# =====================================================================
# Loader
# =====================================================================


def test_carica_vincoli_dal_json_reale() -> None:
    """Verifica che i 2 vincoli HARD si caricano correttamente dal file canonico.

    Entry 92: ridotti a 2 dopo l'eliminazione dei 5 vincoli operativi
    (ATR803, ATR125, ATR115, ALn668, D520) che generavano falsi positivi
    sulle sub-tratte legittime."""
    vincoli = carica_vincoli()
    assert len(vincoli) == 2
    ids = {v.id for v in vincoli}
    assert ids == {
        "tecnico_elettrico_no_linee_diesel",
        "contrattuale_tilo_flirt_524",
    }
    # Vincolo elettrico è blacklist con materiali esenti
    elettrico = next(v for v in vincoli if v.id == "tecnico_elettrico_no_linee_diesel")
    assert elettrico.modalita == "blacklist"
    assert "ETR421" in elettrico.materiale_tipo_codici_target
    assert "ATR803" in elettrico.materiale_tipo_codici_esenti
    assert "ATR125" in elettrico.materiale_tipo_codici_esenti
    assert "D520" in elettrico.materiale_tipo_codici_esenti
    # Vincolo TILO è whitelist
    tilo = next(v for v in vincoli if v.id == "contrattuale_tilo_flirt_524")
    assert tilo.modalita == "whitelist"
    assert tilo.materiale_tipo_codici_target == frozenset({"ETR524"})
