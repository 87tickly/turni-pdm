"""
Builder V2 — turno materiale → lista PdC applicando NORMATIVA-PDC.

Endpoint REST del nuovo builder implementato in
`src/turn_builder/material_to_pdc.py`. Produce turni PdC da una lista
di segmenti materiale, senza toccare il builder genetico legacy.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.turn_builder.material_to_pdc import (
    CoverResult,
    EventoKind,
    EventoPdC,
    MaterialPool,
    PdC,
    Segment,
    SegmentKind,
    build_single_pdc,
    cap_prestazione,
    cover_material,
    hhmm_to_min,
    min_to_hhmm,
    validate_pdc,
)

router = APIRouter(prefix="/api/builder-v2", tags=["builder_v2"])


# ---------------------------------------------------------------------------
# Pydantic payloads
# ---------------------------------------------------------------------------


class SegmentIn(BaseModel):
    numero: str
    kind: str = Field(
        ...,
        description="commerciale | vuoto_i | vuoto_u",
    )
    da_stazione: str
    a_stazione: str
    partenza: str = Field(..., description="HH:MM")
    arrivo: str = Field(..., description="HH:MM")


class CoverRequest(BaseModel):
    materiale: list[SegmentIn]
    deposito_preferito: Optional[str] = Field(
        None,
        description=(
            "Deposito da preferire per i PdC MI.PG-related. "
            "Default: GARIBALDI_ALE."
        ),
    )


class EventoOut(BaseModel):
    kind: str
    inizio: str
    fine: str
    durata_min: int
    stazione: str = ""
    stazione_a: str = ""
    treno: str = ""
    note: str = ""


class PdCOut(BaseModel):
    deposito: str
    presa_servizio: str
    fine_servizio: str
    prestazione_min: int
    condotta_min: int
    cap_prestazione_min: int
    eventi: list[EventoOut]
    violazioni: list[str]


class CoverResponse(BaseModel):
    pdc: list[PdCOut]
    residui_numeri: list[str]
    residui_count: int
    violazioni_totali: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _segment_from_in(s: SegmentIn) -> Segment:
    try:
        kind = SegmentKind(s.kind)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"kind sconosciuto: {s.kind!r} "
                   f"(attesi: commerciale / vuoto_i / vuoto_u)",
        )
    try:
        partenza = hhmm_to_min(s.partenza)
        arrivo = hhmm_to_min(s.arrivo)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"orario non valido su {s.numero}: {e}",
        )
    return Segment(
        numero=s.numero,
        kind=kind,
        da_stazione=s.da_stazione.upper(),
        a_stazione=s.a_stazione.upper(),
        partenza_min=partenza,
        arrivo_min=arrivo,
    )


def _pdc_to_out(pdc: PdC) -> PdCOut:
    s = pdc.presa_servizio_min or 0
    e = pdc.fine_servizio_min or 0
    return PdCOut(
        deposito=pdc.deposito,
        presa_servizio=min_to_hhmm(s),
        fine_servizio=min_to_hhmm(e),
        prestazione_min=pdc.prestazione_min,
        condotta_min=pdc.condotta_min,
        cap_prestazione_min=cap_prestazione(s),
        eventi=[
            EventoOut(
                kind=ev.kind.value,
                inizio=min_to_hhmm(ev.inizio_min),
                fine=min_to_hhmm(ev.fine_min),
                durata_min=ev.durata_min,
                stazione=ev.stazione,
                stazione_a=ev.stazione_a,
                treno=ev.treno,
                note=ev.note,
            )
            for ev in pdc.eventi
        ],
        violazioni=validate_pdc(pdc),
    )


def _default_scegli_deposito_factory(pref: Optional[str]):
    """Strategia default: PdC MI.PG per segmenti Mi/FIOz, Sondrio per
    Valtellina, Lecco per Lecco; fallback a `pref` o GARIBALDI_ALE."""
    fallback = pref or "GARIBALDI_ALE"

    def scegli(seg: Segment) -> str:
        da = seg.da_stazione.upper()
        if "FIOR" in da or "CERTOSA" in da or "MI." in da or "MILANO" in da:
            return fallback
        if "TIRANO" in da or "SONDRIO" in da:
            return "SONDRIO"
        if "LECCO" in da:
            return "LECCO"
        return fallback

    return scegli


def _stub_vettura_lookup(
    da: str, a: str, after_min: int
):
    """Stub provvisorio per la vettura di rientro: ritorna sempre una
    finestra stimata di 60 min. Sarà sostituito da query ARTURO in step
    futuro."""
    return (after_min, after_min + 60, f"V-{da[:3]}-{a[:3]}")


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/cover", response_model=CoverResponse)
def cover(req: CoverRequest) -> CoverResponse:
    """Copre un turno materiale con una lista di PdC validi.

    Input: lista di segmenti con orari HH:MM.
    Output: lista PdC (con eventi, violazioni) + residui.
    """
    if not req.materiale:
        raise HTTPException(400, "materiale vuoto")

    segments = [_segment_from_in(s) for s in req.materiale]
    scegli = _default_scegli_deposito_factory(req.deposito_preferito)

    result: CoverResult = cover_material(
        segments,
        scegli_deposito=scegli,
        vettura_lookup=_stub_vettura_lookup,
    )

    return CoverResponse(
        pdc=[_pdc_to_out(p) for p in result.pdc_list],
        residui_numeri=[r.numero for r in result.residui],
        residui_count=len(result.residui),
        violazioni_totali=result.violazioni_totali,
    )


@router.get("/example/p1-1130")
def example_p1_1130() -> CoverRequest:
    """Payload di esempio: P1 turno materiale 1130 (Valtellina).

    Utile al frontend per pre-popolare la textarea con un caso reale.
    """
    return CoverRequest(
        materiale=[
            SegmentIn(numero="U8335", kind="vuoto_u",
                      da_stazione="FIORENZA", a_stazione="MI.CERTOSA",
                      partenza="05:18", arrivo="05:25"),
            SegmentIn(numero="28335i", kind="vuoto_i",
                      da_stazione="MI.CERTOSA", a_stazione="MI.C.LE",
                      partenza="05:25", arrivo="05:45"),
            SegmentIn(numero="2812", kind="commerciale",
                      da_stazione="MI.C.LE", a_stazione="TIRANO",
                      partenza="06:20", arrivo="08:52"),
            SegmentIn(numero="2821", kind="commerciale",
                      da_stazione="TIRANO", a_stazione="MI.C.LE",
                      partenza="09:08", arrivo="11:40"),
            SegmentIn(numero="2824", kind="commerciale",
                      da_stazione="MI.C.LE", a_stazione="TIRANO",
                      partenza="12:20", arrivo="14:52"),
            SegmentIn(numero="2833", kind="commerciale",
                      da_stazione="TIRANO", a_stazione="MI.C.LE",
                      partenza="15:08", arrivo="17:40"),
            SegmentIn(numero="2836", kind="commerciale",
                      da_stazione="MI.C.LE", a_stazione="TIRANO",
                      partenza="18:20", arrivo="20:52"),
            SegmentIn(numero="28371i", kind="vuoto_i",
                      da_stazione="TIRANO", a_stazione="SONDRIO",
                      partenza="21:25", arrivo="22:00"),
        ],
        deposito_preferito="GARIBALDI_ALE",
    )
