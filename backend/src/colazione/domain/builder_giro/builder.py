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
  ``no_giro_appeso`` (rinominato in 5.1, ex
  ``no_giro_non_chiuso_a_localita``). Gli altri (overcapacity, ecc.)
  sono scope futuro.

Spec:
- ``docs/PROGRAMMA-MATERIALE.md`` §6 (strict mode granulare)
- ``docs/LOGICA-COSTRUZIONE.md`` §3 (Algoritmo A end-to-end)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.domain.builder_giro.catena import costruisci_catene
from colazione.domain.builder_giro.composizione import (
    GiroAssegnato,
    assegna_e_rileva_eventi,
)
from colazione.domain.builder_giro.multi_giornata import (
    ParamMultiGiornata,
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
    ParamPosizionamento,
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


class PeriodoFuoriProgrammaError(ValueError):
    """Il range richiesto sfora il periodo di validità del programma.
    Sprint 7.3 fix data validità.
    """

    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.motivo = motivo


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
        n_giri_non_chiusi: giri non chiusi (km_cap, max_giornate o
            non_chiuso).
        n_giri_km_cap: giri chiusi per ``km_cumulati >= km_max_ciclo``
            (Sprint 5.4). Sottoinsieme di ``n_giri_non_chiusi``: il giro
            è "chiuso operativamente" (va a manutenzione) ma non
            geograficamente alla sede.
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
    n_giri_km_cap: int = 0
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


async def _carica_whitelist_stazioni(session: AsyncSession, localita_id: int) -> frozenset[str]:
    """Carica i codici stazione "vicini" alla sede da
    `localita_stazione_vicina` (Sprint 5.3).

    Set vuoto se la sede non ha whitelist configurata (caso TILO o
    aziende non-Trenord che non l'hanno ancora popolata): in quel caso
    il builder non genera vuoti tecnici, tutte le chiusure sono
    "naturali" o demandate a multi_giornata.
    """
    stmt = text(
        "SELECT stazione_codice FROM localita_stazione_vicina "
        "WHERE localita_manutenzione_id = :loc_id"
    )
    rows = (await session.execute(stmt, {"loc_id": localita_id})).scalars().all()
    return frozenset(rows)


async def _carica_accoppiamenti_ammessi(session: AsyncSession) -> frozenset[tuple[str, str]]:
    """Carica le coppie ammesse da `materiale_accoppiamento_ammesso`
    (Sprint 5.5).

    Le coppie sono già normalizzate lex (a <= b) dalla migration 0007
    via CHECK constraint. Ritorna ``frozenset[tuple]`` per lookup O(1)
    nel callback ``is_accoppiamento_ammesso``.

    Set vuoto = nessun accoppiamento configurato → ogni composizione
    doppia con ``is_composizione_manuale=False`` viene rifiutata da
    `risolvi_corsa()`. Le composizioni singole (1 elemento) non sono
    affette.
    """
    stmt = text(
        "SELECT materiale_a_codice, materiale_b_codice FROM materiale_accoppiamento_ammesso"
    )
    rows = (await session.execute(stmt)).all()
    return frozenset((str(r[0]), str(r[1])) for r in rows)


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

    Ordine FK-safe critico:

    1. Salva gli id dei vuoti collegati ai giri (li referenziano
       i ``giro_blocco materiale_vuoto`` con FK RESTRICT).
    2. ``DELETE giro_materiale`` → CASCADE cancella giornate/varianti/
       blocchi → la FK ``giro_blocco_corsa_materiale_vuoto_id``
       smette di proteggere i vuoti.
    3. Cancella i vuoti orfani identificati al passo 1.

    L'ordine inverso (vuoti prima dei giri) viola la FK
    ``giro_blocco_corsa_materiale_vuoto_id_fkey``. Bug intercettato
    da smoke test reale (2026-04-26).
    """
    pid_param = {"pid": str(programma_id)}

    cmv_ids = list(
        (
            await session.execute(
                text(
                    "SELECT cmv.id FROM corsa_materiale_vuoto cmv "
                    "JOIN giro_materiale gm ON gm.id = cmv.giro_materiale_id "
                    "WHERE gm.generation_metadata_json->>'programma_id' = :pid"
                ),
                pid_param,
            )
        )
        .scalars()
        .all()
    )

    await session.execute(
        text("DELETE FROM giro_materiale WHERE generation_metadata_json->>'programma_id' = :pid"),
        pid_param,
    )

    if cmv_ids:
        await session.execute(
            text("DELETE FROM corsa_materiale_vuoto WHERE id = ANY(:ids)"),
            {"ids": cmv_ids},
        )


# =====================================================================
# Helpers data filtering
# =====================================================================


def _valida_periodo_programma(
    programma: ProgrammaMateriale, data_inizio: date, n_giornate: int
) -> None:
    """Valida che il range richiesto sia contenuto nel periodo del
    programma ``[valido_da, valido_a]``. Sprint 7.3 fix data validità.

    Raises:
        PeriodoFuoriProgrammaError: quando il range API sfora il
            periodo del programma.
    """
    data_fine_richiesta = data_inizio + timedelta(days=n_giornate - 1)
    if data_inizio < programma.valido_da or data_fine_richiesta > programma.valido_a:
        raise PeriodoFuoriProgrammaError(
            f"Range richiesto {data_inizio.isoformat()} → "
            f"{data_fine_richiesta.isoformat()} fuori dal periodo del "
            f"programma [{programma.valido_da.isoformat()} → "
            f"{programma.valido_a.isoformat()}]."
        )


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

    Implementati in 4.4.5b (flag rinominato in 5.1):
    - ``no_corse_residue``: nessuna corsa senza regola applicabile.
    - ``no_giro_appeso`` (ex ``no_giro_non_chiuso_a_localita``): tutti i
      giri devono avere un rientro programmato a fine ciclo. Sprint 5.1
      ha rinominato il flag per riflettere la nuova semantica
      multi-giornata.

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

    if opts.get("no_giro_appeso"):
        n_non_chiusi = sum(1 for g in giri if not g.chiuso)
        if n_non_chiusi > 0:
            violazioni.append(f"no_giro_appeso=true ma {n_non_chiusi} giri non chiusi")

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

    # Sprint 7.3 fix: vincolo HARD su valido_da/valido_a + stagione del
    # programma. Prima il builder ignorava entrambi e generava giri
    # anche per date fuori dal periodo o stagione dichiarata. Adesso:
    # 422 prima di toccare la pipeline.
    _valida_periodo_programma(programma, data_inizio, n_giornate)

    regole = await _carica_regole(session, programma_id)
    localita = await _carica_localita(session, localita_codice, azienda_id)
    whitelist = await _carica_whitelist_stazioni(session, localita.id)
    accoppiamenti = await _carica_accoppiamenti_ammessi(session)

    def is_accoppiamento_ammesso(a: str, b: str) -> bool:
        """Lookup nella set degli accoppiamenti ammessi (Sprint 5.5).
        Coppie normalizzate lex dal chiamante."""
        return (a, b) in accoppiamenti

    # 2. Anti-rigenerazione (decisione utente: 409 senza force=true)
    n_esistenti = await _count_giri_esistenti(session, programma_id)
    if n_esistenti > 0:
        if not force:
            raise GiriEsistentiError(programma_id, n_esistenti)
        await _wipe_giri_programma(session, programma_id)

    # 3. Pipeline: carica corse + costruisci catene per data
    date_range = [data_inizio + timedelta(days=i) for i in range(n_giornate)]
    corse = await _carica_corse(session, azienda_id, date_range[0], date_range[-1])

    # Sprint 5.6: filtro pool catene = corse che matchano almeno una
    # regola del programma. Evita giri "shell" generati da catene di
    # corse fuori-perimetro che il programma non assegna comunque.
    # Il giorno_tipo è euristico (`feriale`) — ai fini del filtro pool
    # è sufficiente; l'assegnazione finale userà il giorno_tipo reale.
    from colazione.domain.builder_giro.risolvi_corsa import matches_all

    def _corsa_in_perimetro_programma(c: Any) -> bool:
        return any(matches_all(r.filtri_json, c, "feriale") for r in regole)

    corse_perimetro = [c for c in corse if _corsa_in_perimetro_programma(c)]

    warnings: list[str] = []
    # Sprint 5.6 Feature 3: attiva il vincolo finestra uscita deposito
    # 01:00-03:00 per programmi reali (non per test puri legacy).
    param_pos = ParamPosizionamento(finestra_uscita_vietata_attiva=True)
    catene_per_data: dict[date, list[CatenaPosizionata]] = {}
    for d in date_range:
        corse_giorno = [c for c in corse_perimetro if _corsa_vale_in_data(c, d)]
        if not corse_giorno:
            continue
        catene = costruisci_catene(corse_giorno)
        catene_pos: list[CatenaPosizionata] = []
        for cat in catene:
            try:
                cat_pos = posiziona_su_localita(cat, localita, whitelist, param_pos)
            except (LocalitaSenzaStazioneError, PosizionamentoImpossibileError) as exc:
                warnings.append(f"Catena del {d.isoformat()} scartata: {exc}")
                continue
            catene_pos.append(cat_pos)
        catene_per_data[d] = catene_pos

    # 4. Multi-giornata (cross-notte) con cumulo km e chiusura dinamica.
    # Sprint 5.6: il giro chiude solo se km_cap raggiunto AND treno in
    # whitelist sede ("vicino_sede"). `n_giornate_default` del programma
    # diventa SAFETY NET (non più termine attivo): default 30 se non
    # configurato, comunque protegge da loop pathologici.
    param_mg = ParamMultiGiornata(
        n_giornate_max=max(programma.n_giornate_default, 30),
        km_max_ciclo=float(programma.km_max_ciclo) if programma.km_max_ciclo else None,
        whitelist_sede=whitelist,
    )
    giri_dom = costruisci_giri_multigiornata(catene_per_data, param_mg)

    # 5. Assegnazione regole + eventi composizione (Sprint 5.5: validazione
    #    accoppiamenti via callback)
    giri_assegnati = assegna_e_rileva_eventi(giri_dom, regole, is_accoppiamento_ammesso)

    # 6. Strict mode pre-persistenza
    _check_strict_mode(programma, giri_assegnati)

    # 7. Genera numero_turno + persisti.
    # Sprint 5.6: in modo dinamico (km_max_ciclo configurato) attiva la
    # creazione automatica della corsa rientro 9XXXX a fine giro
    # "naturale" (Feature 4).
    modo_dinamico = programma.km_max_ciclo is not None
    giri_da_persistere = [
        GiroDaPersistere(
            numero_turno=f"G-{localita.codice_breve}-{idx:03d}",
            giro=giro,
            genera_rientro_sede=modo_dinamico,
        )
        for idx, giro in enumerate(giri_assegnati, start=1)
    ]
    giro_ids = await persisti_giri(
        giri_da_persistere,
        session,
        programma_id,
        azienda_id,
        periodo_valido_da=programma.valido_da,
        periodo_valido_a=programma.valido_a,
    )
    await session.commit()

    # 8. Stats
    n_corse_processate = sum(len(gg.blocchi_assegnati) for g in giri_assegnati for gg in g.giornate)
    n_corse_residue = sum(len(g.corse_residue) for g in giri_assegnati)
    n_giri_chiusi = sum(1 for g in giri_assegnati if g.chiuso)
    n_giri_non_chiusi = sum(1 for g in giri_assegnati if not g.chiuso)
    n_giri_km_cap = sum(1 for g in giri_assegnati if g.motivo_chiusura == "km_cap")
    n_eventi = sum(len(gg.eventi_composizione) for g in giri_assegnati for gg in g.giornate)
    n_incompat = sum(len(g.incompatibilita_materiale) for g in giri_assegnati)

    return BuilderResult(
        giri_ids=giro_ids,
        n_giri_creati=len(giro_ids),
        n_corse_processate=n_corse_processate,
        n_corse_residue=n_corse_residue,
        n_giri_chiusi=n_giri_chiusi,
        n_giri_non_chiusi=n_giri_non_chiusi,
        n_giri_km_cap=n_giri_km_cap,
        n_eventi_composizione=n_eventi,
        n_incompatibilita_materiale=n_incompat,
        warnings=warnings,
    )
