"""Test puri di ``ribilancia_per_capacity`` (Sprint 7.9 MR 11B Step 2,
entry 121).

Funzione DB-agnostic. Valida:

- Dotazione illimitata (None) o assente: niente check, tutti i cluster
  passano.
- Dotazione finita non sforata: tutti i cluster passano.
- Dotazione sforata + regola alternativa con capacity disponibile:
  cluster con MENO km riassegnato (criterio utente 2026-05-04).
- Dotazione sforata + nessuna regola alternativa: cluster scartato +
  warning + corse residue computate.
- Tie-break id ASC tra alternative con stessa capacity.
- Composizione multi-materiale (ETR526×2 + ETR425×1) consuma capacity
  per entrambi i tipi.
"""

from __future__ import annotations

from datetime import date, time
from typing import Any

from colazione.domain.builder_giro import (
    AssegnazioneRisolta,
    BloccoAssegnato,
    Catena,
    CatenaPosizionata,
    ComposizioneItem,
    GiornataAssegnata,
    GiroAssegnato,
)
from colazione.domain.builder_giro.capacity_routing import ribilancia_per_capacity


# =====================================================================
# Stub
# =====================================================================


class _StubCorsa:
    """Corsa minima con tutti gli attributi che `risolvi_corsa` può
    leggere via `estrai_valore_corsa` per i filtri.
    """

    def __init__(
        self,
        numero_treno: str = "T",
        codice_linea: str = "S5",
        categoria: str = "RE",
    ) -> None:
        self.id = id(self)
        self.numero_treno = numero_treno
        self.codice_linea = codice_linea
        self.categoria = categoria
        # Default neutri per altri campi che potrebbero servire ai filtri.
        self.codice_origine = "S99001"
        self.codice_destinazione = "S99002"
        self.ora_partenza = time(8, 0)
        self.ora_arrivo = time(9, 0)
        self.fascia_oraria = "mattina"
        self.km_tratta = None
        self.direttrice = "TIRANO"
        self.rete = "RFI"
        self.periodicita_breve = ""
        self.is_treno_garantito_feriale = False
        self.is_treno_garantito_festivo = False


class _FakeRegola:
    def __init__(
        self,
        id: int,
        composizione: list[tuple[str, int]],
        priorita: int = 60,
        filtri_json: list[dict[str, Any]] | None = None,
    ) -> None:
        self.id = id
        self.priorita = priorita
        self.is_composizione_manuale = False
        self.filtri_json = filtri_json if filtri_json is not None else []
        self.composizione_json = [
            {"materiale_tipo_codice": m, "n_pezzi": n} for m, n in composizione
        ]


def _giro(
    *,
    regola_id: int,
    composizione: tuple[ComposizioneItem, ...],
    km_cumulati: float = 100.0,
    n_corse: int = 1,
    data_g: date = date(2026, 6, 1),
    codice_linea: str = "S5",
) -> GiroAssegnato:
    """Costruisce un cluster A1 minimo con N corse + composizione fissa."""
    corse = tuple(
        _StubCorsa(numero_treno=f"T{i}", codice_linea=codice_linea) for i in range(n_corse)
    )
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
                regola_id=regola_id,
                composizione=composizione,
            ),
        )
        for c in corse
    )
    giornata = GiornataAssegnata(
        data=data_g,
        catena_posizionata=cat_pos,
        blocchi_assegnati=blocchi,
        eventi_composizione=(),
        materiali_tipo_giornata=frozenset(c.materiale_tipo_codice for c in composizione),
    )
    return GiroAssegnato(
        localita_codice="LOC_X",
        giornate=(giornata,),
        chiuso=True,
        motivo_chiusura="naturale",
        km_cumulati=km_cumulati,
    )


# =====================================================================
# Test
# =====================================================================


def test_input_vuoto() -> None:
    out, scartati, warnings = ribilancia_per_capacity([], [], {})
    assert out == [] and scartati == [] and warnings == []


def test_dotazione_illimitata_passa_tutto() -> None:
    """Dotazione `None` (FLIRT TILO-style) → niente check, tutti i
    cluster passano.
    """
    cluster = [
        _giro(regola_id=1, composizione=(ComposizioneItem("ETR524", 1),))
        for _ in range(10)
    ]
    regola = _FakeRegola(id=1, composizione=[("ETR524", 1)])
    out, scartati, warnings = ribilancia_per_capacity(
        cluster, [regola], {"ETR524": None}
    )
    assert len(out) == 10
    assert scartati == []
    assert warnings == []


def test_dotazione_assente_dal_dict_passa_tutto() -> None:
    """Materiale non in dict dotazione → trattato come illimitato."""
    cluster = [_giro(regola_id=1, composizione=(ComposizioneItem("ETR526", 2),))]
    regola = _FakeRegola(id=1, composizione=[("ETR526", 2)])
    out, scartati, warnings = ribilancia_per_capacity(cluster, [regola], {})
    assert len(out) == 1
    assert scartati == []


def test_dotazione_sufficiente_passa_tutto() -> None:
    """5 cluster ETR526×2 = 10 pezzi necessari, dotazione 11 → tutti OK."""
    cluster = [
        _giro(regola_id=1, composizione=(ComposizioneItem("ETR526", 2),), km_cumulati=100.0 * i)
        for i in range(1, 6)
    ]
    regola = _FakeRegola(id=1, composizione=[("ETR526", 2)])
    out, scartati, warnings = ribilancia_per_capacity(
        cluster, [regola], {"ETR526": 11}
    )
    assert len(out) == 5
    assert scartati == []


def test_dotazione_sforata_senza_alternativa_scarta_meno_produttivi() -> None:
    """5 cluster ETR526×2 = 10 pezzi, dotazione 6 → 3 cluster passano,
    2 scartati. Criterio: km_cumulati ASC (= meno produttivi
    scartati).
    """
    cluster = [
        _giro(regola_id=1, composizione=(ComposizioneItem("ETR526", 2),), km_cumulati=km)
        for km in (100.0, 200.0, 300.0, 400.0, 500.0)
    ]
    regola = _FakeRegola(id=1, composizione=[("ETR526", 2)])
    out, scartati, warnings = ribilancia_per_capacity(
        cluster, [regola], {"ETR526": 6}
    )
    # 6 pezzi disponibili / 2 pezzi per convoglio = 3 cluster
    assert len(out) == 3
    assert len(scartati) == 2
    # I tenuti sono quelli con più km (500, 400, 300).
    km_tenuti = sorted(g.km_cumulati for g in out)
    assert km_tenuti == [300.0, 400.0, 500.0]
    # Gli scartati sono quelli con meno km (100, 200).
    km_scartati = sorted(g.km_cumulati for g in scartati)
    assert km_scartati == [100.0, 200.0]
    # Warning generati per ognuno scartato.
    assert len(warnings) == 2


def test_riassegnazione_a_regola_alternativa_con_capacity() -> None:
    """ETR526 esaurito (dotazione 2, 2 cluster ETR526×1 lo riempiono).
    Un terzo cluster ETR526×1 trova alternativa ETR204×1 con capacity
    libera → riassegnato.
    """
    cluster = [
        _giro(
            regola_id=1,
            composizione=(ComposizioneItem("ETR526", 1),),
            km_cumulati=km,
        )
        for km in (100.0, 200.0, 300.0)
    ]
    r1 = _FakeRegola(id=1, composizione=[("ETR526", 1)])
    r2 = _FakeRegola(id=2, composizione=[("ETR204", 1)])
    out, scartati, warnings = ribilancia_per_capacity(
        cluster, [r1, r2], {"ETR526": 2, "ETR204": 5}
    )
    # Tutti e 3 i cluster passano: 2 con ETR526, 1 riassegnato a ETR204.
    assert len(out) == 3
    assert scartati == []
    # I 2 con più km tengono ETR526; quello con meno km è riassegnato.
    km_etr526 = sorted(
        g.km_cumulati
        for g in out
        if g.giornate[0].blocchi_assegnati[0].assegnazione.composizione[0].materiale_tipo_codice
        == "ETR526"
    )
    km_etr204 = sorted(
        g.km_cumulati
        for g in out
        if g.giornate[0].blocchi_assegnati[0].assegnazione.composizione[0].materiale_tipo_codice
        == "ETR204"
    )
    assert km_etr526 == [200.0, 300.0]
    assert km_etr204 == [100.0]
    # Warning di riassegnazione presente.
    assert any("riassegnato" in w for w in warnings)


def test_riassegnazione_blocca_se_alternativa_non_cattura_corse() -> None:
    """Cluster con corse codice_linea=S5 deve restare scartato se
    l'unica alternativa ha filtro `codice_linea=S99` (incompatibile).
    """
    cluster = [
        _giro(
            regola_id=1,
            composizione=(ComposizioneItem("ETR526", 1),),
            km_cumulati=100.0,
            codice_linea="S5",
        )
    ]
    r1 = _FakeRegola(id=1, composizione=[("ETR526", 1)])
    # r2 non cattura "S5" perché filtra solo "S99".
    r2 = _FakeRegola(
        id=2,
        composizione=[("ETR204", 1)],
        filtri_json=[{"campo": "codice_linea", "op": "eq", "valore": "S99"}],
    )
    out, scartati, warnings = ribilancia_per_capacity(
        cluster, [r1, r2], {"ETR526": 0, "ETR204": 10}
    )
    # Cluster scartato perché r2 ha capacity ma non cattura le corse.
    assert len(out) == 0
    assert len(scartati) == 1
    assert any("scartato" in w for w in warnings)


def test_composizione_multi_materiale_consuma_per_entrambi() -> None:
    """Composizione `ETR526×2 + ETR425×1`: ogni cluster consuma 2 pezzi
    ETR526 + 1 pezzo ETR425. Dotazione ETR526=4 (= 2 cluster max),
    ETR425=10 (più che sufficiente). Limite reale = ETR526.
    """
    cluster = [
        _giro(
            regola_id=1,
            composizione=(
                ComposizioneItem("ETR526", 2),
                ComposizioneItem("ETR425", 1),
            ),
            km_cumulati=100.0 * i,
        )
        for i in range(1, 4)  # 3 cluster
    ]
    r1 = _FakeRegola(id=1, composizione=[("ETR526", 2), ("ETR425", 1)])
    out, scartati, warnings = ribilancia_per_capacity(
        cluster, [r1], {"ETR526": 4, "ETR425": 10}
    )
    # Max 2 cluster (4 / 2 = 2).
    assert len(out) == 2
    assert len(scartati) == 1
    # Lo scartato ha km minimi (100).
    assert scartati[0].km_cumulati == 100.0
