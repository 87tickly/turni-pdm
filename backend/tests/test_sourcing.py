"""Test puri di ``arricchisci_sourcing`` (Sprint 7.9 MR β2-3)."""

from __future__ import annotations

from datetime import date, time

from colazione.domain.builder_giro import (
    AssegnazioneRisolta,
    BloccoAssegnato,
    Catena,
    CatenaPosizionata,
    ComposizioneItem,
    EventoComposizione,
    GiornataAssegnata,
    GiroAssegnato,
)
from colazione.domain.builder_giro.sourcing import arricchisci_sourcing


# =====================================================================
# Stubs minimi
# =====================================================================


class _StubCorsa:
    def __init__(
        self,
        numero_treno: str,
        codice_origine: str,
        codice_destinazione: str,
        ora_partenza: time,
        ora_arrivo: time,
    ) -> None:
        self.id = id(self)
        self.numero_treno = numero_treno
        self.codice_origine = codice_origine
        self.codice_destinazione = codice_destinazione
        self.ora_partenza = ora_partenza
        self.ora_arrivo = ora_arrivo


def _giro_minimo(
    *,
    materiale: str,
    corse: list[_StubCorsa],
    eventi: tuple[EventoComposizione, ...] = (),
    sede: str = "LOC_X",
    data_g: date = date(2026, 5, 4),
) -> GiroAssegnato:
    cat = Catena(corse=tuple(corse))
    cat_pos = CatenaPosizionata(
        localita_codice=sede,
        stazione_collegata=corse[0].codice_origine if corse else "S99001",
        vuoto_testa=None,
        catena=cat,
        vuoto_coda=None,
        chiusa_a_localita=True,
    )
    blocchi = tuple(
        BloccoAssegnato(
            corsa=c,
            assegnazione=AssegnazioneRisolta(
                regola_id=1,
                composizione=(ComposizioneItem(materiale, 3),),
            ),
        )
        for c in corse
    )
    return GiroAssegnato(
        localita_codice=sede,
        giornate=(
            GiornataAssegnata(
                data=data_g,
                catena_posizionata=cat_pos,
                blocchi_assegnati=blocchi,
                eventi_composizione=eventi,
                materiali_tipo_giornata=frozenset({materiale}),
            ),
        ),
        chiuso=True,
        motivo_chiusura="naturale",
    )


# =====================================================================
# Test
# =====================================================================


def test_input_vuoto_ritorna_lista_vuota() -> None:
    out, w = arricchisci_sourcing([], "FIO", {})
    assert out == []
    assert w == []


def test_giro_senza_eventi_passa_invariato() -> None:
    """Un giro senza agganci/sganci viene restituito senza modifiche."""
    corse = [_StubCorsa("2811", "A", "B", time(8, 0), time(9, 0))]
    g = _giro_minimo(materiale="ETR526", corse=corse)
    out, w = arricchisci_sourcing([g], "FIO", {})
    assert len(out) == 1
    assert out[0].giornate[0].eventi_composizione == ()
    assert w == []


def test_aggancio_sourceable_da_altra_catena() -> None:
    """Catena A termina B alle 09:55. Catena B parte da B alle 10:05
    e all'idx 1 c'è un aggancio +1 ETR526. Sourcing deve trovare A.
    """
    # Catena sorgente A: arriva a B alle 09:55 (= ultima.ora_arrivo)
    corse_a = [_StubCorsa("9001", "X", "B", time(9, 0), time(9, 55))]
    g_a = _giro_minimo(materiale="ETR526", corse=corse_a)
    # Catena B: 2 corse. La seconda parte alle 10:05 da B.
    # Evento aggancio in posizione 0 (= tra blocco 0 e blocco 1).
    corse_b = [
        _StubCorsa("2811", "Y", "B", time(9, 30), time(10, 0)),
        _StubCorsa("2812", "B", "Z", time(10, 5), time(11, 0)),
    ]
    ev = EventoComposizione(
        tipo="aggancio",
        materiale_tipo_codice="ETR526",
        pezzi_delta=1,
        stazione_proposta="B",
        posizione_dopo_blocco=0,
        note_builder="test",
    )
    g_b = _giro_minimo(materiale="ETR526", corse=corse_b, eventi=(ev,))
    out, w = arricchisci_sourcing([g_a, g_b], "FIO", {})
    # Il giro B (nuovo) deve avere l'evento arricchito con sourceDescr.
    ev_arr = out[1].giornate[0].eventi_composizione[0]
    assert ev_arr.source_descrizione is not None
    assert "9001" in ev_arr.source_descrizione
    assert "B" in ev_arr.source_descrizione
    assert ev_arr.capacity_warning is False


def test_aggancio_non_sourceable_fallback_deposito() -> None:
    """Se nessuna catena candidata, fallback 'Pezzi da deposito FIO'."""
    corse = [
        _StubCorsa("2811", "X", "B", time(9, 30), time(10, 0)),
        _StubCorsa("2812", "B", "Z", time(10, 5), time(11, 0)),
    ]
    ev = EventoComposizione(
        tipo="aggancio",
        materiale_tipo_codice="ETR526",
        pezzi_delta=1,
        stazione_proposta="B",
        posizione_dopo_blocco=0,
        note_builder="test",
    )
    g = _giro_minimo(materiale="ETR526", corse=corse, eventi=(ev,))
    out, w = arricchisci_sourcing([g], "FIO", {"ETR526": 11})
    ev_arr = out[0].giornate[0].eventi_composizione[0]
    assert ev_arr.source_descrizione is not None
    assert "deposito FIO" in ev_arr.source_descrizione
    assert ev_arr.capacity_warning is False
    assert w == []  # Sotto cap, no warning


def test_aggancio_capacity_warning_se_dotazione_satura() -> None:
    """Dotazione 1 ETR526 + 2 agganci non sourceable → secondo warn."""
    corse_1 = [
        _StubCorsa("2811", "X", "B", time(9, 30), time(10, 0)),
        _StubCorsa("2812", "B", "Z", time(10, 5), time(11, 0)),
    ]
    ev_1 = EventoComposizione(
        tipo="aggancio",
        materiale_tipo_codice="ETR526",
        pezzi_delta=1,
        stazione_proposta="B",
        posizione_dopo_blocco=0,
        note_builder="test1",
    )
    corse_2 = [
        _StubCorsa("3811", "X", "C", time(11, 30), time(12, 0)),
        _StubCorsa("3812", "C", "Z", time(12, 5), time(13, 0)),
    ]
    ev_2 = EventoComposizione(
        tipo="aggancio",
        materiale_tipo_codice="ETR526",
        pezzi_delta=1,
        stazione_proposta="C",
        posizione_dopo_blocco=0,
        note_builder="test2",
    )
    g1 = _giro_minimo(materiale="ETR526", corse=corse_1, eventi=(ev_1,))
    g2 = _giro_minimo(materiale="ETR526", corse=corse_2, eventi=(ev_2,))
    out, w = arricchisci_sourcing([g1, g2], "FIO", {"ETR526": 1})
    # Primo aggancio: cap=1, ok. Secondo: pezzi_in_uso=2 > 1 → warn.
    ev1_arr = out[0].giornate[0].eventi_composizione[0]
    ev2_arr = out[1].giornate[0].eventi_composizione[0]
    assert ev1_arr.capacity_warning is False
    assert ev2_arr.capacity_warning is True
    assert "NON SOURCEABLE" in (ev2_arr.source_descrizione or "")
    assert len(w) == 1
    assert "satura" in w[0].lower()


def test_sgancio_destinabile_a_catena_successiva() -> None:
    """Catena B sgancia alle 10:30 a B. Catena C parte da B alle 10:35."""
    corse_b = [
        _StubCorsa("2811", "X", "B", time(10, 0), time(10, 25)),
        _StubCorsa("2812", "B", "Z", time(10, 30), time(11, 0)),
    ]
    ev = EventoComposizione(
        tipo="sgancio",
        materiale_tipo_codice="ETR526",
        pezzi_delta=-1,
        stazione_proposta="B",
        posizione_dopo_blocco=0,
        note_builder="test",
    )
    g_b = _giro_minimo(materiale="ETR526", corse=corse_b, eventi=(ev,))
    corse_c = [_StubCorsa("9999", "B", "K", time(10, 35), time(11, 0))]
    g_c = _giro_minimo(materiale="ETR526", corse=corse_c)
    out, w = arricchisci_sourcing([g_b, g_c], "FIO", {})
    ev_arr = out[0].giornate[0].eventi_composizione[0]
    assert ev_arr.dest_descrizione is not None
    assert "9999" in ev_arr.dest_descrizione
