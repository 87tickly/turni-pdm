"""Test §11.4 riposo settimanale — Sprint 8.2 MR-PD7b-3."""

from __future__ import annotations

from datetime import date, datetime, time

from colazione.domain.builder_pdc.builder import _GiornataPdcDraft
from colazione.domain.builder_pdc.riposo_settimanale import (
    GIORNATE_CONSECUTIVE_MAX_SENZA_RIPOSO,
    RIPOSO_SETTIMANALE_MIN_MIN,
    _giorni_solari_interi_in_finestra,
    valida_riposo_settimanale,
)
from colazione.domain.calendario import festivita_italiane


def _draft(
    numero: int,
    inizio_h: int,
    fine_h: int,
    riposo_post_min: int = 0,
) -> _GiornataPdcDraft:
    """Helper draft con riposo_post pre-popolato (simula MR-PD7b-2)."""
    return _GiornataPdcDraft(
        numero_giornata=numero,
        variante_calendario="GG",
        blocchi=[],
        stazione_inizio=None,
        stazione_fine=None,
        inizio_prestazione=time(inizio_h, 0),
        fine_prestazione=time(fine_h, 0),
        prestazione_min=8 * 60,
        condotta_min=4 * 60,
        refezione_min=30,
        is_notturno=False,
        is_cap_notturno=False,
        violazioni=[],
        riposo_min_post=riposo_post_min,
    )


# =====================================================================
# _giorni_solari_interi_in_finestra
# =====================================================================


class TestGiorniSolariInteri:
    def test_sabato_14_a_martedi_04_dom_lun_inclusi(self) -> None:
        # Esempio NORMATIVA: sabato 14:00 → martedì 04:00 = 62h.
        # Inclusi: domenica + lunedì interi = 2.
        start = datetime(2026, 3, 7, 14, 0)  # sabato
        end = datetime(2026, 3, 10, 4, 0)  # martedì
        assert _giorni_solari_interi_in_finestra(start, end) == 2

    def test_domenica_10_a_mercoledi_00_lun_mar_inclusi(self) -> None:
        # Esempio NORMATIVA: dom 10:00 → mer 00:00 = 62h. Lun + mar = 2.
        start = datetime(2026, 3, 8, 10, 0)
        end = datetime(2026, 3, 11, 0, 0)
        # Mercoledì 00:00 è START di mercoledì → "ultimo intero precedente"
        # = martedì 23:59:59. Quindi: lun + mar = 2.
        assert _giorni_solari_interi_in_finestra(start, end) == 2

    def test_finestra_50h_solo_1_giorno_intero(self) -> None:
        start = datetime(2026, 3, 7, 14, 0)
        end = start.replace(day=9, hour=16)  # +50h ma rimaniamo entro lunedì
        # Day +50h: 7/3 14:00 + 50h = 9/3 16:00.
        # Primo intero: 8/3 (dom). Ultimo: 8/3 (dom 23:59:59) → 1.
        # Wait: end = 9/3 16:00. Ultimo intero precedente = 8/3 23:59:59.
        # Sì 1 giorno (dom).
        assert _giorni_solari_interi_in_finestra(start, end) == 1

    def test_finestra_24h_zero_giorni_interi(self) -> None:
        # 24h esatte da 14:00 a 14:00: nessun giorno intero contenuto.
        start = datetime(2026, 3, 7, 14, 0)
        end = datetime(2026, 3, 8, 14, 0)
        # Primo intero: 8/3 00:00. Ultimo intero: 7/3 23:59:59.
        # primo > ultimo → 0.
        assert _giorni_solari_interi_in_finestra(start, end) == 0

    def test_end_prima_di_start_zero(self) -> None:
        start = datetime(2026, 3, 8, 14, 0)
        end = datetime(2026, 3, 7, 14, 0)
        assert _giorni_solari_interi_in_finestra(start, end) == 0


# =====================================================================
# valida_riposo_settimanale — algoritmo "≥1 ogni 7gg"
# =====================================================================


class TestValidatoreSettimanale:
    def test_lista_vuota_no_violazioni(self) -> None:
        assert valida_riposo_settimanale([]) == []

    def test_ciclo_5gg_wrap_64h_proxy_2gg_ok(self) -> None:
        # 5 giornate consecutive senza riposo settimanale interno + wrap
        # 64h con 2 giorni interi (proxy).
        drafts = [
            _draft(1, 6, 18, riposo_post_min=12 * 60),  # 12h std ok
            _draft(2, 6, 18, riposo_post_min=12 * 60),
            _draft(3, 6, 18, riposo_post_min=12 * 60),
            _draft(4, 6, 18, riposo_post_min=12 * 60),
            _draft(5, 6, 18, riposo_post_min=64 * 60),  # 64h riposo settimanale
        ]
        viol = valida_riposo_settimanale(drafts, ciclo_giorni=7)
        # Proxy giorni interi: 64*60 // (24*60) = 2 ✅
        # Riposi attesi per ciclo 7gg: ceil(7/7)=1, trovati=1 ✅
        # Contatore mai raggiunge 7
        assert viol == []

    def test_ciclo_5gg_wrap_64h_solo_1_giorno_intero_proxy_violazione(self) -> None:
        drafts = [
            _draft(1, 6, 18, riposo_post_min=12 * 60),
            _draft(2, 6, 18, riposo_post_min=12 * 60),
            _draft(3, 6, 18, riposo_post_min=12 * 60),
            _draft(4, 6, 18, riposo_post_min=12 * 60),
            # 47h: ≥ 62h? No, 47 < 62 → non riposo settimanale → contatore continua
            # Per testare "giorni solari interi insufficienti" serve gap ≥62h ma <48h interi
            # Es: 62h e 1 minuto è il borderline. Uso 63h.
            _draft(5, 6, 18, riposo_post_min=63 * 60),  # 63h riposo, proxy = 63//24 = 2 → ok
        ]
        viol = valida_riposo_settimanale(drafts, ciclo_giorni=7)
        # Proxy: 63h//24=2 → 2 giorni ≥ 2 richiesti → ok
        assert viol == []

    def test_ciclo_5gg_wrap_50h_no_settimanale_violazione(self) -> None:
        drafts = [
            _draft(1, 6, 18, riposo_post_min=12 * 60),
            _draft(2, 6, 18, riposo_post_min=12 * 60),
            _draft(3, 6, 18, riposo_post_min=12 * 60),
            _draft(4, 6, 18, riposo_post_min=12 * 60),
            _draft(5, 6, 18, riposo_post_min=50 * 60),  # 50h < 62h → non settimanale
        ]
        viol = valida_riposo_settimanale(drafts, ciclo_giorni=7)
        # Riposi trovati: 0 < 1 atteso → violazione "numero_insufficiente"
        assert any("numero_insufficiente" in v for v in viol)

    def test_ciclo_14gg_due_riposi_settimanali_ok(self) -> None:
        # 14 giornate, 2 riposi settimanali (uno a metà, uno al wrap).
        drafts = (
            [_draft(i, 6, 18, riposo_post_min=12 * 60) for i in range(1, 7)]
            + [_draft(7, 6, 18, riposo_post_min=64 * 60)]  # primo riposo
            + [_draft(i, 6, 18, riposo_post_min=12 * 60) for i in range(8, 14)]
            + [_draft(14, 6, 18, riposo_post_min=64 * 60)]  # secondo riposo wrap
        )
        viol = valida_riposo_settimanale(drafts, ciclo_giorni=14)
        # 2 riposi trovati ≥ ceil(14/7) = 2 ✅
        # Contatore: G1..G6 = 6, G7 reset, G8..G13 = 6, G14 reset
        # → mai raggiunge 7 → no violazione "no_in_7gg"
        assert viol == []

    def test_ciclo_14gg_solo_1_riposo_violazione_no_in_7gg(self) -> None:
        # 14 giornate, 1 solo riposo settimanale → algoritmo "≥1 ogni 7gg"
        # genera "no_in_7gg" sul secondo blocco di 7 giornate.
        drafts = (
            [_draft(i, 6, 18, riposo_post_min=12 * 60) for i in range(1, 7)]
            + [_draft(7, 6, 18, riposo_post_min=64 * 60)]
            + [_draft(i, 6, 18, riposo_post_min=12 * 60) for i in range(8, 15)]
        )
        viol = valida_riposo_settimanale(drafts, ciclo_giorni=14)
        # G14 ha riposo_post=12h < 62h → no riposo settimanale.
        # Contatore G8..G14 = 7 → violazione "no_in_7gg".
        # Riposi trovati: 1 < ceil(14/7)=2 → violazione "numero_insufficiente".
        assert any("no_in_7gg" in v for v in viol)
        assert any("numero_insufficiente" in v for v in viol)

    def test_ciclo_5gg_con_date_concrete_2_giorni_interi_ok(self) -> None:
        """Test con date concrete: enumera_date_giornata + conteggio giorni
        solari reali invece di proxy."""
        drafts = [
            _draft(1, 6, 14, riposo_post_min=12 * 60),  # G1 fine 14:00
            _draft(2, 6, 14, riposo_post_min=12 * 60),
            _draft(3, 6, 14, riposo_post_min=12 * 60),
            _draft(4, 6, 14, riposo_post_min=12 * 60),
            _draft(5, 6, 14, riposo_post_min=64 * 60),  # G5 fine 14:00 → riposo 64h
        ]
        # Programma marzo 2026, ciclo 7gg ancorato lunedì 2/3.
        # G5 = 1*7+5 = giornata 5 di ciclo 7 → cade venerdì 6/3.
        # Riposo G5→G1: parte ven 14:00, dura 64h → arriva lun 06:00 (2 giorni interi).
        festivita = frozenset(d for d, _ in festivita_italiane(2026))
        viol = valida_riposo_settimanale(
            drafts,
            ciclo_giorni=7,
            data_inizio_programma=date(2026, 3, 2),  # lun
            data_fine_programma=date(2026, 3, 31),
            festivita=festivita,
        )
        assert viol == []

    def test_ciclo_5gg_con_date_concrete_24h_no_giorno_intero(self) -> None:
        """Date concrete: gap 65h dal venerdì 14:00 al lunedì 07:00 = 65h
        ma include solo 2 giorni interi (sab+dom). Proxy darebbe 65/24=2.7=2,
        date concrete dà 2. Ok."""
        drafts = [
            _draft(1, 7, 14, riposo_post_min=12 * 60),
            _draft(2, 7, 14, riposo_post_min=12 * 60),
            _draft(3, 7, 14, riposo_post_min=12 * 60),
            _draft(4, 7, 14, riposo_post_min=12 * 60),
            _draft(5, 7, 14, riposo_post_min=65 * 60),  # 65h
        ]
        festivita = frozenset(d for d, _ in festivita_italiane(2026))
        viol = valida_riposo_settimanale(
            drafts,
            ciclo_giorni=7,
            data_inizio_programma=date(2026, 3, 2),
            data_fine_programma=date(2026, 3, 31),
            festivita=festivita,
        )
        # G5 ven 6/3 14:00 + 65h = lun 9/3 07:00. Sab + dom = 2 giorni interi.
        assert viol == []


def test_riposo_min_costante_3720() -> None:
    """Sanity: 62h = 3720 min."""
    assert RIPOSO_SETTIMANALE_MIN_MIN == 3720


def test_giornate_consecutive_max_7() -> None:
    assert GIORNATE_CONSECUTIVE_MAX_SENZA_RIPOSO == 7


# =====================================================================
# Sprint 8.3 S8 SEVERO post-Sprint: tracciamento strisce continue
# =====================================================================


class TestStrisceContinue:
    """Sprint 8.3 S8: il refactor traccia STRISCE CONTINUE invece di
    multipli di 7. Una striscia di 21gg consecutivi senza riposo emette
    1 sola violazione con lunghezza completa, non 3 generiche."""

    def test_ciclo_21gg_zero_riposi_una_violazione_striscia_21(self) -> None:
        """21 giornate consecutive senza riposo settimanale → 1 sola
        violazione 'striscia_consecutiva_da_G1_a_G21:21_giornate' (più
        informativa del vecchio output che emetteva 3 violazioni
        generiche 'contatore_raggiunto_7' a G7, G14, G21)."""
        drafts = [
            _draft(i, 6, 18, riposo_post_min=12 * 60) for i in range(1, 22)
        ]
        viol = valida_riposo_settimanale(drafts, ciclo_giorni=21)
        # Conta violazioni "no_in_7gg" (= strisce). Solo 1, non 3.
        viol_strisce = [v for v in viol if "no_in_7gg" in v]
        assert len(viol_strisce) == 1, (
            f"atteso 1 violazione striscia, ottenute {len(viol_strisce)}: "
            f"{viol_strisce}"
        )
        # Messaggio deve indicare lunghezza 21 + range G1-G21.
        assert "G1" in viol_strisce[0]
        assert "G21" in viol_strisce[0]
        assert "21_giornate" in viol_strisce[0]
        # Atteso anche numero_insufficiente: 0 riposi vs ceil(21/7)=3.
        assert any("numero_insufficiente" in v for v in viol)

    def test_ciclo_14gg_zero_riposi_una_violazione_striscia_14(self) -> None:
        """14 giornate consecutive senza riposo → 1 violazione striscia
        14gg (vecchio algoritmo: 2 violazioni separate G7+G14)."""
        drafts = [
            _draft(i, 6, 18, riposo_post_min=12 * 60) for i in range(1, 15)
        ]
        viol = valida_riposo_settimanale(drafts, ciclo_giorni=14)
        viol_strisce = [v for v in viol if "no_in_7gg" in v]
        assert len(viol_strisce) == 1
        assert "14_giornate" in viol_strisce[0]
        assert "G1" in viol_strisce[0]
        assert "G14" in viol_strisce[0]

    def test_ciclo_8gg_zero_riposi_una_violazione_striscia_8(self) -> None:
        """8 giornate consecutive (1 oltre soglia) → 1 violazione 8gg."""
        drafts = [
            _draft(i, 6, 18, riposo_post_min=12 * 60) for i in range(1, 9)
        ]
        viol = valida_riposo_settimanale(drafts, ciclo_giorni=8)
        viol_strisce = [v for v in viol if "no_in_7gg" in v]
        assert len(viol_strisce) == 1
        assert "8_giornate" in viol_strisce[0]

    def test_due_strisce_separate_da_riposo_due_violazioni(self) -> None:
        """G1-G7 senza riposo, G8 riposo, G9-G15 senza riposo →
        2 violazioni striscia distinte (G1-G7 e G9-G15)."""
        drafts = (
            [_draft(i, 6, 18, riposo_post_min=12 * 60) for i in range(1, 8)]  # G1-7
            + [_draft(8, 6, 18, riposo_post_min=64 * 60)]  # G8 riposo
            + [_draft(i, 6, 18, riposo_post_min=12 * 60) for i in range(9, 16)]  # G9-15
        )
        viol = valida_riposo_settimanale(drafts, ciclo_giorni=15)
        viol_strisce = [v for v in viol if "no_in_7gg" in v]
        assert len(viol_strisce) == 2
        # Striscia 1: G1-G7 (7 giornate). G8 ha riposo → striscia chiusa
        # all'idx=7 cioè drafts[6].numero_giornata = G7.
        assert any(
            "G1" in v and "G7" in v and "7_giornate" in v
            for v in viol_strisce
        )
        # Striscia 2: G9-G15 (7 giornate).
        assert any(
            "G9" in v and "G15" in v and "7_giornate" in v
            for v in viol_strisce
        )

    def test_striscia_6gg_sotto_soglia_no_violazione(self) -> None:
        """6 giornate consecutive senza riposo: SOTTO soglia 7gg → no
        violazione striscia (solo numero_insufficiente per ciclo 6gg)."""
        drafts = [
            _draft(i, 6, 18, riposo_post_min=12 * 60) for i in range(1, 7)
        ]
        viol = valida_riposo_settimanale(drafts, ciclo_giorni=6)
        viol_strisce = [v for v in viol if "no_in_7gg" in v]
        assert viol_strisce == []
