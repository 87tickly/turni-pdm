"""Test puri Sprint 4.4.4 — assegnazione + rilevamento eventi composizione.

Tutti i test sono **senza DB**: usano dataclass minimali per simulare
corse e regole, costruiscono `Giro` direttamente.

Coprono:

- `assegna_materiali`:
  - Casi base (1 corsa con 1 regola, nessuna regola → corsa residua)
  - Più giornate
  - Incompatibilità materiale (giornata con 2 tipi)
  - `RegolaAmbiguaError` bubble up
- `rileva_eventi_composizione`:
  - Composizione costante → 0 eventi
  - Aggancio (3 → 6)
  - Sgancio (6 → 3)
  - Sequenza S5 mattina/pomeriggio/sera (3 → 6 → 3)
  - Stazione proposta + posizione corretta
- `assegna_e_rileva_eventi`: orchestrator
- Frozen + determinismo
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import date, time
from typing import Any

import pytest

from colazione.domain.builder_giro import (
    BloccoAssegnato,
    Catena,
    CatenaPosizionata,
    CorsaResidua,
    EventoComposizione,
    GiornataAssegnata,
    GiornataGiro,
    Giro,
    IncompatibilitaMateriale,
    RegolaAmbiguaError,
    assegna_e_rileva_eventi,
    assegna_materiali,
    rileva_eventi_composizione,
)

# =====================================================================
# Fixture
# =====================================================================


@dataclass
class FakeCorsa:
    codice_origine: str = "MI_FIO"
    codice_destinazione: str = "BG"
    ora_partenza: time = time(8, 0)
    ora_arrivo: time = time(9, 0)
    numero_treno: str = "12345"
    codice_linea: str | None = "S5"
    categoria: str | None = "S"
    direttrice: str | None = "MI-BG"
    rete: str | None = "RFI"
    is_treno_garantito_feriale: bool = False
    is_treno_garantito_festivo: bool = False


@dataclass
class FakeRegola:
    id: int
    filtri_json: list[dict[str, Any]] = field(default_factory=list)
    materiale_tipo_codice: str = "ALe711"
    numero_pezzi: int = 3
    priorita: int = 60


def _giro_singolo(corse: tuple[FakeCorsa, ...], data_g: date) -> Giro:
    """Helper: Giro 1-giornata con catena posizionata FIO."""
    cat_pos = CatenaPosizionata(
        localita_codice="FIO",
        stazione_collegata="MI_FIO",
        vuoto_testa=None,
        catena=Catena(corse=corse),
        vuoto_coda=None,
        chiusa_a_localita=True,
    )
    return Giro(
        localita_codice="FIO",
        giornate=(GiornataGiro(data=data_g, catena_posizionata=cat_pos),),
        chiuso=True,
        motivo_chiusura="naturale",
    )


D_LUN = date(2026, 4, 27)  # lunedì feriale
D_DOM = date(2026, 4, 26)  # domenica festivo


# =====================================================================
# assegna_materiali
# =====================================================================


def test_una_corsa_una_regola_match() -> None:
    c = FakeCorsa(codice_linea="S5")
    r = FakeRegola(id=1, filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "S5"}])
    giro = _giro_singolo((c,), D_LUN)
    out = assegna_materiali(giro, [r])
    assert len(out.giornate) == 1
    assert len(out.giornate[0].blocchi_assegnati) == 1
    blocco = out.giornate[0].blocchi_assegnati[0]
    assert blocco.corsa is c
    assert blocco.assegnazione.regola_id == 1
    assert blocco.assegnazione.materiale_tipo_codice == "ALe711"
    assert blocco.assegnazione.numero_pezzi == 3
    assert out.corse_residue == ()
    assert out.incompatibilita_materiale == ()


def test_corsa_senza_regola_va_in_residue() -> None:
    c = FakeCorsa(codice_linea="S99")  # nessuna regola la matcha
    r = FakeRegola(id=1, filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "S5"}])
    giro = _giro_singolo((c,), D_LUN)
    out = assegna_materiali(giro, [r])
    assert out.giornate[0].blocchi_assegnati == ()
    assert len(out.corse_residue) == 1
    assert out.corse_residue[0].corsa is c
    assert out.corse_residue[0].data == D_LUN


def test_giornata_un_tipo_materiale_no_incompat() -> None:
    c1 = FakeCorsa(numero_treno="A", codice_linea="S5")
    c2 = FakeCorsa(
        numero_treno="B", codice_linea="S5", codice_origine="BG", codice_destinazione="MI_FIO"
    )
    r = FakeRegola(id=1, filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "S5"}])
    giro = _giro_singolo((c1, c2), D_LUN)
    out = assegna_materiali(giro, [r])
    assert out.incompatibilita_materiale == ()
    assert out.giornate[0].materiali_tipo_giornata == frozenset({"ALe711"})


def test_giornata_due_tipi_materiale_incompat() -> None:
    c1 = FakeCorsa(numero_treno="A", codice_linea="S5")
    c2 = FakeCorsa(
        numero_treno="B", codice_linea="S6", codice_origine="BG", codice_destinazione="BS"
    )
    r1 = FakeRegola(
        id=1,
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "S5"}],
        materiale_tipo_codice="ALe711",
    )
    r2 = FakeRegola(
        id=2,
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "S6"}],
        materiale_tipo_codice="ETR526",
    )
    giro = _giro_singolo((c1, c2), D_LUN)
    out = assegna_materiali(giro, [r1, r2])
    assert len(out.incompatibilita_materiale) == 1
    assert out.incompatibilita_materiale[0].tipi_materiale == frozenset({"ALe711", "ETR526"})


def test_regola_ambigua_bubble_up() -> None:
    c = FakeCorsa(codice_linea="S5")
    # Due regole con stessa priorità + stessa specificità = ambigue
    r1 = FakeRegola(
        id=1,
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "S5"}],
        priorita=80,
        materiale_tipo_codice="ALe711",
    )
    r2 = FakeRegola(
        id=2,
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "S5"}],
        priorita=80,
        materiale_tipo_codice="ETR526",
    )
    giro = _giro_singolo((c,), D_LUN)
    with pytest.raises(RegolaAmbiguaError):
        assegna_materiali(giro, [r1, r2])


def test_pass_through_metadata_giro() -> None:
    """Il `GiroAssegnato` mantiene `localita`, `chiuso`, `motivo_chiusura`."""
    giro = _giro_singolo((FakeCorsa(),), D_LUN)
    out = assegna_materiali(giro, [])
    assert out.localita_codice == "FIO"
    assert out.chiuso is True
    assert out.motivo_chiusura == "naturale"


def test_giro_due_giornate_assegnazione_per_giornata() -> None:
    """Multi-giornata: ogni giornata ha le sue assegnazioni."""
    c1 = FakeCorsa(numero_treno="lun", codice_linea="S5")
    c2 = FakeCorsa(numero_treno="mar", codice_linea="S5")
    cat1 = CatenaPosizionata(
        localita_codice="FIO",
        stazione_collegata="MI_FIO",
        vuoto_testa=None,
        catena=Catena(corse=(c1,)),
        vuoto_coda=None,
        chiusa_a_localita=False,
    )
    cat2 = CatenaPosizionata(
        localita_codice="FIO",
        stazione_collegata="MI_FIO",
        vuoto_testa=None,
        catena=Catena(corse=(c2,)),
        vuoto_coda=None,
        chiusa_a_localita=True,
    )
    giro = Giro(
        localita_codice="FIO",
        giornate=(
            GiornataGiro(data=D_LUN, catena_posizionata=cat1),
            GiornataGiro(data=date(2026, 4, 28), catena_posizionata=cat2),
        ),
        chiuso=True,
        motivo_chiusura="naturale",
    )
    r = FakeRegola(id=1, filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "S5"}])
    out = assegna_materiali(giro, [r])
    assert len(out.giornate) == 2
    assert out.giornate[0].blocchi_assegnati[0].corsa is c1
    assert out.giornate[1].blocchi_assegnati[0].corsa is c2


# =====================================================================
# rileva_eventi_composizione
# =====================================================================


def test_composizione_costante_zero_eventi() -> None:
    c1 = FakeCorsa(numero_treno="A")
    c2 = FakeCorsa(numero_treno="B", codice_origine="BG", codice_destinazione="MI_FIO")
    r = FakeRegola(id=1, numero_pezzi=3)  # tutte le corse → 3 pezzi
    giro = _giro_singolo((c1, c2), D_LUN)
    out = rileva_eventi_composizione(assegna_materiali(giro, [r]))
    assert out.giornate[0].eventi_composizione == ()


def test_aggancio_3_a_6() -> None:
    """Mattina 3 pezzi → pomeriggio 6 pezzi → 1 evento aggancio +3."""
    c_matt = FakeCorsa(numero_treno="A", codice_linea="MAT")
    c_pom = FakeCorsa(
        numero_treno="B",
        codice_linea="POM",
        codice_origine="BG",
        codice_destinazione="MI_FIO",
    )
    r1 = FakeRegola(
        id=1,
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "MAT"}],
        numero_pezzi=3,
    )
    r2 = FakeRegola(
        id=2,
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "POM"}],
        numero_pezzi=6,
    )
    giro = _giro_singolo((c_matt, c_pom), D_LUN)
    out = rileva_eventi_composizione(assegna_materiali(giro, [r1, r2]))
    eventi = out.giornate[0].eventi_composizione
    assert len(eventi) == 1
    assert eventi[0].tipo == "aggancio"
    assert eventi[0].pezzi_delta == 3
    assert eventi[0].stazione_proposta == "BG"  # origine del blocco corrente
    assert eventi[0].posizione_dopo_blocco == 0
    assert eventi[0].is_validato_utente is False


def test_sgancio_6_a_3() -> None:
    c_pom = FakeCorsa(numero_treno="A", codice_linea="POM")
    c_sera = FakeCorsa(
        numero_treno="B",
        codice_linea="SER",
        codice_origine="BG",
        codice_destinazione="MI_FIO",
    )
    r1 = FakeRegola(
        id=1,
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "POM"}],
        numero_pezzi=6,
    )
    r2 = FakeRegola(
        id=2,
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "SER"}],
        numero_pezzi=3,
    )
    giro = _giro_singolo((c_pom, c_sera), D_LUN)
    out = rileva_eventi_composizione(assegna_materiali(giro, [r1, r2]))
    eventi = out.giornate[0].eventi_composizione
    assert len(eventi) == 1
    assert eventi[0].tipo == "sgancio"
    assert eventi[0].pezzi_delta == -3


def test_sequenza_s5_mattina_pomeriggio_sera() -> None:
    """3 → 6 → 3: aggancio + sgancio."""
    c1 = FakeCorsa(numero_treno="A", codice_linea="MAT")
    c2 = FakeCorsa(
        numero_treno="B", codice_linea="POM", codice_origine="BG", codice_destinazione="BS"
    )
    c3 = FakeCorsa(
        numero_treno="C", codice_linea="SER", codice_origine="BS", codice_destinazione="MI_FIO"
    )
    r1 = FakeRegola(
        id=1,
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "MAT"}],
        numero_pezzi=3,
    )
    r2 = FakeRegola(
        id=2,
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "POM"}],
        numero_pezzi=6,
    )
    r3 = FakeRegola(
        id=3,
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "SER"}],
        numero_pezzi=3,
    )
    giro = _giro_singolo((c1, c2, c3), D_LUN)
    out = rileva_eventi_composizione(assegna_materiali(giro, [r1, r2, r3]))
    eventi = out.giornate[0].eventi_composizione
    assert len(eventi) == 2
    # Aggancio fra blocco 0 e 1
    assert eventi[0].tipo == "aggancio"
    assert eventi[0].pezzi_delta == 3
    assert eventi[0].stazione_proposta == "BG"
    assert eventi[0].posizione_dopo_blocco == 0
    # Sgancio fra blocco 1 e 2
    assert eventi[1].tipo == "sgancio"
    assert eventi[1].pezzi_delta == -3
    assert eventi[1].stazione_proposta == "BS"
    assert eventi[1].posizione_dopo_blocco == 1


def test_eventi_solo_intra_giornata_non_cross_notte() -> None:
    """Delta tra ultima corsa G1 (6 pezzi) e prima corsa G2 (3 pezzi)
    NON genera evento (cross-notte è scope di 4.4.5)."""
    c_g1 = FakeCorsa(numero_treno="lun", codice_linea="POM")
    c_g2 = FakeCorsa(numero_treno="mar", codice_linea="MAT")
    cat1 = CatenaPosizionata(
        localita_codice="FIO",
        stazione_collegata="MI_FIO",
        vuoto_testa=None,
        catena=Catena(corse=(c_g1,)),
        vuoto_coda=None,
        chiusa_a_localita=False,
    )
    cat2 = CatenaPosizionata(
        localita_codice="FIO",
        stazione_collegata="MI_FIO",
        vuoto_testa=None,
        catena=Catena(corse=(c_g2,)),
        vuoto_coda=None,
        chiusa_a_localita=True,
    )
    giro = Giro(
        localita_codice="FIO",
        giornate=(
            GiornataGiro(data=D_LUN, catena_posizionata=cat1),
            GiornataGiro(data=date(2026, 4, 28), catena_posizionata=cat2),
        ),
        chiuso=True,
        motivo_chiusura="naturale",
    )
    r1 = FakeRegola(
        id=1,
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "POM"}],
        numero_pezzi=6,
    )
    r2 = FakeRegola(
        id=2,
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "MAT"}],
        numero_pezzi=3,
    )
    out = rileva_eventi_composizione(assegna_materiali(giro, [r1, r2]))
    # Nessun evento intra-giornata (singola corsa per giornata)
    assert out.giornate[0].eventi_composizione == ()
    assert out.giornate[1].eventi_composizione == ()


# =====================================================================
# Orchestrator
# =====================================================================


def test_orchestrator_assegna_e_rileva_eventi() -> None:
    c1 = FakeCorsa(numero_treno="A", codice_linea="MAT")
    c2 = FakeCorsa(
        numero_treno="B", codice_linea="POM", codice_origine="BG", codice_destinazione="MI_FIO"
    )
    r1 = FakeRegola(
        id=1,
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "MAT"}],
        numero_pezzi=3,
    )
    r2 = FakeRegola(
        id=2,
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "POM"}],
        numero_pezzi=6,
    )
    giro = _giro_singolo((c1, c2), D_LUN)
    out = assegna_e_rileva_eventi([giro], [r1, r2])
    assert len(out) == 1
    assert len(out[0].giornate[0].blocchi_assegnati) == 2
    assert len(out[0].giornate[0].eventi_composizione) == 1
    assert out[0].giornate[0].eventi_composizione[0].tipo == "aggancio"


def test_orchestrator_giri_vuoti() -> None:
    assert assegna_e_rileva_eventi([], [FakeRegola(id=1)]) == []


# =====================================================================
# Determinismo + frozen
# =====================================================================


def test_determinismo_due_chiamate_stesso_output() -> None:
    c = FakeCorsa()
    r = FakeRegola(id=1, filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "S5"}])
    giro = _giro_singolo((c,), D_LUN)
    out1 = assegna_e_rileva_eventi([giro], [r])
    out2 = assegna_e_rileva_eventi([giro], [r])
    assert out1 == out2


def test_blocco_assegnato_frozen() -> None:
    from colazione.domain.builder_giro import AssegnazioneRisolta

    b = BloccoAssegnato(
        corsa=FakeCorsa(),
        assegnazione=AssegnazioneRisolta(
            regola_id=1, materiale_tipo_codice="ALe711", numero_pezzi=3
        ),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        b.corsa = None  # type: ignore[misc]


def test_evento_composizione_frozen() -> None:
    e = EventoComposizione(
        tipo="aggancio",
        pezzi_delta=3,
        stazione_proposta="BG",
        posizione_dopo_blocco=0,
        note_builder="test",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        e.is_validato_utente = True  # type: ignore[misc]


def test_giornata_assegnata_frozen() -> None:
    cat = CatenaPosizionata(
        localita_codice="FIO",
        stazione_collegata="MI_FIO",
        vuoto_testa=None,
        catena=Catena(corse=()),
        vuoto_coda=None,
        chiusa_a_localita=True,
    )
    g = GiornataAssegnata(
        data=D_LUN,
        catena_posizionata=cat,
        blocchi_assegnati=(),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        g.data = D_DOM  # type: ignore[misc]


def test_giro_assegnato_frozen() -> None:
    giro = _giro_singolo((FakeCorsa(),), D_LUN)
    out = assegna_materiali(giro, [])
    with pytest.raises(dataclasses.FrozenInstanceError):
        out.chiuso = False  # type: ignore[misc]


def test_corsa_residua_e_incompat_dataclass() -> None:
    c = FakeCorsa()
    r = CorsaResidua(data=D_LUN, corsa=c)
    assert r.data == D_LUN
    assert r.corsa is c
    i = IncompatibilitaMateriale(data=D_LUN, tipi_materiale=frozenset({"X", "Y"}))
    assert i.tipi_materiale == frozenset({"X", "Y"})
