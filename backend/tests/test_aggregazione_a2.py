"""Test puri di ``aggrega_a2`` (Sprint 7.7 MR 5).

Funzione DB-agnostic. Valida:

- Aggregazione per chiave A2: ``(materiale, sede, n_giornate)``.
- Per ogni cluster A2, ogni giornata K ha M varianti (= N cluster A1
  fusi).
- Ordine canonico delle varianti: ``variant_index=0`` = giro con data
  di partenza minima.
- Stats aggregate: ``chiuso``, ``motivo_chiusura``, ``km_cumulati``
  ereditati dal canonico.
- Giri orfani (senza materiale) scartati.
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
    aggrega_a2,
)


# =====================================================================
# Stub corsa minimo (compatibile con BloccoAssegnato).
# =====================================================================


class _StubCorsa:
    def __init__(
        self,
        numero_treno: str,
        codice_origine: str,
        codice_destinazione: str,
        ora_partenza: time,
        ora_arrivo: time,
        km_tratta: Decimal | None = None,
        periodicita_breve: str | None = None,
    ) -> None:
        self.id = id(self)  # opaco, gli aggregati non lo usano
        self.numero_treno = numero_treno
        self.codice_origine = codice_origine
        self.codice_destinazione = codice_destinazione
        self.ora_partenza = ora_partenza
        self.ora_arrivo = ora_arrivo
        self.km_tratta = km_tratta
        self.periodicita_breve = periodicita_breve


def _giornata(
    *,
    data: date,
    materiale: str,
    origine: str = "S99001",
    destinazione: str = "S99002",
    dates_apply: tuple[date, ...] = (),
) -> GiornataAssegnata:
    """Costruisce una ``GiornataAssegnata`` con 1 corsa + 1 blocco
    assegnato.
    """
    corsa = _StubCorsa(
        numero_treno=f"T-{data.isoformat()}",
        codice_origine=origine,
        codice_destinazione=destinazione,
        ora_partenza=time(8, 0),
        ora_arrivo=time(9, 0),
    )
    cat_pos = CatenaPosizionata(
        localita_codice="LOC_X",
        stazione_collegata=origine,
        vuoto_testa=None,
        catena=Catena(corse=(corsa,)),
        vuoto_coda=None,
        chiusa_a_localita=True,
    )
    blocco = BloccoAssegnato(
        corsa=corsa,
        assegnazione=AssegnazioneRisolta(
            regola_id=1,
            composizione=(ComposizioneItem(materiale, 3),),
        ),
    )
    return GiornataAssegnata(
        data=data,
        catena_posizionata=cat_pos,
        blocchi_assegnati=(blocco,),
        eventi_composizione=(),
        materiali_tipo_giornata=frozenset({materiale}),
        dates_apply=dates_apply,
    )


def _giro(
    *,
    materiale: str,
    sede: str = "LOC_X",
    giornate: tuple[GiornataAssegnata, ...],
    chiuso: bool = True,
) -> GiroAssegnato:
    return GiroAssegnato(
        localita_codice=sede,
        giornate=giornate,
        chiuso=chiuso,
        motivo_chiusura="naturale" if chiuso else "non_chiuso",
        km_cumulati=0.0,
    )


# =====================================================================
# Test
# =====================================================================


def test_input_vuoto_ritorna_lista_vuota() -> None:
    assert aggrega_a2([]) == []


def test_un_giro_un_aggregato_una_variante_per_giornata() -> None:
    """Caso degenere: 1 GiroAssegnato → 1 GiroAggregato con 1 variante
    per giornata."""
    g = _giro(
        materiale="ETR204",
        giornate=(
            _giornata(data=date(2026, 5, 4), materiale="ETR204"),
        ),
    )
    out = aggrega_a2([g])
    assert len(out) == 1
    aggregato = out[0]
    assert aggregato.materiale_tipo_codice == "ETR204"
    assert aggregato.localita_codice == "LOC_X"
    assert len(aggregato.giornate) == 1
    assert len(aggregato.giornate[0].varianti) == 1
    assert aggregato.n_cluster_a1 == 1


def test_due_giri_stessa_chiave_a2_si_fondono_in_un_aggregato() -> None:
    """2 cluster A1 con stessa (materiale, sede, n_giornate=1) →
    1 aggregato con 2 varianti per giornata 1.

    Modella il caso utente: stesso ETR204 FIO 1-giornata, ma percorsi
    diversi nel calendario (LV vs F).
    """
    g_lv = _giro(
        materiale="ETR204",
        giornate=(
            _giornata(
                data=date(2026, 5, 4),
                materiale="ETR204",
                destinazione="TREVIGLIO",
                dates_apply=(date(2026, 5, 4),),
            ),
        ),
    )
    g_f = _giro(
        materiale="ETR204",
        giornate=(
            _giornata(
                data=date(2026, 5, 10),  # domenica → variante festiva
                materiale="ETR204",
                destinazione="CREMONA",
                dates_apply=(date(2026, 5, 10),),
            ),
        ),
    )
    out = aggrega_a2([g_lv, g_f])
    assert len(out) == 1
    aggregato = out[0]
    assert aggregato.n_cluster_a1 == 2
    assert len(aggregato.giornate) == 1
    varianti = aggregato.giornate[0].varianti
    assert len(varianti) == 2
    # Canonica = data_partenza_minima → variante "LV" (4/5)
    dest_var0 = varianti[0].catena_posizionata.catena.corse[-1].codice_destinazione
    dest_var1 = varianti[1].catena_posizionata.catena.corse[-1].codice_destinazione
    assert dest_var0 == "TREVIGLIO"  # canonica
    assert dest_var1 == "CREMONA"


def test_due_giri_chiave_diversa_restano_aggregati_distinti() -> None:
    """Materiali diversi → 2 aggregati separati."""
    g_204 = _giro(
        materiale="ETR204",
        giornate=(_giornata(data=date(2026, 5, 4), materiale="ETR204"),),
    )
    g_425 = _giro(
        materiale="ETR425",
        giornate=(_giornata(data=date(2026, 5, 4), materiale="ETR425"),),
    )
    out = aggrega_a2([g_204, g_425])
    assert len(out) == 2
    materiali = {a.materiale_tipo_codice for a in out}
    assert materiali == {"ETR204", "ETR425"}


def test_n_giornate_diverse_date_disgiunte_si_fondono() -> None:
    """Sprint 7.9 MR 10 (entry 109): cluster con n_giornate diversi MA
    date di applicazione DISGIUNTE → fondono in UN aggregato di
    lunghezza max. Il cluster corto contribuisce varianti alle prime K
    giornate. Modello Trenord: "stesso convoglio in date diverse fa
    percorsi diversi".
    """
    g_8 = _giro(
        materiale="ETR204",
        giornate=tuple(
            _giornata(
                data=date(2026, 5, 4 + i),
                materiale="ETR204",
                dates_apply=(date(2026, 5, 4 + i),),
            )
            for i in range(8)
        ),
    )
    # g_5 a giugno (disgiunto da g_8 a maggio)
    g_5 = _giro(
        materiale="ETR204",
        giornate=tuple(
            _giornata(
                data=date(2026, 6, 1 + i),
                materiale="ETR204",
                dates_apply=(date(2026, 6, 1 + i),),
            )
            for i in range(5)
        ),
    )
    out = aggrega_a2([g_8, g_5])
    # 1 solo aggregato (date disgiunte), lunghezza canonica 8 (= max).
    assert len(out) == 1
    agg = out[0]
    assert len(agg.giornate) == 8
    assert agg.n_cluster_a1 == 2
    # Giornate 1-5: entrambi i cluster contribuiscono (2 varianti).
    for k in range(5):
        assert len(agg.giornate[k].varianti) == 2, (
            f"giornata {k+1}: attese 2 varianti, ottenute {len(agg.giornate[k].varianti)}"
        )
    # Giornate 6-8: solo il cluster lungo contribuisce (1 variante).
    for k in range(5, 8):
        assert len(agg.giornate[k].varianti) == 1, (
            f"giornata {k+1}: attesa 1 variante, ottenute {len(agg.giornate[k].varianti)}"
        )


def test_date_sovrapposte_creano_turni_separati() -> None:
    """Sprint 7.9 MR 10 (entry 109): cluster con date di applicazione
    SOVRAPPOSTE rappresentano convogli FISICI DIVERSI in parallelo,
    quindi vanno in turni materiali separati (non come varianti dello
    stesso turno).

    Caso reale: PdE Trenord ETR421+FIO con N convogli paralleli — il
    builder produce N cluster A1 con date di applicazione sovrapposte;
    A2 li separa in N turni, uno per convoglio fisico.
    """
    # Stesso periodo (4-11 maggio) per entrambi → date sovrapposte.
    g_8 = _giro(
        materiale="ETR204",
        giornate=tuple(
            _giornata(
                data=date(2026, 5, 4 + i),
                materiale="ETR204",
                dates_apply=(date(2026, 5, 4 + i),),
            )
            for i in range(8)
        ),
    )
    g_5 = _giro(
        materiale="ETR204",
        giornate=tuple(
            _giornata(
                data=date(2026, 5, 4 + i),
                materiale="ETR204",
                dates_apply=(date(2026, 5, 4 + i),),
            )
            for i in range(5)
        ),
    )
    out = aggrega_a2([g_8, g_5])
    # 2 aggregati distinti (turni materiali per convogli paralleli).
    assert len(out) == 2
    # Entrambi stessa coppia (materiale, sede) ma turni separati.
    for agg in out:
        assert agg.materiale_tipo_codice == "ETR204"
        assert agg.localita_codice == "LOC_X"
        assert agg.n_cluster_a1 == 1
    # Lunghezze: il primo turno è il canonico (8 giornate, cluster più
    # lungo), il secondo è il convoglio parallelo (5 giornate).
    lunghezze = sorted(len(a.giornate) for a in out)
    assert lunghezze == [5, 8]


def test_giro_orfano_senza_composizione_viene_scartato() -> None:
    """Un GiroAssegnato senza alcun blocco assegnato (= solo corse
    residue) non ha materiale → l'aggregazione lo scarta.
    """
    giornata = GiornataAssegnata(
        data=date(2026, 5, 4),
        catena_posizionata=CatenaPosizionata(
            localita_codice="LOC_X",
            stazione_collegata="S99001",
            vuoto_testa=None,
            catena=Catena(corse=()),
            vuoto_coda=None,
            chiusa_a_localita=True,
        ),
        blocchi_assegnati=(),  # niente composizione
        eventi_composizione=(),
        materiali_tipo_giornata=frozenset(),
    )
    g_orfano = GiroAssegnato(
        localita_codice="LOC_X",
        giornate=(giornata,),
        chiuso=False,
        motivo_chiusura="non_chiuso",
    )
    out = aggrega_a2([g_orfano])
    assert out == []


def test_canonico_eredita_chiuso_e_motivo() -> None:
    """L'aggregato eredita ``chiuso``/``motivo_chiusura`` dal canonico
    (= primo per data_partenza_minima).
    """
    g_canonico_chiuso = _giro(
        materiale="ETR204",
        giornate=(
            _giornata(
                data=date(2026, 5, 4),  # parte prima
                materiale="ETR204",
                dates_apply=(date(2026, 5, 4),),
            ),
        ),
        chiuso=True,
    )
    g_secondo_aperto = _giro(
        materiale="ETR204",
        giornate=(
            _giornata(
                data=date(2026, 5, 11),
                materiale="ETR204",
                dates_apply=(date(2026, 5, 11),),
            ),
        ),
        chiuso=False,
    )
    out = aggrega_a2([g_secondo_aperto, g_canonico_chiuso])
    assert len(out) == 1
    aggregato = out[0]
    # Canonico = primo per data → g_canonico_chiuso
    assert aggregato.chiuso is True
    assert aggregato.motivo_chiusura == "naturale"


def test_output_ordinato_per_chiave_a2() -> None:
    """L'output è deterministico: ordinato per (materiale, sede,
    n_giornate)."""
    g_525 = _giro(
        materiale="ETR525",
        giornate=(_giornata(data=date(2026, 5, 4), materiale="ETR525"),),
    )
    g_204 = _giro(
        materiale="ETR204",
        giornate=(_giornata(data=date(2026, 5, 4), materiale="ETR204"),),
    )
    out = aggrega_a2([g_525, g_204])
    assert [a.materiale_tipo_codice for a in out] == ["ETR204", "ETR525"]
