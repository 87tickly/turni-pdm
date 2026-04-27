"""Test puri Sprint 4.4.2 — `posiziona_su_localita`.

Tutti i test sono **senza DB**: usano dataclass minimali per simulare
corse e località manutenzione (Protocol-compatibili).

Coprono:

- Validazione input: catena vuota, località senza stazione collegata.
- Casi base posizionamento: parte+finisce in stazione, solo testa,
  solo coda, testa+coda.
- Calcolo orari corretto (gap + durata stimata).
- Cross-notte: catena chiusa cross-notte → niente vuoto coda.
- Edge case: vuoto di testa pre-mezzanotte (errore), vuoto di coda
  post-mezzanotte (no vuoto, chiusa=False).
- Determinismo + frozen.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import time

import pytest

from colazione.domain.builder_giro import (
    BloccoMaterialeVuoto,
    Catena,
    LocalitaSenzaStazioneError,
    ParamPosizionamento,
    PosizionamentoImpossibileError,
    posiziona_su_localita,
)

# =====================================================================
# Fixture
# =====================================================================


@dataclass
class FakeCorsa:
    codice_origine: str
    codice_destinazione: str
    ora_partenza: time
    ora_arrivo: time
    numero_treno: str = ""


@dataclass
class FakeLocalita:
    codice: str
    stazione_collegata_codice: str | None


def _c(o: str, d: str, p: tuple[int, int], a: tuple[int, int]) -> FakeCorsa:
    return FakeCorsa(o, d, time(*p), time(*a))


# Località Trenord di esempio per i test
LOC_FIORENZA = FakeLocalita(codice="IMPMAN_FIORENZA", stazione_collegata_codice="MI_FIO")
LOC_NOVATE = FakeLocalita(codice="NOVATE", stazione_collegata_codice="MI_NOV")

# Whitelist "piena" di test: tutte le stazioni periferiche usate sono
# considerate ammesse per i vuoti (eccetto la sede MI_FIO/MI_NOV).
# I test che vogliono testare il caso "fuori whitelist" usano una
# whitelist ridotta esplicitamente.
_WL = frozenset({"MI_CADORNA", "BG", "BS", "CV", "VARESE"})


# =====================================================================
# Validazione input
# =====================================================================


def test_catena_vuota_raises() -> None:
    with pytest.raises(ValueError, match="catena vuota"):
        posiziona_su_localita(Catena(corse=()), LOC_FIORENZA, _WL)


def test_localita_senza_stazione_raises() -> None:
    loc = FakeLocalita(codice="ORFANA", stazione_collegata_codice=None)
    cat = Catena(corse=(_c("MI_FIO", "BG", (8, 0), (9, 0)),))
    with pytest.raises(LocalitaSenzaStazioneError) as exc_info:
        posiziona_su_localita(cat, loc, _WL)
    assert exc_info.value.codice_localita == "ORFANA"


# =====================================================================
# Casi base posizionamento
# =====================================================================


def test_catena_inizia_e_finisce_in_stazione_localita_no_vuoti() -> None:
    """Caso ideale: il giro chiude naturalmente."""
    a = _c("MI_FIO", "BG", (8, 0), (9, 0))
    b = _c("BG", "MI_FIO", (9, 30), (10, 30))
    cat = Catena(corse=(a, b))
    res = posiziona_su_localita(cat, LOC_FIORENZA, _WL)
    assert res.vuoto_testa is None
    assert res.vuoto_coda is None
    assert res.chiusa_a_localita is True
    assert res.localita_codice == "IMPMAN_FIORENZA"
    assert res.stazione_collegata == "MI_FIO"


def test_catena_solo_vuoto_testa() -> None:
    """Prima corsa parte da MI (stazione diversa da Fiorenza) ma chiude lì."""
    a = _c("MI_CADORNA", "BG", (8, 0), (9, 0))
    b = _c("BG", "MI_FIO", (9, 30), (10, 30))
    cat = Catena(corse=(a, b))
    res = posiziona_su_localita(cat, LOC_FIORENZA, _WL)
    assert res.vuoto_testa is not None
    assert res.vuoto_testa.codice_origine == "MI_FIO"
    assert res.vuoto_testa.codice_destinazione == "MI_CADORNA"
    assert res.vuoto_testa.motivo == "testa"
    assert res.vuoto_coda is None
    assert res.chiusa_a_localita is True


def test_catena_solo_vuoto_coda() -> None:
    """Parte già da Fiorenza, finisce altrove."""
    a = _c("MI_FIO", "BG", (8, 0), (9, 0))
    b = _c("BG", "BS", (9, 30), (10, 30))
    cat = Catena(corse=(a, b))
    res = posiziona_su_localita(cat, LOC_FIORENZA, _WL)
    assert res.vuoto_testa is None
    assert res.vuoto_coda is not None
    assert res.vuoto_coda.codice_origine == "BS"
    assert res.vuoto_coda.codice_destinazione == "MI_FIO"
    assert res.vuoto_coda.motivo == "coda"
    assert res.chiusa_a_localita is True


def test_catena_entrambi_i_vuoti() -> None:
    a = _c("MI_CADORNA", "BG", (10, 0), (11, 0))
    b = _c("BG", "BS", (11, 30), (12, 30))
    cat = Catena(corse=(a, b))
    res = posiziona_su_localita(cat, LOC_FIORENZA, _WL)
    assert res.vuoto_testa is not None
    assert res.vuoto_coda is not None
    assert res.chiusa_a_localita is True


# =====================================================================
# Calcolo orari
# =====================================================================


def test_orari_vuoto_testa_corretti() -> None:
    """Vuoto di testa: arrivo = prima.partenza - gap; partenza = arrivo - durata."""
    a = _c("MI_CADORNA", "BG", (10, 0), (11, 0))
    cat = Catena(corse=(a,))
    params = ParamPosizionamento(durata_vuoto_default_min=30, gap_min=5)
    res = posiziona_su_localita(cat, LOC_FIORENZA, _WL, params)
    # arrivo = 10:00 - 5' = 09:55
    # partenza = 09:55 - 30' = 09:25
    assert res.vuoto_testa is not None
    assert res.vuoto_testa.ora_arrivo == time(9, 55)
    assert res.vuoto_testa.ora_partenza == time(9, 25)


def test_orari_vuoto_coda_corretti() -> None:
    """Vuoto di coda: partenza = ultima.arrivo + gap; arrivo = partenza + durata."""
    a = _c("MI_FIO", "BG", (10, 0), (11, 0))
    cat = Catena(corse=(a,))
    params = ParamPosizionamento(durata_vuoto_default_min=30, gap_min=5)
    res = posiziona_su_localita(cat, LOC_FIORENZA, _WL, params)
    # partenza = 11:00 + 5' = 11:05
    # arrivo = 11:05 + 30' = 11:35
    assert res.vuoto_coda is not None
    assert res.vuoto_coda.ora_partenza == time(11, 5)
    assert res.vuoto_coda.ora_arrivo == time(11, 35)


# =====================================================================
# Cross-notte e bordi mezzanotte
# =====================================================================


def test_catena_cross_notte_no_vuoto_coda_e_non_chiusa() -> None:
    """Catena che termina dopo mezzanotte → niente coda, chiusa=False."""
    a = _c("MI_FIO", "BG", (22, 0), (23, 0))
    b = _c("BG", "BS", (23, 30), (0, 30))  # cross-notte
    cat = Catena(corse=(a, b))
    res = posiziona_su_localita(cat, LOC_FIORENZA, _WL)
    assert res.vuoto_coda is None
    assert res.chiusa_a_localita is False


def test_vuoto_testa_pre_mezzanotte_raises() -> None:
    """Prima corsa alle 00:10 con durata stimata 30' + gap 5' → impossibile."""
    a = _c("MI_CADORNA", "BG", (0, 10), (1, 0))
    cat = Catena(corse=(a,))
    with pytest.raises(PosizionamentoImpossibileError, match="00:00"):
        posiziona_su_localita(cat, LOC_FIORENZA, _WL)


def test_vuoto_coda_post_mezzanotte_no_vuoto_e_non_chiusa() -> None:
    """Ultima corsa arriva alle 23:50 con stima vuoto 30' → finirebbe oltre 24."""
    a = _c("MI_FIO", "BS", (23, 0), (23, 50))
    cat = Catena(corse=(a,))
    res = posiziona_su_localita(cat, LOC_FIORENZA, _WL)
    # partenza vuoto = 23:50 + 5' = 23:55; arrivo = 23:55 + 30' = 00:25 (oltre)
    assert res.vuoto_coda is None
    assert res.chiusa_a_localita is False


def test_catena_inizia_in_stazione_localita_no_testa_anche_se_presto() -> None:
    """Se prima corsa parte già in stazione, niente vuoto di testa,
    quindi nessun problema di mezzanotte."""
    a = _c("MI_FIO", "BG", (0, 5), (1, 0))
    cat = Catena(corse=(a,))
    res = posiziona_su_localita(cat, LOC_FIORENZA, _WL)
    assert res.vuoto_testa is None


# =====================================================================
# Determinismo + frozen
# =====================================================================


def test_determinismo_due_chiamate_stesso_output() -> None:
    a = _c("MI_CADORNA", "BG", (10, 0), (11, 0))
    b = _c("BG", "MI_FIO", (11, 30), (12, 30))
    cat = Catena(corse=(a, b))
    out1 = posiziona_su_localita(cat, LOC_FIORENZA, _WL)
    out2 = posiziona_su_localita(cat, LOC_FIORENZA, _WL)
    assert out1 == out2


def test_param_default_30_e_5() -> None:
    p = ParamPosizionamento()
    assert p.durata_vuoto_default_min == 30
    assert p.gap_min == 5


def test_blocco_materiale_vuoto_frozen() -> None:
    b = BloccoMaterialeVuoto(
        codice_origine="A",
        codice_destinazione="B",
        ora_partenza=time(8, 0),
        ora_arrivo=time(9, 0),
        motivo="testa",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        b.codice_origine = "X"  # type: ignore[misc]


def test_catena_posizionata_frozen() -> None:
    cat = Catena(corse=(_c("MI_FIO", "BG", (8, 0), (9, 0)),))
    res = posiziona_su_localita(cat, LOC_FIORENZA, _WL)
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.chiusa_a_localita = False  # type: ignore[misc]


def test_param_posizionamento_frozen() -> None:
    p = ParamPosizionamento()
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.gap_min = 99  # type: ignore[misc]


# =====================================================================
# Esempio realistico Trenord
# =====================================================================


def test_esempio_giro_s5_cadorna_fiorenza() -> None:
    """Giro S5 che parte da Cadorna alle 06:30 e finisce a Cadorna alle 22:00.

    La località manutenzione è Fiorenza (MI_FIO). Servono entrambi
    i vuoti: posizionamento Fiorenza → Cadorna prima delle 06:30
    (vuoto testa) e rientro Cadorna → Fiorenza dopo le 22:00 (vuoto
    coda).
    """
    # 4 corse della giornata (semplificato)
    c1 = _c("MI_CADORNA", "VARESE", (6, 30), (8, 0))
    c2 = _c("VARESE", "MI_CADORNA", (8, 30), (10, 0))
    c3 = _c("MI_CADORNA", "VARESE", (20, 0), (21, 0))
    c4 = _c("VARESE", "MI_CADORNA", (21, 15), (22, 0))
    cat = Catena(corse=(c1, c2, c3, c4))
    res = posiziona_su_localita(cat, LOC_FIORENZA, _WL)
    assert res.vuoto_testa is not None
    assert res.vuoto_testa.codice_origine == "MI_FIO"
    assert res.vuoto_testa.codice_destinazione == "MI_CADORNA"
    assert res.vuoto_coda is not None
    assert res.vuoto_coda.codice_origine == "MI_CADORNA"
    assert res.vuoto_coda.codice_destinazione == "MI_FIO"
    assert res.chiusa_a_localita is True
    # La catena originale è preservata
    assert res.catena.corse == (c1, c2, c3, c4)


# =====================================================================
# Sprint 5.3: whitelist enforcement (vuoti SOLO intra-whitelist)
# =====================================================================


def test_prima_corsa_fuori_whitelist_no_vuoto_testa() -> None:
    """TIRANO ∉ whitelist: niente vuoto testa, treno è già a Tirano
    dalla sera precedente (multi-giornata)."""
    a = _c("TIRANO", "MI_CENTRALE", (6, 30), (10, 0))
    b = _c("MI_CENTRALE", "MI_FIO", (10, 30), (11, 0))
    cat = Catena(corse=(a, b))
    res = posiziona_su_localita(cat, LOC_FIORENZA, _WL)
    assert res.vuoto_testa is None, (
        "Vuoto testa MI_FIO→TIRANO vietato: TIRANO non è in whitelist FIO"
    )
    # Coda OK perché ultima arriva alla sede stessa
    assert res.vuoto_coda is None
    assert res.chiusa_a_localita is True


def test_ultima_corsa_fuori_whitelist_no_vuoto_coda_chiusa_false() -> None:
    """ASSO ∉ whitelist: niente vuoto coda, chiusa=False (treno dorme
    in linea ad ASSO la sera, multi-giornata gestirà)."""
    a = _c("MI_FIO", "MI_CENTRALE", (8, 0), (8, 30))
    b = _c("MI_CENTRALE", "ASSO", (9, 0), (10, 30))
    cat = Catena(corse=(a, b))
    res = posiziona_su_localita(cat, LOC_FIORENZA, _WL)
    assert res.vuoto_testa is None  # parte già da MI_FIO
    assert res.vuoto_coda is None, "Vuoto coda ASSO→MI_FIO vietato: ASSO non è in whitelist FIO"
    assert res.chiusa_a_localita is False, (
        "Treno dorme in linea ad ASSO, giro continua il giorno dopo"
    )


def test_entrambe_fuori_whitelist_nessun_vuoto_chiusa_false() -> None:
    """Tipico giro intermedio multi-giornata: il treno parte da TIRANO
    al mattino e finisce ad ASSO la sera. Entrambe fuori whitelist FIO,
    nessun vuoto, chiusa=False."""
    a = _c("TIRANO", "MI_CENTRALE", (6, 30), (10, 0))
    b = _c("MI_CENTRALE", "ASSO", (12, 0), (14, 0))
    cat = Catena(corse=(a, b))
    res = posiziona_su_localita(cat, LOC_FIORENZA, _WL)
    assert res.vuoto_testa is None
    assert res.vuoto_coda is None
    assert res.chiusa_a_localita is False


def test_whitelist_vuota_no_vuoti_mai() -> None:
    """Whitelist vuota = nessun vuoto generato mai (caso TILO o sede
    non ancora configurata). chiusa_a_localita resta True solo se
    ultima arriva direttamente alla sede."""
    a = _c("MI_CADORNA", "BG", (8, 0), (9, 0))
    b = _c("BG", "BS", (9, 30), (10, 30))
    cat = Catena(corse=(a, b))
    res = posiziona_su_localita(cat, LOC_FIORENZA, frozenset())
    assert res.vuoto_testa is None  # MI_CADORNA non in whitelist (vuota)
    assert res.vuoto_coda is None  # BS non in whitelist (vuota)
    assert res.chiusa_a_localita is False


def test_solo_origine_in_whitelist_solo_vuoto_testa() -> None:
    """Caso "in/out": prima ∈ whitelist (genera vuoto testa), ultima
    ∉ whitelist (no vuoto coda, chiusa=False)."""
    # MI_CADORNA in WL, ASSO fuori
    a = _c("MI_CADORNA", "BG", (8, 0), (9, 0))
    b = _c("BG", "ASSO", (9, 30), (12, 0))
    cat = Catena(corse=(a, b))
    res = posiziona_su_localita(cat, LOC_FIORENZA, _WL)
    assert res.vuoto_testa is not None
    assert res.vuoto_testa.codice_destinazione == "MI_CADORNA"
    assert res.vuoto_coda is None
    assert res.chiusa_a_localita is False


def test_solo_destinazione_in_whitelist_solo_vuoto_coda() -> None:
    """Caso "out/in": prima ∉ whitelist (no vuoto testa), ultima ∈
    whitelist (genera vuoto coda, chiusa=True)."""
    a = _c("TIRANO", "MI_CENTRALE", (6, 30), (10, 0))
    b = _c("MI_CENTRALE", "MI_CADORNA", (10, 30), (11, 0))
    cat = Catena(corse=(a, b))
    res = posiziona_su_localita(cat, LOC_FIORENZA, _WL)
    assert res.vuoto_testa is None
    assert res.vuoto_coda is not None
    assert res.vuoto_coda.codice_origine == "MI_CADORNA"
    assert res.vuoto_coda.codice_destinazione == "MI_FIO"
    assert res.chiusa_a_localita is True


def test_origine_uguale_sede_no_vuoto_testa_anche_se_in_whitelist() -> None:
    """Sentinella: la stazione_sede stessa NON deve essere in whitelist
    per logica di consumo (la whitelist sono "vicine"). Anche se per
    qualche motivo il pianificatore l'avesse messa, la condizione `!=
    stazione_localita` impedisce comunque il vuoto."""
    wl_with_sede = frozenset({"MI_FIO", "MI_CADORNA", "BG"})
    a = _c("MI_FIO", "BG", (8, 0), (9, 0))
    cat = Catena(corse=(a,))
    res = posiziona_su_localita(cat, LOC_FIORENZA, wl_with_sede)
    assert res.vuoto_testa is None  # parte da sede, niente vuoto
    assert res.vuoto_coda is not None  # BG in whitelist, coda OK
    assert res.chiusa_a_localita is True


def test_smoke_realistico_tirano_multi_giornata() -> None:
    """Caso reale Mi.Centrale↔Tirano (Sprint 5.6 anticipato): il treno
    parte da Mi.Centrale al mattino, fa Centrale→Tirano e Tirano→Centrale
    alternati, dorme a Tirano la sera. La giornata di andata chiude
    con vuoto coda Mi.Centrale→MI_FIO. Quella intermedia (T→C→T) ha
    chiusa=False (il treno dorme a Tirano)."""
    # Giornata 1: parte da Mi.Centrale (in whitelist), fa servizio, dorme a Tirano
    g1 = Catena(
        corse=(
            _c("MI_CENTRALE", "TIRANO", (6, 30), (10, 0)),
            _c("TIRANO", "MI_CENTRALE", (11, 0), (14, 30)),
            _c("MI_CENTRALE", "TIRANO", (15, 30), (19, 0)),  # dorme a Tirano
        )
    )
    wl_centrale = frozenset({"MI_CENTRALE", "MI_CADORNA"})
    r1 = posiziona_su_localita(g1, LOC_FIORENZA, wl_centrale)
    # Prima parte da MI_CENTRALE (in whitelist) → genera vuoto testa
    assert r1.vuoto_testa is not None
    assert r1.vuoto_testa.codice_origine == "MI_FIO"
    assert r1.vuoto_testa.codice_destinazione == "MI_CENTRALE"
    # Ultima arriva a TIRANO (fuori whitelist) → no vuoto coda
    assert r1.vuoto_coda is None
    assert r1.chiusa_a_localita is False, "Il treno dorme a Tirano"
