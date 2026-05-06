"""Test puri MR-1110 Step 3 — ``genera_varianti_calendariali``.

Coprono: raggruppamento per sequenza-treni, etichette parlanti,
calcolo prestazione/km, ordinamento varianti, casi degenere.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

from colazione.domain.builder_giro.catena import Catena
from colazione.domain.builder_giro.giornata_tipo import (
    CatenaIstanza,
    GiornataTipo,
)
from colazione.domain.builder_giro.posizionamento import (
    BloccoMaterialeVuoto,
    CatenaPosizionata,
)
from colazione.domain.builder_giro.varianti_calendariali import (
    GiornataTipoConVarianti,
    VarianteCalendariale,
    genera_varianti_calendariali,
)
from colazione.domain.calendario import festivita_italiane

# =====================================================================
# Setup
# =====================================================================

PERIODO_2026 = (date(2026, 1, 1), date(2026, 12, 31))


def _festivita_2026() -> frozenset[date]:
    return frozenset(d for d, _n in festivita_italiane(2026))


FESTIVITA_2026 = _festivita_2026()


@dataclass
class FakeCorsa:
    codice_origine: str
    codice_destinazione: str
    ora_partenza: time
    ora_arrivo: time
    numero_treno: str = ""
    km_tratta: float | None = None


def _c(
    o: str,
    d: str,
    p: tuple[int, int],
    a: tuple[int, int],
    *,
    numero_treno: str = "",
    km: float | None = None,
) -> FakeCorsa:
    return FakeCorsa(o, d, time(*p), time(*a), numero_treno=numero_treno, km_tratta=km)


def _cat_pos(
    *,
    corse: tuple[FakeCorsa, ...],
    vuoto_testa: BloccoMaterialeVuoto | None = None,
    vuoto_coda: BloccoMaterialeVuoto | None = None,
) -> CatenaPosizionata:
    return CatenaPosizionata(
        localita_codice="FIO",
        stazione_collegata="MI.CERT",
        vuoto_testa=vuoto_testa,
        catena=Catena(corse=corse),
        vuoto_coda=vuoto_coda,
        chiusa_a_localita=True,
    )


def _ist(*, data_: date, corse: tuple[FakeCorsa, ...]) -> CatenaIstanza:
    return CatenaIstanza(
        data=data_,
        catena_posizionata=_cat_pos(corse=corse),
        materiale_tipo_codice="ETR421",
    )


def _make_gt(istanze: list[CatenaIstanza]) -> GiornataTipo:
    return GiornataTipo(
        materiale_tipo_codice="ETR421",
        localita_codice="FIO",
        staz_inizio=istanze[0].catena_posizionata.catena.corse[0].codice_origine,
        staz_fine=istanze[0].catena_posizionata.catena.corse[-1].codice_destinazione,
        codice_servizio_dominante="S5",
        istanze=tuple(istanze),
    )


# =====================================================================
# Casi base
# =====================================================================


def test_giornata_senza_istanze_zero_varianti() -> None:
    gt = GiornataTipo(
        materiale_tipo_codice="ETR421",
        localita_codice="FIO",
        staz_inizio="A",
        staz_fine="B",
        codice_servizio_dominante=None,
        istanze=(),
    )
    out = genera_varianti_calendariali(gt, FESTIVITA_2026, PERIODO_2026)
    assert isinstance(out, GiornataTipoConVarianti)
    assert out.varianti == ()


def test_due_istanze_stessa_sequenza_una_variante() -> None:
    """2 istanze identiche in 2 date → 1 variante con dates_apply
    (D_LUN, D_MAR).
    """
    seq = (_c("VARESE", "MI.CERT", (8, 0), (9, 0), numero_treno="24519", km=50.0),)
    ist_lun = _ist(data_=date(2026, 4, 27), corse=seq)
    ist_mar = _ist(data_=date(2026, 4, 28), corse=seq)
    gt = _make_gt([ist_lun, ist_mar])

    out = genera_varianti_calendariali(gt, FESTIVITA_2026, PERIODO_2026)
    assert len(out.varianti) == 1
    v = out.varianti[0]
    assert v.dates_apply == frozenset(
        {date(2026, 4, 27), date(2026, 4, 28)}
    )
    assert v.km_giornaliera == 50.0
    # Prestazione = 9:00 - 8:00 = 60 min
    assert v.prestazione_minuti == 60


def test_due_sequenze_diverse_due_varianti() -> None:
    """2 istanze con sequenze-treni diverse → 2 varianti distinte."""
    seq_a = (_c("VARESE", "MI.CERT", (8, 0), (9, 0), numero_treno="24519", km=50.0),)
    seq_b = (_c("VARESE", "MI.CERT", (10, 0), (11, 0), numero_treno="24521", km=50.0),)
    ist_lun = _ist(data_=date(2026, 4, 27), corse=seq_a)
    ist_mar = _ist(data_=date(2026, 4, 28), corse=seq_b)
    gt = _make_gt([ist_lun, ist_mar])

    out = genera_varianti_calendariali(gt, FESTIVITA_2026, PERIODO_2026)
    assert len(out.varianti) == 2


# =====================================================================
# Etichette parlanti
# =====================================================================


def test_variante_lv_1_5_etichetta_corretta() -> None:
    """Istanze in tutti i lavorativi 1-5 del periodo → variante con
    etichetta 'LV 1:5'.
    """
    seq = (_c("VARESE", "MI.CERT", (8, 0), (9, 0), numero_treno="24519", km=50.0),)
    from datetime import timedelta

    inizio, fine = PERIODO_2026
    n = (fine - inizio).days
    istanze = []
    for i in range(n + 1):
        d = inizio + timedelta(days=i)
        if d.weekday() in (0, 1, 2, 3, 4) and d not in FESTIVITA_2026:
            istanze.append(_ist(data_=d, corse=seq))

    gt = _make_gt(istanze)
    out = genera_varianti_calendariali(gt, FESTIVITA_2026, PERIODO_2026)
    assert len(out.varianti) == 1
    assert out.varianti[0].etichetta == "LV 1:5"


def test_variante_si_eff_due_date_specifiche() -> None:
    """Istanze solo 22/3 e 12/4 → etichetta 'Si eff. 22/3, 12/4'."""
    seq = (_c("MI.CERT", "MI.CERT", (10, 0), (12, 0), numero_treno="MCPTC", km=0.0),)
    istanze = [
        _ist(data_=date(2026, 3, 22), corse=seq),
        _ist(data_=date(2026, 4, 12), corse=seq),
    ]
    gt = _make_gt(istanze)
    out = genera_varianti_calendariali(gt, FESTIVITA_2026, PERIODO_2026)
    assert len(out.varianti) == 1
    assert out.varianti[0].etichetta == "Si eff. 22/3, 12/4"
    assert out.varianti[0].km_giornaliera == 0.0
    assert out.varianti[0].prestazione_minuti == 120  # 10:00 → 12:00


# =====================================================================
# Calcolo prestazione/km
# =====================================================================


def test_prestazione_con_vuoto_testa_e_coda() -> None:
    """Prestazione include vuoti tecnici testa/coda."""
    vuoto_testa = BloccoMaterialeVuoto(
        codice_origine="FIO",
        codice_destinazione="VARESE",
        ora_partenza=time(7, 30),
        ora_arrivo=time(7, 50),
        motivo="testa",
    )
    vuoto_coda = BloccoMaterialeVuoto(
        codice_origine="MI.CERT",
        codice_destinazione="FIO",
        ora_partenza=time(13, 10),
        ora_arrivo=time(13, 30),
        motivo="coda",
    )
    seq = (_c("VARESE", "MI.CERT", (8, 0), (13, 0), numero_treno="24519", km=131.57),)
    cat_pos_full = CatenaPosizionata(
        localita_codice="FIO",
        stazione_collegata="FIO",
        vuoto_testa=vuoto_testa,
        catena=Catena(corse=seq),
        vuoto_coda=vuoto_coda,
        chiusa_a_localita=True,
    )
    ist = CatenaIstanza(
        data=date(2026, 4, 27),
        catena_posizionata=cat_pos_full,
        materiale_tipo_codice="ETR421",
    )
    ist_due = CatenaIstanza(
        data=date(2026, 4, 28),
        catena_posizionata=cat_pos_full,
        materiale_tipo_codice="ETR421",
    )
    gt = GiornataTipo(
        materiale_tipo_codice="ETR421",
        localita_codice="FIO",
        staz_inizio="VARESE",
        staz_fine="MI.CERT",
        codice_servizio_dominante="S5",
        istanze=(ist, ist_due),
    )
    out = genera_varianti_calendariali(gt, FESTIVITA_2026, PERIODO_2026)
    v = out.varianti[0]
    # Prestazione = 13:30 - 7:30 = 360 minuti
    assert v.prestazione_minuti == 360
    assert v.km_giornaliera == 131.57


def test_prestazione_cross_mezzanotte() -> None:
    """Servizio cross-mezzanotte: prestazione = (arrivo - partenza)
    + 1440.
    """
    seq = (
        _c(
            "MI.CERT",
            "VARESE",
            (22, 30),
            (1, 0),
            numero_treno="LATE",
            km=80.0,
        ),
    )
    ist1 = _ist(data_=date(2026, 4, 27), corse=seq)
    ist2 = _ist(data_=date(2026, 4, 28), corse=seq)
    gt = _make_gt([ist1, ist2])
    out = genera_varianti_calendariali(gt, FESTIVITA_2026, PERIODO_2026)
    v = out.varianti[0]
    # Da 22:30 a 01:00 → 150 min
    assert v.prestazione_minuti == 150


# =====================================================================
# Ordinamento + acceptance
# =====================================================================


def test_varianti_ordinate_per_dates_apply_desc() -> None:
    """Variante con più date prima della variante con meno date."""
    seq_principale = (
        _c("V", "M", (8, 0), (9, 0), numero_treno="A", km=50.0),
    )
    seq_minore = (
        _c("V", "M", (10, 0), (11, 0), numero_treno="B", km=50.0),
    )
    # 5 istanze su seq_principale, 2 su seq_minore
    from datetime import timedelta

    istanze_principali = [
        _ist(data_=date(2026, 4, 27) + timedelta(days=i), corse=seq_principale)
        for i in range(5)
    ]
    istanze_minori = [
        _ist(data_=date(2026, 6, 1) + timedelta(days=i), corse=seq_minore)
        for i in range(2)
    ]
    gt = _make_gt(istanze_principali + istanze_minori)
    out = genera_varianti_calendariali(gt, FESTIVITA_2026, PERIODO_2026)
    assert len(out.varianti) == 2
    # La prima è la più popolata
    assert len(out.varianti[0].dates_apply) == 5
    assert len(out.varianti[1].dates_apply) == 2


def test_giornata_tipo_con_varianti_forwarder_property() -> None:
    """GiornataTipoConVarianti espone le proprietà della giornata-tipo
    via property forwarder.
    """
    seq = (_c("V", "M", (8, 0), (9, 0), numero_treno="A", km=10.0),)
    gt = _make_gt(
        [
            _ist(data_=date(2026, 4, 27), corse=seq),
            _ist(data_=date(2026, 4, 28), corse=seq),
        ]
    )
    out = genera_varianti_calendariali(gt, FESTIVITA_2026, PERIODO_2026)
    assert out.materiale_tipo_codice == "ETR421"
    assert out.localita_codice == "FIO"
    assert out.staz_inizio == "V"
    assert out.staz_fine == "M"
    assert out.codice_servizio_dominante == "S5"


def test_acceptance_turno_1110_g6_genera_6_varianti() -> None:
    """Modello concettuale del turno 1110 G6: 6 sequenze-treni
    distinte sulle istanze → 6 varianti calendariali.

    Test a fixture sintetica — ogni "sequenza" è simulata da un
    numero treno diverso così il chiavaggio le separa correttamente.
    """
    # 6 sequenze diverse (rappresentano le 6 varianti del PDF)
    sequenze = [
        (_c("VARESE", "MI.CERT", (6, 30), (7, 30), numero_treno=f"S{i}", km=131.57),)
        for i in range(6)
    ]
    istanze: list[CatenaIstanza] = []
    # 5 istanze per ciascuna sequenza (così tutte sono varianti
    # significative)
    from datetime import timedelta

    for i, seq in enumerate(sequenze):
        for j in range(5):
            d = date(2026, 4, 1) + timedelta(days=(i * 30 + j))
            istanze.append(_ist(data_=d, corse=seq))

    gt = _make_gt(istanze)
    out = genera_varianti_calendariali(gt, FESTIVITA_2026, PERIODO_2026)
    assert len(out.varianti) == 6
    # Ogni variante ha 5 dates_apply
    for v in out.varianti:
        assert len(v.dates_apply) == 5


def test_dataclass_e_frozen() -> None:
    import dataclasses

    seq = (_c("V", "M", (8, 0), (9, 0), numero_treno="A", km=10.0),)
    gt = _make_gt(
        [
            _ist(data_=date(2026, 4, 27), corse=seq),
            _ist(data_=date(2026, 4, 28), corse=seq),
        ]
    )
    out = genera_varianti_calendariali(gt, FESTIVITA_2026, PERIODO_2026)
    v = out.varianti[0]
    try:
        v.km_giornaliera = 999.0  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:
        raise AssertionError("VarianteCalendariale doveva essere frozen")


def _check_unused() -> None:
    """Sanity di compilazione: VarianteCalendariale è esposto."""
    assert VarianteCalendariale is not None
