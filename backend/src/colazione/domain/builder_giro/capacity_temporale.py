"""Sprint 7.9 MR β2-5 — capacity check istante-per-istante sui thread.

Estende ``capacity_routing.py`` (entry 121) da check aggregato per
cluster a check temporale sui ``MaterialeThread`` proiettati. Per
ogni materiale, calcola il numero MAX di pezzi simultaneamente in
uso e confronta con la dotazione azienda. Se supera, emette un
warning specifico con timestamp e count.

Versione MVP: granularità per **giorno** (= conta thread distinti
attivi in una data, ovvero che hanno almeno un evento commerciale o
vuoto in quella data). La granularità minuto-per-minuto è scope
futuro (= MR β2-5 v2).

Algoritmo:

1. Carica tutti i thread del programma + i loro eventi.
2. Per ogni evento "in uso" (corsa_singolo / corsa_doppia_pos1 /
   corsa_doppia_pos2 / corsa_tripla_pos* / vuoto_solo):
   - Estrae `(data_giorno, materiale)` se popolata. Se data NULL,
     l'evento è "non datato" → skip per ora (limitazione modello
     attuale: GiroGiornata non ha date_canonica, popolata in MR β2-4
     v2 quando bridgeremo le `dates_apply` delle varianti).
3. Per ogni `(data, materiale)`: count thread distinti.
4. Se count > dotazione[materiale] → warning specifico.

Limitazioni note:

- Granularità giornaliera: due thread che operano la stessa data ma
  in finestre orarie disgiunte (es. mattina vs pomeriggio) sono
  contati entrambi anche se fisicamente potrebbero condividere lo
  stesso pezzo. Nessun fix MVP — quello vero è β2-5 v2.
- Eventi senza `data_giorno`: skipped, nessun warning generato.
  Il fix richiede popolare `data_giorno` su `MaterialeThreadEvento`
  bridgeando `GiroGiornata.numero_giornata` + `programma.valido_da`.

Il modulo è async (richiede session per query thread + dotazione).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.models.anagrafica import MaterialeThread, MaterialeThreadEvento

# Tipi di evento che indicano "pezzo in uso" (non sosta/marker).
_TIPI_IN_USO = frozenset(
    {
        "corsa_singolo",
        "corsa_doppia_pos1",
        "corsa_doppia_pos2",
        "corsa_tripla_pos1",
        "corsa_tripla_pos2",
        "corsa_tripla_pos3",
        "corsa_multipla_pos1",
        "corsa_multipla_pos2",
        "corsa_multipla_pos3",
        "corsa_multipla_pos4",
        "vuoto_solo",
        "uscita_deposito",
        "rientro_deposito",
    }
)


async def verifica_capacity_temporale(
    session: AsyncSession,
    *,
    programma_id: int,
    dotazione: dict[str, int | None],
) -> list[str]:
    """Verifica capacity istante-per-istante (MVP: per giorno) sui
    thread di TUTTA l'azienda.

    Args:
        session: AsyncSession SQLAlchemy.
        programma_id: id programma corrente (usato per dedurre
            l'azienda — il check guarda tutti i programmi della
            stessa azienda).
        dotazione: mappa ``materiale_codice → pezzi_disponibili``.
            ``None`` = capacity illimitata. Materiali assenti = check
            disabilitato.

    Returns:
        Lista di warning testuali per ogni `(data, materiale)` che
        sfora la dotazione. Vuota se tutto ok.

    Sprint 7.9 MR β2-5 fix (post smoke 2026-05-04): il check è
    AZIENDA-level, non programma-level. Bug pre-fix: il filtro
    `programma_id` ignorava i thread di altri programmi della stessa
    azienda — la dotazione è azienda-level, quindi il check scoped
    sul singolo programma sotto-stimava il peak. Esempio: programma
    A genera 8 thread ETR421 + programma B genera 12 thread ETR421
    sullo stesso giorno = 20 thread totali; con dotazione=16 deve
    scattare warning, ma il vecchio check vedeva solo 8 (per A) o
    12 (per B) singolarmente.
    """
    # Trova azienda_id dal programma corrente
    from colazione.models.programmi import ProgrammaMateriale

    azienda_id = (
        await session.execute(
            select(ProgrammaMateriale.azienda_id).where(
                ProgrammaMateriale.id == programma_id
            )
        )
    ).scalar_one_or_none()
    if azienda_id is None:
        return []

    # Carica tutti gli eventi "in uso" dei thread di TUTTI i programmi
    # dell'azienda (la dotazione è azienda-level, vedi
    # `materiale_dotazione_azienda`).
    stmt = (
        select(
            MaterialeThreadEvento.thread_id,
            MaterialeThreadEvento.tipo,
            MaterialeThreadEvento.data_giorno,
            MaterialeThread.tipo_materiale_codice,
        )
        .join(
            MaterialeThread,
            MaterialeThread.id == MaterialeThreadEvento.thread_id,
        )
        .where(MaterialeThread.azienda_id == azienda_id)
    )
    rows = (await session.execute(stmt)).all()

    # (data, materiale) → set thread_id distinti
    contatori: dict[tuple[date, str], set[int]] = defaultdict(set)
    for row in rows:
        if row.tipo not in _TIPI_IN_USO:
            continue
        if row.data_giorno is None:
            continue
        contatori[(row.data_giorno, row.tipo_materiale_codice)].add(
            row.thread_id
        )

    warnings: list[str] = []
    for (data_giorno, materiale), thread_ids in sorted(contatori.items()):
        count = len(thread_ids)
        cap = dotazione.get(materiale)
        if cap is None:
            continue  # capacity illimitata
        if count > cap:
            warnings.append(
                f"CAPACITY {materiale}: {count} pezzi simultanei in "
                f"data {data_giorno.isoformat()} "
                f"(dotazione azienda = {cap}). "
                f"Differenza {count - cap}."
            )

    return warnings


__all__ = ["verifica_capacity_temporale"]
