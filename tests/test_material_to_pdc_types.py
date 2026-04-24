"""Test sui tipi base di material_to_pdc (step 2 ALGORITMO-BUILDER).

Verifica Segment, EventoPdC, PdC, MaterialPool + utility tempo.
Scenario reale usato: P1 del turno materiale 1130 (Valtellina),
letto in sessione 2026-04-24 con l'utente.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.turn_builder.material_to_pdc import (
    EventoKind,
    EventoPdC,
    MaterialPool,
    PdC,
    Segment,
    SegmentKind,
    hhmm_to_min,
    min_to_hhmm,
)


# ---------------------------------------------------------------------------
# Utility tempo
# ---------------------------------------------------------------------------


class TestTimeUtils:
    def test_hhmm_to_min_basic(self):
        assert hhmm_to_min("00:00") == 0
        assert hhmm_to_min("04:10") == 250
        assert hhmm_to_min("12:20") == 740
        assert hhmm_to_min("23:59") == 1439

    def test_min_to_hhmm_basic(self):
        assert min_to_hhmm(0) == "00:00"
        assert min_to_hhmm(250) == "04:10"
        assert min_to_hhmm(740) == "12:20"
        assert min_to_hhmm(1439) == "23:59"

    def test_roundtrip(self):
        for s in ["05:25", "08:52", "11:40", "22:00"]:
            assert min_to_hhmm(hhmm_to_min(s)) == s

    def test_hhmm_invalid(self):
        with pytest.raises(ValueError):
            hhmm_to_min("25:00")
        with pytest.raises(ValueError):
            hhmm_to_min("12:60")

    def test_min_invalid(self):
        with pytest.raises(ValueError):
            min_to_hhmm(-1)
        with pytest.raises(ValueError):
            min_to_hhmm(1440)


# ---------------------------------------------------------------------------
# Segment
# ---------------------------------------------------------------------------


class TestSegment:
    def test_28335i_vuoto_i(self):
        """28335i: vuoto "i" di testa giornata, P1 1130."""
        seg = Segment(
            numero="28335i",
            kind=SegmentKind.VUOTO_I,
            da_stazione="MI.CERTOSA",
            a_stazione="MI.C.LE",
            partenza_min=hhmm_to_min("05:25"),
            arrivo_min=hhmm_to_min("05:45"),
        )
        assert seg.durata_min == 20
        assert seg.kind == SegmentKind.VUOTO_I

    def test_2812_commerciale(self):
        """2812: commerciale MICL→Tirano durata 2:32."""
        seg = Segment(
            numero="2812",
            kind=SegmentKind.COMMERCIALE,
            da_stazione="MI.C.LE",
            a_stazione="TIRANO",
            partenza_min=hhmm_to_min("06:20"),
            arrivo_min=hhmm_to_min("08:52"),
        )
        assert seg.durata_min == 152  # 2h32

    def test_u8335_calcolato(self):
        """U8335: vuoto aziendale FIOz→MiCertosa, 7' prima del commerciale."""
        seg = Segment(
            numero="U8335",
            kind=SegmentKind.VUOTO_U,
            da_stazione="FIORENZA",
            a_stazione="MI.CERTOSA",
            partenza_min=hhmm_to_min("05:18"),
            arrivo_min=hhmm_to_min("05:25"),
        )
        assert seg.durata_min == 7  # §8.5

    def test_repr(self):
        seg = Segment("2812", SegmentKind.COMMERCIALE, "A", "B", 380, 532)
        r = repr(seg)
        assert "2812" in r
        assert "06:20" in r
        assert "08:52" in r

    def test_hashable_and_frozen(self):
        """Segment è immutabile e hashable (per uso in set/dict)."""
        seg = Segment("1", SegmentKind.COMMERCIALE, "A", "B", 0, 10)
        with pytest.raises(Exception):
            seg.numero = "2"  # frozen
        _ = {seg}  # set OK
        _ = {seg: "x"}  # dict key OK


# ---------------------------------------------------------------------------
# MaterialPool
# ---------------------------------------------------------------------------


def _segmenti_p1() -> list[Segment]:
    """Segmenti P1 turno materiale 1130 (letti con l'utente 2026-04-24)."""
    return [
        Segment("U8335", SegmentKind.VUOTO_U, "FIORENZA", "MI.CERTOSA",
                hhmm_to_min("05:18"), hhmm_to_min("05:25")),
        Segment("28335i", SegmentKind.VUOTO_I, "MI.CERTOSA", "MI.C.LE",
                hhmm_to_min("05:25"), hhmm_to_min("05:45")),
        Segment("2812", SegmentKind.COMMERCIALE, "MI.C.LE", "TIRANO",
                hhmm_to_min("06:20"), hhmm_to_min("08:52")),
        Segment("2821", SegmentKind.COMMERCIALE, "TIRANO", "MI.C.LE",
                hhmm_to_min("09:08"), hhmm_to_min("11:40")),
        Segment("2824", SegmentKind.COMMERCIALE, "MI.C.LE", "TIRANO",
                hhmm_to_min("12:20"), hhmm_to_min("14:52")),
        Segment("2833", SegmentKind.COMMERCIALE, "TIRANO", "MI.C.LE",
                hhmm_to_min("15:08"), hhmm_to_min("17:40")),
        Segment("2836", SegmentKind.COMMERCIALE, "MI.C.LE", "TIRANO",
                hhmm_to_min("18:20"), hhmm_to_min("20:52")),
        Segment("28371i", SegmentKind.VUOTO_I, "TIRANO", "SONDRIO",
                hhmm_to_min("21:25"), hhmm_to_min("22:00")),
    ]


class TestMaterialPool:
    def test_pool_inizialmente_piena(self):
        pool = MaterialPool(segments=_segmenti_p1())
        assert not pool.is_empty()
        assert len(pool.segments) == 8

    def test_first_prende_u8335(self):
        """Il primo segmento è U8335 (partenza 05:18)."""
        pool = MaterialPool(segments=_segmenti_p1())
        first = pool.first()
        assert first is not None
        assert first.numero == "U8335"

    def test_remove_e_is_empty(self):
        pool = MaterialPool(segments=_segmenti_p1())
        for s in list(pool.segments):
            pool.remove(s)
        assert pool.is_empty()

    def test_next_same_material_u8335_to_28335i(self):
        """U8335 finisce MI.CERTOSA 05:25, 28335i parte MI.CERTOSA 05:25 ✓"""
        pool = MaterialPool(segments=_segmenti_p1())
        u8335 = next(s for s in pool.segments if s.numero == "U8335")
        nxt = pool.next_same_material(u8335)
        assert nxt is not None
        assert nxt.numero == "28335i"

    def test_next_same_material_28335i_to_2812(self):
        """28335i finisce MI.C.LE 05:45, 2812 parte MI.C.LE 06:20 (gap 35')"""
        pool = MaterialPool(segments=_segmenti_p1())
        seg = next(s for s in pool.segments if s.numero == "28335i")
        nxt = pool.next_same_material(seg)
        assert nxt is not None
        assert nxt.numero == "2812"

    def test_next_same_material_rispetta_stazione(self):
        """2812 finisce TIRANO, il prossimo da TIRANO è 2821 (non da MICL)."""
        pool = MaterialPool(segments=_segmenti_p1())
        seg = next(s for s in pool.segments if s.numero == "2812")
        nxt = pool.next_same_material(seg)
        assert nxt is not None
        assert nxt.numero == "2821"

    def test_next_same_material_ultimo_none(self):
        """28371i arriva SONDRIO, nessun successivo nella pool."""
        pool = MaterialPool(segments=_segmenti_p1())
        seg = next(s for s in pool.segments if s.numero == "28371i")
        assert pool.next_same_material(seg) is None

    def test_remove_many_rimuove_catena(self):
        pool = MaterialPool(segments=_segmenti_p1())
        to_remove = [s for s in pool.segments
                     if s.numero in ("U8335", "28335i", "2812")]
        pool.remove_many(to_remove)
        assert len(pool.segments) == 5
        assert all(s.numero not in ("U8335", "28335i", "2812")
                   for s in pool.segments)


# ---------------------------------------------------------------------------
# EventoPdC + PdC
# ---------------------------------------------------------------------------


def _pdc_1_di_p1() -> PdC:
    """PdC 1 stilato a mano in sessione (scenario S1: CV Lecco).

    Presa servizio MI.PG 04:10, taxi FIOz, ACCp, condotta 28335i +
    2812 fino Lecco, CV Lecco, vettura rientro, fine ~08:20.
    """
    u8335 = Segment("U8335", SegmentKind.VUOTO_U, "FIORENZA", "MI.CERTOSA",
                    hhmm_to_min("05:18"), hhmm_to_min("05:25"))
    v28335i = Segment("28335i", SegmentKind.VUOTO_I, "MI.CERTOSA", "MI.C.LE",
                      hhmm_to_min("05:25"), hhmm_to_min("05:45"))
    v2812_pre = Segment("2812", SegmentKind.COMMERCIALE, "MI.C.LE", "LECCO",
                        hhmm_to_min("06:20"), hhmm_to_min("06:59"))

    eventi = [
        EventoPdC(EventoKind.PRESA_SERVIZIO,
                  hhmm_to_min("04:10"), hhmm_to_min("04:10"),
                  stazione="MI.PG"),
        EventoPdC(EventoKind.TAXI,
                  hhmm_to_min("04:25"), hhmm_to_min("04:45"),
                  stazione="MI.PG", stazione_a="FIORENZA"),
        EventoPdC(EventoKind.ACCP,
                  hhmm_to_min("04:45"), hhmm_to_min("05:25"),
                  stazione="FIORENZA", note="40' include U8335"),
        EventoPdC(EventoKind.CONDOTTA,
                  hhmm_to_min("05:18"), hhmm_to_min("05:25"),
                  stazione="FIORENZA", stazione_a="MI.CERTOSA",
                  segment=u8335, treno="U8335"),
        EventoPdC(EventoKind.CONDOTTA,
                  hhmm_to_min("05:25"), hhmm_to_min("05:45"),
                  stazione="MI.CERTOSA", stazione_a="MI.C.LE",
                  segment=v28335i, treno="28335i"),
        EventoPdC(EventoKind.BUCO,
                  hhmm_to_min("05:45"), hhmm_to_min("06:20"),
                  stazione="MI.C.LE", note="35' gap stesso materiale"),
        EventoPdC(EventoKind.CONDOTTA,
                  hhmm_to_min("06:20"), hhmm_to_min("06:59"),
                  stazione="MI.C.LE", stazione_a="LECCO",
                  segment=v2812_pre, treno="2812"),
        EventoPdC(EventoKind.CVA,
                  hhmm_to_min("06:59"), hhmm_to_min("07:02"),
                  stazione="LECCO", note="consegna a PdC2 Lecco"),
        # vettura rientro + fine servizio (placeholder orari)
        EventoPdC(EventoKind.FINE_SERVIZIO,
                  hhmm_to_min("08:20"), hhmm_to_min("08:20"),
                  stazione="MI.PG"),
    ]
    return PdC(deposito="MI.PG", eventi=eventi)


class TestPdC:
    def test_presa_e_fine_servizio(self):
        p = _pdc_1_di_p1()
        assert p.presa_servizio_min == hhmm_to_min("04:10")
        assert p.fine_servizio_min == hhmm_to_min("08:20")

    def test_prestazione_4h10(self):
        """PdC 1 S1 = 4h10 prestazione."""
        p = _pdc_1_di_p1()
        assert p.prestazione_min == 250  # 4h10

    def test_condotta_66min(self):
        """Condotta: 7 (U8335) + 20 (28335i) + 39 (2812→Lecco) = 66'."""
        p = _pdc_1_di_p1()
        assert p.condotta_min == 66

    def test_segmenti_usati_3(self):
        """Segmenti consumati dal PdC: U8335, 28335i, 2812(parte)."""
        p = _pdc_1_di_p1()
        used = p.segmenti_usati
        assert len(used) == 3
        numeri = {s.numero for s in used}
        assert numeri == {"U8335", "28335i", "2812"}

    def test_no_refez_sotto_6h(self):
        """Prestazione 4h10 < 6h → REFEZ non inserita, ha_refez False."""
        p = _pdc_1_di_p1()
        assert p.ha_refez is False

    def test_pdc_vuoto_proiezioni(self):
        p = PdC(deposito="MI.PG")
        assert p.presa_servizio_min is None
        assert p.fine_servizio_min is None
        assert p.prestazione_min == 0
        assert p.condotta_min == 0
        assert p.segmenti_usati == []

    def test_repr_utile(self):
        p = _pdc_1_di_p1()
        r = repr(p)
        assert "MI.PG" in r
        assert "04:10" in r
        assert "08:20" in r


# ---------------------------------------------------------------------------
# Integrazione: PdC 1 consuma 3 segmenti → pool scende a 5
# §15 NORMATIVA-PDC (no doppioni)
# ---------------------------------------------------------------------------


class TestPoolPdCIntegration:
    def test_pool_dopo_pdc1_cinque_segmenti(self):
        pool = MaterialPool(segments=_segmenti_p1())
        pdc1 = _pdc_1_di_p1()

        # Simula rimozione dei segmenti consumati (logica §15 poi
        # farà cover_material()).
        for s in pdc1.segmenti_usati:
            # Il pool ha l'intero 2812 (MICL→TIRANO), mentre il PdC1
            # ha usato solo 2812(MICL→LECCO). Per ora, rimuovo i
            # segmenti della pool che matchano per numero + estremi
            # identici. Per il 2812 parziale test usa numero.
            matches = [p for p in pool.segments if p.numero == s.numero]
            if matches:
                pool.remove(matches[0])

        # U8335, 28335i rimossi completamente. 2812 rimosso (sarà spezzato
        # nello step successivo: pre-CV consumato, post-CV nuovo segmento).
        # Per ora la pool scende di 3.
        assert len(pool.segments) == 5
        residui = {s.numero for s in pool.segments}
        assert residui == {"2821", "2824", "2833", "2836", "28371i"}
