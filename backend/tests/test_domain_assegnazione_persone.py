"""Test domain/normativa/assegnazione_persone.py — Sub-MR 2.bis-a.

Unit pure (no DB) per l'algoritmo greedy di auto-assegnazione persone
PdC alle giornate dei turni. Copre:

- HARD: indisponibilità, doppia assegnazione, riposo intraturno (11/14/16h)
- SOFT: FR cap 1/sett + 3/28gg, riposo settimanale 62h (euristica),
  primo giorno post-riposo non mattino
- Determinismo (idempotenza): stesso input → stesso output
- delta_copertura_pct
- assegnazioni_esistenti rispettate
"""

from __future__ import annotations

from datetime import date, time

from colazione.domain.normativa.assegnazione_persone import (
    FR_CAP_28GG,
    FR_CAP_SETTIMANA,
    Assegnazione,
    AssegnazioneEsistente,
    GiornataDaAssegnare,
    IndisponibilitaPeriodo,
    Mancanza,
    MotivoMancanza,
    PersonaCandidata,
    RisultatoAutoAssegna,
    TipoWarningSoft,
    auto_assegna,
)

# =====================================================================
# Helpers di costruzione (DRY)
# =====================================================================


def _gd(
    *,
    giornata_id: int,
    turno_id: int = 100,
    data_iso: str,
    deposito_id: int = 1,
    inizio: tuple[int, int] = (6, 0),
    fine: tuple[int, int] = (14, 0),
    is_notturno: bool = False,
    is_fr: bool = False,
) -> GiornataDaAssegnare:
    return GiornataDaAssegnare(
        turno_pdc_giornata_id=giornata_id,
        turno_pdc_id=turno_id,
        data=date.fromisoformat(data_iso),
        deposito_pdc_id=deposito_id,
        inizio_prestazione=time(*inizio),
        fine_prestazione=time(*fine),
        is_notturno=is_notturno,
        is_fr=is_fr,
    )


def _persona(
    *,
    pid: int,
    deposito_id: int = 1,
    indisp: tuple[tuple[str, str], ...] = (),
) -> PersonaCandidata:
    return PersonaCandidata(
        id=pid,
        sede_residenza_id=deposito_id,
        indisponibilita=tuple(
            IndisponibilitaPeriodo(
                data_inizio=date.fromisoformat(d_da),
                data_fine=date.fromisoformat(d_a),
            )
            for d_da, d_a in indisp
        ),
    )


# =====================================================================
# Caso base: tutto coperto
# =====================================================================


def test_caso_base_una_giornata_una_persona_assegnata() -> None:
    risultato = auto_assegna(
        giornate=[_gd(giornata_id=1, data_iso="2026-05-04")],
        persone=[_persona(pid=10)],
        assegnazioni_esistenti=[],
    )
    assert risultato.n_giornate_totali == 1
    assert risultato.n_giornate_coperte == 1
    assert risultato.delta_copertura_pct == 100.0
    assert risultato.mancanze == ()
    assert risultato.warning_soft == ()
    assert risultato.assegnazioni == (
        Assegnazione(persona_id=10, turno_pdc_giornata_id=1, data=date(2026, 5, 4)),
    )


def test_first_fit_id_minimo_deterministico() -> None:
    """Tra più candidati, vince il persona.id minimo (idempotenza)."""
    risultato = auto_assegna(
        giornate=[_gd(giornata_id=1, data_iso="2026-05-04")],
        persone=[_persona(pid=30), _persona(pid=10), _persona(pid=20)],
        assegnazioni_esistenti=[],
    )
    assert risultato.assegnazioni[0].persona_id == 10


def test_idempotenza_run_ripetuto() -> None:
    """Con stesso input, due chiamate producono lo stesso output."""
    giornate = [
        _gd(giornata_id=1, data_iso="2026-05-04"),
        _gd(giornata_id=2, data_iso="2026-05-05"),
    ]
    persone = [_persona(pid=10), _persona(pid=20)]
    r1 = auto_assegna(
        giornate=giornate, persone=persone, assegnazioni_esistenti=[]
    )
    r2 = auto_assegna(
        giornate=giornate, persone=persone, assegnazioni_esistenti=[]
    )
    assert r1 == r2


# =====================================================================
# Vincoli HARD
# =====================================================================


def test_hard_nessun_pdc_deposito() -> None:
    """Giornata con deposito_pdc_id senza persone → mancanza."""
    risultato = auto_assegna(
        giornate=[_gd(giornata_id=1, data_iso="2026-05-04", deposito_id=99)],
        persone=[_persona(pid=10, deposito_id=1)],  # deposito 1 ≠ 99
        assegnazioni_esistenti=[],
    )
    assert risultato.assegnazioni == ()
    assert len(risultato.mancanze) == 1
    assert risultato.mancanze[0].motivo == MotivoMancanza.NESSUN_PDC_DEPOSITO


def test_hard_indisponibilita_blocca_persona() -> None:
    """Persona con indisp che copre la data → skippata."""
    risultato = auto_assegna(
        giornate=[_gd(giornata_id=1, data_iso="2026-05-04")],
        persone=[
            _persona(pid=10, indisp=(("2026-05-01", "2026-05-10"),)),
            _persona(pid=20),
        ],
        assegnazioni_esistenti=[],
    )
    assert risultato.assegnazioni[0].persona_id == 20


def test_hard_tutti_indisponibili_genera_motivo_specifico() -> None:
    risultato = auto_assegna(
        giornate=[_gd(giornata_id=1, data_iso="2026-05-04")],
        persone=[
            _persona(pid=10, indisp=(("2026-05-04", "2026-05-04"),)),
            _persona(pid=20, indisp=(("2026-04-01", "2026-12-31"),)),
        ],
        assegnazioni_esistenti=[],
    )
    assert risultato.assegnazioni == ()
    assert risultato.mancanze[0].motivo == MotivoMancanza.TUTTI_INDISPONIBILI


def test_hard_indisp_estremi_inclusivi() -> None:
    """Data uguale a data_inizio o data_fine → indisponibile."""
    # data_inizio = data target
    r1 = auto_assegna(
        giornate=[_gd(giornata_id=1, data_iso="2026-05-04")],
        persone=[_persona(pid=10, indisp=(("2026-05-04", "2026-05-10"),))],
        assegnazioni_esistenti=[],
    )
    assert r1.mancanze[0].motivo == MotivoMancanza.TUTTI_INDISPONIBILI
    # data_fine = data target
    r2 = auto_assegna(
        giornate=[_gd(giornata_id=1, data_iso="2026-05-04")],
        persone=[_persona(pid=10, indisp=(("2026-05-01", "2026-05-04"),))],
        assegnazioni_esistenti=[],
    )
    assert r2.mancanze[0].motivo == MotivoMancanza.TUTTI_INDISPONIBILI


def test_hard_no_doppia_assegnazione_stessa_data() -> None:
    """Una persona non può coprire 2 giornate la stessa data."""
    risultato = auto_assegna(
        giornate=[
            _gd(giornata_id=1, turno_id=100, data_iso="2026-05-04"),
            _gd(giornata_id=2, turno_id=200, data_iso="2026-05-04"),
        ],
        persone=[_persona(pid=10)],  # solo 1 persona
        assegnazioni_esistenti=[],
    )
    assert len(risultato.assegnazioni) == 1
    assert len(risultato.mancanze) == 1
    assert risultato.mancanze[0].motivo == MotivoMancanza.TUTTI_GIA_ASSEGNATI


def test_hard_assegnazione_esistente_blocca_persona() -> None:
    """Esistente DB su (persona, data) → skippa quella persona."""
    risultato = auto_assegna(
        giornate=[_gd(giornata_id=1, data_iso="2026-05-04")],
        persone=[_persona(pid=10), _persona(pid=20)],
        assegnazioni_esistenti=[
            AssegnazioneEsistente(
                persona_id=10,
                data=date(2026, 5, 4),
                turno_pdc_giornata_id=99,
            ),
        ],
    )
    # 10 è già assegnata altrove → vince 20
    assert risultato.assegnazioni[0].persona_id == 20


def test_hard_giornata_gia_coperta_skip_no_riassegna() -> None:
    """Se l'esistente copre già (giornata, data), skip senza riassegnare."""
    risultato = auto_assegna(
        giornate=[_gd(giornata_id=1, data_iso="2026-05-04")],
        persone=[_persona(pid=10)],
        assegnazioni_esistenti=[
            AssegnazioneEsistente(
                persona_id=99,
                data=date(2026, 5, 4),
                turno_pdc_giornata_id=1,  # stessa giornata!
            ),
        ],
    )
    assert risultato.assegnazioni == ()
    assert risultato.mancanze == ()
    assert risultato.n_giornate_coperte == 1  # contata come coperta
    assert risultato.delta_copertura_pct == 100.0


# =====================================================================
# HARD: riposo intraturno §11.5
# =====================================================================


def test_hard_riposo_intraturno_11h_blocca_consecutiva() -> None:
    """Persona finisce 14:00 D1, prossima giornata non può iniziare prima di 01:00 D2."""
    risultato = auto_assegna(
        giornate=[
            _gd(giornata_id=1, data_iso="2026-05-04", inizio=(6, 0), fine=(20, 0)),
            _gd(giornata_id=2, data_iso="2026-05-05", inizio=(5, 0), fine=(13, 0)),
        ],
        persone=[_persona(pid=10)],  # solo 1 → forza riposo
        assegnazioni_esistenti=[],
    )
    # G1: assegnata. fine=20:00 D1.
    # G2: inizia 05:00 D2 → gap = 9h < 11h → riposo violato.
    assert len(risultato.assegnazioni) == 1
    assert risultato.assegnazioni[0].turno_pdc_giornata_id == 1
    assert len(risultato.mancanze) == 1
    assert (
        risultato.mancanze[0].motivo
        == MotivoMancanza.TUTTI_RIPOSO_INTRATURNO_VIOLATO
    )


def test_hard_riposo_intraturno_11h_ok_se_gap_sufficiente() -> None:
    """Gap di 12h è ok (≥11h)."""
    risultato = auto_assegna(
        giornate=[
            _gd(giornata_id=1, data_iso="2026-05-04", inizio=(6, 0), fine=(14, 0)),
            _gd(giornata_id=2, data_iso="2026-05-05", inizio=(2, 0), fine=(10, 0)),
        ],
        persone=[_persona(pid=10)],
        assegnazioni_esistenti=[],
    )
    # G1 fine=14:00 D1, G2 inizio=02:00 D2 → gap 12h ≥ 11h → ok
    assert len(risultato.assegnazioni) == 2


def test_hard_riposo_14h_dopo_fine_notte_tarda() -> None:
    """Giornata che finisce 00:30 (notte tarda 00:01-01:00) richiede 14h."""
    risultato = auto_assegna(
        giornate=[
            # G1 inizio=18:00 D1, fine=00:30 D2 (notte tarda)
            _gd(giornata_id=1, data_iso="2026-05-04", inizio=(18, 0), fine=(0, 30)),
            # G2 inizio=13:00 D2 → gap 12h30m < 14h → violato
            _gd(giornata_id=2, data_iso="2026-05-05", inizio=(13, 0), fine=(21, 0)),
        ],
        persone=[_persona(pid=10)],
        assegnazioni_esistenti=[],
    )
    assert len(risultato.assegnazioni) == 1
    assert risultato.assegnazioni[0].turno_pdc_giornata_id == 1
    assert (
        risultato.mancanze[0].motivo
        == MotivoMancanza.TUTTI_RIPOSO_INTRATURNO_VIOLATO
    )


def test_hard_riposo_16h_dopo_notturna() -> None:
    """is_notturno=True → richiede 16h dopo."""
    risultato = auto_assegna(
        giornate=[
            # G1 inizio=22:00 D1, fine=06:00 D2, is_notturno=True
            _gd(
                giornata_id=1,
                data_iso="2026-05-04",
                inizio=(22, 0),
                fine=(6, 0),
                is_notturno=True,
            ),
            # G2 inizio=20:00 D2 → gap 14h < 16h → violato
            _gd(giornata_id=2, data_iso="2026-05-05", inizio=(20, 0), fine=(22, 0)),
        ],
        persone=[_persona(pid=10)],
        assegnazioni_esistenti=[],
    )
    assert len(risultato.assegnazioni) == 1
    assert (
        risultato.mancanze[0].motivo
        == MotivoMancanza.TUTTI_RIPOSO_INTRATURNO_VIOLATO
    )


# =====================================================================
# Vincoli SOFT
# =====================================================================


def test_soft_fr_cap_settimana_oltre_1_warning() -> None:
    """2 FR nella stessa settimana ISO per stessa persona → warning."""
    risultato = auto_assegna(
        giornate=[
            # 2026-05-04 (lun, settimana W19) e 2026-05-06 (mer, settimana W19)
            _gd(giornata_id=1, data_iso="2026-05-04", is_fr=True),
            _gd(giornata_id=2, data_iso="2026-05-06", is_fr=True),
        ],
        persone=[_persona(pid=10)],
        assegnazioni_esistenti=[],
    )
    assert len(risultato.assegnazioni) == 2
    fr_warnings = [
        w for w in risultato.warning_soft
        if w.tipo == TipoWarningSoft.FR_CAP_SETTIMANA_SUPERATO
    ]
    assert len(fr_warnings) == 1  # solo il secondo FR triggera (1° è ammesso)
    assert fr_warnings[0].data == date(2026, 5, 6)
    assert fr_warnings[0].persona_id == 10
    # Sanity check sulla costante
    assert FR_CAP_SETTIMANA == 1


def test_soft_fr_cap_28gg_oltre_3_warning() -> None:
    """4 FR nei 28 giorni rolling per stessa persona → warning."""
    risultato = auto_assegna(
        giornate=[
            _gd(giornata_id=1, data_iso="2026-05-04", is_fr=True),
            _gd(giornata_id=2, data_iso="2026-05-11", is_fr=True),
            _gd(giornata_id=3, data_iso="2026-05-18", is_fr=True),
            _gd(giornata_id=4, data_iso="2026-05-25", is_fr=True),
        ],
        persone=[_persona(pid=10)],
        assegnazioni_esistenti=[],
    )
    assert len(risultato.assegnazioni) == 4
    fr28_warnings = [
        w for w in risultato.warning_soft
        if w.tipo == TipoWarningSoft.FR_CAP_28GG_SUPERATO
    ]
    # Il 4° FR triggera. (eventualmente anche il 5° in altri scenari).
    assert len(fr28_warnings) == 1
    assert fr28_warnings[0].data == date(2026, 5, 25)
    assert FR_CAP_28GG == 3


def test_soft_fr_non_emesso_se_giornata_non_fr() -> None:
    """is_fr=False → nessun warning FR."""
    risultato = auto_assegna(
        giornate=[
            _gd(giornata_id=1, data_iso="2026-05-04", is_fr=False),
            _gd(giornata_id=2, data_iso="2026-05-06", is_fr=False),
        ],
        persone=[_persona(pid=10)],
        assegnazioni_esistenti=[],
    )
    fr_warnings = [
        w for w in risultato.warning_soft
        if w.tipo
        in (
            TipoWarningSoft.FR_CAP_SETTIMANA_SUPERATO,
            TipoWarningSoft.FR_CAP_28GG_SUPERATO,
        )
    ]
    assert fr_warnings == []


def test_soft_riposo_settimanale_warning_su_6_assegnazioni_in_7gg() -> None:
    """Heuristica: 6 assegnazioni in 7gg → warning §11.4."""
    # 6 giornate distribuite su 7gg, gap intraturno 12h ok (HARD passa)
    giornate = [
        _gd(
            giornata_id=i,
            data_iso=f"2026-05-{i:02d}",
            inizio=(8, 0),
            fine=(16, 0),
        )
        for i in range(4, 10)  # 4..9 = 6 date
    ]
    risultato = auto_assegna(
        giornate=giornate,
        persone=[_persona(pid=10)],
        assegnazioni_esistenti=[],
    )
    assert len(risultato.assegnazioni) == 6
    riposo_warnings = [
        w for w in risultato.warning_soft
        if w.tipo == TipoWarningSoft.RIPOSO_SETTIMANALE_VIOLATO
    ]
    # Triggers from the 6th assignment onwards
    assert len(riposo_warnings) >= 1


def test_soft_primo_giorno_post_riposo_mattina_warning() -> None:
    """Persona ha gap ≥2gg, riprende prima delle 06:00 → warning §11.2."""
    risultato = auto_assegna(
        giornate=[
            _gd(giornata_id=1, data_iso="2026-05-04", inizio=(8, 0), fine=(16, 0)),
            # gap di 3gg
            _gd(giornata_id=2, data_iso="2026-05-08", inizio=(5, 0), fine=(13, 0)),
        ],
        persone=[_persona(pid=10)],
        assegnazioni_esistenti=[],
    )
    assert len(risultato.assegnazioni) == 2
    mattino_warnings = [
        w for w in risultato.warning_soft
        if w.tipo == TipoWarningSoft.PRIMO_GIORNO_POST_RIPOSO_MATTINA
    ]
    assert len(mattino_warnings) == 1
    assert mattino_warnings[0].data == date(2026, 5, 8)


def test_soft_primo_giorno_post_riposo_no_warning_se_inizio_dopo_06() -> None:
    risultato = auto_assegna(
        giornate=[
            _gd(giornata_id=1, data_iso="2026-05-04", inizio=(8, 0), fine=(16, 0)),
            _gd(giornata_id=2, data_iso="2026-05-08", inizio=(7, 0), fine=(15, 0)),
        ],
        persone=[_persona(pid=10)],
        assegnazioni_esistenti=[],
    )
    mattino_warnings = [
        w for w in risultato.warning_soft
        if w.tipo == TipoWarningSoft.PRIMO_GIORNO_POST_RIPOSO_MATTINA
    ]
    assert mattino_warnings == []


# =====================================================================
# delta_copertura_pct
# =====================================================================


def test_delta_copertura_zero_giornate_e_100_pct() -> None:
    """Vuoto = perfetto."""
    risultato = auto_assegna(giornate=[], persone=[], assegnazioni_esistenti=[])
    assert risultato.delta_copertura_pct == 100.0


def test_delta_copertura_50_pct() -> None:
    """1 coperta su 2 → 50.0."""
    risultato = auto_assegna(
        giornate=[
            _gd(giornata_id=1, data_iso="2026-05-04"),
            _gd(giornata_id=2, data_iso="2026-05-04", deposito_id=99),  # no PdC
        ],
        persone=[_persona(pid=10, deposito_id=1)],
        assegnazioni_esistenti=[],
    )
    assert risultato.delta_copertura_pct == 50.0


def test_delta_copertura_round_a_1_decimale() -> None:
    """66.67% → 66.7"""
    risultato = auto_assegna(
        giornate=[
            _gd(giornata_id=1, data_iso="2026-05-04"),
            _gd(giornata_id=2, data_iso="2026-05-05"),
            _gd(giornata_id=3, data_iso="2026-05-06", deposito_id=99),
        ],
        persone=[_persona(pid=10, deposito_id=1), _persona(pid=20, deposito_id=1)],
        assegnazioni_esistenti=[],
    )
    assert risultato.delta_copertura_pct == 66.7


# =====================================================================
# Determinismo con dataclass
# =====================================================================


def test_risultato_e_frozen_dataclass() -> None:
    r = auto_assegna(giornate=[], persone=[], assegnazioni_esistenti=[])
    assert isinstance(r, RisultatoAutoAssegna)
    # Mancanza è frozen
    m = Mancanza(
        turno_pdc_giornata_id=1,
        turno_pdc_id=2,
        data=date(2026, 1, 1),
        motivo=MotivoMancanza.NESSUN_PDC_DEPOSITO,
    )
    # frozen → eq comparison stabile
    m2 = Mancanza(
        turno_pdc_giornata_id=1,
        turno_pdc_id=2,
        data=date(2026, 1, 1),
        motivo=MotivoMancanza.NESSUN_PDC_DEPOSITO,
    )
    assert m == m2
