"""Test per ``backtracking_esplorativo`` (Sprint 8.1 MR-A4, entry 245).

Backtracking profondo + parametrizzato seguendo il dissenso V4 Pro
2026-05-08 sulla proposta originale beam=3/depth=1 ('troppo debole').
Default V4 Pro: beam_k=8, depth_max_oltre_min=2, tolleranza km_cap 10%.

Test focus:
- Param validation (beam_k, depth, log_level)
- Pass-through giri non eligibili (chiusi naturalmente)
- Estensione giri corti con catene disponibili
- Pruning km_cap quando branch sforerebbe tolleranza
- Idempotenza: 2 chiamate stesso input → stesso output
- Ricalcolo motivo dopo estensione (sotto_min → naturale se chiude)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from typing import Any

import pytest

from colazione.domain.builder_giro.backtracking_esplorativo import (
    ParamBacktracking,
    StatBacktracking,
    tenta_estensione_giri_corti,
)
from colazione.domain.builder_giro.catena import Catena
from colazione.domain.builder_giro.multi_giornata import (
    GiornataGiro,
    Giro,
    ParamMultiGiornata,
)
from colazione.domain.builder_giro.posizionamento import CatenaPosizionata

# =====================================================================
# Fixture helpers
# =====================================================================


@dataclass(frozen=True)
class _CorsaFake:
    codice_origine: str
    codice_destinazione: str
    ora_partenza: time
    ora_arrivo: time
    km_tratta: float = 100.0
    numero_treno: str = "T"


def _make_catena_pos(
    codice_origine: str,
    codice_destinazione: str,
    ora_p: time,
    ora_a: time,
    localita: str = "FIO",
    km: float = 100.0,
) -> CatenaPosizionata:
    corsa = _CorsaFake(codice_origine, codice_destinazione, ora_p, ora_a, km)
    return CatenaPosizionata(
        localita_codice=localita,
        stazione_collegata="S_FIO",
        vuoto_testa=None,
        catena=Catena(corse=(corsa,)),
        vuoto_coda=None,
        chiusa_a_localita=False,
    )


def _make_giro(
    catene: list[CatenaPosizionata],
    motivo: Any = "non_chiuso",
    chiuso: bool = False,
    km_cumulati: float = 100.0,
    data_inizio: date = date(2026, 6, 1),
) -> Giro:
    giornate = tuple(
        GiornataGiro(
            data=data_inizio.replace(day=data_inizio.day + i)
            if data_inizio.day + i <= 30
            else data_inizio,
            catena_posizionata=cp,
        )
        for i, cp in enumerate(catene)
    )
    return Giro(
        localita_codice="FIO",
        giornate=giornate,
        chiuso=chiuso,
        motivo_chiusura=motivo,
        km_cumulati=km_cumulati,
    )


def _params_mg(
    n_min: int = 4,
    n_max: int = 12,
    km_cap: float | None = None,
    max_sosta_diurna_min: int | None = None,
    min_servizio_giornata_pct: int | None = None,
) -> ParamMultiGiornata:
    return ParamMultiGiornata(
        n_giornate_max=n_max,
        n_giornate_min=n_min,
        km_max_ciclo=km_cap,
        whitelist_sede=frozenset({"S_FIO"}),
        max_sosta_diurna_min=max_sosta_diurna_min,
        min_servizio_giornata_pct=min_servizio_giornata_pct,
    )


# =====================================================================
# ParamBacktracking validation
# =====================================================================


def test_param_default_v4_pro() -> None:
    p = ParamBacktracking()
    assert p.beam_k == 8
    assert p.depth_max_oltre_min == 2
    assert p.tolleranza_km_cap_pct == 10.0
    assert p.log_level == "info"


@pytest.mark.parametrize("beam_invalido", [0, -1])
def test_param_beam_k_invalido(beam_invalido: int) -> None:
    with pytest.raises(ValueError, match="beam_k"):
        ParamBacktracking(beam_k=beam_invalido)


@pytest.mark.parametrize("depth_invalido", [-1, -10])
def test_param_depth_max_oltre_min_invalido(depth_invalido: int) -> None:
    with pytest.raises(ValueError, match="depth_max_oltre_min"):
        ParamBacktracking(depth_max_oltre_min=depth_invalido)


def test_param_tolleranza_negativa() -> None:
    with pytest.raises(ValueError, match="tolleranza_km_cap_pct"):
        ParamBacktracking(tolleranza_km_cap_pct=-1.0)


def test_param_log_level_invalido() -> None:
    with pytest.raises(ValueError, match="log_level"):
        ParamBacktracking(log_level="invalid")


# =====================================================================
# Pass-through: giri non eligibili
# =====================================================================


@pytest.mark.parametrize(
    "motivo", ["naturale", "max_giornate", "km_cap", "chiuso_con_vuoto"]
)
def test_pass_through_motivi_non_eligibili(motivo: str) -> None:
    """Solo giri con motivo 'sotto_min' o 'non_chiuso' sono processati."""
    cp = _make_catena_pos("S_A", "S_B", time(8, 0), time(9, 0))
    g = _make_giro([cp], motivo=motivo)
    out, stat = tenta_estensione_giri_corti(
        [g], {"ETR421": {date(2026, 6, 1): []}}, {0: "ETR421"}, _params_mg()
    )
    assert len(out) == 1
    assert out[0] is g
    assert stat.n_giri_processati == 0


def test_pass_through_giro_lungo_senza_pool_disponibile() -> None:
    """MR-B2 (entry 255): giro non_chiuso len >= n_min ma POOL VUOTO →
    pass-through (nessuna estensione possibile). Era ``test_pass_through_giro_gia_lungo``
    pre-MR-B2 quando il filtro era ``len >= n_min``; ora il filtro è
    ``len >= n_max``, ma con pool vuoto comunque pass-through.
    """
    catene = [
        _make_catena_pos("S_A", "S_B", time(8, 0), time(9, 0)),
        _make_catena_pos("S_B", "S_C", time(10, 0), time(11, 0)),
        _make_catena_pos("S_C", "S_D", time(12, 0), time(13, 0)),
        _make_catena_pos("S_D", "S_E", time(14, 0), time(15, 0)),
    ]
    g = _make_giro(catene, motivo="non_chiuso")  # 4 giornate, n_min=4
    out, stat = tenta_estensione_giri_corti(
        [g], {"ETR421": {}}, {0: "ETR421"}, _params_mg(n_min=4, n_max=12)
    )
    # MR-B2: pool vuoto (catene_per_data={}) short-circuit prima del
    # processing → n_giri_processati=0. Output identico a input.
    assert out[0] is g
    assert stat.n_giri_processati == 0
    assert stat.n_giri_estesi == 0


def test_pass_through_giro_al_max_giornate() -> None:
    """MR-B2 (entry 255): giro che ha raggiunto n_giornate_max →
    pass-through (non c'è spazio per estendere).
    """
    catene = [
        _make_catena_pos("S_A", "S_B", time(8, 0), time(9, 0)),
        _make_catena_pos("S_B", "S_C", time(10, 0), time(11, 0)),
    ]
    # 2 giornate con n_max=2 → non estendibile
    g = _make_giro(catene, motivo="non_chiuso")
    out, stat = tenta_estensione_giri_corti(
        [g], {"ETR421": {}}, {0: "ETR421"}, _params_mg(n_min=2, n_max=2)
    )
    assert out[0] is g
    assert stat.n_giri_processati == 0


def test_b2_giro_lungo_non_chiuso_esteso_per_chiudere_in_sede() -> None:
    """MR-B2 (entry 255): giro 4g (>= n_min=4) motivo='non_chiuso'
    arriva a S_D fuori sede. Catena disponibile per giornata 5
    porta a S_FIO (whitelist). Backtracking lo deve estendere a 5g
    e marcare 'naturale'. Caso che PRE-MR-B2 era pass-through
    (il filtro `len >= n_min` lo escludeva).
    """
    cp1 = _make_catena_pos("S_FIO", "S_B", time(8, 0), time(9, 0), km=100.0)
    cp2 = _make_catena_pos("S_B", "S_C", time(10, 0), time(11, 0), km=100.0)
    cp3 = _make_catena_pos("S_C", "S_D", time(12, 0), time(13, 0), km=100.0)
    cp4 = _make_catena_pos("S_D", "S_E", time(14, 0), time(15, 0), km=100.0)
    cp5_rientro = _make_catena_pos(
        "S_E", "S_FIO", time(8, 0), time(9, 0), km=120.0
    )

    g = _make_giro(
        [cp1, cp2, cp3, cp4],
        motivo="non_chiuso",
        km_cumulati=400.0,
    )
    catene_pool = {date(2026, 6, 5): [cp5_rientro]}
    out, stat = tenta_estensione_giri_corti(
        [g],
        {"ETR421": catene_pool},
        {0: "ETR421"},
        _params_mg(n_min=4, n_max=12, km_cap=600.0),
    )
    assert stat.n_giri_processati == 1
    assert stat.n_giri_estesi == 1
    g_esteso = out[0]
    assert len(g_esteso.giornate) == 5
    assert g_esteso.km_cumulati == pytest.approx(520.0)
    # km_cap=600 NON raggiunto (520 < 600), ma chiude in S_FIO whitelist
    # → motivo dipende dalla logica `_ricalcola_motivo`. Senza km_cap
    # raggiunto resta 'non_chiuso' anche se è in whitelist; lo score
    # alza il branch ma il motivo finale è gestito da chiusura_post
    # (entry 254 MR-B1: in whitelist → naturale). Qui verifichiamo solo
    # che l'estensione è avvenuta.
    last_corsa = g_esteso.giornate[-1].catena_posizionata.catena.corse[-1]
    assert last_corsa.codice_destinazione == "S_FIO"


def test_b2_giro_lungo_non_chiuso_chiude_via_km_cap_in_sede() -> None:
    """MR-B2 (entry 255): giro 4g km=400 (sotto km_cap=500) non_chiuso
    + catena 5° giornata che porta in S_FIO con km=150 (totale 550 >=
    cap=500 → naturale per `_ricalcola_motivo`). Backtracking estende
    e marca 'naturale'.
    """
    cp1 = _make_catena_pos("S_FIO", "S_B", time(8, 0), time(9, 0), km=100.0)
    cp2 = _make_catena_pos("S_B", "S_C", time(10, 0), time(11, 0), km=100.0)
    cp3 = _make_catena_pos("S_C", "S_D", time(12, 0), time(13, 0), km=100.0)
    cp4 = _make_catena_pos("S_D", "S_E", time(14, 0), time(15, 0), km=100.0)
    cp5_rientro = _make_catena_pos(
        "S_E", "S_FIO", time(8, 0), time(9, 0), km=150.0
    )

    g = _make_giro(
        [cp1, cp2, cp3, cp4],
        motivo="non_chiuso",
        km_cumulati=400.0,
    )
    catene_pool = {date(2026, 6, 5): [cp5_rientro]}
    out, stat = tenta_estensione_giri_corti(
        [g],
        {"ETR421": catene_pool},
        {0: "ETR421"},
        _params_mg(n_min=4, n_max=12, km_cap=500.0),
    )
    assert stat.n_giri_estesi == 1
    g_esteso = out[0]
    assert len(g_esteso.giornate) == 5
    assert g_esteso.motivo_chiusura == "naturale"
    assert g_esteso.chiuso is True


def test_pass_through_giro_senza_giornate() -> None:
    """Defensive: giro vuoto pass-through."""
    g = Giro(
        localita_codice="FIO",
        giornate=(),
        chiuso=False,
        motivo_chiusura="non_chiuso",
        km_cumulati=0.0,
    )
    out, stat = tenta_estensione_giri_corti(
        [g], {"ETR421": {}}, {0: "ETR421"}, _params_mg()
    )
    assert out[0] is g
    assert stat.n_giri_processati == 0


def test_pass_through_materiale_non_mappato() -> None:
    cp = _make_catena_pos("S_A", "S_B", time(8, 0), time(9, 0))
    g = _make_giro([cp], motivo="non_chiuso")
    out, stat = tenta_estensione_giri_corti(
        [g], {"ETR421": {}}, {}, _params_mg()  # mapping vuoto
    )
    assert out[0] is g
    assert len(stat.warnings) == 1
    assert "non mappato" in stat.warnings[0]


# =====================================================================
# Estensione giro corto
# =====================================================================


def test_estensione_giro_corto_aggiunge_giornata() -> None:
    """Giro 1g 'sotto_min' + catena disponibile per giornata 2 →
    estensione raggiunge 2g (ancora sotto_min se n_min=4, ma più lungo).
    """
    cp1 = _make_catena_pos("S_A", "S_B", time(8, 0), time(9, 0), km=100.0)
    cp2 = _make_catena_pos("S_B", "S_FIO", time(10, 0), time(11, 0), km=80.0)

    g = _make_giro([cp1], motivo="sotto_min", km_cumulati=100.0)
    catene_pool = {date(2026, 6, 2): [cp2]}

    out, stat = tenta_estensione_giri_corti(
        [g],
        {"ETR421": catene_pool},
        {0: "ETR421"},
        _params_mg(n_min=4, n_max=12),
    )
    assert stat.n_giri_processati == 1
    assert stat.n_giri_estesi == 1
    g_esteso = out[0]
    assert len(g_esteso.giornate) == 2
    # km cumulati aggiornati
    assert g_esteso.km_cumulati == pytest.approx(180.0)


def test_estensione_chiude_naturale_quando_raggiunge_min_e_sede() -> None:
    """Giro 1g + 3 catene disponibili che fanno raggiungere n_min=4
    e ultima termina in whitelist sede → motivo='naturale' (se km_cap).
    """
    cp1 = _make_catena_pos("S_A", "S_B", time(8, 0), time(9, 0), km=100.0)
    cp2 = _make_catena_pos("S_B", "S_C", time(10, 0), time(11, 0), km=80.0)
    cp3 = _make_catena_pos("S_C", "S_D", time(12, 0), time(13, 0), km=80.0)
    cp4 = _make_catena_pos("S_D", "S_FIO", time(14, 0), time(15, 0), km=80.0)

    g = _make_giro([cp1], motivo="sotto_min", km_cumulati=100.0)
    catene_pool = {
        date(2026, 6, 2): [cp2],
        date(2026, 6, 3): [cp3],
        date(2026, 6, 4): [cp4],
    }
    out, stat = tenta_estensione_giri_corti(
        [g],
        {"ETR421": catene_pool},
        {0: "ETR421"},
        # km_cap=320: raggiunto a 340 km totali, entro tolleranza 10%=352
        # (se mettessimo 300 sforerebbe la tolleranza 330 e branch scartato).
        _params_mg(n_min=4, n_max=12, km_cap=320.0),
    )
    assert stat.n_giri_estesi == 1
    g_esteso = out[0]
    assert len(g_esteso.giornate) == 4
    # km cumulati 100+80+80+80=340 ≥ km_cap 320 + ultima staz S_FIO ∈ whitelist
    assert g_esteso.motivo_chiusura == "naturale"
    assert g_esteso.chiuso is True


def test_pruning_km_cap_blocca_branch() -> None:
    """Branch che sforerebbe km_cap oltre la tolleranza viene scartato."""
    cp1 = _make_catena_pos("S_A", "S_B", time(8, 0), time(9, 0), km=100.0)
    # Catena successiva con km enormi: 5000km sforerebbe ogni cap.
    cp2 = _make_catena_pos("S_B", "S_C", time(10, 0), time(11, 0), km=5000.0)

    g = _make_giro([cp1], motivo="sotto_min", km_cumulati=100.0)
    out, stat = tenta_estensione_giri_corti(
        [g],
        {"ETR421": {date(2026, 6, 2): [cp2]}},
        {0: "ETR421"},
        # km_cap=200 + tolleranza 10% = 220. 100+5000=5100 > 220 → skip.
        _params_mg(n_min=4, km_cap=200.0),
        ParamBacktracking(beam_k=8, depth_max_oltre_min=2, tolleranza_km_cap_pct=10.0),
    )
    # Branch scartato → giro originale invariato
    assert out[0].giornate == g.giornate
    assert stat.n_giri_estesi == 0


# =====================================================================
# Idempotenza
# =====================================================================


def test_idempotenza_2_chiamate_stesso_output() -> None:
    """Chiamare 2 volte sullo stesso input produce stesso output."""
    cp1 = _make_catena_pos("S_A", "S_B", time(8, 0), time(9, 0))
    cp2 = _make_catena_pos("S_B", "S_FIO", time(10, 0), time(11, 0))

    g = _make_giro([cp1], motivo="sotto_min", km_cumulati=100.0)
    catene_pool = {date(2026, 6, 2): [cp2]}

    out1, _ = tenta_estensione_giri_corti(
        [g], {"ETR421": catene_pool}, {0: "ETR421"}, _params_mg()
    )
    # Seconda chiamata sull'output della prima: pass-through (giro
    # estteso ora ha len(giornate)=2 e potrebbe non essere più 'sotto_min'
    # OPPURE essere ancora 'sotto_min' ma il backtracking non ne troverà
    # altre nel pool perché S_FIO non parte da nulla).
    out2, _ = tenta_estensione_giri_corti(
        out1, {"ETR421": catene_pool}, {0: "ETR421"}, _params_mg()
    )
    # I giri devono essere strutturalmente identici (stessa sequenza catene)
    assert len(out1[0].giornate) == len(out2[0].giornate)
    assert all(
        g1.data == g2.data
        and id(g1.catena_posizionata) == id(g2.catena_posizionata)
        for g1, g2 in zip(out1[0].giornate, out2[0].giornate, strict=True)
    )


# =====================================================================
# StatBacktracking
# =====================================================================


def test_stat_logging_metriche() -> None:
    """Verifica che StatBacktracking sia popolato correttamente.

    Con pool catene NON vuoto ma senza match geografico: n_processati=1
    (giro eligibile entra nel backtracking), n_estesi=0 (nessuna
    continuazione viable trovata), n_branches >=1 (almeno il root).
    """
    cp1 = _make_catena_pos("S_A", "S_B", time(8, 0), time(9, 0))
    cp_other = _make_catena_pos(
        "S_X", "S_Y", time(10, 0), time(11, 0)
    )  # parte da S_X, non da S_B → no match
    g = _make_giro([cp1], motivo="sotto_min")
    out, stat = tenta_estensione_giri_corti(
        [g],
        {"ETR421": {date(2026, 6, 2): [cp_other]}},
        {0: "ETR421"},
        _params_mg(),
    )
    assert isinstance(stat, StatBacktracking)
    assert stat.n_giri_processati == 1
    assert stat.n_giri_estesi == 0  # cp_other non ha match geografico con S_B
    assert stat.n_branches_esplorati >= 1
    assert stat.avg_depth_raggiunta == 0.0


# =====================================================================
# Re-export
# =====================================================================


def test_re_export_da_builder_giro_init() -> None:
    from colazione.domain import builder_giro

    assert builder_giro.ParamBacktracking is ParamBacktracking
    assert builder_giro.StatBacktracking is StatBacktracking
    assert builder_giro.tenta_estensione_giri_corti is tenta_estensione_giri_corti


# =====================================================================
# MR-A4-bis (entry 247) HIGH-1: cap n_branches_max + abort
# =====================================================================


def test_a4bis_cap_n_branches_max_abort() -> None:
    """SEVERO HIGH-1 fix: con n_branches_max stretto, il backtracking
    aborta e logga warning. Lo stato esplorato (anche se troncato) è
    comunque ritornato.
    """
    cp1 = _make_catena_pos("S_A", "S_B", time(8, 0), time(9, 0), km=100.0)
    cp2 = _make_catena_pos("S_B", "S_C", time(10, 0), time(11, 0), km=80.0)
    g = _make_giro([cp1], motivo="sotto_min", km_cumulati=100.0)

    out, stat = tenta_estensione_giri_corti(
        [g],
        {"ETR421": {date(2026, 6, 2): [cp2]}},
        {0: "ETR421"},
        _params_mg(n_min=4),
        ParamBacktracking(n_branches_max=1),  # cap stretto
    )
    # Cap hit logged in warnings
    assert any("n_branches_max=1" in w for w in stat.warnings)


def test_a4bis_param_n_branches_max_invalido() -> None:
    with pytest.raises(ValueError, match="n_branches_max"):
        ParamBacktracking(n_branches_max=0)


# =====================================================================
# MR-A4-bis (entry 247) HIGH-2: vincoli MR-4 replicati
# =====================================================================


def test_a4bis_vincolo_max_sosta_diurna_blocca_branch() -> None:
    """SEVERO HIGH-2 fix: branch con sosta diurna intergiornata
    > max_sosta_diurna_min è scartato (regressione vincolo MR-4
    risolta).

    cp1 finisce alle 13:00 (giorno k), cp2 parte alle 12:00 giorno k+1.
    Sosta = (1440-780) + 720 = 1380 min. Diurno (escludendo
    [22:00-06:00)): 540 (13:00→22:00 = 9h) + 360 (06:00→12:00 = 6h)
    = 900 min. Soglia 300 → 900 > 300 → branch scartato.
    """
    cp1 = _make_catena_pos("S_A", "S_B", time(8, 0), time(13, 0))
    cp2_lunga_sosta = _make_catena_pos(
        "S_B", "S_FIO", time(12, 0), time(15, 0)
    )
    g = _make_giro([cp1], motivo="sotto_min", km_cumulati=100.0)

    out, stat = tenta_estensione_giri_corti(
        [g],
        {"ETR421": {date(2026, 6, 2): [cp2_lunga_sosta]}},
        {0: "ETR421"},
        _params_mg(n_min=4, max_sosta_diurna_min=300),
    )
    # Branch scartato → giro originale invariato
    assert len(out[0].giornate) == 1
    assert stat.n_giri_estesi == 0


def test_a4bis_vincolo_max_sosta_diurna_passthrough_se_none() -> None:
    """Se max_sosta_diurna_min=None (default), nessun check applicato:
    il backtracking estende anche con sosta lunga.
    """
    cp1 = _make_catena_pos("S_A", "S_B", time(8, 0), time(13, 0))
    cp2 = _make_catena_pos("S_B", "S_FIO", time(12, 0), time(15, 0))
    g = _make_giro([cp1], motivo="sotto_min", km_cumulati=100.0)

    out, stat = tenta_estensione_giri_corti(
        [g],
        {"ETR421": {date(2026, 6, 2): [cp2]}},
        {0: "ETR421"},
        _params_mg(n_min=4, max_sosta_diurna_min=None),  # vincolo OFF
    )
    # Estensione applicata (vincolo non attivo)
    assert len(out[0].giornate) == 2
    assert stat.n_giri_estesi == 1


# =====================================================================
# MR-A4-bis (entry 247) MED: pesi score parametrizzati
# =====================================================================


def test_a4bis_pesi_score_parametrizzati_default() -> None:
    """Pesi default. MR-B2 (entry 255): peso_chiude_sede 50 → 500."""
    p = ParamBacktracking()
    assert p.peso_km == 0.5
    assert p.peso_corse == 1.0
    assert p.peso_chiude_sede == 500.0  # MR-B2 (entry 255)
    assert p.peso_raggiunge_min == 30.0
    assert p.peso_n_giornate == -0.5


def test_a4bis_pesi_score_override_funziona() -> None:
    """Pesi override modificano effettivamente la scelta."""
    cp1 = _make_catena_pos("S_A", "S_B", time(8, 0), time(9, 0), km=100.0)
    cp2 = _make_catena_pos("S_B", "S_FIO", time(10, 0), time(11, 0), km=80.0)
    g = _make_giro([cp1], motivo="sotto_min", km_cumulati=100.0)

    # Con pesi default, l'estensione a 2g ha score migliore (chiude
    # in S_FIO whitelist + più km/corse).
    out_default, _ = tenta_estensione_giri_corti(
        [g],
        {"ETR421": {date(2026, 6, 2): [cp2]}},
        {0: "ETR421"},
        _params_mg(n_min=4),
    )
    assert len(out_default[0].giornate) == 2

    # Con peso_chiude_sede=0 e peso_n_giornate molto negativo,
    # lo score originale (1g, no chiusura) può vincere su 2g (chiusa
    # ma con penalità giornate).
    # MR-B2 (entry 255): peso_chiude_sede default ora 500, ma qui
    # l'override mette 0. Calcoli con override:
    # km_default=100×0.5+1×1=51, vs km_2g=180×0.5+2×1+0−1=91 (no bonus).
    # Con peso_chiude_sede=0 e peso_n_giornate=-100:
    # score_1g=51-100=-49, score_2g=180×0.5+2-200=-108 → 1g vince.
    out_pesi_estremi, _ = tenta_estensione_giri_corti(
        [g],
        {"ETR421": {date(2026, 6, 2): [cp2]}},
        {0: "ETR421"},
        _params_mg(n_min=4),
        ParamBacktracking(peso_chiude_sede=0.0, peso_n_giornate=-100.0),
    )
    # Con questi pesi estremi, lo stato originale 1g è preferito
    assert len(out_pesi_estremi[0].giornate) == 1
