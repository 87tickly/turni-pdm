"""Test red-phase TDD — Sprint 8.2 MR-PD1.

Verifica le 3 violazioni dichiarate dall'utente che sono testabili a
livello pure-function nel builder PdC attuale (la 4ª, deposito_pdc_id
NOT NULL, richiede DB session ed è coperta in MR-PD2 via migration +
MR-PD4 via test integrato).

Ogni test è marcato ``xfail(strict=True)``: fallisce sul builder
attuale, passerà sul nuovo builder deposito-first (MR-PD3, MR-PD4).

Quando MR-PD3 chiude le violazioni:
- i test diventano green
- ``strict=True`` causa il fallimento del test xfail che ora passa
- a quel punto: rimuovere ``xfail`` (i test diventano normali asserzioni)

Niente fixture DB: test puri su ``_build_giornata_pdc``.

Riferimento: ``docs/AUDIT-PDC-NORMATIVA-2026-05-09.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

import pytest

from colazione.domain.builder_pdc.builder import (
    CONDOTTA_MAX_MIN,
    _build_giornata_pdc,
)


@dataclass
class _StubBlocco:
    """Stub minimale che imita ``GiroBlocco`` per i test puri.

    ``_build_giornata_pdc`` accede solo a: ``ora_inizio``, ``ora_fine``,
    ``stazione_da_codice``, ``stazione_a_codice``, ``id``,
    ``corsa_commerciale_id``, ``corsa_materiale_vuoto_id``. Lo stub
    espone questi campi.
    """

    seq: int
    ora_inizio: time | None
    ora_fine: time | None
    stazione_da_codice: str | None
    stazione_a_codice: str | None
    corsa_commerciale_id: int | None = None
    corsa_materiale_vuoto_id: int | None = None
    id: int | None = None


def _b(
    seq: int,
    ini_h: int,
    ini_m: int,
    fin_h: int,
    fin_m: int,
    da: str,
    a: str,
) -> _StubBlocco:
    """Helper: blocco con orari HH:MM da/a stazioni."""
    return _StubBlocco(
        seq=seq,
        ora_inizio=time(ini_h, ini_m),
        ora_fine=time(fin_h, fin_m),
        stazione_da_codice=da,
        stazione_a_codice=a,
        id=seq,
    )


# =====================================================================
# Violazione A — Cap condotta 5h30 (330 min) non rispettato
# =====================================================================


@pytest.mark.xfail(
    strict=True,
    reason=(
        "MR-PD1 red phase: builder monolitico costruisce 1 giornata con "
        "TUTTI i blocchi del giro, anche se condotta totale > 330 min. "
        "Risolto in MR-PD3 builder deposito-first che spezza per "
        "costruzione (cap condotta HARD)."
    ),
)
def test_violazione_a_cap_condotta_giornata_non_supera_330min() -> None:
    """Una giornata costruita con blocchi che totalizzano >330 min di
    condotta DEVE rispettare il cap §3 (condotta max 5h30 = 330 min).

    Stato attuale: builder monolitico annota la violazione ma non la
    previene (genera la giornata con condotta_min > 330).
    """
    # 4 blocchi da 100 min ciascuno = 400 min condotta totale (>330)
    blocchi = [
        _b(1, 6, 0, 7, 40, "MILANO_CENTRALE", "BERGAMO"),
        _b(2, 8, 0, 9, 40, "BERGAMO", "BRESCIA"),
        _b(3, 10, 0, 11, 40, "BRESCIA", "VERONA"),
        _b(4, 12, 0, 13, 40, "VERONA", "PADOVA"),
    ]
    draft = _build_giornata_pdc(
        numero_giornata=1,
        variante_calendario="LMXGV",
        blocchi_giro=blocchi,  # type: ignore[arg-type]
    )
    assert draft is not None
    assert draft.condotta_min <= CONDOTTA_MAX_MIN, (
        f"condotta_min={draft.condotta_min} eccede cap §3 "
        f"({CONDOTTA_MAX_MIN}min). Violazione A: builder non spezza."
    )


# =====================================================================
# Violazione C — Turno non chiude in stazione deposito
# =====================================================================


@pytest.mark.xfail(
    strict=True,
    reason=(
        "MR-PD1 red phase: builder monolitico setta stazione_fine = "
        "ultimo blocco condotta del giro, NON il deposito. "
        "Risolto in MR-PD3 builder deposito-first che forza chiusura "
        "in stazione_principale_codice del deposito (NORMATIVA §2.3)."
    ),
)
def test_violazione_c_giornata_chiude_in_stazione_deposito() -> None:
    """Una giornata DEVE chiudere in ``stazione_principale_codice`` del
    deposito di appartenenza (NORMATIVA §2.3 "il PdC rientra sempre al
    proprio deposito").

    Stato attuale: ``_build_giornata_pdc`` non riceve il deposito e
    setta ``stazione_fine = ultimo.stazione_a_codice``.
    """
    # Giro Mi.PG → Mi.Centrale → Tirano. PdC deposito MILANO_PG → DEVE
    # chiudere in MILANO_PG (non TIRANO).
    blocchi = [
        _b(1, 6, 0, 7, 0, "MILANO_PG", "MILANO_CENTRALE"),
        _b(2, 7, 30, 11, 0, "MILANO_CENTRALE", "TIRANO"),
    ]
    draft = _build_giornata_pdc(
        numero_giornata=1,
        variante_calendario="LMXGV",
        blocchi_giro=blocchi,  # type: ignore[arg-type]
    )
    assert draft is not None
    deposito_atteso = "MILANO_PG"
    assert draft.stazione_fine == deposito_atteso, (
        f"stazione_fine={draft.stazione_fine!r} ≠ deposito atteso "
        f"{deposito_atteso!r}. Violazione C: builder non chiude in "
        f"stazione deposito."
    )


# =====================================================================
# Violazione D — Vetture rientro mancanti
# =====================================================================


@pytest.mark.xfail(
    strict=True,
    reason=(
        "MR-PD1 red phase: builder monolitico NON aggiunge mai un blocco "
        "VETTURA/MM/VOCTAXI in coda. Ultimo blocco rilevante è ACCa + FINE. "
        "Risolto in MR-PD3 builder deposito-first + vettura_resolver §7.2 "
        "(priorità vettura → MM → VOCTAXI)."
    ),
)
def test_violazione_d_giornata_lontana_da_deposito_ha_vettura_rientro() -> None:
    """Quando una giornata termina lontano dal deposito DEVE avere un
    blocco di rientro (VETTURA, MM, o VOCTAXI) come ultimo blocco
    rilevante PRIMA della FINE servizio (NORMATIVA §7.2 priorità).

    Stato attuale: ``_build_giornata_pdc`` chiude con [..., ACCa, FINE]
    senza vettura di rientro.
    """
    # Giornata che termina a TIRANO (lontano da qualunque deposito).
    blocchi = [
        _b(1, 6, 0, 7, 0, "MILANO_PG", "MILANO_CENTRALE"),
        _b(2, 7, 30, 11, 0, "MILANO_CENTRALE", "TIRANO"),
    ]
    draft = _build_giornata_pdc(
        numero_giornata=1,
        variante_calendario="LMXGV",
        blocchi_giro=blocchi,  # type: ignore[arg-type]
    )
    assert draft is not None
    tipi_rientro = {"VETTURA", "MM", "VOCTAXI"}
    # Cerca l'ultimo blocco non-FINE: dovrebbe essere uno dei tipi_rientro
    # quando la giornata termina lontano dal deposito.
    blocchi_rilevanti = [b for b in draft.blocchi if b.tipo_evento != "FINE"]
    assert blocchi_rilevanti, "draft senza blocchi rilevanti"
    ultimo_rilevante = blocchi_rilevanti[-1]
    assert ultimo_rilevante.tipo_evento in tipi_rientro, (
        f"ultimo blocco rilevante è {ultimo_rilevante.tipo_evento!r}, "
        f"atteso uno di {tipi_rientro}. Violazione D: nessun rientro "
        f"§7.2."
    )


# =====================================================================
# Violazione B — deposito_pdc_id NOT NULL (rimandata a MR-PD2 + MR-PD4)
# =====================================================================
# La violazione B richiede:
# - migration alembic per ``deposito_pdc_id NOT NULL`` (MR-PD2)
# - test integrato con DB session che verifica builder rifiuti
#   ``deposito_pdc_id=None`` (MR-PD4)
#
# Documentata in ``docs/AUDIT-PDC-NORMATIVA-2026-05-09.md`` Violazione B.
