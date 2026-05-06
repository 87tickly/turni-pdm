"""Detection impatto variazioni PdE su giri/turni PdC esistenti.

Sub-MR 5.bis-impact (Sprint 8.0 follow-up, entry 179). Date le corse
coinvolte da una variazione (UPDATE_ORARIO / RIMUOVI_DATE_VALIDITA /
CANCELLAZIONE), trova i ``programma_materiale`` che hanno giri o
turni PdC che le referenziano. Counter aggregati per UI alert.

**Note**:

- Le INTEGRAZIONI non producono impatto: aggiungono corse nuove che
  nessun blocco preesistente referenzia. Il caller passa
  ``corse_ids=set()`` → ritorno ``[]``.
- Il legame turno→programma passa via ``generation_metadata_json
  ['giro_materiale_id']`` (cast JSONB → BigInteger). Convenzione
  introdotta dal sub-MR 2.bis-a (entry 172).
- ``n_assegnazioni_impattate`` è approssimato: contiamo le
  ``assegnazione_giornata`` su giornate che hanno ALMENO un blocco
  impattato. Una giornata può avere molti blocchi e una sola
  assegnazione, quindi è un upper bound utile per UI ma non
  perfetto per audit fine.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import BigInteger, cast, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.models.giri import GiroBlocco, GiroGiornata, GiroMateriale, GiroVariante
from colazione.models.personale import AssegnazioneGiornata
from colazione.models.programmi import ProgrammaMateriale
from colazione.models.turni_pdc import TurnoPdc, TurnoPdcBlocco, TurnoPdcGiornata
from colazione.schemas.programmi import ProgrammaImpattoRead


async def calcola_impatto_su_programmi(
    session: AsyncSession,
    *,
    corse_ids: Iterable[int],
    azienda_id: int,
) -> list[ProgrammaImpattoRead]:
    """Calcola l'impatto di una variazione su programmi attivi.

    Strategy: 3 query (giri / turni / assegnazioni), poi join in memoria
    via ``programma_id``. Più semplice di una query JOIN unica + più
    flessibile su counter eterogenei.
    """
    corse_set = set(corse_ids)
    if not corse_set:
        return []

    # =========================================================
    # 1) Giri impattati per programma
    # =========================================================
    giri_stmt = (
        select(
            GiroMateriale.programma_id.label("programma_id"),
            func.count(distinct(GiroMateriale.id)).label("n_giri"),
        )
        .join(GiroGiornata, GiroGiornata.giro_materiale_id == GiroMateriale.id)
        .join(GiroVariante, GiroVariante.giro_giornata_id == GiroGiornata.id)
        .join(GiroBlocco, GiroBlocco.giro_variante_id == GiroVariante.id)
        .where(
            GiroMateriale.azienda_id == azienda_id,
            GiroBlocco.corsa_commerciale_id.in_(corse_set),
        )
        .group_by(GiroMateriale.programma_id)
    )
    giri_per_programma: dict[int, int] = {}
    for row in (await session.execute(giri_stmt)).all():
        giri_per_programma[int(row.programma_id)] = int(row.n_giri)

    # =========================================================
    # 2) Turni PdC impattati per programma
    # =========================================================
    # Il turno_pdc non ha programma_id diretto: la relazione passa via
    # generation_metadata_json["giro_materiale_id"] (cast JSONB → int)
    # → giro_materiale.programma_id. Pattern entry 168 / 172.
    turni_stmt = (
        select(
            GiroMateriale.programma_id.label("programma_id"),
            func.count(distinct(TurnoPdc.id)).label("n_turni"),
        )
        .select_from(TurnoPdcBlocco)
        .join(
            TurnoPdcGiornata,
            TurnoPdcGiornata.id == TurnoPdcBlocco.turno_pdc_giornata_id,
        )
        .join(TurnoPdc, TurnoPdc.id == TurnoPdcGiornata.turno_pdc_id)
        .join(
            GiroMateriale,
            GiroMateriale.id
            == cast(
                TurnoPdc.generation_metadata_json["giro_materiale_id"].astext,
                BigInteger,
            ),
        )
        .where(
            TurnoPdc.azienda_id == azienda_id,
            TurnoPdcBlocco.corsa_commerciale_id.in_(corse_set),
        )
        .group_by(GiroMateriale.programma_id)
    )
    turni_per_programma: dict[int, int] = {}
    for row in (await session.execute(turni_stmt)).all():
        turni_per_programma[int(row.programma_id)] = int(row.n_turni)

    # =========================================================
    # 3) Assegnazioni PdC impattate per programma
    # =========================================================
    # Per ogni giornata che ha ≥ 1 blocco impattato, contiamo le
    # assegnazione_giornata.
    assegnazioni_stmt = (
        select(
            GiroMateriale.programma_id.label("programma_id"),
            func.count(distinct(AssegnazioneGiornata.id)).label("n_assegn"),
        )
        .select_from(AssegnazioneGiornata)
        .join(
            TurnoPdcGiornata,
            TurnoPdcGiornata.id == AssegnazioneGiornata.turno_pdc_giornata_id,
        )
        .join(TurnoPdc, TurnoPdc.id == TurnoPdcGiornata.turno_pdc_id)
        .join(
            GiroMateriale,
            GiroMateriale.id
            == cast(
                TurnoPdc.generation_metadata_json["giro_materiale_id"].astext,
                BigInteger,
            ),
        )
        .join(
            TurnoPdcBlocco,
            TurnoPdcBlocco.turno_pdc_giornata_id == TurnoPdcGiornata.id,
        )
        .where(
            TurnoPdc.azienda_id == azienda_id,
            TurnoPdcBlocco.corsa_commerciale_id.in_(corse_set),
        )
        .group_by(GiroMateriale.programma_id)
    )
    assegnazioni_per_programma: dict[int, int] = {}
    for row in (await session.execute(assegnazioni_stmt)).all():
        assegnazioni_per_programma[int(row.programma_id)] = int(row.n_assegn)

    # =========================================================
    # 4) Programmi (intestazione) → fetch nomi/date
    # =========================================================
    programma_ids = (
        set(giri_per_programma)
        | set(turni_per_programma)
        | set(assegnazioni_per_programma)
    )
    if not programma_ids:
        return []

    progr_stmt = select(
        ProgrammaMateriale.id,
        ProgrammaMateriale.nome,
        ProgrammaMateriale.valido_da,
        ProgrammaMateriale.valido_a,
    ).where(
        ProgrammaMateriale.id.in_(programma_ids),
        ProgrammaMateriale.azienda_id == azienda_id,
    )
    programma_rows = (await session.execute(progr_stmt)).all()

    impatti: list[ProgrammaImpattoRead] = []
    for r in programma_rows:
        impatti.append(
            ProgrammaImpattoRead(
                programma_id=int(r.id),
                nome=str(r.nome),
                valido_da=r.valido_da,
                valido_a=r.valido_a,
                n_giri_impattati=giri_per_programma.get(int(r.id), 0),
                n_turni_pdc_impattati=turni_per_programma.get(int(r.id), 0),
                n_assegnazioni_impattate=assegnazioni_per_programma.get(
                    int(r.id), 0
                ),
            )
        )

    # Ordine deterministico: prima programmi più impattati (giri DESC),
    # poi per nome ASC.
    impatti.sort(
        key=lambda p: (-p.n_giri_impattati, -p.n_turni_pdc_impattati, p.nome)
    )
    return impatti


def estrai_corse_ids_da_risultato_pianificazione(risultato: object) -> set[int]:
    """Estrae l'insieme di ``corsa_commerciale.id`` coinvolti in una
    ``RisultatoPianificazione`` (modulo ``domain.variazioni_pde``).

    Le INTEGRAZIONI non sono incluse: ``OpInsert`` non ha ``corsa_id``
    (la corsa nuova si crea, non c'è una preesistente da impattare).

    Wrapper come ``object`` per evitare circular import con
    ``domain/variazioni_pde.py`` che importa da ``schemas/programmi.py``
    già. Il caller passa il ``RisultatoPianificazione`` concreto.
    """
    coinvolte: set[int] = set()
    update_orari = getattr(risultato, "update_orari", []) or []
    for op in update_orari:
        cid = getattr(op, "corsa_id", None)
        if isinstance(cid, int):
            coinvolte.add(cid)
    update_valido_in_date = getattr(risultato, "update_valido_in_date", []) or []
    for op in update_valido_in_date:
        cid = getattr(op, "corsa_id", None)
        if isinstance(cid, int):
            coinvolte.add(cid)
    cancellazioni = getattr(risultato, "cancellazioni", []) or []
    for op in cancellazioni:
        cid = getattr(op, "corsa_id", None)
        if isinstance(cid, int):
            coinvolte.add(cid)
    return coinvolte
