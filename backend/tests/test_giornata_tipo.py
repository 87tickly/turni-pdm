"""Test puri MR-1110 Step 2 — ``identifica_giornate_tipo``.

Tutti i test sono **senza DB**: usano dataclass minimali per simulare
corse con ``codice_linea`` e costruiscono ``CatenaPosizionata``
direttamente (non passano da ``costruisci_catene`` +
``posiziona_su_localita``, per isolare il sub).

Coprono:

- Casi base: lista vuota, singola istanza, due istanze stesso pattern.
- Chiave 5-uple D1: separazione per servizio diverso, raggruppamento
  per servizio identico.
- Calcolo ``codice_servizio_dominante``: majority wins, tie-break
  lessicografico, ``None`` se nessuna corsa ha ``codice_linea``.
- Fallback morbido D1: orfane con servizio ``None`` fuse in gemelli
  valorizzati; orfane senza gemelli restano isolate.
- Filtro significatività D3: ``min_istanze`` configurabile.
- Determinismo: output sempre ordinato per chiave.
- Esempio realistico turno 1110 G6: 6 istanze sotto stessa fase →
  1 sola giornata-tipo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

from colazione.domain.builder_giro.catena import Catena
from colazione.domain.builder_giro.giornata_tipo import (
    CatenaIstanza,
    GiornataTipo,
    ParamGiornataTipo,
    identifica_giornate_tipo,
)
from colazione.domain.builder_giro.posizionamento import CatenaPosizionata

# =====================================================================
# Fixture
# =====================================================================


@dataclass
class FakeCorsa:
    """Corsa minimale per i test, con ``codice_linea`` opzionale.

    Mirror minimo della ``CorsaCommerciale`` ORM: i 4 campi base
    + numero_treno + codice_linea (per il calcolo del
    ``codice_servizio_dominante``).
    """

    codice_origine: str
    codice_destinazione: str
    ora_partenza: time
    ora_arrivo: time
    numero_treno: str = ""
    codice_linea: str | None = None


def _c(
    o: str,
    d: str,
    p: tuple[int, int],
    a: tuple[int, int],
    *,
    codice_linea: str | None = None,
    numero_treno: str = "",
) -> FakeCorsa:
    return FakeCorsa(
        codice_origine=o,
        codice_destinazione=d,
        ora_partenza=time(*p),
        ora_arrivo=time(*a),
        numero_treno=numero_treno,
        codice_linea=codice_linea,
    )


def _cat_pos(
    *,
    localita: str,
    stazione: str,
    corse: tuple[FakeCorsa, ...],
    chiusa: bool = True,
) -> CatenaPosizionata:
    return CatenaPosizionata(
        localita_codice=localita,
        stazione_collegata=stazione,
        vuoto_testa=None,
        catena=Catena(corse=corse),
        vuoto_coda=None,
        chiusa_a_localita=chiusa,
    )


def _ist(
    *,
    data_: date,
    materiale: str = "ETR421",
    localita: str = "FIO",
    stazione_collegata: str = "CERTOSA",
    corse: tuple[FakeCorsa, ...],
) -> CatenaIstanza:
    return CatenaIstanza(
        data=data_,
        catena_posizionata=_cat_pos(
            localita=localita,
            stazione=stazione_collegata,
            corse=corse,
        ),
        materiale_tipo_codice=materiale,
    )


D_LUN = date(2026, 4, 27)
D_MAR = date(2026, 4, 28)
D_MER = date(2026, 4, 29)
D_GIO = date(2026, 4, 30)
D_VEN = date(2026, 5, 1)
D_SAB = date(2026, 5, 2)


# =====================================================================
# Casi base
# =====================================================================


def test_lista_vuota_zero_giornate_tipo() -> None:
    giornate, orfane = identifica_giornate_tipo([])
    assert giornate == []
    assert orfane == []


def test_singola_istanza_orfana_per_min_istanze_2_default() -> None:
    """Default min_istanze=2: 1 sola istanza → 0 giornate-tipo + 1 orfana."""
    ist = _ist(
        data_=D_LUN,
        corse=(_c("VARESE", "MI.CERT", (8, 0), (9, 0), codice_linea="S5"),),
    )
    giornate, orfane = identifica_giornate_tipo([ist])
    assert giornate == []
    assert orfane == [ist]


def test_due_istanze_stesso_pattern_una_giornata_tipo() -> None:
    """2 catene identiche (in/fine/materiale/sede/servizio) → 1 GT con 2 istanze."""
    ist1 = _ist(
        data_=D_LUN,
        corse=(_c("VARESE", "MI.CERT", (8, 0), (9, 0), codice_linea="S5"),),
    )
    ist2 = _ist(
        data_=D_MAR,
        corse=(_c("VARESE", "MI.CERT", (8, 0), (9, 0), codice_linea="S5"),),
    )
    giornate, orfane = identifica_giornate_tipo([ist1, ist2])

    assert orfane == []
    assert len(giornate) == 1
    gt = giornate[0]
    assert gt.materiale_tipo_codice == "ETR421"
    assert gt.localita_codice == "FIO"
    assert gt.staz_inizio == "VARESE"
    assert gt.staz_fine == "MI.CERT"
    assert gt.codice_servizio_dominante == "S5"
    assert len(gt.istanze) == 2
    # Ordinamento per data ascendente
    assert gt.istanze[0].data == D_LUN
    assert gt.istanze[1].data == D_MAR


def test_due_pattern_diversi_due_giornate_tipo_se_min_istanze_1() -> None:
    """staz_inizio diversi, min_istanze=1 → 2 GT separate."""
    ist1 = _ist(
        data_=D_LUN,
        corse=(_c("VARESE", "MI.CERT", (8, 0), (9, 0), codice_linea="S5"),),
    )
    ist2 = _ist(
        data_=D_MAR,
        corse=(_c("BRESCIA", "MI.CERT", (8, 0), (10, 0), codice_linea="R5"),),
    )
    giornate, orfane = identifica_giornate_tipo(
        [ist1, ist2], params=ParamGiornataTipo(min_istanze=1)
    )

    assert orfane == []
    assert len(giornate) == 2
    # Output ordinato per chiave: BRESCIA prima di VARESE
    assert giornate[0].staz_inizio == "BRESCIA"
    assert giornate[1].staz_inizio == "VARESE"


# =====================================================================
# codice_servizio_dominante
# =====================================================================


def test_codice_servizio_majority_wins() -> None:
    """Catena con 3 corse [S5, S5, S7] → S5 (più frequente)."""
    ist1 = _ist(
        data_=D_LUN,
        corse=(
            _c("VARESE", "GALLARATE", (8, 0), (8, 30), codice_linea="S5"),
            _c("GALLARATE", "RHO", (8, 35), (9, 0), codice_linea="S5"),
            _c("RHO", "MI.CERT", (9, 5), (9, 30), codice_linea="S7"),
        ),
    )
    ist2 = _ist(
        data_=D_MAR,
        corse=(
            _c("VARESE", "GALLARATE", (8, 0), (8, 30), codice_linea="S5"),
            _c("GALLARATE", "RHO", (8, 35), (9, 0), codice_linea="S5"),
            _c("RHO", "MI.CERT", (9, 5), (9, 30), codice_linea="S7"),
        ),
    )
    giornate, _ = identifica_giornate_tipo([ist1, ist2])

    assert len(giornate) == 1
    assert giornate[0].codice_servizio_dominante == "S5"


def test_codice_servizio_tie_break_lessicografico() -> None:
    """Catena con 2 corse [S7, S5] → S5 (lessicografico ascendente)."""
    ist1 = _ist(
        data_=D_LUN,
        corse=(
            _c("VARESE", "RHO", (8, 0), (8, 30), codice_linea="S7"),
            _c("RHO", "MI.CERT", (8, 35), (9, 0), codice_linea="S5"),
        ),
    )
    ist2 = _ist(
        data_=D_MAR,
        corse=(
            _c("VARESE", "RHO", (8, 0), (8, 30), codice_linea="S7"),
            _c("RHO", "MI.CERT", (8, 35), (9, 0), codice_linea="S5"),
        ),
    )
    giornate, _ = identifica_giornate_tipo([ist1, ist2])

    assert len(giornate) == 1
    assert giornate[0].codice_servizio_dominante == "S5"


def test_codice_servizio_none_se_nessuna_corsa_ha_linea() -> None:
    """Catena con corse senza codice_linea → servizio None."""
    ist1 = _ist(
        data_=D_LUN,
        corse=(_c("VARESE", "MI.CERT", (8, 0), (9, 0)),),
    )
    ist2 = _ist(
        data_=D_MAR,
        corse=(_c("VARESE", "MI.CERT", (8, 0), (9, 0)),),
    )
    giornate, _ = identifica_giornate_tipo([ist1, ist2])

    assert len(giornate) == 1
    assert giornate[0].codice_servizio_dominante is None


def test_codice_servizio_misto_none_e_valorizzato_filtra_none() -> None:
    """Catena con corse [S5, None] → S5 (None ignorato)."""
    ist1 = _ist(
        data_=D_LUN,
        corse=(
            _c("VARESE", "RHO", (8, 0), (8, 30), codice_linea="S5"),
            _c("RHO", "MI.CERT", (8, 35), (9, 0)),  # no codice_linea
        ),
    )
    ist2 = _ist(
        data_=D_MAR,
        corse=(
            _c("VARESE", "RHO", (8, 0), (8, 30), codice_linea="S5"),
            _c("RHO", "MI.CERT", (8, 35), (9, 0)),
        ),
    )
    giornate, _ = identifica_giornate_tipo([ist1, ist2])

    assert len(giornate) == 1
    assert giornate[0].codice_servizio_dominante == "S5"


# =====================================================================
# Fallback morbido D1 (servizio None ↔ gemelli valorizzati)
# =====================================================================


def test_fallback_morbido_servizio_none_si_fonde_con_gemello_valorizzato() -> None:
    """1 catena con servizio S5 + 2 catene gemelle senza servizio →
    1 GT con 3 istanze e servizio S5 (orfana fusa nel gemello).
    """
    # Gemello principale: servizio S5 valorizzato
    ist_s5 = _ist(
        data_=D_LUN,
        corse=(_c("VARESE", "MI.CERT", (8, 0), (9, 0), codice_linea="S5"),),
    )
    # 2 orfane: stessi 4 prefix campi, servizio None
    ist_orfana_1 = _ist(
        data_=D_MAR,
        corse=(_c("VARESE", "MI.CERT", (8, 0), (9, 0)),),  # niente codice_linea
    )
    ist_orfana_2 = _ist(
        data_=D_MER,
        corse=(_c("VARESE", "MI.CERT", (8, 0), (9, 0)),),
    )

    giornate, orfane = identifica_giornate_tipo(
        [ist_s5, ist_orfana_1, ist_orfana_2]
    )

    assert orfane == []
    assert len(giornate) == 1
    gt = giornate[0]
    assert gt.codice_servizio_dominante == "S5"
    assert len(gt.istanze) == 3
    # Istanze ordinate per data
    assert [i.data for i in gt.istanze] == [D_LUN, D_MAR, D_MER]


def test_fallback_morbido_no_gemelli_orfana_resta_isolata() -> None:
    """2 catene gemelle entrambe senza servizio + nessun gemello
    valorizzato → 1 GT con servizio None.
    """
    ist1 = _ist(
        data_=D_LUN,
        corse=(_c("VARESE", "MI.CERT", (8, 0), (9, 0)),),
    )
    ist2 = _ist(
        data_=D_MAR,
        corse=(_c("VARESE", "MI.CERT", (8, 0), (9, 0)),),
    )
    giornate, orfane = identifica_giornate_tipo([ist1, ist2])

    assert orfane == []
    assert len(giornate) == 1
    assert giornate[0].codice_servizio_dominante is None


def test_fallback_morbido_target_e_minimo_lessicografico() -> None:
    """Più gemelli con servizi diversi → orfana fusa nel
    lessicograficamente minimo (S3 < S5).
    """
    ist_s3 = _ist(
        data_=D_LUN,
        corse=(_c("VARESE", "MI.CERT", (8, 0), (9, 0), codice_linea="S3"),),
    )
    ist_s3_due = _ist(
        data_=D_MAR,
        corse=(_c("VARESE", "MI.CERT", (8, 0), (9, 0), codice_linea="S3"),),
    )
    ist_s5 = _ist(
        data_=D_MER,
        corse=(_c("VARESE", "MI.CERT", (8, 0), (9, 0), codice_linea="S5"),),
    )
    ist_s5_due = _ist(
        data_=D_GIO,
        corse=(_c("VARESE", "MI.CERT", (8, 0), (9, 0), codice_linea="S5"),),
    )
    ist_orfana = _ist(
        data_=D_VEN,
        corse=(_c("VARESE", "MI.CERT", (8, 0), (9, 0)),),  # senza servizio
    )

    giornate, orfane = identifica_giornate_tipo(
        [ist_s3, ist_s3_due, ist_s5, ist_s5_due, ist_orfana]
    )

    assert orfane == []
    assert len(giornate) == 2

    # GT S3: 3 istanze (2 originali + orfana fusa)
    gt_s3 = next(g for g in giornate if g.codice_servizio_dominante == "S3")
    assert len(gt_s3.istanze) == 3
    assert D_VEN in {i.data for i in gt_s3.istanze}

    # GT S5: 2 istanze (orfana NON va qui)
    gt_s5 = next(g for g in giornate if g.codice_servizio_dominante == "S5")
    assert len(gt_s5.istanze) == 2
    assert D_VEN not in {i.data for i in gt_s5.istanze}


def test_servizi_diversi_separati_in_giornate_tipo_distinte() -> None:
    """Stessi 4 prefix campi ma servizi S5 ≠ S7 → 2 GT separate."""
    ist_s5_a = _ist(
        data_=D_LUN,
        corse=(_c("VARESE", "MI.CERT", (8, 0), (9, 0), codice_linea="S5"),),
    )
    ist_s5_b = _ist(
        data_=D_MAR,
        corse=(_c("VARESE", "MI.CERT", (8, 0), (9, 0), codice_linea="S5"),),
    )
    ist_s7_a = _ist(
        data_=D_MER,
        corse=(_c("VARESE", "MI.CERT", (10, 0), (11, 0), codice_linea="S7"),),
    )
    ist_s7_b = _ist(
        data_=D_GIO,
        corse=(_c("VARESE", "MI.CERT", (10, 0), (11, 0), codice_linea="S7"),),
    )

    giornate, _ = identifica_giornate_tipo(
        [ist_s5_a, ist_s5_b, ist_s7_a, ist_s7_b]
    )

    assert len(giornate) == 2
    servizi = {g.codice_servizio_dominante for g in giornate}
    assert servizi == {"S5", "S7"}


# =====================================================================
# Filtro significatività D3 + determinismo
# =====================================================================


def test_min_istanze_configurabile_3() -> None:
    """min_istanze=3 con GT a 2 istanze → vanno tutte in orfane."""
    ist1 = _ist(
        data_=D_LUN,
        corse=(_c("VARESE", "MI.CERT", (8, 0), (9, 0), codice_linea="S5"),),
    )
    ist2 = _ist(
        data_=D_MAR,
        corse=(_c("VARESE", "MI.CERT", (8, 0), (9, 0), codice_linea="S5"),),
    )
    giornate, orfane = identifica_giornate_tipo(
        [ist1, ist2], params=ParamGiornataTipo(min_istanze=3)
    )
    assert giornate == []
    assert len(orfane) == 2


def test_ordinamento_output_deterministico() -> None:
    """Output sempre ordinato per chiave 5-uple ascendente."""
    # 3 GT distinte: differenziamo per staz_inizio
    ist_v_1 = _ist(
        data_=D_LUN,
        corse=(_c("VARESE", "MI.CERT", (8, 0), (9, 0), codice_linea="S5"),),
    )
    ist_v_2 = _ist(
        data_=D_MAR,
        corse=(_c("VARESE", "MI.CERT", (8, 0), (9, 0), codice_linea="S5"),),
    )
    ist_b_1 = _ist(
        data_=D_LUN,
        corse=(_c("BRESCIA", "MI.CERT", (8, 0), (10, 0), codice_linea="R5"),),
    )
    ist_b_2 = _ist(
        data_=D_MAR,
        corse=(_c("BRESCIA", "MI.CERT", (8, 0), (10, 0), codice_linea="R5"),),
    )
    ist_a_1 = _ist(
        data_=D_LUN,
        corse=(_c("ARONA", "MI.CERT", (8, 0), (9, 30), codice_linea="R3"),),
    )
    ist_a_2 = _ist(
        data_=D_MAR,
        corse=(_c("ARONA", "MI.CERT", (8, 0), (9, 30), codice_linea="R3"),),
    )

    # Input mescolato a posta
    giornate, _ = identifica_giornate_tipo(
        [ist_v_1, ist_b_1, ist_a_1, ist_v_2, ist_b_2, ist_a_2]
    )
    staz_in_ordinati = [g.staz_inizio for g in giornate]
    assert staz_in_ordinati == ["ARONA", "BRESCIA", "VARESE"]


def test_materiali_diversi_separati() -> None:
    """Stessi staz/sede/servizio ma materiali diversi → 2 GT distinte."""
    ist_421 = _ist(
        data_=D_LUN,
        materiale="ETR421",
        corse=(_c("VARESE", "MI.CERT", (8, 0), (9, 0), codice_linea="S5"),),
    )
    ist_421_b = _ist(
        data_=D_MAR,
        materiale="ETR421",
        corse=(_c("VARESE", "MI.CERT", (8, 0), (9, 0), codice_linea="S5"),),
    )
    ist_522 = _ist(
        data_=D_MER,
        materiale="ETR522",
        corse=(_c("VARESE", "MI.CERT", (8, 0), (9, 0), codice_linea="S5"),),
    )
    ist_522_b = _ist(
        data_=D_GIO,
        materiale="ETR522",
        corse=(_c("VARESE", "MI.CERT", (8, 0), (9, 0), codice_linea="S5"),),
    )
    giornate, _ = identifica_giornate_tipo(
        [ist_421, ist_421_b, ist_522, ist_522_b]
    )
    assert len(giornate) == 2
    materiali = {g.materiale_tipo_codice for g in giornate}
    assert materiali == {"ETR421", "ETR522"}


def test_sedi_diverse_separate() -> None:
    """Stesso pattern ma sedi diverse → 2 GT distinte."""
    ist_fio_a = _ist(
        data_=D_LUN,
        localita="FIO",
        corse=(_c("VARESE", "MI.CERT", (8, 0), (9, 0), codice_linea="S5"),),
    )
    ist_fio_b = _ist(
        data_=D_MAR,
        localita="FIO",
        corse=(_c("VARESE", "MI.CERT", (8, 0), (9, 0), codice_linea="S5"),),
    )
    ist_nov_a = _ist(
        data_=D_MER,
        localita="NOV",
        corse=(_c("VARESE", "MI.CERT", (8, 0), (9, 0), codice_linea="S5"),),
    )
    ist_nov_b = _ist(
        data_=D_GIO,
        localita="NOV",
        corse=(_c("VARESE", "MI.CERT", (8, 0), (9, 0), codice_linea="S5"),),
    )
    giornate, _ = identifica_giornate_tipo(
        [ist_fio_a, ist_fio_b, ist_nov_a, ist_nov_b]
    )
    assert len(giornate) == 2
    sedi = {g.localita_codice for g in giornate}
    assert sedi == {"FIO", "NOV"}


# =====================================================================
# Esempio realistico: turno 1110 G6 (riferimento PDF Trenord)
# =====================================================================


def test_realistico_turno_1110_g6_un_solo_phase_6_istanze() -> None:
    """Replica concettuale del turno 1110 / G6 dello screen utente.

    6 catene tutte con stessa fase ``(VARESE, VARESE)``, materiale
    ``2ALe711+1ALe710``, sede FIO, servizio dominante S5: il builder
    deve riconoscere che è UNA sola giornata-tipo con 6 istanze
    (che lo Step 3 successivo raggrupperà in M varianti
    calendariali secondo le sequenze-treni concrete).

    Test deliberatamente semplificato: 6 catene identiche su 6 date
    diverse. La sequenza interna è uniforme — il punto del test è
    verificare che la chiave di fase ``(staz_inizio, staz_fine)`` =
    ``(VARESE, VARESE)`` produce 1 GT, non 6 GT diverse.
    """
    date_g6 = [
        date(2026, 4, 27),  # lun
        date(2026, 5, 1),   # ven (festa lavoratori — variante speciale 1110)
        date(2026, 5, 4),   # lun
        date(2026, 5, 9),   # sabato lavorativo
        date(2026, 5, 11),  # lun
        date(2026, 5, 18),  # lun
    ]
    istanze = [
        _ist(
            data_=d,
            materiale="2ALe711+1ALe710",
            localita="FIO",
            stazione_collegata="MI.CERT",
            corse=(
                _c("VARESE", "MI.CERT", (6, 30), (7, 30), codice_linea="S5",
                   numero_treno="24519"),
                _c("MI.CERT", "VARESE", (12, 0), (13, 0), codice_linea="S5",
                   numero_treno="24576"),
            ),
        )
        for d in date_g6
    ]

    giornate, orfane = identifica_giornate_tipo(istanze)

    assert orfane == []
    assert len(giornate) == 1
    gt = giornate[0]
    assert gt.materiale_tipo_codice == "2ALe711+1ALe710"
    assert gt.localita_codice == "FIO"
    assert gt.staz_inizio == "VARESE"
    assert gt.staz_fine == "VARESE"  # G6 inizia e finisce a Varese (turno PDF)
    assert gt.codice_servizio_dominante == "S5"
    assert len(gt.istanze) == 6
    assert [i.data for i in gt.istanze] == sorted(date_g6)


def test_giornata_tipo_e_frozen() -> None:
    """``GiornataTipo`` è ``frozen=True``: tentativo di mutazione
    solleva ``FrozenInstanceError`` (sanity check sul dataclass).
    """
    import dataclasses

    gt = GiornataTipo(
        materiale_tipo_codice="ETR421",
        localita_codice="FIO",
        staz_inizio="VARESE",
        staz_fine="MI.CERT",
        codice_servizio_dominante="S5",
        istanze=(),
    )
    try:
        gt.staz_inizio = "BRESCIA"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:
        raise AssertionError("GiornataTipo doveva essere frozen")
