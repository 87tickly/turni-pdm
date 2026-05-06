"""Test domain — applicazione concreta variazioni PdE (sub-MR 5.bis-a).

Pure unit test del modulo ``domain/variazioni.py``. Niente DB, niente
fastapi: solo dataclass + funzioni pure. Gira fuori CI senza Postgres.
"""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal

from colazione.domain.variazioni import (
    CancellaCorsa,
    CodiceErrore,
    CorsaSnapshot,
    InsertCorsa,
    Operazione,
    RimuoviDateValidita,
    UpdateOrario,
    applica_rimozione_date,
    valida_e_normalizza,
)

# =====================================================================
# Fixtures locali
# =====================================================================


_AZIENDA = 1


def _snap(
    *,
    id: int = 100,
    azienda_id: int = _AZIENDA,
    valido_da: date = date(2026, 1, 1),
    valido_a: date = date(2026, 12, 31),
    valido_in_date_json: tuple[str, ...] = (
        "2026-06-15",
        "2026-06-16",
        "2026-06-17",
    ),
    is_cancellata: bool = False,
) -> CorsaSnapshot:
    return CorsaSnapshot(
        id=id,
        azienda_id=azienda_id,
        numero_treno="13",
        valido_da=valido_da,
        valido_a=valido_a,
        valido_in_date_json=valido_in_date_json,
        is_cancellata=is_cancellata,
    )


def _insert_min(numero_treno: str = "9999") -> InsertCorsa:
    return InsertCorsa(
        numero_treno=numero_treno,
        codice_origine="S01066",
        codice_destinazione="S00018",
        ora_partenza=time(6, 30),
        ora_arrivo=time(7, 45),
        valido_da=date(2026, 1, 1),
        valido_a=date(2026, 12, 31),
    )


# =====================================================================
# InsertCorsa
# =====================================================================


def test_insert_corsa_caso_base_ok() -> None:
    op = _insert_min()
    res = valida_e_normalizza([op], corse_esistenti={}, azienda_id=_AZIENDA)
    assert res.is_valido
    assert res.n_insert_corsa == 1
    assert res.n_no_op == 0
    assert res.errori == ()


def test_insert_corsa_numero_treno_vuoto_errore() -> None:
    op = _insert_min(numero_treno="   ")
    res = valida_e_normalizza([op], corse_esistenti={}, azienda_id=_AZIENDA)
    assert not res.is_valido
    assert res.errori[0].codice == CodiceErrore.INSERT_CAMPI_OBBLIGATORI_MANCANTI
    assert "numero_treno" in res.errori[0].motivo


def test_insert_corsa_codice_origine_vuoto_errore() -> None:
    op = InsertCorsa(
        numero_treno="13",
        codice_origine="",
        codice_destinazione="S00018",
        ora_partenza=time(6, 30),
        ora_arrivo=time(7, 45),
        valido_da=date(2026, 1, 1),
        valido_a=date(2026, 12, 31),
    )
    res = valida_e_normalizza([op], corse_esistenti={}, azienda_id=_AZIENDA)
    assert res.errori[0].codice == CodiceErrore.INSERT_CAMPI_OBBLIGATORI_MANCANTI


def test_insert_corsa_valido_da_dopo_valido_a_errore() -> None:
    op = InsertCorsa(
        numero_treno="13",
        codice_origine="S01066",
        codice_destinazione="S00018",
        ora_partenza=time(6, 30),
        ora_arrivo=time(7, 45),
        valido_da=date(2026, 12, 31),
        valido_a=date(2026, 1, 1),
    )
    res = valida_e_normalizza([op], corse_esistenti={}, azienda_id=_AZIENDA)
    assert res.errori[0].codice == CodiceErrore.INSERT_VALIDO_DA_DOPO_VALIDO_A


# =====================================================================
# UpdateOrario
# =====================================================================


def test_update_orario_caso_base_ok() -> None:
    op = UpdateOrario(corsa_id=100, ora_partenza=time(7, 0))
    res = valida_e_normalizza(
        [op], corse_esistenti={100: _snap()}, azienda_id=_AZIENDA
    )
    assert res.is_valido
    assert res.n_update_orario == 1


def test_update_orario_corsa_inesistente_errore() -> None:
    op = UpdateOrario(corsa_id=999, ora_partenza=time(7, 0))
    res = valida_e_normalizza([op], corse_esistenti={}, azienda_id=_AZIENDA)
    assert res.errori[0].codice == CodiceErrore.CORSA_NON_TROVATA
    assert res.errori[0].corsa_id == 999


def test_update_orario_corsa_altra_azienda_errore() -> None:
    op = UpdateOrario(corsa_id=100, ora_partenza=time(7, 0))
    res = valida_e_normalizza(
        [op],
        corse_esistenti={100: _snap(azienda_id=2)},
        azienda_id=_AZIENDA,
    )
    assert res.errori[0].codice == CodiceErrore.CORSA_DI_ALTRA_AZIENDA


def test_update_orario_corsa_gia_cancellata_errore() -> None:
    op = UpdateOrario(corsa_id=100, ora_partenza=time(7, 0))
    res = valida_e_normalizza(
        [op],
        corse_esistenti={100: _snap(is_cancellata=True)},
        azienda_id=_AZIENDA,
    )
    assert res.errori[0].codice == CodiceErrore.CORSA_GIA_CANCELLATA


def test_update_orario_vuoto_errore() -> None:
    """UpdateOrario senza nessun campo valorizzato è errore (probabile bug
    del parser: meglio segnalare che applicare in silenzio)."""
    op = UpdateOrario(corsa_id=100)
    res = valida_e_normalizza(
        [op], corse_esistenti={100: _snap()}, azienda_id=_AZIENDA
    )
    assert res.errori[0].codice == CodiceErrore.UPDATE_ORARIO_VUOTO


def test_update_orario_solo_km_ok() -> None:
    """Almeno un campo basta: anche solo km_tratta."""
    op = UpdateOrario(corsa_id=100, km_tratta=Decimal("123.456"))
    res = valida_e_normalizza(
        [op], corse_esistenti={100: _snap()}, azienda_id=_AZIENDA
    )
    assert res.is_valido
    assert res.n_update_orario == 1


# =====================================================================
# RimuoviDateValidita
# =====================================================================


def test_rimuovi_date_caso_base_ok() -> None:
    op = RimuoviDateValidita(
        corsa_id=100,
        date_da_rimuovere=(date(2026, 6, 15), date(2026, 6, 16)),
    )
    res = valida_e_normalizza(
        [op], corse_esistenti={100: _snap()}, azienda_id=_AZIENDA
    )
    assert res.is_valido
    assert res.n_rimuovi_date == 1
    assert res.n_no_op == 0


def test_rimuovi_date_lista_vuota_errore() -> None:
    op = RimuoviDateValidita(corsa_id=100, date_da_rimuovere=())
    res = valida_e_normalizza(
        [op], corse_esistenti={100: _snap()}, azienda_id=_AZIENDA
    )
    assert res.errori[0].codice == CodiceErrore.LISTA_DATE_VUOTA


def test_rimuovi_date_fuori_range_validita_errore() -> None:
    op = RimuoviDateValidita(
        corsa_id=100,
        date_da_rimuovere=(date(2027, 1, 1),),  # fuori 2026-01..2026-12
    )
    res = valida_e_normalizza(
        [op], corse_esistenti={100: _snap()}, azienda_id=_AZIENDA
    )
    assert res.errori[0].codice == CodiceErrore.DATA_FUORI_RANGE_VALIDITA


def test_rimuovi_date_no_op_se_data_gia_assente() -> None:
    """Date dentro il range di validità ma non presenti in
    valido_in_date_json → no-op (idempotente)."""
    op = RimuoviDateValidita(
        corsa_id=100,
        date_da_rimuovere=(date(2026, 7, 1),),  # in range, non in JSON
    )
    res = valida_e_normalizza(
        [op],
        corse_esistenti={100: _snap()},
        azienda_id=_AZIENDA,
    )
    assert res.is_valido
    assert res.n_rimuovi_date == 0
    assert res.n_no_op == 1


def test_rimuovi_date_corsa_cancellata_errore() -> None:
    op = RimuoviDateValidita(
        corsa_id=100,
        date_da_rimuovere=(date(2026, 6, 15),),
    )
    res = valida_e_normalizza(
        [op],
        corse_esistenti={100: _snap(is_cancellata=True)},
        azienda_id=_AZIENDA,
    )
    assert res.errori[0].codice == CodiceErrore.CORSA_GIA_CANCELLATA


# =====================================================================
# CancellaCorsa
# =====================================================================


def test_cancella_corsa_caso_base_ok() -> None:
    op = CancellaCorsa(corsa_id=100)
    res = valida_e_normalizza(
        [op], corse_esistenti={100: _snap()}, azienda_id=_AZIENDA
    )
    assert res.is_valido
    assert res.n_cancella_corsa == 1
    assert res.n_no_op == 0


def test_cancella_corsa_idempotente_su_gia_cancellata_no_op() -> None:
    """Cancellare una corsa già cancellata è no-op silenzioso, non errore.
    Coerente con la decisione 2026-05-06 (immutabile + idempotente)."""
    op = CancellaCorsa(corsa_id=100)
    res = valida_e_normalizza(
        [op],
        corse_esistenti={100: _snap(is_cancellata=True)},
        azienda_id=_AZIENDA,
    )
    assert res.is_valido
    assert res.n_cancella_corsa == 0
    assert res.n_no_op == 1


def test_cancella_corsa_inesistente_errore() -> None:
    op = CancellaCorsa(corsa_id=999)
    res = valida_e_normalizza([op], corse_esistenti={}, azienda_id=_AZIENDA)
    assert res.errori[0].codice == CodiceErrore.CORSA_NON_TROVATA


def test_cancella_corsa_altra_azienda_errore() -> None:
    op = CancellaCorsa(corsa_id=100)
    res = valida_e_normalizza(
        [op],
        corse_esistenti={100: _snap(azienda_id=2)},
        azienda_id=_AZIENDA,
    )
    assert res.errori[0].codice == CodiceErrore.CORSA_DI_ALTRA_AZIENDA


# =====================================================================
# Batch misti
# =====================================================================


def test_batch_misto_4_tipi_tutti_validi() -> None:
    snap_100 = _snap(id=100)
    snap_101 = _snap(id=101, valido_in_date_json=("2026-06-15", "2026-06-20"))
    operazioni: list[Operazione] = [
        _insert_min(numero_treno="9001"),
        UpdateOrario(corsa_id=100, ora_partenza=time(8, 0)),
        RimuoviDateValidita(corsa_id=101, date_da_rimuovere=(date(2026, 6, 15),)),
        CancellaCorsa(corsa_id=100),  # nota: stessa corsa di UPDATE → ok lato
        # validazione (l'ordine di applicazione è del caller); il test
        # serve solo a verificare che il dominio non blocchi.
    ]
    # Seconda CancellaCorsa su 100 dopo l'UPDATE? Lo snapshot vede 100 NON
    # cancellata, quindi è valida. Il caller sa che applicandole nell'ordine
    # corretto la cancella all'ultimo step.
    res = valida_e_normalizza(
        operazioni,
        corse_esistenti={100: snap_100, 101: snap_101},
        azienda_id=_AZIENDA,
    )
    assert res.is_valido
    assert res.n_insert_corsa == 1
    assert res.n_update_orario == 1
    assert res.n_rimuovi_date == 1
    assert res.n_cancella_corsa == 1
    assert res.n_errori == 0


def test_batch_errori_e_validi_coesistono() -> None:
    """Errori in alcune operazioni non bloccano le altre. Il caller decide
    se applicare parziale (fail_on_any_error=False) o tutto-o-niente."""
    operazioni: list[Operazione] = [
        _insert_min(numero_treno="9001"),  # OK
        UpdateOrario(corsa_id=999, ora_partenza=time(8, 0)),  # CORSA_NON_TROVATA
        CancellaCorsa(corsa_id=100),  # OK
    ]
    res = valida_e_normalizza(
        operazioni,
        corse_esistenti={100: _snap()},
        azienda_id=_AZIENDA,
    )
    assert not res.is_valido
    assert res.n_insert_corsa == 1
    assert res.n_cancella_corsa == 1
    assert res.n_errori == 1
    assert res.errori[0].indice_operazione == 1
    assert res.errori[0].codice == CodiceErrore.CORSA_NON_TROVATA


def test_indice_operazione_preservato_negli_errori() -> None:
    """L'indice 0-based dell'operazione errata è preservato nella lista
    errori, per UI che evidenzia la riga problematica."""
    operazioni: list[Operazione] = [
        _insert_min(numero_treno="9001"),  # idx 0 OK
        _insert_min(numero_treno="   "),  # idx 1 ERRORE
        UpdateOrario(corsa_id=999, ora_partenza=time(8, 0)),  # idx 2 ERRORE
    ]
    res = valida_e_normalizza(
        operazioni, corse_esistenti={}, azienda_id=_AZIENDA
    )
    assert len(res.errori) == 2
    assert res.errori[0].indice_operazione == 1
    assert res.errori[1].indice_operazione == 2


# =====================================================================
# applica_rimozione_date (helper pure)
# =====================================================================


def test_applica_rimozione_date_basico() -> None:
    iniziali = ["2026-06-15", "2026-06-16", "2026-06-17"]
    nuova, n = applica_rimozione_date(
        iniziali, [date(2026, 6, 15), date(2026, 6, 16)]
    )
    assert nuova == ["2026-06-17"]
    assert n == 2


def test_applica_rimozione_date_nessuna_match_no_op() -> None:
    iniziali = ["2026-06-15", "2026-06-16"]
    nuova, n = applica_rimozione_date(iniziali, [date(2026, 7, 1)])
    assert nuova == iniziali
    assert n == 0


def test_applica_rimozione_date_idempotente() -> None:
    """Applicare la stessa rimozione 2 volte produce stesso risultato."""
    iniziali = ["2026-06-15", "2026-06-16", "2026-06-17"]
    pass1, n1 = applica_rimozione_date(iniziali, [date(2026, 6, 15)])
    pass2, n2 = applica_rimozione_date(pass1, [date(2026, 6, 15)])
    assert pass1 == pass2
    assert n1 == 1
    assert n2 == 0


def test_applica_rimozione_date_input_non_mutato() -> None:
    """Verifico che l'input ``valido_in_date_json`` non venga mutato in
    place (la funzione deve essere pure)."""
    iniziali = ["2026-06-15", "2026-06-16"]
    iniziali_copia = list(iniziali)
    _, _ = applica_rimozione_date(iniziali, [date(2026, 6, 15)])
    assert iniziali == iniziali_copia


# =====================================================================
# Frozen dataclass
# =====================================================================


def test_corsa_snapshot_immutabile() -> None:
    snap = _snap()
    try:
        snap.is_cancellata = True  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("CorsaSnapshot dovrebbe essere frozen")


def test_insert_corsa_uguaglianza_per_valore() -> None:
    """frozen dataclass → __eq__ struttuale. Utile per il caller che
    confronta operazioni in test."""
    op_a = _insert_min(numero_treno="13")
    op_b = _insert_min(numero_treno="13")
    assert op_a == op_b
