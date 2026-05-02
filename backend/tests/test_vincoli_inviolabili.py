"""Test unit del validator vincoli inviolabili (`domain/vincoli/inviolabili.py`).

Test puri (no DB): mockano `CorsaCommerciale` con dataclass minimi e
chiamano direttamente ``valida_regola()``.

Coverage dei 7 vincoli HARD del JSON `data/vincoli_materiale_inviolabili.json`:
1. tecnico_elettrico_no_linee_diesel (blacklist)
2. contrattuale_tilo_flirt_524 (whitelist con pattern_regex)
3. operativo_atr803_linee_assegnate (whitelist con stazioni_ammesse_lista)
4. operativo_atr115_deposito_lecco (whitelist con lista)
5. operativo_atr125_deposito_lecco_e_iseo (whitelist con lista)
6. operativo_aln668_deposito_iseo (whitelist con lista)
7. operativo_treno_dei_sapori_d520 (whitelist con lista)

Entry 94: vincoli operativi ricostruiti con LISTA STAZIONI ESPLICITA
(dal DB Trenord), AND match su entrambe le stazioni della corsa.
Risolve sub-tratte legittime E blocca destinazioni fuori linea.
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
    "ST_VARESE": "VARESE",
    "ST_LUINO": "LUINO",
    # Linea Tirano (elettrificata, NO TILO)
    "ST_MICLE": "MILANO CENTRALE",
    "ST_TIRANO": "TIRANO",
    "ST_SONDRIO": "SONDRIO",
    # Linea Bergamo (elettrificata, fuori da tutte whitelist)
    "ST_BERGAMO": "BERGAMO",
    "ST_TREVIGLIO": "TREVIGLIO",
    # ATR803 deposito (Pavia-Codogno-Cremona-Vercelli-Alessandria-Parma + sub-tratte)
    "ST_PAVIA": "PAVIA",
    "ST_CODOGNO": "CODOGNO",
    "ST_CREMONA": "CREMONA",
    "ST_PIADENA": "PIADENA",
    "ST_VERCELLI": "VERCELLI",
    "ST_ALESSANDRIA": "ALESSANDRIA",
    "ST_PARMA": "PARMA",
    "ST_BELGIOIOSO": "BELGIOIOSO",
    "ST_CORTEOLONA": "CORTEOLONA",
    "ST_CASALPUST": "CASALPUSTERLENGO",
    "ST_MORTARA": "MORTARA",
    "ST_TORREB": "TORREBERETTI",
    # Deposito Lecco (Lecco-Molteno-Como/Mi.P.Gar)
    "ST_LECCO": "LECCO",
    "ST_MOLTENO": "MOLTENO",
    "ST_BESANA": "BESANA",
    "ST_MONZA": "MONZA",
    "ST_MIPGAR": "MILANO PORTA GARIBALDI",
    # Stazioni fuori da tutte le whitelist (per test violazione)
    "ST_LOCARNO": "LOCARNO",
    "ST_DOMODOSSOLA": "DOMODOSSOLA",
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


def test_diesel_atr803_su_brescia_iseo_violazione(vincoli: list[Vincolo]) -> None:
    """ATR803 (esente da elettrico) MA violando whitelist operativa: Brescia-Iseo
    NON è del deposito Coleoni (è del deposito Iseo)."""
    corse = [CorsaMock("R5-100", "ST_BS", "ST_EDOLO")]
    violazioni = valida_regola(
        corse_programma=corse,
        stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "ATR803", "n_pezzi": 1}],
        filtri=[],
        vincoli=vincoli,
    )
    assert len(violazioni) == 1
    assert violazioni[0].vincolo_id == "operativo_atr803_linee_assegnate"


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
    """Verifica che i 7 vincoli HARD si caricano correttamente dal file canonico.

    Entry 94: ricostruiti 5 vincoli operativi con LISTA STAZIONI ESPLICITA
    (dal DB Trenord), AND match. Risolve sub-tratte legittime e blocca
    destinazioni fuori linea."""
    vincoli = carica_vincoli()
    assert len(vincoli) == 7
    ids = {v.id for v in vincoli}
    assert ids == {
        "tecnico_elettrico_no_linee_diesel",
        "contrattuale_tilo_flirt_524",
        "operativo_atr803_linee_assegnate",
        "operativo_atr115_deposito_lecco",
        "operativo_atr125_deposito_lecco_e_iseo",
        "operativo_aln668_deposito_iseo",
        "operativo_treno_dei_sapori_d520",
    }
    # Vincolo elettrico è blacklist con materiali esenti
    elettrico = next(v for v in vincoli if v.id == "tecnico_elettrico_no_linee_diesel")
    assert elettrico.modalita == "blacklist"
    assert "ETR421" in elettrico.materiale_tipo_codici_target
    assert "ATR803" in elettrico.materiale_tipo_codici_esenti
    # ATR803 ha lista stazioni esplicita (AND match)
    atr803 = next(v for v in vincoli if v.id == "operativo_atr803_linee_assegnate")
    assert atr803.modalita == "whitelist"
    assert "BRESCIA" in atr803.stazioni_ammesse_lista
    assert "PARMA" in atr803.stazioni_ammesse_lista
    assert "PAVIA" in atr803.stazioni_ammesse_lista
    assert "BELGIOIOSO" in atr803.stazioni_ammesse_lista
    assert "PIADENA" in atr803.stazioni_ammesse_lista
    assert "BERGAMO" not in atr803.stazioni_ammesse_lista
    # ATR125 multi-deposito ha lista più ampia (Lecco + Iseo)
    atr125 = next(v for v in vincoli if v.id == "operativo_atr125_deposito_lecco_e_iseo")
    assert "LECCO" in atr125.stazioni_ammesse_lista
    assert "EDOLO" in atr125.stazioni_ammesse_lista
    # ATR115 ha lista solo Brianza
    atr115 = next(v for v in vincoli if v.id == "operativo_atr115_deposito_lecco")
    assert "LECCO" in atr115.stazioni_ammesse_lista
    assert "EDOLO" not in atr115.stazioni_ammesse_lista


# =====================================================================
# Vincoli operativi (entry 94: lista stazioni esplicita, AND match)
# =====================================================================


def test_atr803_brescia_parma_ok(vincoli: list[Vincolo]) -> None:
    """ATR803 su Brescia-Parma → ammesso (entrambe in lista)."""
    corse = [
        CorsaMock("R-1", "ST_BS", "ST_PARMA"),
        CorsaMock("R-2", "ST_PARMA", "ST_BS"),
    ]
    violazioni = valida_regola(
        corse_programma=corse, stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "ATR803", "n_pezzi": 1}],
        filtri=[], vincoli=vincoli,
    )
    assert violazioni == []


def test_atr803_sub_tratte_pavia_codogno_cremona_ok(vincoli: list[Vincolo]) -> None:
    """ATR803 su sub-tratte legittime: Cremona-Belgioioso, Corteolona-Cremona,
    Brescia-Piadena, Piadena-Parma → tutte ammesse (lista AND match)."""
    corse = [
        CorsaMock("R-1", "ST_CREMONA", "ST_BELGIOIOSO"),
        CorsaMock("R-2", "ST_CORTEOLONA", "ST_CREMONA"),
        CorsaMock("R-3", "ST_BS", "ST_PIADENA"),
        CorsaMock("R-4", "ST_PIADENA", "ST_PARMA"),
        CorsaMock("R-5", "ST_PAVIA", "ST_CASALPUST"),
        CorsaMock("R-6", "ST_PAVIA", "ST_MORTARA"),
        CorsaMock("R-7", "ST_PAVIA", "ST_TORREB"),
    ]
    violazioni = valida_regola(
        corse_programma=corse, stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "ATR803", "n_pezzi": 1}],
        filtri=[], vincoli=vincoli,
    )
    assert violazioni == []


def test_atr803_locarno_violazione(vincoli: list[Vincolo]) -> None:
    """ATR803 su Locarno (Svizzera, fuori dotazione) → violazione."""
    corse = [CorsaMock("R-X", "ST_CREMONA", "ST_LOCARNO")]
    violazioni = valida_regola(
        corse_programma=corse, stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "ATR803", "n_pezzi": 1}],
        filtri=[], vincoli=vincoli,
    )
    assert len(violazioni) == 1
    assert violazioni[0].vincolo_id == "operativo_atr803_linee_assegnate"


def test_atr803_bergamo_violazione(vincoli: list[Vincolo]) -> None:
    """ATR803 su Bergamo (mai assegnato) → violazione."""
    corse = [CorsaMock("R-X", "ST_PAVIA", "ST_BERGAMO")]
    violazioni = valida_regola(
        corse_programma=corse, stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "ATR803", "n_pezzi": 1}],
        filtri=[], vincoli=vincoli,
    )
    assert len(violazioni) == 1
    assert violazioni[0].vincolo_id == "operativo_atr803_linee_assegnate"


def test_atr125_lecco_ok(vincoli: list[Vincolo]) -> None:
    """ATR125 su Lecco-Molteno (deposito Lecco) → ammesso."""
    corse = [CorsaMock("R-1", "ST_LECCO", "ST_MOLTENO")]
    violazioni = valida_regola(
        corse_programma=corse, stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "ATR125", "n_pezzi": 1}],
        filtri=[], vincoli=vincoli,
    )
    assert violazioni == []


def test_atr125_iseo_ok(vincoli: list[Vincolo]) -> None:
    """ATR125 su Brescia-Iseo (deposito Iseo, multi-deposito) → ammesso."""
    corse = [CorsaMock("R-1", "ST_BS", "ST_EDOLO")]
    violazioni = valida_regola(
        corse_programma=corse, stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "ATR125", "n_pezzi": 1}],
        filtri=[], vincoli=vincoli,
    )
    assert violazioni == []


def test_atr115_iseo_violazione(vincoli: list[Vincolo]) -> None:
    """ATR115 su Brescia-Iseo (NON deposito ATR115) → violazione."""
    corse = [CorsaMock("R-1", "ST_BS", "ST_EDOLO")]
    violazioni = valida_regola(
        corse_programma=corse, stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "ATR115", "n_pezzi": 1}],
        filtri=[], vincoli=vincoli,
    )
    assert len(violazioni) == 1
    assert violazioni[0].vincolo_id == "operativo_atr115_deposito_lecco"


def test_d520_treno_sapori_su_brescia_iseo_ok(vincoli: list[Vincolo]) -> None:
    """D520 Treno dei Sapori su Brescia-Iseo → ammesso."""
    corse = [CorsaMock("R-1", "ST_BS", "ST_EDOLO")]
    violazioni = valida_regola(
        corse_programma=corse, stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "D520", "n_pezzi": 1}],
        filtri=[], vincoli=vincoli,
    )
    assert violazioni == []


def test_aln668_su_bergamo_violazione(vincoli: list[Vincolo]) -> None:
    """ALn668 fuori da Valcamonica → violazione."""
    corse = [CorsaMock("R-1", "ST_BERGAMO", "ST_TREVIGLIO")]
    violazioni = valida_regola(
        corse_programma=corse, stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "ALn668(1000)", "n_pezzi": 1}],
        filtri=[], vincoli=vincoli,
    )
    assert len(violazioni) == 1
    assert violazioni[0].vincolo_id == "operativo_aln668_deposito_iseo"
