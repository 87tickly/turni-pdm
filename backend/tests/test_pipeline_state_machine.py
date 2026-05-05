"""Test domain/pipeline.py — Sprint 8.0 MR 0 (entry 164).

Unit pure (no DB): copre enum, matrici di transizione, helper di policy
visibilità per ruolo.
"""

from __future__ import annotations

import pytest

from colazione.domain.pipeline import (
    SOGLIE_PIPELINE_PER_RUOLO,
    TRANSIZIONI_MANUTENZIONE_AMMESSE,
    TRANSIZIONI_PDC_AMMESSE,
    StatoManutenzione,
    StatoPipelinePdc,
    TipoImportRun,
    TransizioneNonAmmessaError,
    ordinale_manutenzione,
    ordinale_pdc,
    programma_visibile_per_ruoli,
    soglia_pipeline_per_ruoli,
    stati_manutenzione_da,
    stati_pdc_da,
    stato_manutenzione_precedente,
    stato_pdc_precedente,
    valida_transizione_manutenzione,
    valida_transizione_pdc,
)

# =====================================================================
# Enum identity
# =====================================================================


def test_stato_pipeline_pdc_8_valori_ordinati() -> None:
    """8 stati nella sequenza canonica PdE → Vista pubblicata."""
    assert [s.value for s in StatoPipelinePdc] == [
        "PDE_IN_LAVORAZIONE",
        "PDE_CONSOLIDATO",
        "MATERIALE_GENERATO",
        "MATERIALE_CONFERMATO",
        "PDC_GENERATO",
        "PDC_CONFERMATO",
        "PERSONALE_ASSEGNATO",
        "VISTA_PUBBLICATA",
    ]


def test_stato_manutenzione_3_valori_ordinati() -> None:
    assert [s.value for s in StatoManutenzione] == [
        "IN_ATTESA",
        "IN_LAVORAZIONE",
        "MATRICOLE_ASSEGNATE",
    ]


def test_tipo_import_run_5_valori() -> None:
    assert [t.value for t in TipoImportRun] == [
        "BASE",
        "INTEGRAZIONE",
        "VARIAZIONE_INTERRUZIONE",
        "VARIAZIONE_ORARIO",
        "VARIAZIONE_CANCELLAZIONE",
    ]


def test_enum_str_value_round_trip() -> None:
    assert StatoPipelinePdc("PDE_CONSOLIDATO") is StatoPipelinePdc.PDE_CONSOLIDATO
    assert StatoManutenzione("IN_LAVORAZIONE") is StatoManutenzione.IN_LAVORAZIONE
    with pytest.raises(ValueError):
        StatoPipelinePdc("FOOBAR")


# =====================================================================
# Matrici copertura totale
# =====================================================================


def test_transizioni_pdc_chiave_copre_tutti_gli_stati() -> None:
    """Ogni stato deve avere una entry esplicita (anche se frozenset())."""
    assert set(TRANSIZIONI_PDC_AMMESSE.keys()) == set(StatoPipelinePdc)


def test_transizioni_manutenzione_chiave_copre_tutti_gli_stati() -> None:
    assert set(TRANSIZIONI_MANUTENZIONE_AMMESSE.keys()) == set(StatoManutenzione)


def test_vista_pubblicata_terminale() -> None:
    assert TRANSIZIONI_PDC_AMMESSE[StatoPipelinePdc.VISTA_PUBBLICATA] == frozenset()


def test_matricole_assegnate_terminale() -> None:
    assert (
        TRANSIZIONI_MANUTENZIONE_AMMESSE[StatoManutenzione.MATRICOLE_ASSEGNATE]
        == frozenset()
    )


# =====================================================================
# Transizioni PdC
# =====================================================================


def test_transizione_pdc_lineare_ammessa() -> None:
    valida_transizione_pdc(
        StatoPipelinePdc.PDE_IN_LAVORAZIONE, StatoPipelinePdc.PDE_CONSOLIDATO
    )
    valida_transizione_pdc(
        StatoPipelinePdc.MATERIALE_GENERATO, StatoPipelinePdc.MATERIALE_CONFERMATO
    )
    valida_transizione_pdc(
        StatoPipelinePdc.PDC_GENERATO, StatoPipelinePdc.PDC_CONFERMATO
    )
    valida_transizione_pdc(
        StatoPipelinePdc.PERSONALE_ASSEGNATO, StatoPipelinePdc.VISTA_PUBBLICATA
    )


def test_transizione_pdc_skip_da_consolidato_a_confermato() -> None:
    """``PDE_CONSOLIDATO → MATERIALE_CONFERMATO`` salta GENERATO (spec MR 0)."""
    valida_transizione_pdc(
        StatoPipelinePdc.PDE_CONSOLIDATO, StatoPipelinePdc.MATERIALE_CONFERMATO
    )


def test_transizione_pdc_salto_diretto_vietato() -> None:
    with pytest.raises(TransizioneNonAmmessaError, match="non ammessa"):
        valida_transizione_pdc(
            StatoPipelinePdc.PDE_IN_LAVORAZIONE,
            StatoPipelinePdc.MATERIALE_CONFERMATO,
        )


def test_transizione_pdc_inversa_vietata() -> None:
    with pytest.raises(TransizioneNonAmmessaError):
        valida_transizione_pdc(
            StatoPipelinePdc.PDC_CONFERMATO, StatoPipelinePdc.PDC_GENERATO
        )


def test_transizione_pdc_terminale_no_uscita() -> None:
    with pytest.raises(TransizioneNonAmmessaError):
        valida_transizione_pdc(
            StatoPipelinePdc.VISTA_PUBBLICATA, StatoPipelinePdc.PERSONALE_ASSEGNATO
        )


# =====================================================================
# Transizioni manutenzione
# =====================================================================


def test_transizione_manutenzione_lineare_ammessa() -> None:
    valida_transizione_manutenzione(
        StatoManutenzione.IN_ATTESA, StatoManutenzione.IN_LAVORAZIONE
    )
    valida_transizione_manutenzione(
        StatoManutenzione.IN_LAVORAZIONE, StatoManutenzione.MATRICOLE_ASSEGNATE
    )


def test_transizione_manutenzione_salto_vietato() -> None:
    with pytest.raises(TransizioneNonAmmessaError):
        valida_transizione_manutenzione(
            StatoManutenzione.IN_ATTESA, StatoManutenzione.MATRICOLE_ASSEGNATE
        )


def test_transizione_manutenzione_inversa_vietata() -> None:
    with pytest.raises(TransizioneNonAmmessaError):
        valida_transizione_manutenzione(
            StatoManutenzione.IN_LAVORAZIONE, StatoManutenzione.IN_ATTESA
        )


# =====================================================================
# Ordinale + stati_pdc_da
# =====================================================================


def test_ordinale_pdc_estremi() -> None:
    assert ordinale_pdc(StatoPipelinePdc.PDE_IN_LAVORAZIONE) == 0
    assert ordinale_pdc(StatoPipelinePdc.VISTA_PUBBLICATA) == 7


def test_ordinale_manutenzione_estremi() -> None:
    assert ordinale_manutenzione(StatoManutenzione.IN_ATTESA) == 0
    assert ordinale_manutenzione(StatoManutenzione.MATRICOLE_ASSEGNATE) == 2


def test_stati_pdc_da_pdc_confermato() -> None:
    out = stati_pdc_da(StatoPipelinePdc.PDC_CONFERMATO)
    assert out == (
        "PDC_CONFERMATO",
        "PERSONALE_ASSEGNATO",
        "VISTA_PUBBLICATA",
    )


def test_stati_pdc_da_inizio_ritorna_tutti() -> None:
    out = stati_pdc_da(StatoPipelinePdc.PDE_IN_LAVORAZIONE)
    assert len(out) == 8


def test_stati_pdc_da_terminale_solo_se_stesso() -> None:
    assert stati_pdc_da(StatoPipelinePdc.VISTA_PUBBLICATA) == ("VISTA_PUBBLICATA",)


def test_stati_manutenzione_da() -> None:
    assert stati_manutenzione_da(StatoManutenzione.IN_LAVORAZIONE) == (
        "IN_LAVORAZIONE",
        "MATRICOLE_ASSEGNATE",
    )


# =====================================================================
# Precedente (sblocco)
# =====================================================================


def test_stato_pdc_precedente_normale() -> None:
    assert (
        stato_pdc_precedente(StatoPipelinePdc.MATERIALE_CONFERMATO)
        is StatoPipelinePdc.MATERIALE_GENERATO
    )
    assert (
        stato_pdc_precedente(StatoPipelinePdc.VISTA_PUBBLICATA)
        is StatoPipelinePdc.PERSONALE_ASSEGNATO
    )


def test_stato_pdc_precedente_iniziale_none() -> None:
    assert stato_pdc_precedente(StatoPipelinePdc.PDE_IN_LAVORAZIONE) is None


def test_stato_manutenzione_precedente() -> None:
    assert (
        stato_manutenzione_precedente(StatoManutenzione.IN_LAVORAZIONE)
        is StatoManutenzione.IN_ATTESA
    )
    assert stato_manutenzione_precedente(StatoManutenzione.IN_ATTESA) is None


# =====================================================================
# Soglia per ruoli (policy visibilità list-route)
# =====================================================================


def test_soglie_costante_copre_3_ruoli_a_valle() -> None:
    assert set(SOGLIE_PIPELINE_PER_RUOLO.keys()) == {
        "PIANIFICATORE_PDC",
        "GESTIONE_PERSONALE",
        "MANUTENZIONE",
    }


def test_soglia_admin_none() -> None:
    assert soglia_pipeline_per_ruoli(["foo"], is_admin=True) is None


def test_soglia_pianificatore_giro_none() -> None:
    assert (
        soglia_pipeline_per_ruoli(["PIANIFICATORE_GIRO"], is_admin=False) is None
    )


def test_soglia_pianificatore_pdc() -> None:
    assert (
        soglia_pipeline_per_ruoli(["PIANIFICATORE_PDC"], is_admin=False)
        is StatoPipelinePdc.MATERIALE_CONFERMATO
    )


def test_soglia_gestione_personale() -> None:
    assert (
        soglia_pipeline_per_ruoli(["GESTIONE_PERSONALE"], is_admin=False)
        is StatoPipelinePdc.PDC_CONFERMATO
    )


def test_soglia_manutenzione() -> None:
    assert (
        soglia_pipeline_per_ruoli(["MANUTENZIONE"], is_admin=False)
        is StatoPipelinePdc.MATERIALE_CONFERMATO
    )


def test_soglia_multi_ruolo_piu_permissiva_vince() -> None:
    """``[PIANIFICATORE_PDC, GESTIONE_PERSONALE]`` → MATERIALE_CONFERMATO
    (più permissiva fra le 2 soglie)."""
    out = soglia_pipeline_per_ruoli(
        ["PIANIFICATORE_PDC", "GESTIONE_PERSONALE"], is_admin=False
    )
    assert out is StatoPipelinePdc.MATERIALE_CONFERMATO


def test_soglia_ruolo_sconosciuto_none() -> None:
    """Ruolo non in matrice → None (auth dependency a monte rifiuterebbe)."""
    assert soglia_pipeline_per_ruoli(["FOO_BAR"], is_admin=False) is None


# =====================================================================
# programma_visibile_per_ruoli
# =====================================================================


def test_programma_visibile_admin_sempre_true() -> None:
    assert (
        programma_visibile_per_ruoli(
            "PDE_IN_LAVORAZIONE", roles=[], is_admin=True
        )
        is True
    )


def test_programma_invisibile_a_pdc_sotto_soglia() -> None:
    assert (
        programma_visibile_per_ruoli(
            "PDE_CONSOLIDATO", roles=["PIANIFICATORE_PDC"], is_admin=False
        )
        is False
    )


def test_programma_visibile_a_pdc_alla_soglia() -> None:
    assert (
        programma_visibile_per_ruoli(
            "MATERIALE_CONFERMATO", roles=["PIANIFICATORE_PDC"], is_admin=False
        )
        is True
    )


def test_programma_visibile_a_pdc_oltre_soglia() -> None:
    assert (
        programma_visibile_per_ruoli(
            "VISTA_PUBBLICATA", roles=["PIANIFICATORE_PDC"], is_admin=False
        )
        is True
    )


def test_programma_invisibile_se_stato_corrotto() -> None:
    """Difensivo: stato fuori enum → invisibile (CHECK DB lo previene)."""
    assert (
        programma_visibile_per_ruoli(
            "FOOBAR", roles=["PIANIFICATORE_PDC"], is_admin=False
        )
        is False
    )
