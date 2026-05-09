"""Test per aggregazione_linea_centrica.py (Sprint 8.2 MR-D4).

MR-D4 bridge: TurnoConvoglio → Giro compatibile col persister legacy.

Test focus:
- Traduzione 1:1 turno → giro per casi semplici
- Raggruppamento giornate per chiave sequenza (varianti calendariali)
- Determinismo (ordinamento per data canonica)
- Edge cases: turno vuoto, sede non mappata
- Calcolo chiuso/motivo_chiusura
- Wrapper multi-turno
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

from colazione.domain.builder_giro.aggregazione_linea_centrica import (
    traduci_turni_in_giri,
    traduci_turno_in_giro,
)
from colazione.domain.builder_giro.costruisci_turno_linea import (
    GiornataServizio,
    TurnoConvoglio,
)

# =====================================================================
# Fixture helpers
# =====================================================================


@dataclass(frozen=True)
class _CorsaFake:
    codice_origine: str
    codice_destinazione: str
    ora_partenza: time
    ora_arrivo: time
    codice_linea: str = "R31"
    valido_da: date = date(2026, 6, 1)
    valido_a: date = date(2026, 6, 30)
    valido_in_date_json: list[str] | None = None
    numero_treno: str = "T"
    km_tratta: float | None = 50.0


def _corsa(
    o: str, d: str, h_p: int, m_p: int, h_a: int, m_a: int, *, treno: str = "T"
) -> _CorsaFake:
    return _CorsaFake(
        codice_origine=o,
        codice_destinazione=d,
        ora_partenza=time(h_p, m_p),
        ora_arrivo=time(h_a, m_a),
        numero_treno=treno,
    )


def _giornata(
    d: date,
    corse: list[_CorsaFake],
    *,
    sosta_warnings: tuple[str, ...] = (),
) -> GiornataServizio:
    if not corse:
        return GiornataServizio(
            data=d,
            corse=(),
            stazione_inizio="",
            stazione_fine="",
            km_giornata=0.0,
            prestazione_min=0,
            warnings_sosta=sosta_warnings,
        )
    return GiornataServizio(
        data=d,
        corse=tuple(corse),  # type: ignore[arg-type]
        stazione_inizio=corse[0].codice_origine,
        stazione_fine=corse[-1].codice_destinazione,
        km_giornata=sum(c.km_tratta or 0.0 for c in corse),
        prestazione_min=180,
        warnings_sosta=sosta_warnings,
    )


def _turno(
    convoglio_id: str,
    segmento: str,
    sede: str,
    giornate: list[GiornataServizio],
) -> TurnoConvoglio:
    n_corse = sum(len(g.corse) for g in giornate)
    km = sum(g.km_giornata for g in giornate)
    return TurnoConvoglio(
        convoglio_id=convoglio_id,
        segmento_codice=segmento,
        sede_codice=sede,
        giornate=tuple(giornate),
        n_corse_totali=n_corse,
        km_totali=km,
    )


# =====================================================================
# Traduzione singolo turno
# =====================================================================


def test_traduce_turno_singola_giornata_chiusa() -> None:
    """1 giornata che chiude in stazione collegata → giro 'naturale'."""
    g = _giornata(
        date(2026, 6, 8),
        [
            _corsa("S_FIO", "S_B", 8, 0, 9, 0, treno="T1"),
            _corsa("S_B", "S_FIO", 10, 0, 11, 0, treno="T2"),
        ],
    )
    turno = _turno("R31_C0", "R31_completo", "FIO", [g])
    giro = traduci_turno_in_giro(
        turno, stazione_collegata_per_sede={"FIO": "S_FIO"}
    )
    assert giro is not None
    assert giro.localita_codice == "FIO"
    assert giro.chiuso is True
    assert giro.motivo_chiusura == "naturale"
    assert giro.km_cumulati == 100.0
    assert len(giro.giornate) == 1


def test_traduce_turno_singola_giornata_non_chiusa() -> None:
    """Giornata che NON chiude in stazione collegata → 'non_chiuso'."""
    g = _giornata(
        date(2026, 6, 8),
        [_corsa("S_FIO", "S_B", 8, 0, 9, 0, treno="T1")],
    )
    turno = _turno("R31_C0", "R31_completo", "FIO", [g])
    giro = traduci_turno_in_giro(
        turno, stazione_collegata_per_sede={"FIO": "S_FIO"}
    )
    assert giro is not None
    assert giro.chiuso is False
    assert giro.motivo_chiusura == "non_chiuso"


def test_traduce_turno_due_giornate_stessa_sequenza_aggregate() -> None:
    """2 giornate consecutive con stessa sequenza corse → 1 sola
    GiornataGiro con dates_apply=2 date."""
    g1 = _giornata(
        date(2026, 6, 8),
        [_corsa("S_FIO", "S_B", 8, 0, 9, 0, treno="T1")],
    )
    g2 = _giornata(
        date(2026, 6, 9),
        [_corsa("S_FIO", "S_B", 8, 0, 9, 0, treno="T1")],
    )
    turno = _turno("R31_C0", "R31_completo", "FIO", [g1, g2])
    giro = traduci_turno_in_giro(
        turno, stazione_collegata_per_sede={"FIO": "S_FIO"}
    )
    assert giro is not None
    assert len(giro.giornate) == 1
    gg = giro.giornate[0]
    assert gg.dates_apply == (date(2026, 6, 8), date(2026, 6, 9))


def test_traduce_turno_due_giornate_sequenze_diverse_separate() -> None:
    """2 giornate con sequenze diverse → 2 GiornataGiro separate."""
    g1 = _giornata(
        date(2026, 6, 8),
        [_corsa("S_FIO", "S_B", 8, 0, 9, 0, treno="T1")],
    )
    g2 = _giornata(
        date(2026, 6, 9),
        [_corsa("S_FIO", "S_B", 14, 0, 15, 0, treno="T9")],  # sequenza diversa
    )
    turno = _turno("R31_C0", "R31_completo", "FIO", [g1, g2])
    giro = traduci_turno_in_giro(
        turno, stazione_collegata_per_sede={"FIO": "S_FIO"}
    )
    assert giro is not None
    assert len(giro.giornate) == 2
    # Ordinate per data canonica
    assert giro.giornate[0].data < giro.giornate[1].data


def test_traduce_turno_chiuso_solo_se_tutte_le_giornate_chiudono() -> None:
    """Una sola giornata che NON chiude → tutto il giro è non_chiuso."""
    g_chiusa = _giornata(
        date(2026, 6, 8),
        [_corsa("S_FIO", "S_FIO", 8, 0, 9, 0, treno="T1")],
    )
    g_aperta = _giornata(
        date(2026, 6, 9),
        [_corsa("S_FIO", "S_X", 8, 0, 9, 0, treno="T2")],  # finisce a S_X
    )
    turno = _turno("R31_C0", "R31_completo", "FIO", [g_chiusa, g_aperta])
    giro = traduci_turno_in_giro(
        turno, stazione_collegata_per_sede={"FIO": "S_FIO"}
    )
    assert giro is not None
    assert giro.chiuso is False
    assert giro.motivo_chiusura == "non_chiuso"


# =====================================================================
# Edge cases
# =====================================================================


def test_traduce_turno_vuoto_ritorna_none() -> None:
    turno = TurnoConvoglio(
        convoglio_id="X",
        segmento_codice="X",
        sede_codice="FIO",
        giornate=(),
        n_corse_totali=0,
        km_totali=0.0,
    )
    assert (
        traduci_turno_in_giro(
            turno, stazione_collegata_per_sede={"FIO": "S_FIO"}
        )
        is None
    )


def test_traduce_turno_sede_non_mappata_ritorna_none() -> None:
    """Defensive: se la sede non è in stazione_collegata_per_sede →
    None invece di crash."""
    g = _giornata(
        date(2026, 6, 8),
        [_corsa("S_X", "S_Y", 8, 0, 9, 0, treno="T1")],
    )
    turno = _turno("X_C0", "X_completo", "SEDE_NON_MAPPATA", [g])
    assert (
        traduci_turno_in_giro(
            turno, stazione_collegata_per_sede={"FIO": "S_FIO"}
        )
        is None
    )


def test_traduce_turno_regola_id_propagato() -> None:
    """regola_id passato in mapping → propagato a CatenaPosizionata."""
    g = _giornata(
        date(2026, 6, 8),
        [_corsa("S_FIO", "S_B", 8, 0, 9, 0, treno="T1")],
    )
    turno = _turno("R31_C0", "R31_completo", "FIO", [g])
    giro = traduci_turno_in_giro(
        turno,
        stazione_collegata_per_sede={"FIO": "S_FIO"},
        regola_per_segmento={"R31_completo": 42},
    )
    assert giro is not None
    assert giro.giornate[0].catena_posizionata.regola_id == 42


def test_traduce_turno_senza_regola_id_default_none() -> None:
    """Senza mapping regola_id → None (defensive)."""
    g = _giornata(
        date(2026, 6, 8),
        [_corsa("S_FIO", "S_B", 8, 0, 9, 0, treno="T1")],
    )
    turno = _turno("R31_C0", "R31_completo", "FIO", [g])
    giro = traduci_turno_in_giro(
        turno, stazione_collegata_per_sede={"FIO": "S_FIO"}
    )
    assert giro is not None
    assert giro.giornate[0].catena_posizionata.regola_id is None


def test_traduce_turno_segmento_tronco_fallback_completo_mr_d5f() -> None:
    """Sprint 8.2 MR-D5f S2 follow-up: segmento `_tronco_X` non
    direttamente in `regola_per_segmento` ricade su `{linea}_completo`
    come regola madre (chiude bug "0 giri persistiti perché tutti
    regola_id=None" nel retry e2e prog 17)."""
    g = _giornata(
        date(2026, 6, 8),
        [_corsa("S_FIO", "S_B", 8, 0, 9, 0, treno="T1")],
    )
    turno = _turno("R31_C0", "R31_tronco_S00034", "FIO", [g])
    giro = traduci_turno_in_giro(
        turno,
        stazione_collegata_per_sede={"FIO": "S_FIO"},
        regola_per_segmento={"R31_completo": 42},
    )
    assert giro is not None
    assert giro.giornate[0].catena_posizionata.regola_id == 42


def test_traduce_turno_segmento_isolato_fallback_completo_mr_d5f() -> None:
    """Sprint 8.2 MR-D5f S2 follow-up: segmento `_isolato_X_Y`
    fallback a `{linea}_completo` (stesso pattern dei tronchi)."""
    g = _giornata(
        date(2026, 6, 8),
        [_corsa("S_FIO", "S_B", 8, 0, 9, 0, treno="T1")],
    )
    turno = _turno("RE8_C0", "RE8_isolato_S01420_S01820", "FIO", [g])
    giro = traduci_turno_in_giro(
        turno,
        stazione_collegata_per_sede={"FIO": "S_FIO"},
        regola_per_segmento={"RE8_completo": 99},
    )
    assert giro is not None
    assert giro.giornate[0].catena_posizionata.regola_id == 99


def test_traduce_turno_segmento_completo_mancante_no_fallback_mr_d5f() -> None:
    """Se ANCHE `{linea}_completo` non è mappato → regola_id resta
    None (caso davvero degenerato; downstream `_traduce_e_filtra`
    scarta con warning trasparente)."""
    g = _giornata(
        date(2026, 6, 8),
        [_corsa("S_FIO", "S_B", 8, 0, 9, 0, treno="T1")],
    )
    turno = _turno("RX_C0", "RX_tronco_S99999", "FIO", [g])
    giro = traduci_turno_in_giro(
        turno,
        stazione_collegata_per_sede={"FIO": "S_FIO"},
        regola_per_segmento={"R5_completo": 100},  # mappa una linea diversa
    )
    assert giro is not None
    assert giro.giornate[0].catena_posizionata.regola_id is None


# =====================================================================
# Sprint 8.2 MR-D5h-DUAL (entry 276) — scissione sede target/operativa
# =====================================================================


def test_traduce_turno_sede_target_diversa_da_operativa_mr_d5h() -> None:
    """Sede target (regola, dato utente) ≠ sede operativa (MR-D2 ottima)
    → Giro.localita_codice = sede_target, Giro.sede_operativa_codice
    = sede_operativa. Caso prog 17: regola ETR526 sede=FIO, MR-D2
    sceglie LEC più vicina al capolinea TIRANO.
    """
    g = _giornata(
        date(2026, 6, 8),
        [_corsa("TIRANO", "S_LEC", 8, 0, 12, 0, treno="R5-1")],
    )
    turno = _turno("R5_C0", "R5_completo", "LEC", [g])  # operativa = LEC
    giro = traduci_turno_in_giro(
        turno,
        stazione_collegata_per_sede={"LEC": "S_LEC", "FIO": "S_FIO"},
        regola_per_segmento={"R5_completo": 47},
        sede_target_per_regola={47: "FIO"},  # target = FIO (regola)
    )
    assert giro is not None
    assert giro.localita_codice == "FIO"  # = sede target (utente)
    assert giro.sede_operativa_codice == "LEC"  # = sede operativa MR-D2


def test_traduce_turno_sede_target_uguale_operativa_mr_d5h() -> None:
    """Sede target = sede operativa → Giro.sede_operativa_codice = None
    (= no divergenza segnalabile, comportamento ottimale)."""
    g = _giornata(
        date(2026, 6, 8),
        [_corsa("S_FIO", "S_B", 8, 0, 9, 0, treno="T1")],
    )
    turno = _turno("R31_C0", "R31_completo", "FIO", [g])
    giro = traduci_turno_in_giro(
        turno,
        stazione_collegata_per_sede={"FIO": "S_FIO"},
        regola_per_segmento={"R31_completo": 42},
        sede_target_per_regola={42: "FIO"},  # target == operativa
    )
    assert giro is not None
    assert giro.localita_codice == "FIO"
    assert giro.sede_operativa_codice is None  # no divergenza


def test_traduce_turno_senza_sede_target_mapping_legacy_behavior() -> None:
    """Senza `sede_target_per_regola` (chiamante legacy) → comportamento
    pre-MR-D5h-DUAL: localita_codice = sede operativa, no campo
    sede_operativa_codice."""
    g = _giornata(
        date(2026, 6, 8),
        [_corsa("S_FIO", "S_B", 8, 0, 9, 0, treno="T1")],
    )
    turno = _turno("R31_C0", "R31_completo", "FIO", [g])
    giro = traduci_turno_in_giro(
        turno,
        stazione_collegata_per_sede={"FIO": "S_FIO"},
        regola_per_segmento={"R31_completo": 42},
        # sede_target_per_regola=None
    )
    assert giro is not None
    assert giro.localita_codice == "FIO"  # = sede operativa (legacy)
    assert giro.sede_operativa_codice is None


def test_traduce_turno_sede_target_per_regola_vuoto_legacy() -> None:
    """`sede_target_per_regola={}` (mapping presente ma vuoto) →
    comportamento legacy come parametro None."""
    g = _giornata(
        date(2026, 6, 8),
        [_corsa("S_FIO", "S_B", 8, 0, 9, 0, treno="T1")],
    )
    turno = _turno("R31_C0", "R31_completo", "FIO", [g])
    giro = traduci_turno_in_giro(
        turno,
        stazione_collegata_per_sede={"FIO": "S_FIO"},
        regola_per_segmento={"R31_completo": 42},
        sede_target_per_regola={},  # vuoto
    )
    assert giro is not None
    assert giro.localita_codice == "FIO"
    assert giro.sede_operativa_codice is None


def test_traduce_turno_regola_id_non_in_sede_target_per_regola() -> None:
    """`sede_target_per_regola` non contiene regola_id → fallback
    legacy (target = operativa, no divergenza segnalabile)."""
    g = _giornata(
        date(2026, 6, 8),
        [_corsa("S_FIO", "S_B", 8, 0, 9, 0, treno="T1")],
    )
    turno = _turno("R31_C0", "R31_completo", "FIO", [g])
    giro = traduci_turno_in_giro(
        turno,
        stazione_collegata_per_sede={"FIO": "S_FIO"},
        regola_per_segmento={"R31_completo": 42},
        sede_target_per_regola={99: "ALTRA"},  # 42 NON in mapping
    )
    assert giro is not None
    assert giro.localita_codice == "FIO"
    assert giro.sede_operativa_codice is None


# =====================================================================
# Sprint 8.2 MR-D6 (entry 279) — vuoto rientro target
# =====================================================================


def test_traduce_turno_mr_d6_vuoto_rientro_chiude_giro() -> None:
    """MR-D6: turno con sede_target=FIO ma sede_operativa=LEC (capolinea
    = S_LEC). L'ultima giornata acquisisce `vuoto_coda` da S_LEC a
    S_FIO + `chiusa_a_localita=True` → giro chiuso."""
    g = _giornata(
        date(2026, 6, 8),
        [_corsa("TIRANO", "S_LEC", 14, 30, 16, 0, treno="R5-1")],
    )
    turno = _turno("R5_C0", "R5_completo", "LEC", [g])
    giro = traduci_turno_in_giro(
        turno,
        stazione_collegata_per_sede={"LEC": "S_LEC", "FIO": "S_FIO"},
        regola_per_segmento={"R5_completo": 47},
        sede_target_per_regola={47: "FIO"},
    )
    assert giro is not None
    assert giro.chiuso is True  # vuoto rientro chiude il giro
    assert giro.motivo_chiusura == "naturale"
    # Vuoto coda presente nella catena posizionata dell'ultima giornata
    cat_pos = giro.giornate[-1].catena_posizionata
    assert cat_pos.vuoto_coda is not None
    assert cat_pos.vuoto_coda.codice_origine == "S_LEC"
    assert cat_pos.vuoto_coda.codice_destinazione == "S_FIO"
    assert cat_pos.vuoto_coda.motivo == "coda"
    # ora_partenza = ora_arrivo ultima corsa (16:00)
    from datetime import time
    assert cat_pos.vuoto_coda.ora_partenza == time(16, 0)
    # ora_arrivo = +60 min default = 17:00
    assert cat_pos.vuoto_coda.ora_arrivo == time(17, 0)
    assert cat_pos.chiusa_a_localita is True


def test_traduce_turno_mr_d6_no_vuoto_se_target_uguale_operativa() -> None:
    """MR-D6: se sede_target == sede_operativa, NESSUN vuoto rientro
    aggiunto (caso felice geometrico)."""
    g = _giornata(
        date(2026, 6, 8),
        [_corsa("S_FIO", "S_FIO", 8, 0, 9, 0, treno="T1")],
    )
    turno = _turno("R31_C0", "R31_completo", "FIO", [g])
    giro = traduci_turno_in_giro(
        turno,
        stazione_collegata_per_sede={"FIO": "S_FIO"},
        regola_per_segmento={"R31_completo": 42},
        sede_target_per_regola={42: "FIO"},
    )
    assert giro is not None
    cat_pos = giro.giornate[-1].catena_posizionata
    assert cat_pos.vuoto_coda is None  # no vuoto necessario
    assert cat_pos.chiusa_a_localita is True  # già a target


def test_traduce_turno_mr_d6_vuoto_solo_ultima_giornata_di_2() -> None:
    """MR-D6: se il turno ha 2 giornate, il vuoto rientro è SOLO sulla
    seconda (= ultima del giro). La prima giornata può chiudere a
    sede operativa (= parking notte LEC)."""
    g1 = _giornata(
        date(2026, 6, 8),
        [_corsa("TIRANO", "S_LEC", 14, 0, 15, 0, treno="R5-1")],
    )
    g2 = _giornata(
        date(2026, 6, 9),
        [_corsa("S_LEC", "MILANO", 8, 0, 9, 0, treno="R5-2")],
        # nota: g2 ha sequenza DIVERSA da g1 (per evitare aggregazione)
    )
    turno = _turno("R5_C0", "R5_completo", "LEC", [g1, g2])
    giro = traduci_turno_in_giro(
        turno,
        stazione_collegata_per_sede={"LEC": "S_LEC", "FIO": "S_FIO"},
        regola_per_segmento={"R5_completo": 47},
        sede_target_per_regola={47: "FIO"},
    )
    assert giro is not None
    assert len(giro.giornate) == 2
    # G1 NO vuoto rientro (= parking LEC)
    cat_pos_g1 = giro.giornate[0].catena_posizionata
    assert cat_pos_g1.vuoto_coda is None
    # G2 SI vuoto rientro a target
    cat_pos_g2 = giro.giornate[-1].catena_posizionata
    assert cat_pos_g2.vuoto_coda is not None
    assert cat_pos_g2.vuoto_coda.codice_destinazione == "S_FIO"


def test_traduce_turno_mr_d6_no_vuoto_se_legacy_no_sede_target() -> None:
    """MR-D6: senza `sede_target_per_regola` (chiamante legacy),
    NESSUN vuoto rientro (= comportamento pre-MR-D5h-DUAL invariato).
    Backward-compat preservato."""
    g = _giornata(
        date(2026, 6, 8),
        [_corsa("X", "Y", 8, 0, 9, 0, treno="T1")],
    )
    turno = _turno("R31_C0", "R31_completo", "FIO", [g])
    giro = traduci_turno_in_giro(
        turno,
        stazione_collegata_per_sede={"FIO": "S_FIO"},
        regola_per_segmento={"R31_completo": 42},
        # sede_target_per_regola=None
    )
    assert giro is not None
    cat_pos = giro.giornate[-1].catena_posizionata
    assert cat_pos.vuoto_coda is None  # comportamento legacy invariato


def test_traduce_turno_mr_d6_stazione_target_assente_skip_vuoto() -> None:
    """MR-D6: se `sede_target` è risolto ma la sua `stazione_collegata`
    non è in `stazione_collegata_per_sede` (defensive), NO vuoto
    rientro aggiunto. Giro non chiuso (= warning trasparente)."""
    g = _giornata(
        date(2026, 6, 8),
        [_corsa("TIRANO", "S_LEC", 14, 0, 16, 0, treno="R5-1")],
    )
    turno = _turno("R5_C0", "R5_completo", "LEC", [g])
    giro = traduci_turno_in_giro(
        turno,
        stazione_collegata_per_sede={"LEC": "S_LEC"},  # FIO NON in mapping
        regola_per_segmento={"R5_completo": 47},
        sede_target_per_regola={47: "FIO"},  # target FIO ma stazione None
    )
    assert giro is not None
    cat_pos = giro.giornate[-1].catena_posizionata
    assert cat_pos.vuoto_coda is None
    # Giro NON chiuso: stazione_fine S_LEC != stazione_collegata sede
    # operativa (S_LEC) ... in realtà coincide. Caso edge: se è uguale
    # alla sede operativa, è chiuso a sede_operativa ma non a target.
    # Questo è il comportamento legacy: chiude se finisce in
    # stazione_collegata operativa.
    assert cat_pos.chiusa_a_localita is True


# =====================================================================
# Wrapper multi-turno
# =====================================================================


def test_wrapper_multi_turni_ordinati_deterministicamente() -> None:
    """Più turni → output ordinato per (sede, data prima giornata)."""
    g_fio = _giornata(
        date(2026, 6, 8),
        [_corsa("S_FIO", "S_FIO", 8, 0, 9, 0, treno="T1")],
    )
    g_cre = _giornata(
        date(2026, 6, 8),
        [_corsa("S_CRE", "S_CRE", 8, 0, 9, 0, treno="T2")],
    )
    turno_fio = _turno("R31_C0", "R31_completo", "FIO", [g_fio])
    turno_cre = _turno("R6_C0", "R6_completo", "CRE", [g_cre])

    giri = traduci_turni_in_giri(
        [turno_cre, turno_fio],  # ordine input invertito
        stazione_collegata_per_sede={"FIO": "S_FIO", "CRE": "S_CRE"},
    )
    # Output ordinato alfabeticamente per sede
    assert [g.localita_codice for g in giri] == ["CRE", "FIO"]


def test_wrapper_skippa_turni_vuoti() -> None:
    """Turni con giornate=() vengono skippati."""
    g = _giornata(
        date(2026, 6, 8),
        [_corsa("S_FIO", "S_FIO", 8, 0, 9, 0, treno="T1")],
    )
    turno_ok = _turno("OK_C0", "OK_seg", "FIO", [g])
    turno_vuoto = TurnoConvoglio(
        convoglio_id="V_C0",
        segmento_codice="V_seg",
        sede_codice="FIO",
        giornate=(),
        n_corse_totali=0,
        km_totali=0.0,
    )
    giri = traduci_turni_in_giri(
        [turno_ok, turno_vuoto],
        stazione_collegata_per_sede={"FIO": "S_FIO"},
    )
    assert len(giri) == 1


def test_wrapper_skippa_turni_sede_non_mappata() -> None:
    g = _giornata(
        date(2026, 6, 8),
        [_corsa("S_X", "S_Y", 8, 0, 9, 0, treno="T1")],
    )
    turno = _turno("X_C0", "X_seg", "SEDE_X", [g])
    giri = traduci_turni_in_giri(
        [turno], stazione_collegata_per_sede={"FIO": "S_FIO"}
    )
    assert giri == []


# =====================================================================
# Idempotenza
# =====================================================================


def test_idempotenza_traduzione() -> None:
    g = _giornata(
        date(2026, 6, 8),
        [_corsa("S_FIO", "S_B", 8, 0, 9, 0, treno="T1")],
    )
    turno = _turno("R31_C0", "R31_completo", "FIO", [g])
    giro1 = traduci_turno_in_giro(
        turno, stazione_collegata_per_sede={"FIO": "S_FIO"}
    )
    giro2 = traduci_turno_in_giro(
        turno, stazione_collegata_per_sede={"FIO": "S_FIO"}
    )
    assert giro1 == giro2


# =====================================================================
# Integrazione D2-D3 (raccomandazione SEVERO non bloccante #1)
# =====================================================================


def test_integrazione_chain_d2_d3_d4() -> None:
    """Test cross-modulo: AssegnazioneSegmento (D2) →
    TurnoConvoglio (D3) → Giro (D4) end-to-end. Verifica che
    le interfacce siano compatibili.
    """
    from colazione.domain.builder_giro.assegna_convogli_linea import (
        AssegnazioneSegmento,
    )
    from colazione.domain.builder_giro.costruisci_turno_linea import (
        costruisci_turno_per_convoglio,
    )
    from colazione.domain.builder_giro.definizione_linea import (
        SegmentoLinea,
        TipoSegmento,
        VincoliSosta,
    )
    from colazione.domain.builder_giro.gestione_calendario_linea import (
        CalendarioSegmento,
        TipoCalendario,
    )

    seg = SegmentoLinea(
        codice="R31_completo",
        tipo=TipoSegmento.LINEARE,
        capolinee=frozenset({"S_FIO", "S_B"}),
        stazioni_sosta_notturna=frozenset({"S_FIO", "S_B"}),
        vincoli_sosta=VincoliSosta(),
        n_corse_per_die_media=2.0,
    )
    cal = CalendarioSegmento(
        segmento_codice="R31_completo",
        date_per_tipo={
            TipoCalendario.FERIALE: frozenset({date(2026, 6, 8)})
        },
    )
    ass = AssegnazioneSegmento(
        segmento_codice="R31_completo",
        sede_codice="FIO",
        n_convogli=1,
        materiale="ETR522",
    )
    corse = [
        _corsa("S_FIO", "S_B", 8, 0, 9, 0, treno="T1"),
        _corsa("S_B", "S_FIO", 10, 0, 11, 0, treno="T2"),
    ]
    # D3: costruisce turno
    turno = costruisci_turno_per_convoglio(
        convoglio_id="R31_completo_C0",
        segmento=seg,
        assegnazione=ass,
        calendario=cal,
        corse_segmento=corse,  # type: ignore[arg-type]
        indice_convoglio=0,
        n_convogli_segmento=1,
    )
    # D4: traduce in giro
    giro = traduci_turno_in_giro(
        turno, stazione_collegata_per_sede={"FIO": "S_FIO"}
    )
    assert giro is not None
    assert giro.localita_codice == "FIO"
    assert giro.chiuso is True
    assert giro.km_cumulati == 100.0
