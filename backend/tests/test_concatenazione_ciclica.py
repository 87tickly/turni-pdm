"""Test puri MR-1110 sotto-MR 3 — ``concatena_in_turni``.

Tutti i test sono **senza DB**: usano direttamente le dataclass
``GiornataTipo`` di ``giornata_tipo.py``, costruite a mano (niente
catene/corse — il modulo concatenazione opera solo su
giornate-tipo già identificate).

Coprono:

- Casi base: lista vuota, singolo nodo con/senza auto-loop, due nodi
  che si concatenano ciclicamente.
- Cicli hamiltoniani: triangolo (N=3), settimanale (N=7),
  Caravaggio-style (N=17 benchmark Trenord).
- D2 ciclo rotto: gruppo disconnesso → multi-turno; SCC con cicli
  separati.
- Caso degenere N=1: auto-loop = turno valido; senza auto-loop = orfana.
- Multi-gruppo: (materiale, sede) diversi → turni distinti.
- Determinismo: input mescolato → output stabile.
- Orfane: nodi non concatenabili finiscono nelle orfane.
"""

from __future__ import annotations

from colazione.domain.builder_giro.concatenazione_ciclica import (
    Turno,
    concatena_in_turni,
)
from colazione.domain.builder_giro.giornata_tipo import (
    CatenaIstanza,
    GiornataTipo,
)

# =====================================================================
# Fixture
# =====================================================================


def _gt(
    *,
    staz_inizio: str,
    staz_fine: str,
    materiale: str = "ETR421",
    sede: str = "FIO",
    servizio: str | None = "S5",
    n_istanze: int = 2,
) -> GiornataTipo:
    """Costruisce GiornataTipo minimale per i test.

    Usa istanze=tuple() perché il modulo concatenazione opera solo
    su staz_inizio/fine + chiave gruppo, non sulle istanze interne.
    Per realismo del test però produciamo n_istanze stub.
    """
    # Niente CatenaIstanza reali — il test del modulo non ne ha
    # bisogno. La tuple delle istanze è opaca al modulo.
    istanze: tuple[CatenaIstanza, ...] = tuple()  # noqa: F841
    # Ma GiornataTipo è frozen: deve essere ben costruito.
    return GiornataTipo(
        materiale_tipo_codice=materiale,
        localita_codice=sede,
        staz_inizio=staz_inizio,
        staz_fine=staz_fine,
        codice_servizio_dominante=servizio,
        istanze=istanze,
    )


# =====================================================================
# Casi base
# =====================================================================


def test_lista_vuota() -> None:
    turni, orfane = concatena_in_turni([])
    assert turni == []
    assert orfane == []


def test_singolo_nodo_con_auto_loop_turno_n1() -> None:
    """N=1, staz_fine == staz_inizio (auto-loop) → 1 Turno valido.

    Caso reale: turno 1104 stagionale MDVE/MDVC con 1 sola
    giornata-tipo che si chiude su stessa stazione.
    """
    gt = _gt(staz_inizio="VARESE", staz_fine="VARESE")
    turni, orfane = concatena_in_turni([gt])

    assert orfane == []
    assert len(turni) == 1
    assert turni[0].n_giornate == 1
    assert turni[0].giornate_tipo == (gt,)


def test_singolo_nodo_senza_auto_loop_finisce_in_orfane() -> None:
    """N=1, staz_fine != staz_inizio → orfana (impossibile chiudere)."""
    gt = _gt(staz_inizio="VARESE", staz_fine="MI.CERT")
    turni, orfane = concatena_in_turni([gt])

    assert turni == []
    assert orfane == [gt]


def test_due_nodi_che_si_concatenano_ciclicamente() -> None:
    """G1: A→B, G2: B→A → ciclo (G1, G2) di lunghezza 2."""
    g1 = _gt(staz_inizio="VARESE", staz_fine="MI.CERT")
    g2 = _gt(staz_inizio="MI.CERT", staz_fine="VARESE")
    turni, orfane = concatena_in_turni([g1, g2])

    assert orfane == []
    assert len(turni) == 1
    assert turni[0].n_giornate == 2
    # Determinismo: parte dal lessicograficamente minimo (MI.CERT).
    assert turni[0].giornate_tipo[0].staz_inizio == "MI.CERT"
    assert turni[0].giornate_tipo[1].staz_inizio == "VARESE"


# =====================================================================
# Cicli hamiltoniani
# =====================================================================


def test_triangolo_ciclo_n3() -> None:
    """A→B, B→C, C→A → ciclo (A, B, C)."""
    g1 = _gt(staz_inizio="A", staz_fine="B")
    g2 = _gt(staz_inizio="B", staz_fine="C")
    g3 = _gt(staz_inizio="C", staz_fine="A")
    turni, orfane = concatena_in_turni([g1, g2, g3])

    assert orfane == []
    assert len(turni) == 1
    assert turni[0].n_giornate == 3
    seq = [g.staz_inizio for g in turni[0].giornate_tipo]
    assert seq == ["A", "B", "C"]


def test_settimanale_ciclo_n7_chiuso() -> None:
    """7 giornate-tipo che concatenano linearmente A→B→C→D→E→F→G→A.

    Modello concettuale di un turno settimanale Trenord (es. ATR803
    Coleoni 1115 con 7 giornate concatenate).
    """
    nodi = [
        _gt(staz_inizio="A", staz_fine="B"),
        _gt(staz_inizio="B", staz_fine="C"),
        _gt(staz_inizio="C", staz_fine="D"),
        _gt(staz_inizio="D", staz_fine="E"),
        _gt(staz_inizio="E", staz_fine="F"),
        _gt(staz_inizio="F", staz_fine="G"),
        _gt(staz_inizio="G", staz_fine="A"),
    ]
    turni, orfane = concatena_in_turni(nodi)

    assert orfane == []
    assert len(turni) == 1
    assert turni[0].n_giornate == 7
    seq = [g.staz_inizio for g in turni[0].giornate_tipo]
    assert seq == ["A", "B", "C", "D", "E", "F", "G"]


def test_caravaggio_style_n17_lungo() -> None:
    """Stress test: 17 giornate-tipo concatenate (benchmark turno 1125
    Caravaggio Trenord).
    """
    # Ciclo lineare A0→A1→A2→…→A16→A0
    nodi = [
        _gt(staz_inizio=f"A{i}", staz_fine=f"A{(i + 1) % 17}")
        for i in range(17)
    ]
    turni, orfane = concatena_in_turni(nodi)

    assert orfane == []
    assert len(turni) == 1
    assert turni[0].n_giornate == 17


def test_chiusura_ciclica_obbligatoria() -> None:
    """A→B→C ma niente arco C→A: ciclo NON esiste, gruppo non si chiude.

    Tutte e 3 le giornate finiscono in orfane (D2: SCC senza ciclo
    hamiltoniano).
    """
    g1 = _gt(staz_inizio="A", staz_fine="B")
    g2 = _gt(staz_inizio="B", staz_fine="C")
    g3 = _gt(staz_inizio="C", staz_fine="D")  # va a D, non A
    turni, orfane = concatena_in_turni([g1, g2, g3])

    assert turni == []
    # Tutte 3 vanno orfane (DAG senza ciclo, 3 SCC singleton senza auto-loop)
    assert len(orfane) == 3


# =====================================================================
# D2 — ciclo rotto: multi-turno via SCC
# =====================================================================


def test_due_cicli_separati_nello_stesso_gruppo_due_turni() -> None:
    """Gruppo (materiale, sede) con 2 cicli hamiltoniani disgiunti
    → 2 Turni separati (D2 chiusa: multi-turno via SCC).

    Ciclo 1: A↔B (2 giornate)
    Ciclo 2: C↔D (2 giornate)
    Stesso (materiale, sede) → stesso gruppo → bisogna decomporre via SCC.
    """
    g_ab = _gt(staz_inizio="A", staz_fine="B")
    g_ba = _gt(staz_inizio="B", staz_fine="A")
    g_cd = _gt(staz_inizio="C", staz_fine="D")
    g_dc = _gt(staz_inizio="D", staz_fine="C")

    turni, orfane = concatena_in_turni([g_ab, g_ba, g_cd, g_dc])

    assert orfane == []
    assert len(turni) == 2
    # Determinismo: ordinati per (materiale, sede, n desc, staz_inizio)
    # Tutti hanno stesso (mat, sede), stesso N=2 → ordina per
    # primo staz_inizio.
    primi_inizi = [t.giornate_tipo[0].staz_inizio for t in turni]
    assert primi_inizi == ["A", "C"]


def test_un_ciclo_e_un_orfano() -> None:
    """Ciclo (A↔B) + nodo isolato (X→Y, niente connessione) →
    1 Turno con il ciclo + 1 orfana.
    """
    g_ab = _gt(staz_inizio="A", staz_fine="B")
    g_ba = _gt(staz_inizio="B", staz_fine="A")
    g_xy = _gt(staz_inizio="X", staz_fine="Y")

    turni, orfane = concatena_in_turni([g_ab, g_ba, g_xy])

    assert len(turni) == 1
    assert turni[0].n_giornate == 2
    assert orfane == [g_xy]


def test_auto_loop_singleton_e_ciclo_normale_due_turni() -> None:
    """1 nodo con auto-loop (forma turno N=1) + ciclo A↔B → 2 turni."""
    g_self = _gt(staz_inizio="HUB", staz_fine="HUB")
    g_ab = _gt(staz_inizio="A", staz_fine="B")
    g_ba = _gt(staz_inizio="B", staz_fine="A")

    turni, orfane = concatena_in_turni([g_self, g_ab, g_ba])

    assert orfane == []
    assert len(turni) == 2
    # Ordinamento: N=2 prima di N=1 (n_giornate desc).
    assert turni[0].n_giornate == 2
    assert turni[1].n_giornate == 1


# =====================================================================
# Multi-gruppo
# =====================================================================


def test_materiali_diversi_turni_distinti() -> None:
    """Stesso pattern A↔B ma materiali diversi → 2 turni distinti."""
    g_421_ab = _gt(staz_inizio="A", staz_fine="B", materiale="ETR421")
    g_421_ba = _gt(staz_inizio="B", staz_fine="A", materiale="ETR421")
    g_522_ab = _gt(staz_inizio="A", staz_fine="B", materiale="ETR522")
    g_522_ba = _gt(staz_inizio="B", staz_fine="A", materiale="ETR522")

    turni, orfane = concatena_in_turni(
        [g_421_ab, g_421_ba, g_522_ab, g_522_ba]
    )

    assert orfane == []
    assert len(turni) == 2
    materiali = {t.materiale_tipo_codice for t in turni}
    assert materiali == {"ETR421", "ETR522"}


def test_sedi_diverse_turni_distinti() -> None:
    """Stesso pattern A↔B, stesso materiale, sedi diverse → 2 turni."""
    g_fio_ab = _gt(staz_inizio="A", staz_fine="B", sede="FIO")
    g_fio_ba = _gt(staz_inizio="B", staz_fine="A", sede="FIO")
    g_nov_ab = _gt(staz_inizio="A", staz_fine="B", sede="NOV")
    g_nov_ba = _gt(staz_inizio="B", staz_fine="A", sede="NOV")

    turni, orfane = concatena_in_turni(
        [g_fio_ab, g_fio_ba, g_nov_ab, g_nov_ba]
    )

    assert orfane == []
    assert len(turni) == 2
    sedi = {t.localita_codice for t in turni}
    assert sedi == {"FIO", "NOV"}


# =====================================================================
# Determinismo
# =====================================================================


def test_input_mescolato_output_stabile() -> None:
    """Input shuffled → output sempre nello stesso ordine."""
    nodi_a = [
        _gt(staz_inizio="A", staz_fine="B"),
        _gt(staz_inizio="B", staz_fine="C"),
        _gt(staz_inizio="C", staz_fine="A"),
    ]
    nodi_b = list(reversed(nodi_a))

    turni_a, _ = concatena_in_turni(nodi_a)
    turni_b, _ = concatena_in_turni(nodi_b)

    seq_a = [
        (g.staz_inizio, g.staz_fine) for g in turni_a[0].giornate_tipo
    ]
    seq_b = [
        (g.staz_inizio, g.staz_fine) for g in turni_b[0].giornate_tipo
    ]
    assert seq_a == seq_b


def test_turni_ordinati_per_n_giornate_desc() -> None:
    """Turni dello stesso (materiale, sede) ordinati per n_giornate
    desc.
    """
    # Ciclo lungo (4) + ciclo corto (2) nello stesso gruppo
    nodi = [
        _gt(staz_inizio="A", staz_fine="B"),
        _gt(staz_inizio="B", staz_fine="C"),
        _gt(staz_inizio="C", staz_fine="D"),
        _gt(staz_inizio="D", staz_fine="A"),
        # Ciclo separato X↔Y
        _gt(staz_inizio="X", staz_fine="Y"),
        _gt(staz_inizio="Y", staz_fine="X"),
    ]
    turni, _ = concatena_in_turni(nodi)
    assert len(turni) == 2
    assert turni[0].n_giornate == 4
    assert turni[1].n_giornate == 2


# =====================================================================
# Acceptance turno 1110 (modello concettuale)
# =====================================================================


def test_turno_1110_concettuale_ciclo_minimale() -> None:
    """Modello concettuale del turno 1110 (TSR 3pz, FIO, 2ALe711+1ALe710).

    Il turno PDF ha N giornate concatenate. Per questo test usiamo
    una versione minimale a 2 giornate-tipo:

    - G_AB: VARESE → MI.CERT (mattina)
    - G_BA: MI.CERT → VARESE (pomeriggio)

    Ciclo: G_AB → G_BA → G_AB → … → 1 Turno.
    """
    g_ab = _gt(
        staz_inizio="VARESE",
        staz_fine="MI.CERT",
        materiale="2ALe711+1ALe710",
        sede="FIO",
        servizio="S5",
    )
    g_ba = _gt(
        staz_inizio="MI.CERT",
        staz_fine="VARESE",
        materiale="2ALe711+1ALe710",
        sede="FIO",
        servizio="S5",
    )
    turni, orfane = concatena_in_turni([g_ab, g_ba])

    assert orfane == []
    assert len(turni) == 1
    t = turni[0]
    assert t.materiale_tipo_codice == "2ALe711+1ALe710"
    assert t.localita_codice == "FIO"
    assert t.n_giornate == 2
    # Verifica chiusura ciclica esplicita
    n = t.n_giornate
    for k in range(n):
        gt_k = t.giornate_tipo[k]
        gt_next = t.giornate_tipo[(k + 1) % n]
        assert gt_k.staz_fine == gt_next.staz_inizio


def test_turno_e_n_giornate_property() -> None:
    """``Turno.n_giornate`` == ``len(giornate_tipo)``."""
    g1 = _gt(staz_inizio="HUB", staz_fine="HUB")
    t = Turno(
        materiale_tipo_codice="ETR421",
        localita_codice="FIO",
        giornate_tipo=(g1,),
    )
    assert t.n_giornate == 1
