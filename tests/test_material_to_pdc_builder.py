"""Test end-to-end per il builder material_to_pdc.

Scenario: P1 turno materiale 1130 (Valtellina), letto e validato in
sessione con l'utente 2026-04-24. 8 segmenti, 05:18 → 22:00.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.turn_builder.material_to_pdc import (
    CoverResult,
    EventoKind,
    MaterialPool,
    PdC,
    Segment,
    SegmentKind,
    build_single_pdc,
    cap_prestazione,
    cover_material,
    gap_rule,
    GapMode,
    hhmm_to_min,
    min_to_hhmm,
    validate_pdc,
)


# ---------------------------------------------------------------------------
# Helper scenario P1 1130
# ---------------------------------------------------------------------------


def segmenti_p1_completo() -> list[Segment]:
    """Tutti gli 8 segmenti di P1 turno materiale 1130."""
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


def vettura_lookup_stub(
    da: str, a: str, after_min: int
):
    """Stub deterministico per test: restituisce una vettura fittizia
    con partenza immediata e durata 60 min."""
    # Ritorna (partenza_min, arrivo_min, numero_treno).
    return (after_min, after_min + 60, f"V-{da[:2]}-{a[:2]}")


# ---------------------------------------------------------------------------
# Sanity primitive
# ---------------------------------------------------------------------------


class TestPrimitive:
    def test_cap_prestazione_finestra_notte(self):
        assert cap_prestazione(hhmm_to_min("01:00")) == 420
        assert cap_prestazione(hhmm_to_min("03:00")) == 420
        assert cap_prestazione(hhmm_to_min("04:59")) == 420

    def test_cap_prestazione_finestra_diurna(self):
        assert cap_prestazione(hhmm_to_min("05:00")) == 510
        assert cap_prestazione(hhmm_to_min("12:00")) == 510
        assert cap_prestazione(hhmm_to_min("23:00")) == 510

    def test_gap_rule_piccolo(self):
        modes = gap_rule(30)
        assert GapMode.CV in modes and GapMode.PK in modes

    def test_gap_rule_medio(self):
        modes = gap_rule(120)
        assert GapMode.ACC in modes and GapMode.PK in modes
        assert GapMode.CV not in modes

    def test_gap_rule_grande(self):
        modes = gap_rule(500)
        assert GapMode.ACC in modes and GapMode.PK in modes


# ---------------------------------------------------------------------------
# build_single_pdc su P1
# ---------------------------------------------------------------------------


class TestBuildSinglePdC_P1:
    def test_primo_segmento_u8335_build_pdc_mipg(self):
        """PdC MI.PG prende il primo segmento (U8335 da Fiorenza)."""
        pool = MaterialPool(segments=segmenti_p1_completo())
        primo = pool.first()
        assert primo.numero == "U8335"
        pdc = build_single_pdc(
            primo, pool, "GARIBALDI_ALE",
            vettura_lookup=vettura_lookup_stub,
        )
        assert pdc.deposito == "GARIBALDI_ALE"
        assert len(pdc.eventi) > 0
        # Presa servizio nel finestra notte → cap 7h
        presa = pdc.presa_servizio_min
        assert presa is not None
        assert pdc.prestazione_min > 0

    def test_pdc_contiene_taxi_e_accp(self):
        pool = MaterialPool(segments=segmenti_p1_completo())
        primo = pool.first()
        pdc = build_single_pdc(
            primo, pool, "GARIBALDI_ALE",
            vettura_lookup=vettura_lookup_stub,
        )
        kinds = [e.kind for e in pdc.eventi]
        assert EventoKind.TAXI in kinds
        assert EventoKind.ACCP in kinds
        assert EventoKind.CONDOTTA in kinds

    def test_pdc_rispetta_cap_7h(self):
        pool = MaterialPool(segments=segmenti_p1_completo())
        primo = pool.first()
        pdc = build_single_pdc(
            primo, pool, "GARIBALDI_ALE",
            vettura_lookup=vettura_lookup_stub,
        )
        presa = pdc.presa_servizio_min
        cap = cap_prestazione(presa)
        # cap deve essere 420 (finestra notte)
        assert cap == 420
        assert pdc.prestazione_min <= cap

    def test_pdc_rispetta_condotta(self):
        pool = MaterialPool(segments=segmenti_p1_completo())
        primo = pool.first()
        pdc = build_single_pdc(
            primo, pool, "GARIBALDI_ALE",
            vettura_lookup=vettura_lookup_stub,
        )
        assert pdc.condotta_min <= 330


# ---------------------------------------------------------------------------
# validate_pdc
# ---------------------------------------------------------------------------


class TestValidate:
    def test_pdc_valido_nessuna_violazione(self):
        pool = MaterialPool(segments=segmenti_p1_completo())
        primo = pool.first()
        pdc = build_single_pdc(
            primo, pool, "GARIBALDI_ALE",
            vettura_lookup=vettura_lookup_stub,
        )
        viol = validate_pdc(pdc)
        assert viol == [], f"violazioni inattese: {viol}"

    def test_pdc_vuoto_segnala_errore(self):
        from src.turn_builder.material_to_pdc import PdC
        pdc = PdC(deposito="MI.PG")
        viol = validate_pdc(pdc)
        assert any("presa servizio" in v.lower() for v in viol)


# ---------------------------------------------------------------------------
# cover_material end-to-end su P1
# ---------------------------------------------------------------------------


def _scegli_deposito_valtellina(seg: Segment) -> str:
    """Strategia stub per P1: PdC GARIBALDI_ALE per Mi/FIOz, LECCO per
    segmenti che partono da stazioni lombarde/Valtellina."""
    da = seg.da_stazione.upper()
    if "FIOR" in da or "CERTOSA" in da or "MI.C" in da or "MILANO" in da:
        return "GARIBALDI_ALE"
    if "TIRANO" in da or "SONDRIO" in da:
        return "SONDRIO"
    if "LECCO" in da:
        return "LECCO"
    return "GARIBALDI_ALE"


class TestCoverMaterial_P1:
    def test_cover_produce_almeno_un_pdc(self):
        result = cover_material(
            segmenti_p1_completo(),
            scegli_deposito=_scegli_deposito_valtellina,
            vettura_lookup=vettura_lookup_stub,
        )
        assert len(result.pdc_list) >= 1
        assert isinstance(result, CoverResult)

    def test_cover_pool_vuota_o_ridotta(self):
        """Dopo cover, la pool residua deve essere ridotta rispetto ai 8
        segmenti iniziali."""
        result = cover_material(
            segmenti_p1_completo(),
            scegli_deposito=_scegli_deposito_valtellina,
            vettura_lookup=vettura_lookup_stub,
        )
        assert len(result.residui) < 8

    def test_cover_pdc_tutti_validi_o_viol_tracciate(self):
        """Ogni PdC prodotto è validabile; violazioni totali sono
        contate (possono essere >0 se lo stub vettura produce tempi
        non realistici, ma il meccanismo gira)."""
        result = cover_material(
            segmenti_p1_completo(),
            scegli_deposito=_scegli_deposito_valtellina,
            vettura_lookup=vettura_lookup_stub,
        )
        # Smoke check: tutti i pdc hanno almeno un evento
        for pdc in result.pdc_list:
            assert len(pdc.eventi) > 0
            assert pdc.presa_servizio_min is not None
        # Total violations è un int
        assert isinstance(result.violazioni_totali, int)

    def test_cover_no_doppioni_15(self):
        """§15: un segmento non compare in due PdC diversi."""
        result = cover_material(
            segmenti_p1_completo(),
            scegli_deposito=_scegli_deposito_valtellina,
            vettura_lookup=vettura_lookup_stub,
        )
        seen: set[str] = set()
        for pdc in result.pdc_list:
            for seg in pdc.segmenti_usati:
                key = f"{seg.numero}|{seg.partenza_min}|{seg.arrivo_min}"
                assert key not in seen, (
                    f"segmento {seg.numero} in piu' di un PdC"
                )
                seen.add(key)


# ---------------------------------------------------------------------------
# Stampe diagnostiche: utile per debug manuale
# ---------------------------------------------------------------------------


def test_diagnostic_stampa_pdc_p1(capsys):
    """Stampa la lista dei PdC prodotti (usare con -s per vederla)."""
    result = cover_material(
        segmenti_p1_completo(),
        scegli_deposito=_scegli_deposito_valtellina,
        vettura_lookup=vettura_lookup_stub,
    )
    print(f"\n--- P1 cover result ---")
    print(f"PdC prodotti: {len(result.pdc_list)}")
    print(f"Segmenti residui: {len(result.residui)}")
    print(f"Violazioni totali: {result.violazioni_totali}")
    for i, pdc in enumerate(result.pdc_list, 1):
        print(f"\nPdC {i}: {pdc}")
        for e in pdc.eventi:
            start = min_to_hhmm(e.inizio_min)
            end = min_to_hhmm(e.fine_min)
            treno = f" {e.treno}" if e.treno else ""
            print(f"  {start}-{end} {e.kind.value:<18}{treno} "
                  f"{e.stazione}{'→' + e.stazione_a if e.stazione_a else ''}"
                  f" {e.note}")
    # Non assert: questo test serve solo a vedere l'output con -s
