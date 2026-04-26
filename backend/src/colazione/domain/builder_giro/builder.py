"""Builder orchestrator + loader Sprint 4.4.5b.

Funzione end-to-end ``genera_giri()`` che orchestra l'intera pipeline
del sub-sprint 4.4 partendo dall'input DB e arrivando ai giri persistiti:

1. **Loader**: carica `ProgrammaMateriale` + regole + `LocalitaManutenzione`
   + `CorsaCommerciale` valide nella finestra dal DB.
2. **Pipeline pure** (4.4.1→4.4.4):
   - Per ogni data: filtra corse, ``costruisci_catene()``, per ogni
     catena ``posiziona_su_localita()``.
   - ``costruisci_giri_multigiornata()`` (cross-notte).
   - ``assegna_e_rileva_eventi()``.
3. **Strict mode check**: applica i flag dello ``strict_options_json``
   del programma; se uno è violato, alza ``StrictModeViolation``.
4. **Numero turno**: genera ``f"G-{LOC_BREVE}-{SEQ:03d}"``.
5. **Persister** (4.4.5a): scrive ORM, commit transazione.

Convenzione numerazione (decisione utente, ARTURO independent):

- ``G`` prefisso = "Giro materiale"
- ``LOC_BREVE`` da `LocalitaManutenzione.codice_breve` (migration 0006)
- ``SEQ:03d`` = sequenza progressiva 1-based per (programma, località)

Limiti del sub-sprint 4.4.5b:

- **Una località per chiamata**: l'endpoint accetta ``localita_codice``
  obbligatorio. Per generare giri di N località il pianificatore lancia
  N chiamate. Decisione esplicita per non introdurre euristica
  geografica (località naturale di una catena) in questa fase.
- **Filtro corse per `valido_in_date_json`**: una corsa vale in una data
  ``D`` se ``D`` è nella sua lista. Corse con lista vuota sono "inerti"
  (non assegnate). Coerente con feedback utente "PdE testo Periodicità
  = verità".
- **Strict checks parziali**: implementati ``no_corse_residue`` e
  ``no_giro_non_chiuso_a_localita``. Gli altri (overcapacity, ecc.)
  sono scope futuro.

Spec:
- ``docs/PROGRAMMA-MATERIALE.md`` §6 (strict mode granulare)
- ``docs/LOGICA-COSTRUZIONE.md`` §3 (Algoritmo A end-to-end)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.domain.builder_giro.catena import costruisci_catene
from colazione.domain.builder_giro.composizione import (
    GiroAssegnato,
    assegna_e_rileva_eventi,
)
from colazione.domain.builder_giro.multi_giornata import (
    costruisci_giri_multigiornata,
)
from colazione.domain.builder_giro.persister import (
    GiroDaPersistere,
    LocalitaNonTrovataError,
    persisti_giri,
)
from colazione.domain.builder_giro.posizionamento import (
    CatenaPosizionata,
    LocalitaSenzaStazioneError,
    PosizionamentoImpossibileError,
    posiziona_su_localita,
)
from colazione.models.anagrafica import LocalitaManutenzione
from colazione.models.corse import CorsaCommerciale
from colazione.models.programmi import (
    ProgrammaMateriale,
    ProgrammaRegolaAssegnazione,
)

# =====================================================================
# Errori
# =====================================================================


class ProgrammaNonAttivoError(ValueError):
    """Il programma non è in stato ``'attivo'`` (deve essere pubblicato)."""

    def __init__(self, programma_id: int, stato: str) -> None:
        super().__init__(
            f"Programma {programma_id} è in stato {stato!r}, non 'attivo'. "
            "Pubblica il programma prima di generare giri."
        )
        self.programma_id = programma_id
        self.stato = stato


class GiriEsistentiError(RuntimeError):
    """Il programma ha già giri persistiti (rigenerazione richiede ``force=True``)."""

    def __init__(self, programma_id: int, n_esistenti: int) -> None:
        super().__init__(
            f"Programma {programma_id} ha già {n_esistenti} giro(i) persistiti. "
            "Per rigenerare passa force=True (cancella tutti i giri esistenti)."
        )
        self.programma_id = programma_id
        self.n_esistenti = n_esistenti


class ProgrammaNonTrovatoError(LookupError):
    """Programma materiale non trovato per l'azienda."""

    def __init__(self, programma_id: int, azienda_id: int) -> None:
        super().__init__(f"Programma {programma_id} non trovato per azienda_id={azienda_id}.")
        self.programma_id = programma_id
        self.azienda_id = azienda_id


class StrictModeViolation(ValueError):
    """Uno o più flag strict del programma sono violati dal builder output."""

    def __init__(self, violazioni: list[str]) -> None:
        super().__init__("Strict mode violato: " + "; ".join(violazioni))
        self.violazioni = violazioni


# =====================================================================
# Output dataclass
# =====================================================================


@dataclass(frozen=True)
class BuilderResult:
    """Risultato dell'esecuzione del builder.

    Attributi:
        giri_ids: id dei `GiroMateriale` creati.
        n_giri_creati: == ``len(giri_ids)``.
        n_corse_processate: corse incluse in almeno un giro.
        n_corse_residue: corse senza regola applicabile.
        n_giri_chiusi: giri con ``motivo_chiusura='naturale'``.
        n_giri_non_chiusi: giri non chiusi (max_giornate o non_chiuso).
        n_eventi_composizione: blocchi aggancio/sgancio inseriti.
        n_incompatibilita_materiale: warning più tipi materiale per giornata.
        warnings: messaggi human-readable per il pianificatore (UI).
    """

    giri_ids: list[int]
    n_giri_creati: int
    n_corse_processate: int
    n_corse_residue: int
    n_giri_chiusi: int
    n_giri_non_chiusi: int
    n_eventi_composizione: int
    n_incompatibilita_materiale: int
    warnings: list[str] = field(default_factory=list)


# =====================================================================
# Loader (DB → dataclass)
# =====================================================================


async def _carica_programma(
    session: AsyncSession, programma_id: int, azienda_id: int
) -> ProgrammaMateriale:
    stmt = select(ProgrammaMateriale).where(
        ProgrammaMateriale.id == programma_id,
        ProgrammaMateriale.azienda_id == azienda_id,
    )
    p = (await session.execute(stmt)).scalar_one_or_none()
    if p is None:
        raise ProgrammaNonTrovatoError(programma_id, azienda_id)
    return p


async def _carica_regole(
    session: AsyncSession, programma_id: int
) -> list[ProgrammaRegolaAssegnazione]:
    stmt = (
        select(ProgrammaRegolaAssegnazione)
        .where(ProgrammaRegolaAssegnazione.programma_id == programma_id)
        .order_by(ProgrammaRegolaAssegnazione.priorita.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def _carica_localita(
    session: AsyncSession, codice: str, azienda_id: int
) -> LocalitaManutenzione:
    stmt = select(LocalitaManutenzione).where(
        LocalitaManutenzione.codice == codice,
        LocalitaManutenzione.azienda_id == azienda_id,
    )
    loc = (await session.execute(stmt)).scalar_one_or_none()
    if loc is None:
        raise LocalitaNonTrovataError(codice, azienda_id)
    return loc


async def _carica_corse(
    session: AsyncSession,
    azienda_id: int,
    data_da: date,
    data_a: date,
) -> list[CorsaCommerciale]:
    """Corse con finestra di validità che si sovrappone all'intervallo."""
    stmt = select(CorsaCommerciale).where(
        CorsaCommerciale.azienda_id == azienda_id,
        CorsaCommerciale.valido_da <= data_a,
        CorsaCommerciale.valido_a >= data_da,
    )
    return list((await session.execute(stmt)).scalars().all())


async def _count_giri_esistenti(session: AsyncSession, programma_id: int) -> int:
    """Conta i giri già persistiti per questo programma (via metadata)."""
    stmt = text(
        "SELECT COUNT(*) FROM giro_materiale WHERE generation_metadata_json->>'programma_id' = :pid"
    )
    row = await session.execute(stmt, {"pid": str(programma_id)})
    val = row.scalar_one()
    return int(val)


async def _wipe_giri_programma(session: AsyncSession, programma_id: int) -> None:
    """Cancella tutti i giri (e blocchi a cascade) di questo programma.

    `giro_blocco`/`giro_variante`/`giro_giornata` hanno ON DELETE
    CASCADE su `giro_materiale`. `corsa_materiale_vuoto` ha ON DELETE
    SET NULL su `giro_materiale_id`, quindi va cancellata esplicitamente.
    """
    pid_param = {"pid": str(programma_id)}
    # Vuoti collegati ai giri
    await session.execute(
        text(
            "DELETE FROM corsa_materiale_vuoto "
            "WHERE giro_materiale_id IN ("
            "  SELECT id FROM giro_materiale "
            "  WHERE generation_metadata_json->>'programma_id' = :pid"
            ")"
        ),
        pid_param,
    )
    # Giri (cascade su giornate/varianti/blocchi)
    await session.execute(
        text("DELETE FROM giro_materiale WHERE generation_metadata_json->>'programma_id' = :pid"),
        pid_param,
    )


# =====================================================================
# Helpers data filtering
# =====================================================================


def _corsa_vale_in_data(corsa: CorsaCommerciale, d: date) -> bool:
    """``True`` se ``corsa.valido_in_date_json`` contiene la data come
    stringa ISO (``YYYY-MM-DD``).

    Coerente con feedback utente: ``valido_in_date_json`` è la fonte
    autorevole. Lista vuota → corsa non vale in alcuna data
    (parser non ha generato la lista, comportamento conservativo).
    """
    return d.isoformat() in corsa.valido_in_date_json


# =====================================================================
# Strict mode
# =====================================================================


def _check_strict_mode(programma: ProgrammaMateriale, giri: list[GiroAssegnato]) -> None:
    """Verifica i flag strict configurati sul programma.

    Implementati in 4.4.5b:
    - ``no_corse_residue``: nessuna corsa senza regola applicabile.
    - ``no_giro_non_chiuso_a_localita``: tutti i giri devono chiudere a
      località (``motivo_chiusura='naturale'``).

    Altri flag (``no_overcapacity``, ``no_aggancio_non_validato``,
    ``no_orphan_blocks``, ``no_km_eccesso``) sono scope futuro.

    Raises:
        StrictModeViolation: con lista di violazioni human-readable.
    """
    opts = programma.strict_options_json or {}
    violazioni: list[str] = []

    if opts.get("no_corse_residue"):
        n_residue = sum(len(g.corse_residue) for g in giri)
        if n_residue > 0:
            violazioni.append(f"no_corse_residue=true ma {n_residue} corse senza regola")

    if opts.get("no_giro_non_chiuso_a_localita"):
        n_non_chiusi = sum(1 for g in giri if not g.chiuso)
        if n_non_chiusi > 0:
            violazioni.append(
                f"no_giro_non_chiuso_a_localita=true ma {n_non_chiusi} giri non chiusi"
            )

    if violazioni:
        raise StrictModeViolation(violazioni)


# =====================================================================
# Orchestrator
# =====================================================================


async def genera_giri(
    *,
    programma_id: int,
    data_inizio: date,
    n_giornate: int,
    localita_codice: str,
    session: AsyncSession,
    azienda_id: int,
    force: bool = False,
) -> BuilderResult:
    """Genera giri materiali end-to-end e li persiste.

    Pipeline:
    1. Carica programma + regole + località.
    2. Verifica programma ``stato='attivo'``.
    3. Verifica niente giri esistenti (o ``force=True`` → wipe).
    4. Carica corse del periodo, filtra per data, costruisci catene,
       posiziona su località, multi-giornata, assegnazione regole +
       eventi.
    5. Strict mode check.
    6. Genera ``numero_turno = "G-{LOC_BREVE}-{NNN}"``, persisti.

    Args:
        programma_id: id ``ProgrammaMateriale``.
        data_inizio: prima data del range.
        n_giornate: numero giornate (>= 1).
        localita_codice: codice località manutenzione (es.
            ``IMPMAN_MILANO_FIORENZA``).
        session: ``AsyncSession``.
        azienda_id: per multi-tenant filtering.
        force: se ``True`` cancella i giri esistenti del programma
            prima di rigenerare.

    Returns:
        ``BuilderResult`` con stats + warning.

    Raises:
        ProgrammaNonTrovatoError, ProgrammaNonAttivoError,
        LocalitaNonTrovataError, GiriEsistentiError, StrictModeViolation,
        RegolaAmbiguaError (da ``risolvi_corsa``).
    """
    if n_giornate < 1:
        raise ValueError(f"n_giornate deve essere >= 1, ricevuto {n_giornate}")

    # 1. Carica programma + regole + località
    programma = await _carica_programma(session, programma_id, azienda_id)
    if programma.stato != "attivo":
        raise ProgrammaNonAttivoError(programma_id, programma.stato)

    regole = await _carica_regole(session, programma_id)
    localita = await _carica_localita(session, localita_codice, azienda_id)

    # 2. Anti-rigenerazione (decisione utente: 409 senza force=true)
    n_esistenti = await _count_giri_esistenti(session, programma_id)
    if n_esistenti > 0:
        if not force:
            raise GiriEsistentiError(programma_id, n_esistenti)
        await _wipe_giri_programma(session, programma_id)

    # 3. Pipeline: carica corse + costruisci catene per data
    date_range = [data_inizio + timedelta(days=i) for i in range(n_giornate)]
    corse = await _carica_corse(session, azienda_id, date_range[0], date_range[-1])

    warnings: list[str] = []
    catene_per_data: dict[date, list[CatenaPosizionata]] = {}
    for d in date_range:
        corse_giorno = [c for c in corse if _corsa_vale_in_data(c, d)]
        if not corse_giorno:
            continue
        catene = costruisci_catene(corse_giorno)
        catene_pos: list[CatenaPosizionata] = []
        for cat in catene:
            try:
                cat_pos = posiziona_su_localita(cat, localita)
            except (LocalitaSenzaStazioneError, PosizionamentoImpossibileError) as exc:
                warnings.append(f"Catena del {d.isoformat()} scartata: {exc}")
                continue
            catene_pos.append(cat_pos)
        catene_per_data[d] = catene_pos

    # 4. Multi-giornata (cross-notte)
    giri_dom = costruisci_giri_multigiornata(catene_per_data)

    # 5. Assegnazione regole + eventi composizione
    giri_assegnati = assegna_e_rileva_eventi(giri_dom, regole)

    # 6. Strict mode pre-persistenza
    _check_strict_mode(programma, giri_assegnati)

    # 7. Genera numero_turno + persisti
    giri_da_persistere = [
        GiroDaPersistere(
            numero_turno=f"G-{localita.codice_breve}-{idx:03d}",
            giro=giro,
        )
        for idx, giro in enumerate(giri_assegnati, start=1)
    ]
    giro_ids = await persisti_giri(giri_da_persistere, session, programma_id, azienda_id)
    await session.commit()

    # 8. Stats
    n_corse_processate = sum(len(gg.blocchi_assegnati) for g in giri_assegnati for gg in g.giornate)
    n_corse_residue = sum(len(g.corse_residue) for g in giri_assegnati)
    n_giri_chiusi = sum(1 for g in giri_assegnati if g.chiuso)
    n_giri_non_chiusi = sum(1 for g in giri_assegnati if not g.chiuso)
    n_eventi = sum(len(gg.eventi_composizione) for g in giri_assegnati for gg in g.giornate)
    n_incompat = sum(len(g.incompatibilita_materiale) for g in giri_assegnati)

    return BuilderResult(
        giri_ids=giro_ids,
        n_giri_creati=len(giro_ids),
        n_corse_processate=n_corse_processate,
        n_corse_residue=n_corse_residue,
        n_giri_chiusi=n_giri_chiusi,
        n_giri_non_chiusi=n_giri_non_chiusi,
        n_eventi_composizione=n_eventi,
        n_incompatibilita_materiale=n_incompat,
        warnings=warnings,
    )
