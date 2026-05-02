"""Test integration Sprint 4.4.5a — persister giri (dominio → ORM).

Richiede:
- Postgres locale up + migrazioni 0001-0005 applicate.
- Seed Trenord (azienda_id=1, materiale_tipo "ALe711").

Set ``SKIP_DB_TESTS=1`` per saltare. Pattern come ``test_programmi_api.py``.

Coverage:

- Caso base: 1 giro 1 giornata 1 corsa, 0 vuoti, 0 eventi → ORM creati.
- Vuoto testa, vuoto coda, entrambi.
- Multi-giornata (2 giornate cross-notte).
- Eventi composizione (aggancio + sgancio).
- Lista vuota → ``[]`` ritornato.
- Località non trovata → ``LocalitaNonTrovataError``.
- ``numero_treno_vuoto`` formato ``V-{numero_turno}-{NNN}``.
- ``generation_metadata_json`` popolato (versione, motivo, ecc.).
- ``GiroGiornata.dates_apply_json`` popolato con la data della giornata
  (Sprint 7.7 MR 3: i campi di validità sono saliti su GiroGiornata,
  GiroVariante è stato droppato).
"""

from __future__ import annotations

import dataclasses
import os
from datetime import date, time

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.db import dispose_engine, session_scope
from colazione.domain.builder_giro import (
    AssegnazioneRisolta,
    BloccoAssegnato,
    BloccoMaterialeVuoto,
    Catena,
    CatenaPosizionata,
    ComposizioneItem,
    EventoComposizione,
    GiornataAssegnata,
    GiroAssegnato,
    GiroDaPersistere,
    LocalitaNonTrovataError,
    persisti_giri,
)
from colazione.models.anagrafica import LocalitaManutenzione, Stazione
from colazione.models.corse import CorsaCommerciale, CorsaMaterialeVuoto
from colazione.models.giri import GiroBlocco, GiroGiornata, GiroMateriale
from colazione.models.programmi import ProgrammaMateriale

pytestmark = pytest.mark.skipif(
    os.getenv("SKIP_DB_TESTS") == "1",
    reason="DB not configured for tests",
)


# =====================================================================
# Setup / Teardown
# =====================================================================


MATERIALE_TIPO = "ALe711"  # seed Trenord


async def _get_azienda_trenord_id() -> int:
    """Recupera dinamicamente l'id Trenord (sequence può variare in dev)."""
    async with session_scope() as session:
        row = (
            await session.execute(text("SELECT id FROM azienda WHERE codice = 'trenord'"))
        ).first()
        if row is None:
            raise RuntimeError("Seed Trenord non trovato nel DB")
        return int(row[0])


@pytest.fixture(scope="module")
async def azienda_id() -> int:
    return await _get_azienda_trenord_id()


async def _wipe_test_data() -> None:
    """Pulisce i dati di test (prefisso TEST_) + tutti i giri.

    Ordine FK-safe: turni PdC → blocchi → giornate → vuoti →
    giri → corse test → località test → stazioni test.

    `turno_pdc_blocco.corsa_materiale_vuoto_id` e
    `turno_pdc_blocco.corsa_commerciale_id` sono FK RESTRICT: senza
    cancellare prima i turni PdC, il `DELETE FROM corsa_materiale_vuoto`
    fallisce con `ForeignKeyViolation`. CASCADE su `turno_pdc` →
    `turno_pdc_giornata` → `turno_pdc_blocco` libera tutto.
    """
    async with session_scope() as session:
        # FK RESTRICT su turno_pdc_blocco → corse: pulire i turni PRIMA.
        await session.execute(text("DELETE FROM turno_pdc"))
        # Tutti i giri (sono tutti di test in dev: nessuno in produzione).
        # Sprint 7.7 MR 3: giro_variante droppato.
        await session.execute(text("DELETE FROM giro_blocco"))
        await session.execute(text("DELETE FROM giro_giornata"))
        await session.execute(text("DELETE FROM corsa_materiale_vuoto"))
        await session.execute(text("DELETE FROM giro_materiale"))
        # Programmi/regole di test (Sprint 5.6: aggiunti per i test
        # km_media e 9XXXX rientro)
        await session.execute(
            text(
                "DELETE FROM programma_regola_assegnazione WHERE programma_id IN ("
                "  SELECT id FROM programma_materiale WHERE nome LIKE 'TEST_%'"
                ")"
            )
        )
        await session.execute(text("DELETE FROM programma_materiale WHERE nome LIKE 'TEST_%'"))
        # Corse di test: TEST_* o che usano stazioni S99*
        await session.execute(
            text(
                "DELETE FROM corsa_commerciale "
                "WHERE numero_treno LIKE 'TEST_%' "
                "   OR codice_origine LIKE 'S99%' "
                "   OR codice_destinazione LIKE 'S99%'"
            )
        )
        await session.execute(text("DELETE FROM localita_manutenzione WHERE codice LIKE 'TEST_%'"))
        # Stazioni test: codici S99NNN (formato `^S\d+$` valido)
        await session.execute(text("DELETE FROM stazione WHERE codice LIKE 'S99%'"))


@pytest.fixture(autouse=True)
async def clean_state() -> None:
    """Stato pulito prima e dopo ogni test (evita FK leftover)."""
    await _wipe_test_data()
    yield
    await _wipe_test_data()


@pytest.fixture(scope="module", autouse=True)
async def cleanup_engine() -> None:
    yield
    await dispose_engine()


# =====================================================================
# Fixture builders (helpers per creare entità di test nel DB)
# =====================================================================


async def _crea_stazione(codice: str, az_id: int) -> None:
    async with session_scope() as session:
        session.add(Stazione(codice=codice, nome=codice, azienda_id=az_id))


async def _crea_programma_test(az_id: int, nome: str = "TEST_PROG_PERSISTER") -> int:
    """Crea un `ProgrammaMateriale` di test, ritorna id.

    Migration 0010 (Sprint 7.3): `giro_materiale.programma_id` è NOT
    NULL + FK; ogni `persisti_giri()` richiede un programma esistente.
    Il fixture `clean_state` cancella i programmi `LIKE 'TEST_%'` a
    fine test.
    """
    async with session_scope() as session:
        p = ProgrammaMateriale(
            azienda_id=az_id,
            nome=nome,
            valido_da=date(2026, 1, 1),
            valido_a=date(2026, 12, 31),
            stato="bozza",
        )
        session.add(p)
        await session.flush()
        return int(p.id)


@pytest.fixture
async def programma_test_id(azienda_id: int) -> int:
    """Fixture: crea programma di test, ritorna id. Wipe lo cancella a fine test."""
    return await _crea_programma_test(azienda_id)


async def _crea_localita(codice: str, stazione: str, az_id: int) -> int:
    """Crea LocalitaManutenzione, ritorna id."""
    async with session_scope() as session:
        loc = LocalitaManutenzione(
            codice=codice,
            codice_breve="TST",  # placeholder valido (^[A-Z]{2,8}$)
            nome_canonico=codice,
            stazione_collegata_codice=stazione,
            azienda_id=az_id,
        )
        session.add(loc)
        await session.flush()
        return int(loc.id)


async def _crea_corsa(
    numero_treno: str,
    origine: str,
    destinazione: str,
    ora_p: tuple[int, int],
    ora_a: tuple[int, int],
    az_id: int,
) -> int:
    """Crea CorsaCommerciale, ritorna id."""
    async with session_scope() as session:
        c = CorsaCommerciale(
            azienda_id=az_id,
            row_hash=("test_" + numero_treno).ljust(64, "0")[:64],
            numero_treno=numero_treno,
            codice_origine=origine,
            codice_destinazione=destinazione,
            ora_partenza=time(*ora_p),
            ora_arrivo=time(*ora_a),
            valido_da=date(2026, 1, 1),
            valido_a=date(2026, 12, 31),
        )
        session.add(c)
        await session.flush()
        return int(c.id)


# =====================================================================
# Helpers costruzione GiroAssegnato di test
# =====================================================================


def _giro_assegnato_singolo(
    *,
    localita_codice: str,
    corse_orm: tuple[CorsaCommerciale, ...],
    vuoto_testa: BloccoMaterialeVuoto | None = None,
    vuoto_coda: BloccoMaterialeVuoto | None = None,
    chiusa: bool = True,
    data_giorno: date = date(2026, 4, 27),
    pezzi_per_corsa: tuple[int, ...] | None = None,
    materiale_tipo: str = MATERIALE_TIPO,
) -> GiroAssegnato:
    """Costruisce un GiroAssegnato 1-giornata per test.

    `pezzi_per_corsa` permette di simulare delta composizione
    (aggancio/sgancio) senza passare da `rileva_eventi_composizione`.
    Se `None`, tutte le corse hanno 3 pezzi.
    """
    if pezzi_per_corsa is None:
        pezzi_per_corsa = tuple(3 for _ in corse_orm)
    assert len(pezzi_per_corsa) == len(corse_orm)

    blocchi_assegnati = tuple(
        BloccoAssegnato(
            corsa=c,
            assegnazione=AssegnazioneRisolta(
                regola_id=1,
                composizione=(ComposizioneItem(materiale_tipo, p),),
            ),
        )
        for c, p in zip(corse_orm, pezzi_per_corsa, strict=True)
    )

    cat_pos = CatenaPosizionata(
        localita_codice=localita_codice,
        stazione_collegata=corse_orm[0].codice_origine,
        vuoto_testa=vuoto_testa,
        catena=Catena(corse=corse_orm),
        vuoto_coda=vuoto_coda,
        chiusa_a_localita=chiusa,
    )

    # Eventi: 1 evento per ogni delta consecutivo (Sprint 5.5: ogni
    # evento ha materiale_tipo_codice = materiale_tipo del test)
    eventi: list[EventoComposizione] = []
    for i in range(1, len(pezzi_per_corsa)):
        delta = pezzi_per_corsa[i] - pezzi_per_corsa[i - 1]
        if delta != 0:
            eventi.append(
                EventoComposizione(
                    tipo="aggancio" if delta > 0 else "sgancio",
                    materiale_tipo_codice=materiale_tipo,
                    pezzi_delta=delta,
                    stazione_proposta=corse_orm[i].codice_origine,
                    posizione_dopo_blocco=i - 1,
                    note_builder=f"test delta {delta}",
                )
            )

    giornata = GiornataAssegnata(
        data=data_giorno,
        catena_posizionata=cat_pos,
        blocchi_assegnati=blocchi_assegnati,
        eventi_composizione=tuple(eventi),
        materiali_tipo_giornata=frozenset({materiale_tipo}),
    )

    return GiroAssegnato(
        localita_codice=localita_codice,
        giornate=(giornata,),
        chiuso=chiusa,
        motivo_chiusura="naturale" if chiusa else "non_chiuso",
    )


# =====================================================================
# Casi base
# =====================================================================


async def test_lista_vuota_ritorna_lista_vuota(azienda_id: int) -> None:
    async with session_scope() as session:
        ids = await persisti_giri([], session, programma_id=999, azienda_id=azienda_id)
        assert ids == []


async def test_un_giro_una_corsa_ORM_creati(
    azienda_id: int, programma_test_id: int
) -> None:
    """Verifica che GiroMateriale + GiroGiornata + GiroBlocco siano creati."""
    await _crea_stazione("S99001", azienda_id)
    await _crea_stazione("S99002", azienda_id)
    loc_id = await _crea_localita("TEST_LOC_FIO", "S99001", azienda_id)
    corsa_id = await _crea_corsa("TEST_001", "S99001", "S99002", (8, 0), (9, 0), azienda_id)

    async with session_scope() as session:
        corsa = (
            await session.execute(select(CorsaCommerciale).where(CorsaCommerciale.id == corsa_id))
        ).scalar_one()
        giro = _giro_assegnato_singolo(
            localita_codice="TEST_LOC_FIO",
            corse_orm=(corsa,),
        )
        ids = await persisti_giri(
            [GiroDaPersistere(numero_turno="G-FIO-001", giro=giro)],
            session,
            programma_id=programma_test_id,
            azienda_id=azienda_id,
        )
        assert len(ids) == 1
        gm_id = ids[0]

    # Verifica (in nuova session per essere sicuri del commit)
    async with session_scope() as session:
        gm = (
            await session.execute(select(GiroMateriale).where(GiroMateriale.id == gm_id))
        ).scalar_one()
        assert gm.numero_turno == "G-FIO-001"
        assert gm.numero_giornate == 1
        assert gm.tipo_materiale == "ALe711"
        assert gm.materiale_tipo_codice == "ALe711"
        assert gm.localita_manutenzione_partenza_id == loc_id
        assert gm.localita_manutenzione_arrivo_id == loc_id
        assert gm.stato == "bozza"
        # generation_metadata_json popolato
        assert gm.generation_metadata_json["persister_version"] == "7.7.3"
        assert gm.generation_metadata_json["motivo_chiusura"] == "naturale"
        assert gm.generation_metadata_json["chiuso"] is True
        # Sprint 7.7 MR 3: etichetta calcolata. Per il default
        # `GiroDaPersistere(...)` (senza specificare etichetta_tipo) il
        # builder mette `personalizzata`.
        assert gm.etichetta_tipo == "personalizzata"

        gg = (
            (
                await session.execute(
                    select(GiroGiornata).where(GiroGiornata.giro_materiale_id == gm_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(gg) == 1
        assert gg[0].numero_giornata == 1
        # Sprint 7.7 MR 3: validità ora vivono su giornata.
        assert gg[0].dates_apply_json == ["2026-04-27"]
        assert gg[0].dates_skip_json == []

        blocchi = (
            (
                await session.execute(
                    select(GiroBlocco)
                    .where(GiroBlocco.giro_giornata_id == gg[0].id)
                    .order_by(GiroBlocco.seq)
                )
            )
            .scalars()
            .all()
        )
        assert len(blocchi) == 1
        assert blocchi[0].tipo_blocco == "corsa_commerciale"
        assert blocchi[0].corsa_commerciale_id == corsa_id
        assert blocchi[0].seq == 1  # check schema: seq >= 1
        assert blocchi[0].is_validato_utente is True


async def test_localita_non_trovata_raises(
    azienda_id: int, programma_test_id: int
) -> None:
    giro = GiroAssegnato(
        localita_codice="INESISTENTE",
        giornate=(),
        chiuso=False,
        motivo_chiusura="non_chiuso",
    )
    async with session_scope() as session:
        with pytest.raises(LocalitaNonTrovataError) as exc_info:
            await persisti_giri(
                [GiroDaPersistere(numero_turno="G-X-001", giro=giro)],
                session,
                programma_id=programma_test_id,
                azienda_id=azienda_id,
            )
        assert exc_info.value.codice == "INESISTENTE"
        assert exc_info.value.azienda_id == azienda_id


# =====================================================================
# Vuoti testa/coda
# =====================================================================


async def test_vuoto_testa_genera_corsa_materiale_vuoto_e_blocco(
    azienda_id: int, programma_test_id: int
) -> None:
    await _crea_stazione("S99001", azienda_id)
    await _crea_stazione("S99002", azienda_id)
    await _crea_stazione("S99005", azienda_id)
    await _crea_localita("TEST_LOC_FIO", "S99001", azienda_id)
    corsa_id = await _crea_corsa("TEST_002", "S99005", "S99002", (8, 0), (9, 0), azienda_id)

    vuoto_testa = BloccoMaterialeVuoto(
        codice_origine="S99001",
        codice_destinazione="S99005",
        ora_partenza=time(7, 25),
        ora_arrivo=time(7, 55),
        motivo="testa",
    )

    async with session_scope() as session:
        corsa = (
            await session.execute(select(CorsaCommerciale).where(CorsaCommerciale.id == corsa_id))
        ).scalar_one()
        giro = _giro_assegnato_singolo(
            localita_codice="TEST_LOC_FIO",
            corse_orm=(corsa,),
            vuoto_testa=vuoto_testa,
        )
        ids = await persisti_giri(
            [GiroDaPersistere(numero_turno="G-FIO-002", giro=giro)],
            session,
            programma_id=programma_test_id,
            azienda_id=azienda_id,
        )
        gm_id = ids[0]

    async with session_scope() as session:
        # CorsaMaterialeVuoto creato
        cmvs = (
            (
                await session.execute(
                    select(CorsaMaterialeVuoto).where(
                        CorsaMaterialeVuoto.giro_materiale_id == gm_id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(cmvs) == 1
        assert cmvs[0].numero_treno_vuoto == "V-G-FIO-002-000"
        assert cmvs[0].codice_origine == "S99001"
        assert cmvs[0].codice_destinazione == "S99005"
        assert cmvs[0].origine == "generato_da_giro_materiale"

        # GiroBlocco materiale_vuoto in seq=0
        blocchi = (
            (
                await session.execute(
                    select(GiroBlocco)
                    .join(GiroGiornata, GiroBlocco.giro_giornata_id == GiroGiornata.id)
                    .where(GiroGiornata.giro_materiale_id == gm_id)
                    .order_by(GiroBlocco.seq)
                )
            )
            .scalars()
            .all()
        )
        assert len(blocchi) == 2  # vuoto + corsa
        assert blocchi[0].tipo_blocco == "materiale_vuoto"
        assert blocchi[0].corsa_materiale_vuoto_id == cmvs[0].id
        assert blocchi[0].metadata_json["motivo"] == "testa"
        assert blocchi[1].tipo_blocco == "corsa_commerciale"


async def test_vuoto_coda_genera_corsa_materiale_vuoto_e_blocco(
    azienda_id: int, programma_test_id: int
) -> None:
    await _crea_stazione("S99001", azienda_id)
    await _crea_stazione("S99002", azienda_id)
    await _crea_localita("TEST_LOC_FIO", "S99001", azienda_id)
    corsa_id = await _crea_corsa("TEST_003", "S99001", "S99002", (8, 0), (9, 0), azienda_id)

    vuoto_coda = BloccoMaterialeVuoto(
        codice_origine="S99002",
        codice_destinazione="S99001",
        ora_partenza=time(9, 5),
        ora_arrivo=time(9, 35),
        motivo="coda",
    )

    async with session_scope() as session:
        corsa = (
            await session.execute(select(CorsaCommerciale).where(CorsaCommerciale.id == corsa_id))
        ).scalar_one()
        giro = _giro_assegnato_singolo(
            localita_codice="TEST_LOC_FIO",
            corse_orm=(corsa,),
            vuoto_coda=vuoto_coda,
        )
        ids = await persisti_giri(
            [GiroDaPersistere(numero_turno="G-FIO-003", giro=giro)],
            session,
            programma_id=programma_test_id,
            azienda_id=azienda_id,
        )
        gm_id = ids[0]

    async with session_scope() as session:
        blocchi = (
            (
                await session.execute(
                    select(GiroBlocco)
                    .join(GiroGiornata, GiroBlocco.giro_giornata_id == GiroGiornata.id)
                    .where(GiroGiornata.giro_materiale_id == gm_id)
                    .order_by(GiroBlocco.seq)
                )
            )
            .scalars()
            .all()
        )
        assert len(blocchi) == 2  # corsa + vuoto coda
        assert blocchi[0].tipo_blocco == "corsa_commerciale"
        assert blocchi[1].tipo_blocco == "materiale_vuoto"
        assert blocchi[1].metadata_json["motivo"] == "coda"


# =====================================================================
# Eventi composizione
# =====================================================================


async def test_evento_aggancio_3_a_6_inserito_tra_blocchi(
    azienda_id: int, programma_test_id: int
) -> None:
    """3 → 6 pezzi: blocco 'aggancio' tra le due corse, is_validato_utente=False."""
    await _crea_stazione("S99001", azienda_id)
    await _crea_stazione("S99002", azienda_id)
    await _crea_stazione("S99003", azienda_id)
    await _crea_localita("TEST_LOC_FIO", "S99001", azienda_id)
    c1 = await _crea_corsa("TEST_M1", "S99001", "S99002", (8, 0), (9, 0), azienda_id)
    c2 = await _crea_corsa("TEST_M2", "S99002", "S99003", (9, 30), (10, 30), azienda_id)

    async with session_scope() as session:
        corse = (
            (
                await session.execute(
                    select(CorsaCommerciale)
                    .where(CorsaCommerciale.id.in_([c1, c2]))
                    .order_by(CorsaCommerciale.id)
                )
            )
            .scalars()
            .all()
        )
        giro = _giro_assegnato_singolo(
            localita_codice="TEST_LOC_FIO",
            corse_orm=tuple(corse),
            pezzi_per_corsa=(3, 6),
        )
        ids = await persisti_giri(
            [GiroDaPersistere(numero_turno="G-FIO-004", giro=giro)],
            session,
            programma_id=programma_test_id,
            azienda_id=azienda_id,
        )
        gm_id = ids[0]

    async with session_scope() as session:
        blocchi = (
            (
                await session.execute(
                    select(GiroBlocco)
                    .join(GiroGiornata, GiroBlocco.giro_giornata_id == GiroGiornata.id)
                    .where(GiroGiornata.giro_materiale_id == gm_id)
                    .order_by(GiroBlocco.seq)
                )
            )
            .scalars()
            .all()
        )
        # Sequenza attesa: corsa1, aggancio, corsa2
        assert len(blocchi) == 3
        assert blocchi[0].tipo_blocco == "corsa_commerciale"
        assert blocchi[1].tipo_blocco == "aggancio"
        assert blocchi[1].is_validato_utente is False
        assert blocchi[1].metadata_json["pezzi_delta"] == 3
        assert blocchi[1].metadata_json["stazione_proposta_originale"] == "S99002"
        assert blocchi[1].metadata_json["stazione_finale"] == "S99002"
        assert blocchi[2].tipo_blocco == "corsa_commerciale"


async def test_sequenza_3_6_3_genera_aggancio_e_sgancio(
    azienda_id: int, programma_test_id: int
) -> None:
    await _crea_stazione("S99001", azienda_id)
    await _crea_stazione("S99002", azienda_id)
    await _crea_stazione("S99003", azienda_id)
    await _crea_stazione("S99004", azienda_id)
    await _crea_localita("TEST_LOC_FIO", "S99001", azienda_id)
    c1 = await _crea_corsa("TEST_S1", "S99001", "S99002", (6, 0), (7, 0), azienda_id)
    c2 = await _crea_corsa("TEST_S2", "S99002", "S99003", (8, 0), (9, 0), azienda_id)
    c3 = await _crea_corsa("TEST_S3", "S99003", "S99004", (10, 0), (11, 0), azienda_id)

    async with session_scope() as session:
        corse = (
            (
                await session.execute(
                    select(CorsaCommerciale)
                    .where(CorsaCommerciale.id.in_([c1, c2, c3]))
                    .order_by(CorsaCommerciale.id)
                )
            )
            .scalars()
            .all()
        )
        giro = _giro_assegnato_singolo(
            localita_codice="TEST_LOC_FIO",
            corse_orm=tuple(corse),
            pezzi_per_corsa=(3, 6, 3),
        )
        ids = await persisti_giri(
            [GiroDaPersistere(numero_turno="G-FIO-005", giro=giro)],
            session,
            programma_id=programma_test_id,
            azienda_id=azienda_id,
        )
        gm_id = ids[0]

    async with session_scope() as session:
        blocchi = (
            (
                await session.execute(
                    select(GiroBlocco)
                    .join(GiroGiornata, GiroBlocco.giro_giornata_id == GiroGiornata.id)
                    .where(GiroGiornata.giro_materiale_id == gm_id)
                    .order_by(GiroBlocco.seq)
                )
            )
            .scalars()
            .all()
        )
        # Sequenza attesa: corsa1, aggancio, corsa2, sgancio, corsa3
        assert [b.tipo_blocco for b in blocchi] == [
            "corsa_commerciale",
            "aggancio",
            "corsa_commerciale",
            "sgancio",
            "corsa_commerciale",
        ]
        assert blocchi[1].metadata_json["pezzi_delta"] == 3
        assert blocchi[3].metadata_json["pezzi_delta"] == -3


# =====================================================================
# Multi-giornata
# =====================================================================


async def test_due_giornate_due_GiroGiornata_con_dates_apply(
    azienda_id: int, programma_test_id: int
) -> None:
    await _crea_stazione("S99001", azienda_id)
    await _crea_stazione("S99002", azienda_id)
    await _crea_localita("TEST_LOC_FIO", "S99001", azienda_id)
    c1 = await _crea_corsa("TEST_G1", "S99001", "S99002", (20, 0), (21, 0), azienda_id)
    c2 = await _crea_corsa("TEST_G2", "S99002", "S99001", (6, 0), (7, 0), azienda_id)

    async with session_scope() as session:
        corse_orm = (
            (
                await session.execute(
                    select(CorsaCommerciale)
                    .where(CorsaCommerciale.id.in_([c1, c2]))
                    .order_by(CorsaCommerciale.id)
                )
            )
            .scalars()
            .all()
        )
        c1_orm, c2_orm = corse_orm[0], corse_orm[1]

        cat1 = CatenaPosizionata(
            localita_codice="TEST_LOC_FIO",
            stazione_collegata="S99001",
            vuoto_testa=None,
            catena=Catena(corse=(c1_orm,)),
            vuoto_coda=None,
            chiusa_a_localita=False,
        )
        cat2 = CatenaPosizionata(
            localita_codice="TEST_LOC_FIO",
            stazione_collegata="S99001",
            vuoto_testa=None,
            catena=Catena(corse=(c2_orm,)),
            vuoto_coda=None,
            chiusa_a_localita=True,
        )
        gg1 = GiornataAssegnata(
            data=date(2026, 4, 27),
            catena_posizionata=cat1,
            blocchi_assegnati=(
                BloccoAssegnato(
                    corsa=c1_orm,
                    assegnazione=AssegnazioneRisolta(
                        regola_id=1,
                        composizione=(ComposizioneItem(MATERIALE_TIPO, 3),),
                    ),
                ),
            ),
            materiali_tipo_giornata=frozenset({MATERIALE_TIPO}),
        )
        gg2 = GiornataAssegnata(
            data=date(2026, 4, 28),
            catena_posizionata=cat2,
            blocchi_assegnati=(
                BloccoAssegnato(
                    corsa=c2_orm,
                    assegnazione=AssegnazioneRisolta(
                        regola_id=1,
                        composizione=(ComposizioneItem(MATERIALE_TIPO, 3),),
                    ),
                ),
            ),
            materiali_tipo_giornata=frozenset({MATERIALE_TIPO}),
        )
        giro = GiroAssegnato(
            localita_codice="TEST_LOC_FIO",
            giornate=(gg1, gg2),
            chiuso=True,
            motivo_chiusura="naturale",
        )
        ids = await persisti_giri(
            [GiroDaPersistere(numero_turno="G-FIO-006", giro=giro)],
            session,
            programma_id=programma_test_id,
            azienda_id=azienda_id,
        )
        gm_id = ids[0]

    async with session_scope() as session:
        gm = (
            await session.execute(select(GiroMateriale).where(GiroMateriale.id == gm_id))
        ).scalar_one()
        assert gm.numero_giornate == 2

        giornate = (
            (
                await session.execute(
                    select(GiroGiornata)
                    .where(GiroGiornata.giro_materiale_id == gm_id)
                    .order_by(GiroGiornata.numero_giornata)
                )
            )
            .scalars()
            .all()
        )
        assert len(giornate) == 2
        assert giornate[0].numero_giornata == 1
        assert giornate[1].numero_giornata == 2

        # Sprint 7.7 MR 3: ogni giornata ha le sue dates_apply_json
        # direttamente (no più step intermedio variante).
        assert giornate[0].dates_apply_json == ["2026-04-27"]
        assert giornate[1].dates_apply_json == ["2026-04-28"]


# =====================================================================
# Multi-giri
# =====================================================================


async def test_due_giri_due_id_in_ordine(
    azienda_id: int, programma_test_id: int
) -> None:
    await _crea_stazione("S99001", azienda_id)
    await _crea_stazione("S99002", azienda_id)
    await _crea_localita("TEST_LOC_FIO", "S99001", azienda_id)
    c1 = await _crea_corsa("TEST_X1", "S99001", "S99002", (8, 0), (9, 0), azienda_id)
    c2 = await _crea_corsa("TEST_X2", "S99002", "S99001", (10, 0), (11, 0), azienda_id)

    async with session_scope() as session:
        corse_orm = (
            (
                await session.execute(
                    select(CorsaCommerciale)
                    .where(CorsaCommerciale.id.in_([c1, c2]))
                    .order_by(CorsaCommerciale.id)
                )
            )
            .scalars()
            .all()
        )
        giro1 = _giro_assegnato_singolo(
            localita_codice="TEST_LOC_FIO",
            corse_orm=(corse_orm[0],),
        )
        giro2 = _giro_assegnato_singolo(
            localita_codice="TEST_LOC_FIO",
            corse_orm=(corse_orm[1],),
        )
        ids = await persisti_giri(
            [
                GiroDaPersistere(numero_turno="G-FIO-007", giro=giro1),
                GiroDaPersistere(numero_turno="G-FIO-008", giro=giro2),
            ],
            session,
            programma_id=programma_test_id,
            azienda_id=azienda_id,
        )
        assert len(ids) == 2
        assert ids[0] != ids[1]

    async with session_scope() as session:
        # Verifico che i numeri turno siano corretti
        rows = (
            (
                await session.execute(
                    select(GiroMateriale.numero_turno)
                    .where(GiroMateriale.id.in_(ids))
                    .order_by(GiroMateriale.id)
                )
            )
            .scalars()
            .all()
        )
        assert sorted(rows) == ["G-FIO-007", "G-FIO-008"]


async def test_giro_senza_blocchi_assegnati_tipo_materiale_misto(
    azienda_id: int, programma_test_id: int
) -> None:
    """Edge case: giro tutto in corse_residue → tipo_materiale='MISTO' placeholder."""
    await _crea_stazione("S99001", azienda_id)
    await _crea_localita("TEST_LOC_FIO", "S99001", azienda_id)

    giornata_vuota = GiornataAssegnata(
        data=date(2026, 4, 27),
        catena_posizionata=CatenaPosizionata(
            localita_codice="TEST_LOC_FIO",
            stazione_collegata="S99001",
            vuoto_testa=None,
            catena=Catena(corse=()),
            vuoto_coda=None,
            chiusa_a_localita=False,
        ),
        blocchi_assegnati=(),
    )
    giro = GiroAssegnato(
        localita_codice="TEST_LOC_FIO",
        giornate=(giornata_vuota,),
        chiuso=False,
        motivo_chiusura="non_chiuso",
    )
    async with session_scope() as session:
        ids = await persisti_giri(
            [GiroDaPersistere(numero_turno="G-FIO-009", giro=giro)],
            session,
            programma_id=programma_test_id,
            azienda_id=azienda_id,
        )
        gm_id = ids[0]

    async with session_scope() as session:
        gm = (
            await session.execute(select(GiroMateriale).where(GiroMateriale.id == gm_id))
        ).scalar_one()
        assert gm.tipo_materiale == "MISTO"
        assert gm.materiale_tipo_codice is None


# =====================================================================
# Type assertion (per mypy strict + leggibilità)
# =====================================================================


async def test_persister_version_costante() -> None:
    from colazione.domain.builder_giro.persister import PERSISTER_VERSION

    # Sprint 7.7 MR 3: bumped da "4.4.5a" a "7.7.3" col refactor varianti.
    assert PERSISTER_VERSION == "7.7.3"


async def test_giro_da_persistere_dataclass_smoke() -> None:
    """Smoke: GiroDaPersistere è frozen dataclass costruibile."""
    giro = GiroAssegnato(
        localita_codice="X",
        giornate=(),
        chiuso=False,
        motivo_chiusura="non_chiuso",
    )
    entry = GiroDaPersistere(numero_turno="G-X-001", giro=giro)
    assert entry.numero_turno == "G-X-001"
    assert entry.giro is giro
    assert entry.genera_rientro_sede is False  # default Sprint 5.6


# =====================================================================
# Sprint 5.6 — km_media_giornaliera + corsa rientro 9XXXX
# =====================================================================


async def _crea_programma_minimo(session: AsyncSession, azienda_id: int) -> int:
    """Helper: crea ProgrammaMateriale minimo + 1 regola (matcha tutto).
    Ritorna programma_id.
    """
    from colazione.models.programmi import (
        ProgrammaMateriale,
        ProgrammaRegolaAssegnazione,
    )

    prog = ProgrammaMateriale(
        azienda_id=azienda_id,
        nome="TEST_persister_min",
        valido_da=date(2026, 1, 1),
        valido_a=date(2026, 12, 31),
        stato="bozza",
        n_giornate_default=1,
        fascia_oraria_tolerance_min=30,
        strict_options_json={
            "no_corse_residue": False,
            "no_overcapacity": False,
            "no_aggancio_non_validato": False,
            "no_orphan_blocks": False,
            "no_giro_appeso": False,
            "no_km_eccesso": False,
        },
    )
    session.add(prog)
    await session.flush()
    session.add(
        ProgrammaRegolaAssegnazione(
            programma_id=prog.id,
            filtri_json=[],
            composizione_json=[{"materiale_tipo_codice": MATERIALE_TIPO, "n_pezzi": 3}],
            materiale_tipo_codice=MATERIALE_TIPO,
            numero_pezzi=3,
            priorita=10,
        )
    )
    await session.flush()
    return int(prog.id)


async def test_persister_popola_km_media_giornaliera(azienda_id: int) -> None:
    """Sprint 5.6 Feature 2: km_media_giornaliera = sum(km_tratta) / numero_giornate."""
    await _crea_stazione("S99001", azienda_id)
    await _crea_stazione("S99002", azienda_id)
    await _crea_localita("TEST_LOC_FIO", "S99001", azienda_id)
    c1 = await _crea_corsa("TEST_KM_001", "S99001", "S99002", (8, 0), (9, 0), azienda_id)
    c2 = await _crea_corsa("TEST_KM_002", "S99002", "S99001", (10, 0), (11, 0), azienda_id)

    # Inietto km_tratta sulle corse direttamente nel DB
    async with session_scope() as session:
        await session.execute(
            text("UPDATE corsa_commerciale SET km_tratta = 50 WHERE id IN (:c1, :c2)"),
            {"c1": c1, "c2": c2},
        )

    async with session_scope() as session:
        c1_orm = (
            await session.execute(select(CorsaCommerciale).where(CorsaCommerciale.id == c1))
        ).scalar_one()
        c2_orm = (
            await session.execute(select(CorsaCommerciale).where(CorsaCommerciale.id == c2))
        ).scalar_one()
        prog_id = await _crea_programma_minimo(session, azienda_id)
        giro = _giro_assegnato_singolo(
            localita_codice="TEST_LOC_FIO",
            corse_orm=(c1_orm, c2_orm),
            chiusa=True,
        )
        await persisti_giri(
            [GiroDaPersistere(numero_turno="G-TST-001", giro=giro)],
            session,
            prog_id,
            azienda_id,
        )
        await session.commit()

    async with session_scope() as session:
        gm = (
            await session.execute(
                select(GiroMateriale).where(GiroMateriale.numero_turno == "G-TST-001")
            )
        ).scalar_one()
        # Totale 50+50 = 100 km su 1 giornata
        assert gm.km_media_giornaliera == 100.0


async def test_persister_popola_km_media_annua(azienda_id: int) -> None:
    """Sprint 5.6 R3: km_media_annua = km_giornaliera * n_giorni_validi
    nel periodo del programma. Calcolato intersecando `valido_in_date_json`
    della prima corsa di ogni giornata con [periodo_valido_da, ..._a]."""
    await _crea_stazione("S99001", azienda_id)
    await _crea_stazione("S99002", azienda_id)
    await _crea_localita("TEST_LOC_FIO", "S99001", azienda_id)
    c1 = await _crea_corsa("TEST_AN_001", "S99001", "S99002", (8, 0), (9, 0), azienda_id)

    # Inietto km_tratta + valido_in_date_json (5 lunedì)
    async with session_scope() as session:
        await session.execute(
            text(
                "UPDATE corsa_commerciale SET km_tratta = 100, "
                "valido_in_date_json = '[\"2026-01-05\",\"2026-01-12\",\"2026-01-19\","
                "\"2026-01-26\",\"2026-02-02\"]'::jsonb "
                "WHERE id = :c1"
            ),
            {"c1": c1},
        )

    async with session_scope() as session:
        c1_orm = (
            await session.execute(select(CorsaCommerciale).where(CorsaCommerciale.id == c1))
        ).scalar_one()
        prog_id = await _crea_programma_minimo(session, azienda_id)
        giro = _giro_assegnato_singolo(
            localita_codice="TEST_LOC_FIO",
            corse_orm=(c1_orm,),
            chiusa=True,
        )
        await persisti_giri(
            [GiroDaPersistere(numero_turno="G-TST-AN", giro=giro)],
            session,
            prog_id,
            azienda_id,
            periodo_valido_da=date(2026, 1, 1),
            periodo_valido_a=date(2026, 12, 31),
        )
        await session.commit()

    async with session_scope() as session:
        gm = (
            await session.execute(
                select(GiroMateriale).where(GiroMateriale.numero_turno == "G-TST-AN")
            )
        ).scalar_one()
        # 100 km/giornata × 5 giorni applicabili = 500 km/anno
        assert gm.km_media_annua == 500.0


async def test_persister_corsa_rientro_9xxxx_se_genera_rientro_sede(azienda_id: int) -> None:
    """Sprint 5.6 Feature 4: con genera_rientro_sede=True e ultima dest !=
    stazione_collegata sede, viene creato un blocco materiale_vuoto 9NNNN."""
    await _crea_stazione("S99001", azienda_id)  # sede
    await _crea_stazione("S99002", azienda_id)  # whitelist
    await _crea_localita("TEST_LOC_FIO", "S99001", azienda_id)
    c1 = await _crea_corsa("TEST_R9_001", "S99002", "S99002", (8, 0), (9, 0), azienda_id)

    async with session_scope() as session:
        c1_orm = (
            await session.execute(select(CorsaCommerciale).where(CorsaCommerciale.id == c1))
        ).scalar_one()
        prog_id = await _crea_programma_minimo(session, azienda_id)
        giro = _giro_assegnato_singolo(
            localita_codice="TEST_LOC_FIO",
            corse_orm=(c1_orm,),
            chiusa=True,
        )
        # Forzo motivo='naturale' (Sprint 5.6: chiusura ideale completa)
        giro = dataclasses.replace(giro, motivo_chiusura="naturale")
        await persisti_giri(
            [
                GiroDaPersistere(
                    numero_turno="G-TST-R9",
                    giro=giro,
                    genera_rientro_sede=True,
                    # Sprint 7.7 MR 1 (Fix C): la whitelist DEVE includere
                    # l'ultima destinazione del giro per permettere il
                    # rientro intelligente. Senza, il vuoto non si genera
                    # (no vuoti lunghi). S99002 è l'ultima dest del giro
                    # in test, S99001 la stazione_sede.
                    whitelist_sede=frozenset({"S99002"}),
                )
            ],
            session,
            prog_id,
            azienda_id,
        )
        await session.commit()

    async with session_scope() as session:
        # Verifica creato un CorsaMaterialeVuoto con prefix '9'
        cmv = (
            await session.execute(
                text(
                    "SELECT numero_treno_vuoto, codice_origine, codice_destinazione "
                    "FROM corsa_materiale_vuoto "
                    "WHERE numero_treno_vuoto ~ '^9[0-9]{4}$' "
                    "ORDER BY id DESC LIMIT 1"
                )
            )
        ).first()
        assert cmv is not None
        assert cmv.numero_treno_vuoto.startswith("9")
        assert len(cmv.numero_treno_vuoto) == 5
        assert cmv.codice_origine == "S99002"  # ultima dest
        assert cmv.codice_destinazione == "S99001"  # stazione_collegata sede


# =====================================================================
# Sprint 7.5 — dates_apply post-cluster (refactor bug 5 MR 3)
# =====================================================================


async def test_dates_apply_post_cluster_persistito_in_validita_dates_apply_json(
    azienda_id: int, programma_test_id: int
) -> None:
    """Sprint 7.5 MR 3: se `GiornataAssegnata.dates_apply` è popolato
    (output del clustering A1), il persister salva `validita_dates_apply_json`
    con quelle date REALI invece dell'intersezione menzogna sulle
    `valido_in_date_json` delle corse.
    """
    await _crea_stazione("S99100", azienda_id)
    await _crea_stazione("S99101", azienda_id)
    await _crea_localita("TEST_LOC_DA", "S99100", azienda_id)
    corsa_id = await _crea_corsa("TEST_DA", "S99100", "S99101", (8, 0), (9, 0), azienda_id)

    d1 = date(2026, 4, 27)  # lunedì 1
    d2 = date(2026, 5, 4)  # lunedì 2
    d3 = date(2026, 5, 11)  # lunedì 3

    async with session_scope() as session:
        corsa = (
            await session.execute(select(CorsaCommerciale).where(CorsaCommerciale.id == corsa_id))
        ).scalar_one()

        # Costruisci GiornataAssegnata simulando output post-cluster:
        # tre date "gemelle" che condividono lo stesso pattern A1.
        cat_pos = CatenaPosizionata(
            localita_codice="TEST_LOC_DA",
            stazione_collegata="S99100",
            vuoto_testa=None,
            catena=Catena(corse=(corsa,)),
            vuoto_coda=None,
            chiusa_a_localita=True,
        )
        giornata = GiornataAssegnata(
            data=d1,
            catena_posizionata=cat_pos,
            blocchi_assegnati=(
                BloccoAssegnato(
                    corsa=corsa,
                    assegnazione=AssegnazioneRisolta(
                        regola_id=1,
                        composizione=(ComposizioneItem(MATERIALE_TIPO, 3),),
                    ),
                ),
            ),
            eventi_composizione=(),
            materiali_tipo_giornata=frozenset({MATERIALE_TIPO}),
            dates_apply=(d1, d2, d3),
        )
        giro = GiroAssegnato(
            localita_codice="TEST_LOC_DA",
            giornate=(giornata,),
            chiuso=True,
            motivo_chiusura="naturale",
        )

        ids = await persisti_giri(
            [GiroDaPersistere(numero_turno="G-DA-001", giro=giro)],
            session,
            programma_id=programma_test_id,
            azienda_id=azienda_id,
        )
        gm_id = ids[0]

    async with session_scope() as session:
        gg = (
            await session.execute(
                select(GiroGiornata).where(GiroGiornata.giro_materiale_id == gm_id)
            )
        ).scalar_one()
        assert gg.dates_apply_json == [
            "2026-04-27",
            "2026-05-04",
            "2026-05-11",
        ]


async def test_dates_apply_vuoto_pre_cluster_fallback_a_data_giorno(
    azienda_id: int, programma_test_id: int
) -> None:
    """Sprint 7.5 MR 3: senza clustering (`dates_apply==()`), il
    persister salva `[giornata.data]` come fallback. Comportamento
    legacy preservato per test diretti del persister.
    """
    await _crea_stazione("S99110", azienda_id)
    await _crea_stazione("S99111", azienda_id)
    await _crea_localita("TEST_LOC_DB", "S99110", azienda_id)
    corsa_id = await _crea_corsa("TEST_DB", "S99110", "S99111", (8, 0), (9, 0), azienda_id)

    async with session_scope() as session:
        corsa = (
            await session.execute(select(CorsaCommerciale).where(CorsaCommerciale.id == corsa_id))
        ).scalar_one()
        # _giro_assegnato_singolo NON popola dates_apply → resta `()`
        giro = _giro_assegnato_singolo(
            localita_codice="TEST_LOC_DB",
            corse_orm=(corsa,),
            data_giorno=date(2026, 6, 1),
        )
        ids = await persisti_giri(
            [GiroDaPersistere(numero_turno="G-DB-001", giro=giro)],
            session,
            programma_id=programma_test_id,
            azienda_id=azienda_id,
        )
        gm_id = ids[0]

    async with session_scope() as session:
        gg = (
            await session.execute(
                select(GiroGiornata).where(GiroGiornata.giro_materiale_id == gm_id)
            )
        ).scalar_one()
        assert gg.dates_apply_json == ["2026-06-01"]
