"""Test puri di ``calcola_etichetta_giro`` (Sprint 7.7 MR 3).

Funzione DB-agnostic: prende date di applicazione + festività e
ritorna ``(etichetta_tipo, etichetta_dettaglio)`` per il giro
materiale. Nessun mock/DB qui — solo input/output puri.

Decisioni in copertura:

- 6 categorie monotipo (feriale/sabato/domenica/festivo/data_specifica/
  personalizzata) — utente 2026-05-02, opzione (b) "enum collassato".
- Festivo ha precedenza su sabato/domenica calendariali (decisione
  utente "festivo che cade di sabato è festivo").
- Vuoto/personalizzata fallback ordinato calendariale.
"""

from __future__ import annotations

from datetime import date

from colazione.domain.builder_giro.etichetta import (
    ETICHETTE_AMMESSE,
    calcola_etichetta_giro,
    calcola_etichetta_variante,
)
from colazione.domain.calendario import festivita_italiane


def _festivita_2026() -> frozenset[date]:
    """Festività nazionali italiane 2026 — 12 date (10 fisse + 2 mobili)."""
    return frozenset(d for d, _ in festivita_italiane(2026))


def test_etichette_ammesse_sono_le_sei_concordate() -> None:
    """L'enum è collassato: 6 valori esatti."""
    assert ETICHETTE_AMMESSE == frozenset(
        {"feriale", "sabato", "domenica", "festivo", "data_specifica", "personalizzata"}
    )


def test_giro_vuoto_ritorna_personalizzata_senza_dettaglio() -> None:
    """Caso degenere: nessuna data → personalizzata, no dettaglio."""
    tipo, dettaglio = calcola_etichetta_giro([], frozenset())
    assert tipo == "personalizzata"
    assert dettaglio is None


def test_giornate_senza_date_ritorna_personalizzata() -> None:
    """Più giornate ma tutte con `dates_apply` vuoto."""
    tipo, dettaglio = calcola_etichetta_giro([(), (), ()], frozenset())
    assert tipo == "personalizzata"
    assert dettaglio is None


def test_una_sola_data_unica_ritorna_data_specifica_DDMMYYYY() -> None:
    """Singola data → ``data_specifica`` con dettaglio ``DD/MM/YYYY``."""
    tipo, dettaglio = calcola_etichetta_giro([[date(2026, 5, 4)]], frozenset())
    assert tipo == "data_specifica"
    assert dettaglio == "04/05/2026"


def test_singola_data_ripetuta_su_piu_giornate_resta_data_specifica() -> None:
    """Più giornate ma tutte la stessa data unica → data_specifica."""
    tipo, dettaglio = calcola_etichetta_giro(
        [[date(2026, 5, 4)], [date(2026, 5, 4)]],
        frozenset(),
    )
    assert tipo == "data_specifica"
    assert dettaglio == "04/05/2026"


def test_tutte_feriali_ritorna_feriale_senza_dettaglio() -> None:
    """5 lunedì-venerdì non festivi consecutivi → feriale."""
    # 4-8 maggio 2026: lun-ven, nessuno festivo
    feriali = [date(2026, 5, 4), date(2026, 5, 5), date(2026, 5, 6), date(2026, 5, 7), date(2026, 5, 8)]
    tipo, dettaglio = calcola_etichetta_giro([feriali], _festivita_2026())
    assert tipo == "feriale"
    assert dettaglio is None


def test_tutti_sabato_ritorna_sabato() -> None:
    """3 sabati consecutivi non festivi → sabato."""
    # 9, 16, 23 maggio 2026: sabati, nessuno festivo (1 maggio è ven)
    sabati = [date(2026, 5, 9), date(2026, 5, 16), date(2026, 5, 23)]
    tipo, dettaglio = calcola_etichetta_giro([sabati], _festivita_2026())
    assert tipo == "sabato"
    assert dettaglio is None


def test_tutte_domeniche_ritorna_domenica() -> None:
    """3 domeniche consecutive non festive → domenica."""
    # 10, 17, 24 maggio 2026: domeniche, nessuna festiva
    domeniche = [date(2026, 5, 10), date(2026, 5, 17), date(2026, 5, 24)]
    tipo, dettaglio = calcola_etichetta_giro([domeniche], _festivita_2026())
    assert tipo == "domenica"
    assert dettaglio is None


def test_tutti_festivi_ritorna_festivo() -> None:
    """1 maggio (lavoro) + 2 giugno (repubblica) + 15 ago (ferragosto)."""
    festivi = [date(2026, 5, 1), date(2026, 6, 2), date(2026, 8, 15)]
    tipo, dettaglio = calcola_etichetta_giro([festivi], _festivita_2026())
    assert tipo == "festivo"
    assert dettaglio is None


def test_festivo_che_cade_di_sabato_ha_precedenza_su_sabato() -> None:
    """Decisione utente 2026-05-02: festivo > sabato.

    25 aprile 2026 è sabato + Festa della Liberazione → festivo.
    """
    tipo, _ = calcola_etichetta_giro([[date(2026, 4, 25)]], _festivita_2026())
    # Singola data → data_specifica vince comunque sull'enum monotipo,
    # ma il punto qui è verificare che il giorno è classificato come
    # festivo: lo testiamo con due date entrambe festive su sabato.
    assert tipo == "data_specifica"

    # Caso vero: 2 sabati di festività → festivo (no sabato).
    # 25 aprile 2026 = sab + Liberazione · 26 dicembre 2026 = sab + Santo Stefano.
    festivi_di_sabato = [date(2026, 4, 25), date(2026, 12, 26)]
    tipo2, dettaglio2 = calcola_etichetta_giro(
        [festivi_di_sabato], _festivita_2026()
    )
    assert tipo2 == "festivo"
    assert dettaglio2 is None


def test_mix_sabato_e_festivo_ritorna_personalizzata_con_breakdown() -> None:
    """Mix di tipi → personalizzata. Dettaglio in ordine calendariale."""
    # 9 maggio 2026 = sabato non festivo · 1 giugno 2026 = lun feriale...
    # uso 9 maggio (sab) + 25 dicembre (festivo).
    misto = [date(2026, 5, 9), date(2026, 12, 25)]
    tipo, dettaglio = calcola_etichetta_giro([misto], _festivita_2026())
    assert tipo == "personalizzata"
    assert dettaglio == "sabato+festivo"


def test_mix_completo_quattro_tipi_dettaglio_ordinato() -> None:
    """Feriale + sabato + domenica + festivo → personalizzata, ordine fisso."""
    # 4/5 maggio (lun feriale), 9/5 (sab), 10/5 (dom), 1/5 (festivo Lavoro).
    misto_4 = [
        date(2026, 5, 4),  # feriale
        date(2026, 5, 9),  # sabato
        date(2026, 5, 10),  # domenica
        date(2026, 5, 1),  # festivo
    ]
    tipo, dettaglio = calcola_etichetta_giro([misto_4], _festivita_2026())
    assert tipo == "personalizzata"
    assert dettaglio == "feriale+sabato+domenica+festivo"


def test_aggrega_dates_da_piu_giornate() -> None:
    """Date di più giornate concatenate → unica classificazione del giro."""
    # G1 in 2 lunedì feriali · G2 in 2 martedì feriali → tutto feriale.
    g1 = [date(2026, 5, 4), date(2026, 5, 11)]
    g2 = [date(2026, 5, 5), date(2026, 5, 12)]
    tipo, _ = calcola_etichetta_giro([g1, g2], _festivita_2026())
    assert tipo == "feriale"


def test_festivita_locale_aggiunta_set_diventa_festiva() -> None:
    """Sant'Ambrogio (7/12 a Milano) classifica come festivo se in set."""
    # 7 dicembre 2026 = lunedì → di base feriale.
    nazionali = _festivita_2026()
    tipo_solo_nazionali, _ = calcola_etichetta_giro(
        [[date(2026, 12, 7)]], nazionali
    )
    assert tipo_solo_nazionali == "data_specifica"  # singola data sempre

    # Con Sant'Ambrogio aggiunto: tester con 2 date entrambe locali festive.
    sant_ambrogio = nazionali | frozenset({date(2026, 12, 7), date(2027, 12, 7)})
    tipo2, _ = calcola_etichetta_giro(
        [[date(2026, 12, 7), date(2027, 12, 7)]], sant_ambrogio
    )
    assert tipo2 == "festivo"


# =====================================================================
# Sprint 7.7 MR 6: calcola_etichetta_variante
# =====================================================================


class TestCalcolaEtichettaVariante:
    """Etichetta UI categorica per una variante calendariale.

    Output:
    - "Solo DD/MM/YYYY" per data unica
    - "Lavorativo · N date" / "Prefestivo · N date" / "Festivo · N date"
      per varianti monotipo
    - "Misto: A+B[+C] · N date" per varianti che mescolano categorie
    - "(nessuna data)" per iterable vuoto
    """

    def test_iterable_vuoto_ritorna_placeholder(self) -> None:
        assert calcola_etichetta_variante([], frozenset()) == "(nessuna data)"

    def test_data_unica_formato_italiano(self) -> None:
        assert (
            calcola_etichetta_variante([date(2026, 5, 4)], frozenset())
            == "Solo 04/05/2026"
        )

    def test_data_unica_duplicati_collassano(self) -> None:
        # Stessa data ripetuta 3× → comunque "Solo …"
        d = date(2026, 5, 4)
        assert calcola_etichetta_variante([d, d, d], frozenset()) == "Solo 04/05/2026"

    def test_tutte_lavorativi(self) -> None:
        # 4-8 maggio 2026: lun, mar, mer, gio, ven (1/5 fuori range)
        feriali = [date(2026, 5, 4), date(2026, 5, 5), date(2026, 5, 6), date(2026, 5, 7)]
        assert (
            calcola_etichetta_variante(feriali, _festivita_2026())
            == "Lavorativo · 4 date"
        )

    def test_tutti_prefestivi_sabati(self) -> None:
        # 3 sabati maggio 2026: 2, 9, 16 → tutti prefestivi (vigilie domenica)
        sabati = [date(2026, 5, 2), date(2026, 5, 9), date(2026, 5, 16)]
        assert (
            calcola_etichetta_variante(sabati, _festivita_2026())
            == "Prefestivo · 3 date"
        )

    def test_tutti_festivi_domeniche(self) -> None:
        # Domeniche di maggio 2026: 3, 10, 17 → tutte festivo
        domeniche = [date(2026, 5, 3), date(2026, 5, 10), date(2026, 5, 17)]
        assert (
            calcola_etichetta_variante(domeniche, _festivita_2026())
            == "Festivo · 3 date"
        )

    def test_misto_lavorativo_prefestivo(self) -> None:
        # Mix lavorativi (lun-ven) + sabati prefestivi
        misto = [
            date(2026, 5, 4),  # lunedì → lavorativo
            date(2026, 5, 5),  # martedì → lavorativo
            date(2026, 5, 9),  # sabato → prefestivo (vigilia domenica)
        ]
        out = calcola_etichetta_variante(misto, _festivita_2026())
        assert out == "Misto: Lavorativo+Prefestivo · 3 date"

    def test_misto_lavorativo_festivo_ordine_label(self) -> None:
        # Mix lavorativi + domeniche → label ordinata calendariale
        misto = [
            date(2026, 5, 4),  # lunedì
            date(2026, 5, 3),  # domenica
        ]
        out = calcola_etichetta_variante(misto, _festivita_2026())
        assert out == "Misto: Lavorativo+Festivo · 2 date"

    def test_misto_3_categorie_complete(self) -> None:
        # Mix lavorativo + prefestivo + festivo
        misto = [
            date(2026, 5, 4),  # lun → lavorativo
            date(2026, 5, 2),  # sab → prefestivo
            date(2026, 5, 3),  # dom → festivo
        ]
        out = calcola_etichetta_variante(misto, _festivita_2026())
        assert out == "Misto: Lavorativo+Prefestivo+Festivo · 3 date"

    def test_festivita_nazionale_di_sabato_resta_festivo(self) -> None:
        # Sabato 25/4/2026 = Liberazione → festivo (precedenza su prefestivo)
        # Senza altra data, "Solo …"; con un'altra data lavorativa: misto
        out = calcola_etichetta_variante(
            [date(2026, 4, 25), date(2026, 5, 4)], _festivita_2026()
        )
        assert out == "Misto: Lavorativo+Festivo · 2 date"

    def test_venerdi_24_aprile_2026_e_prefestivo(self) -> None:
        # Vigilia di 25/4 (Liberazione, sabato festivo) → 24/4 prefestivo
        out = calcola_etichetta_variante(
            [date(2026, 4, 24), date(2026, 5, 8)],  # ven 24/4 + ven 8/5
            _festivita_2026(),
        )
        # 8/5/2026 = venerdì lavorativo, 24/4 = prefestivo (vigilia 25/4)
        assert out == "Misto: Lavorativo+Prefestivo · 2 date"

    def test_due_date_uniche_uguali_collassano_a_solo(self) -> None:
        # Pur passando 2 elementi, se sono la stessa data → "Solo …"
        out = calcola_etichetta_variante(
            [date(2026, 5, 4), date(2026, 5, 4)], frozenset()
        )
        assert out == "Solo 04/05/2026"
