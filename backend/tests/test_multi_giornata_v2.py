"""Test orchestratore builder v2 — ``costruisci_turni_v2``.

Test end-to-end della pipeline MR-1110 (Step 2 → Step 3 → Step 4).
Verifica integrazione: catene-istanza → turni con varianti
calendariali concatenate ciclicamente.

Coprono:

- Caso vuoto.
- Singolo turno minimale (2 giornate-tipo concatenate, 1 variante
  ognuna).
- Acceptance turno 1110 G6 concettuale: 6 sequenze diverse sulla
  stessa fase → 1 giornata-tipo con 6 varianti calendariali con
  etichette parlanti.
- Multi-turno via SCC (D2): cicli disgiunti nello stesso gruppo.
- Coesistenza orfane (D3 sotto soglia + D2 non concatenabile).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time, timedelta

from colazione.domain.builder_giro.catena import Catena
from colazione.domain.builder_giro.giornata_tipo import CatenaIstanza
from colazione.domain.builder_giro.multi_giornata_v2 import (
    ParamBuilderV2,
    TurnoConVarianti,
    costruisci_turni_v2,
)
from colazione.domain.builder_giro.posizionamento import CatenaPosizionata
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
    codice_linea: str | None = "S5"
    km_tratta: float | None = None


def _c(
    o: str,
    d: str,
    p: tuple[int, int],
    a: tuple[int, int],
    *,
    numero_treno: str = "",
    codice_linea: str | None = "S5",
    km: float | None = 50.0,
) -> FakeCorsa:
    return FakeCorsa(o, d, time(*p), time(*a), numero_treno=numero_treno,
                     codice_linea=codice_linea, km_tratta=km)


def _cat_pos(corse: tuple[FakeCorsa, ...]) -> CatenaPosizionata:
    return CatenaPosizionata(
        localita_codice="FIO",
        stazione_collegata="MI.CERT",
        vuoto_testa=None,
        catena=Catena(corse=corse),
        vuoto_coda=None,
        chiusa_a_localita=True,
    )


def _ist(
    *,
    data_: date,
    corse: tuple[FakeCorsa, ...],
    materiale: str = "ETR421",
) -> CatenaIstanza:
    return CatenaIstanza(
        data=data_,
        catena_posizionata=_cat_pos(corse),
        materiale_tipo_codice=materiale,
    )


# =====================================================================
# Casi base
# =====================================================================


def test_input_vuoto() -> None:
    turni, orfane = costruisci_turni_v2(
        [], FESTIVITA_2026, PERIODO_2026
    )
    assert turni == []
    assert orfane == []


def test_singola_istanza_orfana_default_min_istanze_2() -> None:
    """1 sola istanza → orfana per filtro D3."""
    seq = (_c("V", "M", (8, 0), (9, 0), numero_treno="A", km=50.0),)
    ist = _ist(data_=date(2026, 4, 27), corse=seq)
    turni, orfane = costruisci_turni_v2(
        [ist], FESTIVITA_2026, PERIODO_2026
    )
    assert turni == []
    assert orfane == [ist]


def test_turno_minimale_due_giornate_concatenate_una_variante() -> None:
    """2 giornate-tipo concatenate ciclicamente (V↔M), 1 variante
    ciascuna → 1 Turno N=2 con 2 varianti totali.
    """
    seq_vm = (
        _c(
            "VARESE",
            "MI.CERT",
            (8, 0),
            (9, 0),
            numero_treno="24519",
            km=50.0,
        ),
    )
    seq_mv = (
        _c(
            "MI.CERT",
            "VARESE",
            (12, 0),
            (13, 0),
            numero_treno="24576",
            km=50.0,
        ),
    )
    # 5 istanze settimanali per ciascuna fase, in date diverse
    istanze: list[CatenaIstanza] = []
    for i in range(5):
        d = date(2026, 4, 27) + timedelta(days=i * 7)  # 5 lunedì successivi
        istanze.append(_ist(data_=d, corse=seq_vm))
        istanze.append(_ist(data_=d, corse=seq_mv))

    turni, orfane = costruisci_turni_v2(
        istanze, FESTIVITA_2026, PERIODO_2026
    )

    assert orfane == []
    assert len(turni) == 1
    t = turni[0]
    assert isinstance(t, TurnoConVarianti)
    assert t.n_giornate == 2
    # Ogni giornata-tipo ha 1 variante
    for gtv in t.giornate_tipo:
        assert len(gtv.varianti) == 1
    # Verifica concatenazione ciclica
    assert (
        t.giornate_tipo[0].staz_fine
        == t.giornate_tipo[1].staz_inizio
    )
    assert (
        t.giornate_tipo[1].staz_fine
        == t.giornate_tipo[0].staz_inizio
    )


# =====================================================================
# Acceptance turno 1110 concettuale
# =====================================================================


def test_acceptance_turno_1110_g6_sei_varianti() -> None:
    """6 sequenze-treni diverse sulla stessa fase ``(VARESE, VARESE)``
    + ciclo che si chiude con 1 giornata auto-loop → 1 Turno N=1
    con 6 varianti.

    Modello concettuale del turno 1110 G6 PDF Trenord.
    """
    # 6 sequenze diverse, ciascuna ripetuta su 5 date distinte
    sequenze = [
        (
            _c(
                "VARESE",
                "VARESE",  # auto-loop per concatenazione D6 N=1
                (6, 30 + i),
                (7, 30 + i),
                numero_treno=f"S{i}_24519",
                km=131.57,
            ),
        )
        for i in range(6)
    ]
    istanze: list[CatenaIstanza] = []
    for i, seq in enumerate(sequenze):
        for j in range(5):
            d = date(2026, 4, 1) + timedelta(days=(i * 30 + j))
            istanze.append(
                _ist(data_=d, corse=seq, materiale="2ALe711+1ALe710")
            )

    turni, orfane = costruisci_turni_v2(
        istanze, FESTIVITA_2026, PERIODO_2026
    )

    assert orfane == []
    assert len(turni) == 1
    t = turni[0]
    # 1 giornata-tipo (auto-loop) con 6 varianti
    assert t.n_giornate == 1
    gtv = t.giornate_tipo[0]
    assert len(gtv.varianti) == 6
    # Ogni variante ha 5 dates_apply
    for v in gtv.varianti:
        assert len(v.dates_apply) == 5
    # Ogni variante ha km e prestazione coerenti
    for v in gtv.varianti:
        assert v.km_giornaliera == 131.57
        # Da 06:30+i a 07:30+i = 60 min
        assert v.prestazione_minuti == 60


# =====================================================================
# Multi-turno via SCC (D2)
# =====================================================================


def test_due_cicli_disgiunti_due_turni_separati() -> None:
    """Stesso (materiale, sede) ma 2 cicli A↔B e C↔D disgiunti →
    2 Turni separati (D2 multi-turno).
    """
    seq_ab = (_c("A", "B", (8, 0), (9, 0), numero_treno="AB", km=10.0),)
    seq_ba = (_c("B", "A", (10, 0), (11, 0), numero_treno="BA", km=10.0),)
    seq_cd = (_c("C", "D", (12, 0), (13, 0), numero_treno="CD", km=20.0),)
    seq_dc = (_c("D", "C", (14, 0), (15, 0), numero_treno="DC", km=20.0),)

    istanze: list[CatenaIstanza] = []
    for i in range(3):
        d = date(2026, 4, 27) + timedelta(days=i * 7)
        istanze.append(_ist(data_=d, corse=seq_ab))
        istanze.append(_ist(data_=d, corse=seq_ba))
        istanze.append(_ist(data_=d, corse=seq_cd))
        istanze.append(_ist(data_=d, corse=seq_dc))

    turni, orfane = costruisci_turni_v2(
        istanze, FESTIVITA_2026, PERIODO_2026
    )
    assert orfane == []
    assert len(turni) == 2
    primi_inizi = sorted(t.giornate_tipo[0].staz_inizio for t in turni)
    assert primi_inizi == ["A", "C"]


# =====================================================================
# Orfane combinate (D3 + D2)
# =====================================================================


def test_orfane_da_min_istanze_e_da_concatenazione_impossibile() -> None:
    """Mix: 1 catena rara (sotto D3) + 2 catene non concatenabili
    (sopra D3 ma niente ciclo) → tutte orfane.
    """
    # 1 catena rara (1 sola data, va in orfane Step 2)
    seq_rara = (_c("X", "Y", (8, 0), (9, 0), numero_treno="rara", km=10.0),)
    ist_rara = _ist(data_=date(2026, 4, 27), corse=seq_rara)

    # 2 catene "ciclabili" (≥2 date) ma incompatibili: V→M e P→Q
    # — staz_inizio/fine totalmente diversi, niente ciclo nemmeno tra
    #   loro.
    seq_vm = (_c("V", "M", (10, 0), (11, 0), numero_treno="VM", km=20.0),)
    seq_pq = (_c("P", "Q", (12, 0), (13, 0), numero_treno="PQ", km=20.0),)
    istanze: list[CatenaIstanza] = [ist_rara]
    for i in range(2):
        d = date(2026, 5, 1) + timedelta(days=i * 7)
        istanze.append(_ist(data_=d, corse=seq_vm))
        istanze.append(_ist(data_=d, corse=seq_pq))

    turni, orfane = costruisci_turni_v2(
        istanze, FESTIVITA_2026, PERIODO_2026
    )
    assert turni == []
    # 1 rara (Step 2) + 4 ciclo-rotto (Step 4) = 5 orfane totali
    assert len(orfane) == 5


def test_param_min_istanze_configurabile() -> None:
    """Override min_istanze=1 → 1 sola istanza diventa giornata-tipo
    significativa.
    """
    seq = (_c("V", "V", (8, 0), (9, 0), numero_treno="A", km=10.0),)  # auto-loop
    ist = _ist(data_=date(2026, 4, 27), corse=seq)
    turni, orfane = costruisci_turni_v2(
        [ist],
        FESTIVITA_2026,
        PERIODO_2026,
        params=ParamBuilderV2(min_istanze=1),
    )
    assert orfane == []
    assert len(turni) == 1
    assert turni[0].n_giornate == 1


def test_turno_con_varianti_property_n_giornate() -> None:
    seq = (_c("V", "V", (8, 0), (9, 0), numero_treno="A", km=10.0),)
    istanze = [
        _ist(data_=date(2026, 4, 27) + timedelta(days=i), corse=seq)
        for i in range(2)
    ]
    turni, _ = costruisci_turni_v2(
        istanze, FESTIVITA_2026, PERIODO_2026
    )
    assert turni[0].n_giornate == 1
