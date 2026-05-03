"""Test puri di ``fonde_cluster_simili`` (Sprint 7.9 MR 12, entry 114).

Funzione DB-agnostic. Valida:

- Cluster con sequenze identiche (Jaccard=1) → fusi in 1 cluster con
  date_apply unite.
- Cluster con sequenze ≥ soglia di similarità → fusi.
- Cluster con sequenze sotto soglia → restano separati.
- Cluster con materiali/sedi/n_giornate diversi → non si fondono mai.
- Componenti connesse via Union-Find (similarità transitiva A~B + B~C →
  A,B,C fusi).
- Giri orfani (senza materiale) → pass-through.
"""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal

from colazione.domain.builder_giro import (
    AssegnazioneRisolta,
    BloccoAssegnato,
    Catena,
    CatenaPosizionata,
    ComposizioneItem,
    GiornataAssegnata,
    GiroAssegnato,
)
from colazione.domain.builder_giro.fusione_cluster_a1 import fonde_cluster_simili


# =====================================================================
# Stub corsa identificabile per Jaccard
# =====================================================================


class _StubCorsa:
    def __init__(self, treno_id: int, numero_treno: str = "T") -> None:
        self.id = treno_id
        self.numero_treno = numero_treno
        self.codice_origine = "S99001"
        self.codice_destinazione = "S99002"
        self.ora_partenza = time(8, 0)
        self.ora_arrivo = time(9, 0)
        self.km_tratta: Decimal | None = None
        self.periodicita_breve: str | None = None


def _giornata(
    *,
    data_g: date,
    materiale: str,
    treni_ids: tuple[int, ...],
    dates_apply: tuple[date, ...] = (),
) -> GiornataAssegnata:
    corse = tuple(_StubCorsa(t) for t in treni_ids)
    cat_pos = CatenaPosizionata(
        localita_codice="LOC_X",
        stazione_collegata="S99001",
        vuoto_testa=None,
        catena=Catena(corse=corse),
        vuoto_coda=None,
        chiusa_a_localita=True,
    )
    blocchi = tuple(
        BloccoAssegnato(
            corsa=c,
            assegnazione=AssegnazioneRisolta(
                regola_id=1,
                composizione=(ComposizioneItem(materiale, 1),),
            ),
        )
        for c in corse
    )
    return GiornataAssegnata(
        data=data_g,
        catena_posizionata=cat_pos,
        blocchi_assegnati=blocchi,
        eventi_composizione=(),
        materiali_tipo_giornata=frozenset({materiale}),
        dates_apply=dates_apply,
    )


def _giro(
    *,
    materiale: str = "ETR204",
    sede: str = "LOC_X",
    giornate: tuple[GiornataAssegnata, ...],
) -> GiroAssegnato:
    return GiroAssegnato(
        localita_codice=sede,
        giornate=giornate,
        chiuso=True,
        motivo_chiusura="naturale",
        km_cumulati=0.0,
    )


# =====================================================================
# Test base
# =====================================================================


def test_input_vuoto() -> None:
    assert fonde_cluster_simili([]) == []


def test_un_cluster_passa_invariato() -> None:
    g = _giro(
        giornate=(
            _giornata(
                data_g=date(2026, 6, 1),
                materiale="ETR204",
                treni_ids=(1, 2, 3),
                dates_apply=(date(2026, 6, 1),),
            ),
        ),
    )
    out = fonde_cluster_simili([g])
    assert len(out) == 1
    assert out[0] is g


def test_cluster_identici_si_fondono_in_uno() -> None:
    """Due cluster con sequenza IDENTICA (Jaccard = 1.0) ma date diverse →
    fusi in UN cluster con date_apply unite.
    """
    g1 = _giro(
        giornate=(
            _giornata(
                data_g=date(2026, 6, 1),
                materiale="ETR204",
                treni_ids=(1, 2, 3),
                dates_apply=(date(2026, 6, 1), date(2026, 6, 8)),
            ),
        ),
    )
    g2 = _giro(
        giornate=(
            _giornata(
                data_g=date(2026, 6, 15),
                materiale="ETR204",
                treni_ids=(1, 2, 3),
                dates_apply=(date(2026, 6, 15), date(2026, 6, 22)),
            ),
        ),
    )
    out = fonde_cluster_simili([g1, g2])
    assert len(out) == 1
    fuso = out[0]
    date_unite = set(fuso.giornate[0].dates_apply_or_data)
    assert date_unite == {
        date(2026, 6, 1),
        date(2026, 6, 8),
        date(2026, 6, 15),
        date(2026, 6, 22),
    }


def test_cluster_simili_sopra_soglia_si_fondono() -> None:
    """Cluster con 3 treni in comune su 4 totali (Jaccard 0.75 ≥ 0.7) →
    fusi.
    """
    g1 = _giro(
        giornate=(
            _giornata(
                data_g=date(2026, 6, 1),
                materiale="ETR204",
                treni_ids=(1, 2, 3),
                dates_apply=(date(2026, 6, 1),),
            ),
        ),
    )
    g2 = _giro(
        giornate=(
            _giornata(
                data_g=date(2026, 6, 8),
                materiale="ETR204",
                treni_ids=(1, 2, 3, 4),  # +1 treno: 3/4 in comune
                dates_apply=(date(2026, 6, 8),),
            ),
        ),
    )
    # Jaccard = |{1,2,3}| / |{1,2,3,4}| = 3/4 = 0.75 ≥ 0.7 → fusi.
    out = fonde_cluster_simili([g1, g2], soglia=0.7)
    assert len(out) == 1


def test_cluster_diversi_sotto_soglia_restano_separati() -> None:
    """Cluster con 1 treno in comune su 4 totali (Jaccard 0.25) →
    restano separati.
    """
    g1 = _giro(
        giornate=(
            _giornata(
                data_g=date(2026, 6, 1),
                materiale="ETR204",
                treni_ids=(1, 2, 3),
                dates_apply=(date(2026, 6, 1),),
            ),
        ),
    )
    g2 = _giro(
        giornate=(
            _giornata(
                data_g=date(2026, 6, 8),
                materiale="ETR204",
                treni_ids=(1, 4, 5),  # 1 treno in comune
                dates_apply=(date(2026, 6, 8),),
            ),
        ),
    )
    out = fonde_cluster_simili([g1, g2], soglia=0.7)
    assert len(out) == 2


def test_cluster_materiali_diversi_non_si_fondono() -> None:
    """Cluster con sequenze identiche ma materiali diversi → separati."""
    g1 = _giro(
        materiale="ETR204",
        giornate=(
            _giornata(
                data_g=date(2026, 6, 1),
                materiale="ETR204",
                treni_ids=(1, 2, 3),
                dates_apply=(date(2026, 6, 1),),
            ),
        ),
    )
    g2 = _giro(
        materiale="ETR522",
        giornate=(
            _giornata(
                data_g=date(2026, 6, 8),
                materiale="ETR522",
                treni_ids=(1, 2, 3),
                dates_apply=(date(2026, 6, 8),),
            ),
        ),
    )
    out = fonde_cluster_simili([g1, g2])
    assert len(out) == 2


def test_cluster_n_giornate_diverse_non_si_fondono() -> None:
    """Cluster con n_giornate diverse → restano separati (struttura
    incompatibile per fusione giornata-K).
    """
    g_3gg = _giro(
        giornate=tuple(
            _giornata(
                data_g=date(2026, 6, i),
                materiale="ETR204",
                treni_ids=(1, 2, 3),
                dates_apply=(date(2026, 6, i),),
            )
            for i in (1, 2, 3)
        ),
    )
    g_5gg = _giro(
        giornate=tuple(
            _giornata(
                data_g=date(2026, 6, i),
                materiale="ETR204",
                treni_ids=(1, 2, 3),
                dates_apply=(date(2026, 6, i),),
            )
            for i in (8, 9, 10, 11, 12)
        ),
    )
    out = fonde_cluster_simili([g_3gg, g_5gg])
    assert len(out) == 2


def test_componente_connessa_transitiva() -> None:
    """A~B (Jaccard ≥ soglia), B~C, ma NOT(A~C). Union-Find unisce
    comunque tutti e tre nello stesso componente.
    """
    g_a = _giro(
        giornate=(
            _giornata(
                data_g=date(2026, 6, 1),
                materiale="ETR204",
                treni_ids=(1, 2, 3, 4),
                dates_apply=(date(2026, 6, 1),),
            ),
        ),
    )
    g_b = _giro(
        giornate=(
            _giornata(
                data_g=date(2026, 6, 8),
                materiale="ETR204",
                treni_ids=(2, 3, 4, 5),  # vs A: {2,3,4}/{1,2,3,4,5} = 0.6
                dates_apply=(date(2026, 6, 8),),
            ),
        ),
    )
    g_c = _giro(
        giornate=(
            _giornata(
                data_g=date(2026, 6, 15),
                materiale="ETR204",
                treni_ids=(3, 4, 5, 6),  # vs B: {3,4,5}/{2,3,4,5,6} = 0.6
                dates_apply=(date(2026, 6, 15),),
            ),
        ),
    )
    # vs C-A: {3,4}/{1,2,3,4,5,6} = 2/6 = 0.33 < soglia, ma B fa da ponte.
    out = fonde_cluster_simili([g_a, g_b, g_c], soglia=0.6)
    assert len(out) == 1


def test_giro_orfano_passa_invariato() -> None:
    """Cluster senza ``blocchi_assegnati`` (= solo corse residue, no
    materiale): pass-through, niente fusione tentata.
    """
    giornata_orfana = GiornataAssegnata(
        data=date(2026, 6, 1),
        catena_posizionata=CatenaPosizionata(
            localita_codice="LOC_X",
            stazione_collegata="S99001",
            vuoto_testa=None,
            catena=Catena(corse=()),
            vuoto_coda=None,
            chiusa_a_localita=True,
        ),
        blocchi_assegnati=(),
        eventi_composizione=(),
        materiali_tipo_giornata=frozenset(),
    )
    g_orfano = GiroAssegnato(
        localita_codice="LOC_X",
        giornate=(giornata_orfana,),
        chiuso=False,
        motivo_chiusura="non_chiuso",
    )
    out = fonde_cluster_simili([g_orfano])
    assert len(out) == 1
    assert out[0] is g_orfano


def test_fusione_preserva_lunghezza_sequenza_canonica() -> None:
    """Fondendo cluster con stesso n_giornate, la sequenza canonica
    (catena_posizionata di ogni giornata) è quella del cluster con più
    date di applicazione totali.
    """
    g_principale = _giro(
        giornate=(
            _giornata(
                data_g=date(2026, 6, 1),
                materiale="ETR204",
                treni_ids=(1, 2, 3, 4, 5),  # spina dorsale principale
                dates_apply=(date(2026, 6, 1), date(2026, 6, 8), date(2026, 6, 15)),
            ),
        ),
    )
    g_minore = _giro(
        giornate=(
            _giornata(
                data_g=date(2026, 6, 22),
                materiale="ETR204",
                treni_ids=(1, 2, 3, 4),  # 1 treno mancante: 4/5 in comune = 0.8
                dates_apply=(date(2026, 6, 22),),
            ),
        ),
    )
    out = fonde_cluster_simili([g_minore, g_principale], soglia=0.7)
    assert len(out) == 1
    fuso = out[0]
    treni_canonici = {
        c.id for c in fuso.giornate[0].catena_posizionata.catena.corse
    }
    # Sequenza canonica = quella del cluster con PIÙ date (g_principale).
    assert treni_canonici == {1, 2, 3, 4, 5}
    # Date totali unite.
    assert set(fuso.giornate[0].dates_apply_or_data) == {
        date(2026, 6, 1),
        date(2026, 6, 8),
        date(2026, 6, 15),
        date(2026, 6, 22),
    }
