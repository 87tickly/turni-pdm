"""Test unit del validator vincoli inviolabili (`domain/vincoli/inviolabili.py`).

Test puri (no DB): mockano `CorsaCommerciale` con dataclass minimi e
chiamano direttamente ``valida_regola()``.

Coverage dei 3 vincoli del JSON `data/vincoli_materiale_inviolabili.json`:
1. tecnico_elettrico_no_linee_diesel (blacklist)
2. contrattuale_tilo_flirt_524 (whitelist)
3. operativo_treno_dei_sapori_d520 (whitelist)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Any

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
    # ATR803 deposito (Pavia-Codogno-Cremona-Vercelli-Alessandria-Parma)
    "ST_PAVIA": "PAVIA",
    "ST_CODOGNO": "CODOGNO",
    "ST_CREMONA": "CREMONA",
    "ST_VERCELLI": "VERCELLI",
    "ST_ALESSANDRIA": "ALESSANDRIA",
    "ST_PARMA": "PARMA",
    "ST_MORTARA": "MORTARA",
    "ST_TORREB": "TORREBERETTI",
    "ST_CASALP": "CASALPUSTERLENGO",
    # Deposito Lecco (Lecco-Molteno-Como/Mi.P.Gar)
    "ST_LECCO": "LECCO",
    "ST_MOLTENO": "MOLTENO",
    "ST_MIPGAR": "MILANO PORTA GARIBALDI",
}


@pytest.fixture(scope="module")
def vincoli() -> list[Vincolo]:
    """Carica i 3 vincoli reali dal JSON canonico."""
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
    assert {c["numero_treno"] for c in v.corse_problematiche} == {"R5-001", "R5-002"}


def test_diesel_atr803_su_brescia_iseo_violazione(vincoli: list[Vincolo]) -> None:
    """ATR803 su Brescia-Iseo (linea del deposito Iseo, NON Coleoni) → violazione
    del vincolo `operativo_atr803_linee_assegnate` (ATR803 ammesso solo su
    Brescia-Parma, Pavia-Alessandria, Pavia-Vercelli, Pavia-Codogno-Cremona)."""
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
    assert violazioni[0].materiale_tipo_codice == "ATR803"


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
    """ETR524 TILO su Mi.Centrale-Tirano (Valtellina) → linea NON ammessa."""
    corse = [
        CorsaMock("R7-001", "ST_MICLE", "ST_TIRANO"),
        CorsaMock("R7-002", "ST_TIRANO", "ST_LECCO"),
    ]
    violazioni = valida_regola(
        corse_programma=corse,
        stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "ETR524", "n_pezzi": 1}],
        filtri=[],
        vincoli=vincoli,
    )
    # 2 violazioni? No: 1 sola Violazione che raggruppa le corse problematiche.
    # Però il vincolo tecnico_elettrico genera ANCHE una violazione a vuoto?
    # No: TILO è in materiale_tipo_codici_target del vincolo elettrico ma
    # le stazioni MICLE/TIRANO/LECCO non sono in stazioni_vietate del vincolo
    # elettrico → nessuna violazione tecnica. Solo TILO whitelist viola.
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
# 3. Vincolo operativo_treno_dei_sapori_d520 (whitelist)
# =====================================================================


def test_treno_dei_sapori_su_brescia_iseo_ok(vincoli: list[Vincolo]) -> None:
    """D520 Treno dei Sapori su Brescia-Iseo → linea ammessa."""
    corse = [CorsaMock("TDS-001", "ST_BS", "ST_PISOGNE")]
    violazioni = valida_regola(
        corse_programma=corse,
        stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "D520", "n_pezzi": 1}],
        filtri=[],
        vincoli=vincoli,
    )
    assert violazioni == []


def test_treno_dei_sapori_su_bergamo_violazione(vincoli: list[Vincolo]) -> None:
    """D520 Treno dei Sapori su Bergamo-Milano → linea NON ammessa."""
    corse = [CorsaMock("R3-X", "ST_BERGAMO", "ST_TREVIGLIO")]
    violazioni = valida_regola(
        corse_programma=corse,
        stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "D520", "n_pezzi": 1}],
        filtri=[],
        vincoli=vincoli,
    )
    assert len(violazioni) == 1
    assert violazioni[0].vincolo_id == "operativo_treno_dei_sapori_d520"
    assert violazioni[0].materiale_tipo_codice == "D520"


# =====================================================================
# Composizione mista
# =====================================================================


def test_composizione_mista_solo_uno_target(vincoli: list[Vincolo]) -> None:
    """Composizione [ETR526, ETR425] su Tirano: entrambi sono Coradia
    Meridian (elettrici), nessuna violazione perché Tirano è elettrificata."""
    corse = [CorsaMock("R7-001", "ST_MICLE", "ST_TIRANO")]
    violazioni = valida_regola(
        corse_programma=corse,
        stazioni_lookup=_STAZIONI,
        composizione=[
            {"materiale_tipo_codice": "ETR526", "n_pezzi": 1},
            {"materiale_tipo_codice": "ETR425", "n_pezzi": 1},
        ],
        filtri=[],
        vincoli=vincoli,
    )
    assert violazioni == []


def test_filtri_giorno_tipo_ignorati(vincoli: list[Vincolo]) -> None:
    """Il filtro `giorno_tipo` viene rimosso dalla validation: il vincolo
    geografico vale per tutti i giorni della settimana."""
    corse = [CorsaMock("R5-001", "ST_BS", "ST_EDOLO")]
    violazioni = valida_regola(
        corse_programma=corse,
        stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "ETR421", "n_pezzi": 1}],
        # Filtro giorno_tipo che limiterebbe a sabato: deve essere ignorato
        # dalla validation (il sabato la corsa è comunque su linea diesel).
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
        # Solo R3 → niente Brescia-Iseo nel subset → nessuna violazione
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
        CorsaMock("R5-X", "ISEO", "EDOLO"),  # codici diretti, no lookup
    ]
    violazioni = valida_regola(
        corse_programma=corse,
        stazioni_lookup={},  # vuoto
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
    """Verifica che i 7 vincoli si caricano correttamente dal file canonico."""
    vincoli = carica_vincoli()
    assert len(vincoli) == 7
    ids = {v.id for v in vincoli}
    assert ids == {
        "tecnico_elettrico_no_linee_diesel",
        "contrattuale_tilo_flirt_524",
        "operativo_treno_dei_sapori_d520",
        "operativo_atr803_linee_assegnate",
        "operativo_atr115_deposito_lecco",
        "operativo_atr125_deposito_lecco_e_iseo",
        "operativo_aln668_deposito_iseo",
    }
    # Vincolo elettrico è blacklist con materiali esenti
    elettrico = next(v for v in vincoli if v.id == "tecnico_elettrico_no_linee_diesel")
    assert elettrico.modalita == "blacklist"
    assert "ETR421" in elettrico.materiale_tipo_codici_target
    assert "ATR803" in elettrico.materiale_tipo_codici_esenti
    # Vincolo TILO è whitelist
    tilo = next(v for v in vincoli if v.id == "contrattuale_tilo_flirt_524")
    assert tilo.modalita == "whitelist"
    assert tilo.materiale_tipo_codici_target == frozenset({"ETR524"})
    # Vincolo ATR803 (operativo deposito assegnamento)
    atr803 = next(v for v in vincoli if v.id == "operativo_atr803_linee_assegnate")
    assert atr803.materiale_tipo_codici_target == frozenset({"ATR803"})
    # Vincolo ATR115 solo deposito Lecco
    atr115 = next(v for v in vincoli if v.id == "operativo_atr115_deposito_lecco")
    assert atr115.materiale_tipo_codici_target == frozenset({"ATR115"})
    # Vincolo ATR125 multi-deposito Lecco + Iseo
    atr125 = next(v for v in vincoli if v.id == "operativo_atr125_deposito_lecco_e_iseo")
    assert atr125.materiale_tipo_codici_target == frozenset({"ATR125"})
    # Vincolo ALn668 deposito Iseo
    iseo = next(v for v in vincoli if v.id == "operativo_aln668_deposito_iseo")
    assert iseo.materiale_tipo_codici_target == frozenset({"ALn668(1000)"})


# =====================================================================
# 4. Vincolo ATR803 (whitelist deposito assegnamento)
# =====================================================================


def test_atr803_su_brescia_parma_ok(vincoli: list[Vincolo]) -> None:
    """ATR803 su Brescia-Parma (linea ammessa) → nessuna violazione."""
    corse = [
        CorsaMock("R-001", "ST_BS", "ST_PARMA"),
        CorsaMock("R-002", "ST_PARMA", "ST_BS"),
    ]
    violazioni = valida_regola(
        corse_programma=corse,
        stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "ATR803", "n_pezzi": 1}],
        filtri=[],
        vincoli=vincoli,
    )
    assert violazioni == []


def test_atr803_su_pavia_codogno_cremona_ok(vincoli: list[Vincolo]) -> None:
    """ATR803 su sub-rotte di Pavia-Codogno-Cremona → tutte ammesse."""
    corse = [
        CorsaMock("R-100", "ST_PAVIA", "ST_CREMONA"),
        CorsaMock("R-101", "ST_PAVIA", "ST_CODOGNO"),
        CorsaMock("R-102", "ST_CODOGNO", "ST_CREMONA"),
        CorsaMock("R-103", "ST_PAVIA", "ST_ALESSANDRIA"),
        CorsaMock("R-104", "ST_PAVIA", "ST_VERCELLI"),
    ]
    violazioni = valida_regola(
        corse_programma=corse,
        stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "ATR803", "n_pezzi": 1}],
        filtri=[],
        vincoli=vincoli,
    )
    assert violazioni == []


def test_atr803_su_brescia_milano_violazione(vincoli: list[Vincolo]) -> None:
    """ATR803 su Brescia-Milano (NON in whitelist) → violazione operativa.

    BRESCIA è capolinea ambiguo: appare nel vincolo Brescia-Parma (ammessa),
    ma una corsa Brescia-Milano deve essere rifiutata. Il pattern bidir
    'BRESCIA.*PARMA|PARMA.*BRESCIA' garantisce questa precisione."""
    corse = [CorsaMock("R-X", "ST_BS", "ST_MICLE")]
    violazioni = valida_regola(
        corse_programma=corse,
        stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "ATR803", "n_pezzi": 1}],
        filtri=[],
        vincoli=vincoli,
    )
    assert len(violazioni) == 1
    assert violazioni[0].vincolo_id == "operativo_atr803_linee_assegnate"


def test_atr803_su_bergamo_violazione(vincoli: list[Vincolo]) -> None:
    """ATR803 su Bergamo (mai usato lì) → violazione."""
    corse = [CorsaMock("R-Y", "ST_BERGAMO", "ST_TREVIGLIO")]
    violazioni = valida_regola(
        corse_programma=corse,
        stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "ATR803", "n_pezzi": 1}],
        filtri=[],
        vincoli=vincoli,
    )
    assert len(violazioni) == 1
    assert violazioni[0].vincolo_id == "operativo_atr803_linee_assegnate"


def test_atr803_pavia_mortara_torreberetti_ok(vincoli: list[Vincolo]) -> None:
    """ATR803 su sub-tratte Pavia-Mortara, Pavia-Torreberetti, Pavia-Casalp → ammesse.

    Sono sub-tratte legittime delle linee Pavia-Alessandria/Pavia-Vercelli/
    Pavia-Codogno, aggiunte su richiesta utente (entry 90)."""
    corse = [
        CorsaMock("R-600", "ST_PAVIA", "ST_MORTARA"),
        CorsaMock("R-601", "ST_MORTARA", "ST_PAVIA"),
        CorsaMock("R-602", "ST_PAVIA", "ST_TORREB"),
        CorsaMock("R-603", "ST_TORREB", "ST_ALESSANDRIA"),
        CorsaMock("R-604", "ST_MORTARA", "ST_ALESSANDRIA"),
        CorsaMock("R-605", "ST_MORTARA", "ST_VERCELLI"),
        CorsaMock("R-606", "ST_PAVIA", "ST_CASALP"),
        CorsaMock("R-607", "ST_CASALP", "ST_CODOGNO"),
    ]
    violazioni = valida_regola(
        corse_programma=corse,
        stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "ATR803", "n_pezzi": 1}],
        filtri=[],
        vincoli=vincoli,
    )
    assert violazioni == []


# =====================================================================
# 5. Vincolo ATR125 + ATR115 deposito Lecco (whitelist)
# =====================================================================


def test_atr125_su_lecco_molteno_ok(vincoli: list[Vincolo]) -> None:
    """ATR125 su Lecco-Molteno (deposito Lecco) → nessuna violazione."""
    corse = [
        CorsaMock("R-200", "ST_LECCO", "ST_MOLTENO"),
        CorsaMock("R-201", "ST_MOLTENO", "ST_COMO"),
        CorsaMock("R-202", "ST_LECCO", "ST_MIPGAR"),
    ]
    violazioni = valida_regola(
        corse_programma=corse,
        stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "ATR125", "n_pezzi": 1}],
        filtri=[],
        vincoli=vincoli,
    )
    assert violazioni == []


def test_atr115_su_brescia_iseo_violazione(vincoli: list[Vincolo]) -> None:
    """ATR115 (SOLO deposito Lecco) su Brescia-Iseo → violazione (a differenza
    di ATR125 che è multi-deposito Lecco+Iseo, ATR115 è esclusivo di Lecco)."""
    corse = [CorsaMock("R-300", "ST_BS", "ST_EDOLO")]
    violazioni = valida_regola(
        corse_programma=corse,
        stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "ATR115", "n_pezzi": 1}],
        filtri=[],
        vincoli=vincoli,
    )
    assert len(violazioni) == 1
    assert violazioni[0].vincolo_id == "operativo_atr115_deposito_lecco"


def test_atr125_su_lecco_molteno_ok_lecco_deposito(vincoli: list[Vincolo]) -> None:
    """ATR125 sul deposito Lecco (Lecco-Molteno-Como) → ammesso."""
    corse = [CorsaMock("R-700", "ST_LECCO", "ST_MOLTENO"),
             CorsaMock("R-701", "ST_MOLTENO", "ST_COMO")]
    violazioni = valida_regola(
        corse_programma=corse,
        stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "ATR125", "n_pezzi": 1}],
        filtri=[],
        vincoli=vincoli,
    )
    assert violazioni == []


def test_atr125_su_brescia_iseo_ok_iseo_deposito(vincoli: list[Vincolo]) -> None:
    """ATR125 sul deposito Iseo (Brescia-Iseo-Edolo) → ammesso (multi-deposito).

    A differenza di ATR115 che è solo Lecco, ATR125 è in dotazione anche
    al deposito Iseo (correzione utente entry 90)."""
    corse = [CorsaMock("R-800", "ST_BS", "ST_EDOLO"),
             CorsaMock("R-801", "ST_BS", "ST_ISEO"),
             CorsaMock("R-802", "ST_ISEO", "ST_EDOLO")]
    violazioni = valida_regola(
        corse_programma=corse,
        stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "ATR125", "n_pezzi": 1}],
        filtri=[],
        vincoli=vincoli,
    )
    assert violazioni == []


def test_atr125_su_bergamo_violazione(vincoli: list[Vincolo]) -> None:
    """ATR125 fuori dai 2 depositi (Lecco, Iseo) → violazione."""
    corse = [CorsaMock("R-900", "ST_BERGAMO", "ST_TREVIGLIO")]
    violazioni = valida_regola(
        corse_programma=corse,
        stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "ATR125", "n_pezzi": 1}],
        filtri=[],
        vincoli=vincoli,
    )
    assert len(violazioni) == 1
    assert violazioni[0].vincolo_id == "operativo_atr125_deposito_lecco_e_iseo"


# =====================================================================
# 6. Vincolo ALn668 deposito Iseo (whitelist)
# =====================================================================


def test_aln668_su_brescia_iseo_ok(vincoli: list[Vincolo]) -> None:
    """ALn668(1000) su Brescia-Iseo (deposito Iseo) → ammesso."""
    corse = [
        CorsaMock("R-400", "ST_BS", "ST_EDOLO"),
        CorsaMock("R-401", "ST_BS", "ST_PISOGNE"),
    ]
    violazioni = valida_regola(
        corse_programma=corse,
        stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "ALn668(1000)", "n_pezzi": 1}],
        filtri=[],
        vincoli=vincoli,
    )
    assert violazioni == []


def test_aln668_su_brescia_parma_violazione(vincoli: list[Vincolo]) -> None:
    """ALn668 (deposito Iseo) su Brescia-Parma (deposito ATR803) → violazione."""
    corse = [CorsaMock("R-500", "ST_BS", "ST_PARMA")]
    violazioni = valida_regola(
        corse_programma=corse,
        stazioni_lookup=_STAZIONI,
        composizione=[{"materiale_tipo_codice": "ALn668(1000)", "n_pezzi": 1}],
        filtri=[],
        vincoli=vincoli,
    )
    assert len(violazioni) == 1
    assert violazioni[0].vincolo_id == "operativo_aln668_deposito_iseo"
