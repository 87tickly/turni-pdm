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

import dataclasses
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.domain.builder_giro.aggregazione_a2 import aggrega_a2
from colazione.domain.builder_giro.capacity_routing import (
    aggrega_corse_residue_da_scartati,
    carica_dotazione_per_azienda,
    ribilancia_per_capacity,
)
from colazione.domain.builder_giro.fusione_cluster_a1 import fonde_cluster_simili
from colazione.domain.builder_giro.catena import costruisci_catene
from colazione.domain.builder_giro.composizione import (
    GiroAssegnato,
    assegna_e_rileva_eventi,
)
from colazione.domain.builder_giro.etichetta import calcola_etichetta_giro
from colazione.domain.builder_giro.multi_giornata import (
    Giro,
    ParamMultiGiornata,
    _km_giornata as _km_giornata_catena,
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
from colazione.models.anagrafica import FestivitaUfficiale, LocalitaManutenzione
from colazione.models.corse import CorsaCommerciale
from colazione.models.programmi import (
    BuilderRun,
    ProgrammaMateriale,
    ProgrammaRegolaAssegnazione,
)

# =====================================================================
# Costanti
# =====================================================================

#: Sprint 7.7 MR 1 — chilometraggio medio giornaliero di un treno
#: regionale italiano. Decisione utente 2026-05-02: "in media un treno
#: al giorno fa circa 700/1000 km". Usato come fallback per il cap
#: effettivo del giro quando né la regola né il programma hanno
#: `km_max_ciclo` configurato. 850 = midpoint.
DEFAULT_KM_MEDIO_GIORNALIERO: int = 850


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
    """Il programma ha già giri persistiti per la stessa sede
    (rigenerazione richiede ``force=True``).

    Sprint 7.6 MR 3.1: il check è SCOPED per (programma, sede): giri di
    una sede diversa NON bloccano una nuova generazione (modello cumulativo,
    decisione utente 2026-05-01: "se inizio a generare un turno materiale
    dal 521 e poi per il 526, deve essere sommato a quello creato in
    precedenza"). Se passi ``force=True``, vengono cancellati SOLO i giri
    di QUESTA sede del programma, non tutti.
    """

    def __init__(self, programma_id: int, localita_codice: str, n_esistenti: int) -> None:
        super().__init__(
            f"Programma {programma_id} ha già {n_esistenti} giro(i) persistiti "
            f"per la sede {localita_codice!r}. Per rigenerare quelli di questa "
            "sede passa force=True. I giri delle altre sedi del programma "
            "NON saranno toccati."
        )
        self.programma_id = programma_id
        self.localita_codice = localita_codice
        self.n_esistenti = n_esistenti


class PdcDipendentiError(RuntimeError):
    """La rigenerazione (force=True) cancellerebbe N turni PdC dipendenti
    dai giri della sede.

    Sprint 7.9 strategy A (decisione utente 2026-05-04): il flusso
    "rigenero giri sede X" richiede una conferma esplicita prima di
    distruggere i turni PdC che derivano da quei giri (FK
    ``turno_pdc_blocco.corsa_materiale_vuoto_id`` con ondelete=RESTRICT
    impedisce wipe silente). Per procedere passa
    ``confirm_delete_pdc=True``.

    Attributi:
        programma_id: id del programma.
        localita_codice: codice sede (es. ``"IMPMAN_MILANO_FIORENZA"``).
        n_pdc: numero turni PdC che verranno cancellati.
        pdc_codici: lista dei ``codice`` dei turni PdC (es.
            ``["T-G-FIO-001-ETR526-7g", ...]``) per UI.
    """

    def __init__(
        self,
        programma_id: int,
        localita_codice: str,
        n_pdc: int,
        pdc_codici: list[str],
    ) -> None:
        super().__init__(
            f"Rigenerazione giri programma {programma_id} sede "
            f"{localita_codice!r} cancellerebbe {n_pdc} turni PdC "
            f"dipendenti. Per confermare passa confirm_delete_pdc=True. "
            f"Turni: {', '.join(pdc_codici[:5])}"
            + (f" (+ altri {n_pdc - 5})" if n_pdc > 5 else "")
        )
        self.programma_id = programma_id
        self.localita_codice = localita_codice
        self.n_pdc = n_pdc
        self.pdc_codici = pdc_codici


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


async def carica_festivita_periodo(
    session: AsyncSession,
    azienda_id: int,
    valido_da: date,
    valido_a: date,
) -> frozenset[date]:
    """Carica festività ufficiali rilevanti per il periodo (Sprint 7.7 MR 3, esposta MR 6).

    Include sia le festività nazionali (``azienda_id IS NULL``) sia le
    festività locali specifiche per l'azienda (es. Sant'Ambrogio per
    Trenord, righe ``azienda_id`` valorizzato). Filtra all'intervallo
    ``[valido_da, valido_a]``.

    **Sprint 7.7 MR 6**: esposta al package builder_giro per riuso da
    ``api/giri.py::get_giro_dettaglio`` (calcolo etichetta categorica
    delle varianti). Caller che usa ``tipo_giorno_categoria`` deve
    estendere il range di +1 giorno per riconoscere il prefestivo
    della data finale.

    Ritorna ``frozenset[date]`` per lookup O(1) in
    ``calcola_etichetta_giro``/``calcola_etichetta_variante``. Se la
    migration 0015 non ha seedato festività per gli anni del periodo
    (oltre 2030), il set risultante può essere vuoto e
    ``tipo_giorno()`` ricadrà solo su feriale/sabato/domenica.
    """
    stmt = select(FestivitaUfficiale.data).where(
        or_(
            FestivitaUfficiale.azienda_id.is_(None),
            FestivitaUfficiale.azienda_id == azienda_id,
        ),
        FestivitaUfficiale.data >= valido_da,
        FestivitaUfficiale.data <= valido_a,
    )
    rows = (await session.execute(stmt)).scalars().all()
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


async def _carica_stazioni_lookup(
    session: AsyncSession, azienda_id: int
) -> dict[str, str]:
    """Carica `{codice: nome}` di tutte le stazioni dell'azienda.

    Entry 96: usato dai vincoli HARD del builder per matchare i
    pattern stazione contro origine/destinazione delle corse.
    """
    stmt = text(
        "SELECT codice, nome FROM stazione WHERE azienda_id = :azienda_id"
    )
    rows = (await session.execute(stmt, {"azienda_id": azienda_id})).all()
    return {str(r[0]): str(r[1]) for r in rows}


async def _count_giri_esistenti(
    session: AsyncSession,
    programma_id: int,
    localita_id: int | None = None,
) -> int:
    """Conta i giri già persistiti per questo programma.

    Sprint 7.6 MR 3.1 (cumulativo): se ``localita_id`` è passato,
    filtra anche per ``localita_manutenzione_partenza_id`` — così la
    rigenerazione di una sede non vede i giri delle altre sedi come
    "esistenti".
    """
    if localita_id is None:
        stmt = text(
            "SELECT COUNT(*) FROM giro_materiale WHERE programma_id = :pid"
        )
        row = await session.execute(stmt, {"pid": programma_id})
    else:
        stmt = text(
            "SELECT COUNT(*) FROM giro_materiale "
            "WHERE programma_id = :pid AND localita_manutenzione_partenza_id = :lid"
        )
        row = await session.execute(stmt, {"pid": programma_id, "lid": localita_id})
    val = row.scalar_one()
    return int(val)


async def _conta_pdc_dipendenti(
    session: AsyncSession,
    programma_id: int,
    localita_id: int | None,
) -> tuple[int, list[str]]:
    """Sprint 7.9 strategy A: conta turni PdC dipendenti dai giri di
    questa sede del programma.

    Un turno PdC è dipendente se almeno uno dei suoi blocchi
    (``turno_pdc_blocco``) referenzia una ``corsa_materiale_vuoto``
    appartenente a un giro della sede indicata. La FK è la stessa
    che farebbe esplodere il wipe (RESTRICT).

    Returns:
        ``(n_pdc, codici)`` dove ``n_pdc`` è il count distinto e
        ``codici`` la lista dei ``turno_pdc.codice`` (per UI).
    """
    if localita_id is None:
        where_giri = "gm.programma_id = :pid"
        params: dict[str, int] = {"pid": programma_id}
    else:
        where_giri = (
            "gm.programma_id = :pid "
            "AND gm.localita_manutenzione_partenza_id = :lid"
        )
        params = {"pid": programma_id, "lid": localita_id}

    sql = text(
        f"""
        SELECT DISTINCT tp.id, tp.codice
        FROM turno_pdc tp
        JOIN turno_pdc_giornata tpg ON tpg.turno_pdc_id = tp.id
        JOIN turno_pdc_blocco tpb ON tpb.turno_pdc_giornata_id = tpg.id
        JOIN corsa_materiale_vuoto cmv ON cmv.id = tpb.corsa_materiale_vuoto_id
        JOIN giro_materiale gm ON gm.id = cmv.giro_materiale_id
        WHERE {where_giri}
        ORDER BY tp.codice
        """
    )
    rows = (await session.execute(sql, params)).all()
    codici = [str(row.codice) for row in rows]
    return len(codici), codici


async def _wipe_giri_programma(
    session: AsyncSession,
    programma_id: int,
    localita_id: int | None = None,
) -> None:
    """Cancella i giri (e blocchi a cascade) di questo programma.

    Sprint 7.6 MR 3.1 (cumulativo): se ``localita_id`` è passato,
    cancella SOLO i giri della sede indicata. ``None`` mantiene il
    comportamento storico (wipe globale del programma) — usato dai
    test di reset e dal fallback admin.

    Sprint 7.9 strategy A (2026-05-04): cancella anche i turni PdC
    dipendenti dai giri prima del wipe vero, perché la FK
    ``turno_pdc_blocco.corsa_materiale_vuoto_id`` con ondelete=RESTRICT
    impedirebbe altrimenti il wipe successivo. La conferma utente è
    rispettata a monte da ``genera_giri`` (sollevando
    ``PdcDipendentiError`` se il caller non ha esplicitamente
    confermato). Qui assumiamo che l'autorizzazione sia già stata
    data: cascade FK ``turno_pdc → giornata → blocco`` porta via il
    resto.

    Ordine FK-safe critico:

    1. Cancella i turni PdC dipendenti (cascade su giornate/blocchi
       libera la FK su ``corsa_materiale_vuoto``).
    2. Salva gli id dei vuoti collegati ai giri (li referenziano
       i ``giro_blocco materiale_vuoto`` con FK RESTRICT).
    3. ``DELETE giro_materiale`` → CASCADE cancella giornate/varianti/
       blocchi → la FK ``giro_blocco_corsa_materiale_vuoto_id``
       smette di proteggere i vuoti.
    4. Cancella i vuoti orfani identificati al passo 2.

    L'ordine inverso (vuoti prima dei giri) viola la FK
    ``giro_blocco_corsa_materiale_vuoto_id_fkey``. Bug intercettato
    da smoke test reale (2026-04-26).
    """
    if localita_id is None:
        where_giri = "WHERE gm.programma_id = :pid"
        delete_where = "WHERE programma_id = :pid"
        params: dict[str, int] = {"pid": programma_id}
    else:
        where_giri = (
            "WHERE gm.programma_id = :pid "
            "AND gm.localita_manutenzione_partenza_id = :lid"
        )
        delete_where = (
            "WHERE programma_id = :pid "
            "AND localita_manutenzione_partenza_id = :lid"
        )
        params = {"pid": programma_id, "lid": localita_id}

    # 1. Wipe a cascata dei turni PdC dipendenti (Sprint 7.9 strategy A).
    pdc_ids = list(
        (
            await session.execute(
                text(
                    f"""
                    SELECT DISTINCT tp.id
                    FROM turno_pdc tp
                    JOIN turno_pdc_giornata tpg ON tpg.turno_pdc_id = tp.id
                    JOIN turno_pdc_blocco tpb ON tpb.turno_pdc_giornata_id = tpg.id
                    JOIN corsa_materiale_vuoto cmv ON cmv.id = tpb.corsa_materiale_vuoto_id
                    JOIN giro_materiale gm ON gm.id = cmv.giro_materiale_id
                    {where_giri}
                    """
                ),
                params,
            )
        )
        .scalars()
        .all()
    )
    if pdc_ids:
        await session.execute(
            text("DELETE FROM turno_pdc WHERE id = ANY(:ids)"),
            {"ids": pdc_ids},
        )

    # 2. Salva i vuoti collegati ai giri (referenziati da giro_blocco RESTRICT).
    cmv_ids = list(
        (
            await session.execute(
                text(
                    "SELECT cmv.id FROM corsa_materiale_vuoto cmv "
                    "JOIN giro_materiale gm ON gm.id = cmv.giro_materiale_id "
                    f"{where_giri}"
                ),
                params,
            )
        )
        .scalars()
        .all()
    )

    # 3. Cancella i giri (cascade su giornate/varianti/blocchi).
    await session.execute(text(f"DELETE FROM giro_materiale {delete_where}"), params)

    # 4. Cancella i vuoti orfani.
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


def _trova_regola_dominante(
    cat_pos: CatenaPosizionata,
    regole: list[ProgrammaRegolaAssegnazione],
) -> ProgrammaRegolaAssegnazione | None:
    """Sprint 7.7 MR 1: regola "dominante" che determina il cap del giro.

    Convenzione: la regola di una catena è quella con `priorita` più
    alta tra le regole che coprono la PRIMA corsa della catena (giorno
    tipo `feriale` come euristica, allineato col filtro perimetro).
    Se più regole hanno la stessa priorità, vince quella con `id` più
    basso (deterministico).

    Ritorna ``None`` se la prima corsa non è coperta da nessuna regola
    (catena orfana — il chiamante la scarta con warning).
    """
    from colazione.domain.builder_giro.risolvi_corsa import matches_all

    if not cat_pos.catena.corse:
        return None
    prima = cat_pos.catena.corse[0]
    candidate = [r for r in regole if matches_all(r.filtri_json, prima, "feriale")]
    if not candidate:
        return None
    candidate.sort(key=lambda r: (-r.priorita, r.id))
    return candidate[0]


def _giro_chiude_in_whitelist(
    giro: Giro,
    whitelist: frozenset[str],
    stazione_sede: str | None,
) -> bool:
    """Sprint 7.7 MR 1 hotfix Fix C2: True se il giro termina in zona
    sede (stazione_sede O qualunque stazione della whitelist).

    Vuoto se il giro è vuoto o l'ultima giornata non ha corse.
    """
    if not giro.giornate:
        return False
    corse_ultima = giro.giornate[-1].catena_posizionata.catena.corse
    if not corse_ultima:
        return False
    dest = corse_ultima[-1].codice_destinazione
    return dest == stazione_sede or dest in whitelist


def _tronca_a_chiusura_whitelist(
    giro: Giro,
    whitelist: frozenset[str],
    stazione_sede: str | None,
) -> Giro | None:
    """Sprint 7.7 MR 1 hotfix Fix C2: tronca il giro all'ultima giornata
    che termina in zona sede (whitelist).

    Itera all'indietro e taglia a primo K dove
    ``giornate[K].catena_posizionata.catena.corse[-1].codice_destinazione``
    è in whitelist o uguale a ``stazione_sede``. Le giornate K+1..N
    vengono scartate (le loro corse diventano orfane di troncamento, il
    chiamante registra il warning).

    Decisione utente 2026-05-02:

    > "dobbiamo sempre chiudere i giri"

    Combinato col vincolo "no vuoti lunghi" (Fix C originale), il
    builder costruisce SEMPRE giri chiusi naturalmente in whitelist,
    accettando di scartare le code che andrebbero fuori zona sede.

    Ritorna ``None`` se nessuna giornata del giro termina in whitelist
    (= sede non coerente con la regola; chiamante scarta l'intero giro
    + warning forte al pianificatore).
    """
    for k in range(len(giro.giornate) - 1, -1, -1):
        corse = giro.giornate[k].catena_posizionata.catena.corse
        if not corse:
            continue
        dest = corse[-1].codice_destinazione
        if dest == stazione_sede or dest in whitelist:
            giornate_troncate = giro.giornate[: k + 1]
            km_nuovi = sum(
                _km_giornata_catena(g.catena_posizionata) for g in giornate_troncate
            )
            return dataclasses.replace(
                giro,
                giornate=giornate_troncate,
                chiuso=True,
                motivo_chiusura="naturale",
                km_cumulati=km_nuovi,
            )
    return None


def _calcola_cap_effettivo(
    regola: ProgrammaRegolaAssegnazione,
    programma: ProgrammaMateriale,
    n_giornate_safety: int,
) -> float | None:
    """Sprint 7.7 MR 1: cap km del giro = primo non-None tra:

    1. ``regola.km_max_ciclo`` — cap specifico per materiale (es.
       ETR526 ~4500). Modello target post-MR 7.7.1.
    2. ``programma.km_max_ciclo`` — cap legacy globale del programma.
       Backward compat per programmi pre-MR 7.7.1.
    3. ``None`` — nessun cap esplicito → ``costruisci_giri_multigiornata``
       opera in modo legacy (chiusura per safety `n_giornate_max` o
       assenza catena successiva). Il fallback informativo
       ``DEFAULT_KM_MEDIO_GIORNALIERO`` (~850 km/giorno) NON è
       applicato come hard cap: è solo una stima UI mostrata al
       pianificatore come placeholder. Decisione 2026-05-02:
       l'utente vuole "indicativamente 700-1000 km/giorno" come
       riferimento, non come limite operativo del builder. Per cap
       hard reale, l'utente compila esplicitamente il campo regola.

    ``n_giornate_safety`` viene mantenuto come parametro per
    futura attivazione del cap di default (es. opzione "applica
    cap stimato"), oggi inutilizzato.
    """
    _ = n_giornate_safety  # reserved
    if regola.km_max_ciclo is not None:
        return float(regola.km_max_ciclo)
    if programma.km_max_ciclo is not None:
        return float(programma.km_max_ciclo)
    return None


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
    data_inizio: date | None = None,
    n_giornate: int | None = None,
    localita_codice: str,
    session: AsyncSession,
    azienda_id: int,
    force: bool = False,
    confirm_delete_pdc: bool = False,
    eseguito_da_user_id: int | None = None,
) -> BuilderResult:
    """Genera giri materiali end-to-end e li persiste.

    Pipeline:
    1. Carica programma + regole + località.
    2. Verifica programma ``stato='attivo'``.
    3. Risolve ``data_inizio`` / ``n_giornate`` (default Sprint 7.5
       MR 4 = periodo intero del programma, decisione utente C3).
    4. Verifica niente giri esistenti (o ``force=True`` → wipe).
    5. Carica corse del periodo, filtra per data, costruisci catene,
       posiziona su località, multi-giornata, assegnazione regole +
       eventi.
    6. Strict mode check.
    7. Genera ``numero_turno = "G-{LOC_BREVE}-{NNN}"``, persisti.

    Args:
        programma_id: id ``ProgrammaMateriale``.
        data_inizio: prima data del range. ``None`` = ``programma.valido_da``
            (Sprint 7.5 MR 4 default).
        n_giornate: numero giornate (>= 1). ``None`` = giornate fino a
            ``programma.valido_a`` inclusa (Sprint 7.5 MR 4 default,
            attiva il clustering A1 su tutto il calendario del
            programma).
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
    if n_giornate is not None and n_giornate < 1:
        raise ValueError(f"n_giornate deve essere >= 1, ricevuto {n_giornate}")

    # 1. Carica programma + regole + località
    programma = await _carica_programma(session, programma_id, azienda_id)
    if programma.stato != "attivo":
        raise ProgrammaNonAttivoError(programma_id, programma.stato)

    # Sprint 7.5 MR 4 (decisione utente C3): se i parametri non sono
    # specificati, default al periodo intero del programma. Il
    # clustering A1 (MR 1) emerge naturalmente solo con osservazione
    # sufficientemente ampia — periodo intero è la scelta canonica.
    data_inizio_eff: date = data_inizio if data_inizio is not None else programma.valido_da
    if n_giornate is None:
        n_giornate_eff = (programma.valido_a - data_inizio_eff).days + 1
        if n_giornate_eff < 1:
            raise PeriodoFuoriProgrammaError(
                f"data_inizio {data_inizio_eff.isoformat()} è oltre "
                f"programma.valido_a {programma.valido_a.isoformat()}."
            )
    else:
        n_giornate_eff = n_giornate

    # Sprint 7.3 fix: vincolo HARD su valido_da/valido_a del programma.
    # Quando i parametri vengono dal default (Sprint 7.5 MR 4), la
    # validazione passa banalmente (per costruzione coincidono).
    _valida_periodo_programma(programma, data_inizio_eff, n_giornate_eff)

    regole = await _carica_regole(session, programma_id)
    localita = await _carica_localita(session, localita_codice, azienda_id)
    whitelist = await _carica_whitelist_stazioni(session, localita.id)
    accoppiamenti = await _carica_accoppiamenti_ammessi(session)
    # Sprint 7.7 MR 3: festività per classificazione etichetta giro.
    festivita = await carica_festivita_periodo(
        session, azienda_id, programma.valido_da, programma.valido_a
    )
    # Entry 96: vincoli HARD applicati nel builder (non più nel POST regola).
    # Le corse incompatibili col materiale di una regola cadono come residue.
    from colazione.domain.vincoli import carica_vincoli

    vincoli_inviolabili = carica_vincoli()
    stazioni_lookup = await _carica_stazioni_lookup(session, azienda_id)

    def is_accoppiamento_ammesso(a: str, b: str) -> bool:
        """Lookup nella set degli accoppiamenti ammessi (Sprint 5.5).
        Coppie normalizzate lex dal chiamante."""
        return (a, b) in accoppiamenti

    # 2. Anti-rigenerazione SCOPED per (programma, sede) — Sprint 7.6 MR 3.1.
    # I giri delle ALTRE sedi del programma non sono toccati: il programma
    # è un turno materiale unico cumulativo che cresce sede-per-sede.
    n_esistenti_sede = await _count_giri_esistenti(
        session, programma_id, localita_id=localita.id
    )
    if n_esistenti_sede > 0:
        if not force:
            raise GiriEsistentiError(programma_id, localita_codice, n_esistenti_sede)
        # Sprint 7.9 strategy A (decisione utente 2026-05-04): se la
        # rigenerazione cancellerebbe turni PdC dipendenti, esige
        # conferma esplicita. Altrimenti il wipe esploderebbe sulla
        # FK turno_pdc_blocco.corsa_materiale_vuoto_id (RESTRICT).
        n_pdc, pdc_codici = await _conta_pdc_dipendenti(
            session, programma_id, localita_id=localita.id
        )
        if n_pdc > 0 and not confirm_delete_pdc:
            raise PdcDipendentiError(
                programma_id, localita_codice, n_pdc, pdc_codici
            )
        await _wipe_giri_programma(session, programma_id, localita_id=localita.id)

    # 3. Pipeline: carica corse + costruisci catene per data
    date_range = [data_inizio_eff + timedelta(days=i) for i in range(n_giornate_eff)]
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
    # Sprint 7.6 MR 3.3 (Fix B): se non c'è alcun giro persistito per
    # questa sede del programma, le catene del PRIMO giorno cronologico
    # sono "uscita reale dal deposito" — il vuoto sede→origine va
    # generato anche se la stazione di partenza è fuori whitelist
    # (non c'è una giornata K-1 del ciclo che abbia portato il treno
    # lì la sera prima).
    is_prima_generazione_sede = n_esistenti_sede == 0 or force
    primo_giorno_con_corse: date | None = None
    catene_per_data: dict[date, list[CatenaPosizionata]] = {}
    for d in date_range:
        corse_giorno = [c for c in corse_perimetro if _corsa_vale_in_data(c, d)]
        if not corse_giorno:
            continue
        if primo_giorno_con_corse is None:
            primo_giorno_con_corse = d
        forza_vuoto_iniziale = is_prima_generazione_sede and d == primo_giorno_con_corse
        catene = costruisci_catene(corse_giorno)
        catene_pos: list[CatenaPosizionata] = []
        for cat in catene:
            try:
                cat_pos = posiziona_su_localita(
                    cat,
                    localita,
                    whitelist,
                    param_pos,
                    forza_vuoto_iniziale=forza_vuoto_iniziale,
                )
            except (LocalitaSenzaStazioneError, PosizionamentoImpossibileError) as exc:
                warnings.append(f"Catena del {d.isoformat()} scartata: {exc}")
                continue
            catene_pos.append(cat_pos)
        catene_per_data[d] = catene_pos

    # 4. Multi-giornata (cross-notte) con cumulo km e chiusura dinamica.
    # Sprint 7.7 MR 1 (refactor cap-per-regola): per ogni catena calcolo
    # la regola dominante (priorità max che copre la prima corsa) e
    # raggruppo. Cap effettivo del giro = regola.km_max_ciclo OR
    # programma.km_max_ciclo (legacy) OR DEFAULT_KM_MEDIO_GIORNALIERO *
    # DEFAULT_N_GIORNATE_SAFETY (≈ 850 × 30 = 25500 km, fallback
    # ragionevole per "no cap esplicito"). Catene di regole diverse
    # NON si fondono cross-notte (= materiali diversi, convogli fisici
    # diversi).
    n_giornate_safety = max(programma.n_giornate_default, 30)
    catene_per_regola: dict[int, dict[date, list[CatenaPosizionata]]] = {}
    catene_orphane = 0
    for d_iter, catene_pos_iter in catene_per_data.items():
        for cp in catene_pos_iter:
            regola_dom = _trova_regola_dominante(cp, regole)
            if regola_dom is None:
                catene_orphane += 1
                continue
            per_data = catene_per_regola.setdefault(regola_dom.id, {})
            per_data.setdefault(d_iter, []).append(cp)
    if catene_orphane > 0:
        warnings.append(
            f"{catene_orphane} catene scartate: nessuna regola del programma copre la prima corsa."
        )

    giri_dom: list[Giro] = []
    n_corse_orfanate_troncamento = 0
    for regola_id, catene_per_d in catene_per_regola.items():
        regola = next(r for r in regole if r.id == regola_id)
        cap_effettivo = _calcola_cap_effettivo(
            regola, programma, n_giornate_safety
        )
        # Sprint 7.8 MR 2: range giornate per giro vincolato dal
        # programma. n_giornate_max è HARD cap, n_giornate_min è SOFT
        # floor (il loop preferisce continuare oltre la chiusura
        # ideale finché sotto min, salvo km_cap).
        param_mg = ParamMultiGiornata(
            n_giornate_max=programma.n_giornate_max,
            n_giornate_min=programma.n_giornate_min,
            km_max_ciclo=cap_effettivo,
            whitelist_sede=whitelist,
        )
        giri_regola = costruisci_giri_multigiornata(catene_per_d, param_mg)

        # Sprint 7.7 MR 1 hotfix Fix C2 (decisione utente 2026-05-02:
        # "dobbiamo sempre chiudere i giri"): per ogni giro che NON termina
        # in zona sede (whitelist), TRONCARE all'ultima giornata in
        # whitelist. Le giornate finali fuori whitelist vengono scartate
        # (corse perse) — combinato col vincolo "no vuoti lunghi" (Fix C
        # originale) garantisce che ogni giro persistito sia SEMPRE
        # chiuso naturalmente. Se nessuna giornata del giro termina in
        # whitelist → giro inutilizzabile (sede non coerente con regola).
        sede_codice = localita.stazione_collegata_codice
        for giro in giri_regola:
            if _giro_chiude_in_whitelist(giro, whitelist, sede_codice):
                giri_dom.append(giro)
                continue
            giro_troncato = _tronca_a_chiusura_whitelist(
                giro, whitelist, sede_codice
            )
            if giro_troncato is not None:
                n_giornate_perse = len(giro.giornate) - len(giro_troncato.giornate)
                n_corse_perse = sum(
                    len(g.catena_posizionata.catena.corse)
                    for g in giro.giornate[len(giro_troncato.giornate) :]
                )
                n_corse_orfanate_troncamento += n_corse_perse
                warnings.append(
                    f"Giro regola id={regola.id} ({regola.materiale_tipo_codice or '?'}): "
                    f"tagliate {n_giornate_perse} giornate finali "
                    f"({n_corse_perse} corse) per chiudere in zona sede."
                )
                giri_dom.append(giro_troncato)
            else:
                n_corse_perse = sum(
                    len(g.catena_posizionata.catena.corse) for g in giro.giornate
                )
                n_corse_orfanate_troncamento += n_corse_perse
                warnings.append(
                    f"Giro regola id={regola.id} ({regola.materiale_tipo_codice or '?'}) "
                    f"SCARTATO: nessuna giornata termina in zona sede {localita.codice} "
                    f"({n_corse_perse} corse non assegnate). La sede potrebbe non essere "
                    f"coerente con questa regola."
                )

    # 5. Assegnazione regole + eventi composizione (Sprint 5.5: validazione
    #    accoppiamenti via callback)
    giri_assegnati = assegna_e_rileva_eventi(
        giri_dom,
        regole,
        is_accoppiamento_ammesso,
        vincoli_inviolabili=vincoli_inviolabili,
        stazioni_lookup=stazioni_lookup,
    )

    # 6. Strict mode pre-persistenza (sui giri pre-aggregazione)
    _check_strict_mode(programma, giri_assegnati)

    # 6.4 Capacity-aware routing (Sprint 7.9 MR 11B Step 2, entry 121):
    #    ribilancia cluster A1 in base alla dotazione fisica
    #    (`materiale_dotazione_azienda`). Se una regola sfora i pezzi
    #    disponibili, i cluster con MENO km vengono spostati a regole
    #    alternative con capacity (decisione utente 2026-05-04). Cluster
    #    che nessuna regola può ospitare → scartati (corse residue +
    #    warning).
    dotazione = await carica_dotazione_per_azienda(session, azienda_id)
    giri_assegnati, giri_scartati_cap, warnings_cap = ribilancia_per_capacity(
        giri_assegnati,
        list(regole),
        dotazione,
        is_accoppiamento_ammesso,
    )
    warnings.extend(warnings_cap)
    # Date di applicazione perse (informativa per stat post-build).
    _ = aggrega_corse_residue_da_scartati(giri_scartati_cap)

    # 6.45 Sourcing thread agganci/sganci (Sprint 7.9 MR β2-3): per
    #     ogni evento composizione, cerca da DOVE arrivano i pezzi
    #     agganciati (= altre catene del giorno-sede che terminano
    #     stessa stazione entro 15min) e DOVE vanno quelli sganciati
    #     (= altre catene che ripartono). Se sourcing fallisce →
    #     fallback "deposito sede" + capacity check sulla dotazione
    #     azienda (warning se sforato).
    from colazione.domain.builder_giro.sourcing import arricchisci_sourcing

    giri_assegnati, warnings_src = arricchisci_sourcing(
        giri_assegnati, localita.codice_breve, dotazione
    )
    warnings.extend(warnings_src)

    # 6.5 Fusione cluster A1 simili (Sprint 7.9 MR 12, entry 114):
    #    riduce la frammentazione del clustering A1 fondendo cluster
    #    con sequenze simili (Jaccard ≥ 0.7) in cluster unificati.
    #    Modello target PDF Trenord 1134: poche varianti per giornata-K,
    #    ognuna con etichetta "tutto il periodo + eccezioni" — non
    #    centinaia di micro-cluster da 1 data ciascuno.
    giri_fusi = fonde_cluster_simili(giri_assegnati)

    # 7. Aggregazione A2 (Sprint 7.8 MR 2.5 + 7.9 MR 10 + 7.9 MR α):
    #    chiave (materiale, sede, n_giornate). Cluster A1 di lunghezze
    #    diverse → turni separati per costruzione (decisione utente
    #    2026-05-04: ogni turno deve essere coerente per ogni data,
    #    niente "ciclo non si estende qui"). Bin-packing per convogli
    #    paralleli resta intatto dentro ogni gruppo per chiave A2.
    giri_aggregati = aggrega_a2(giri_fusi)

    # 8. Genera numero_turno + persisti.
    # Sprint 7.7 MR 1 (Fix C "rientro intelligente"): genera_rientro_sede
    # è SEMPRE True; il persister decide in base alla destinazione
    # dell'ultima variante dell'ultima giornata (vedi persister.py).
    # Sprint 7.7 MR 4: numero_turno include il materiale.
    # Sprint 7.9 MR α: aggiunto suffisso `-{n_giornate}g` per
    # distinguere a colpo d'occhio turni di lunghezze diverse stesso
    # materiale+sede (es. G-FIO-001-ETR526-7g vs G-FIO-002-ETR526-1g).
    giri_da_persistere: list[GiroDaPersistere] = []
    for idx, giro_agg in enumerate(giri_aggregati, start=1):
        numero_turno = (
            f"G-{localita.codice_breve}-{idx:03d}-{giro_agg.materiale_tipo_codice}"
            f"-{len(giro_agg.giornate)}g"
        )
        giri_da_persistere.append(
            GiroDaPersistere(
                numero_turno=numero_turno,
                giro=giro_agg,
                genera_rientro_sede=True,
                whitelist_sede=whitelist,
            )
        )
    # Sprint 7.7 MR 3 reimpiegato (etichetta calcolata sull'AGGREGATO):
    # oggi non più persistita (modello varianti per giornata supersede
    # l'etichetta-su-giro). ``calcola_etichetta_giro`` resta esposta ma
    # inutilizzata in questo orchestrator. Le festività restano caricate
    # per consumi futuri (es. annotazioni varianti UI).
    _ = festivita  # noqa: F841 (reservato per uso futuro)
    _ = calcola_etichetta_giro  # noqa: F841 (export pubblico mantenuto)

    giro_ids = await persisti_giri(
        giri_da_persistere,
        session,
        programma_id,
        azienda_id,
        periodo_valido_da=programma.valido_da,
        periodo_valido_a=programma.valido_a,
    )
    await session.commit()

    # Sprint 7.9 MR β2-5: capacity check istante-per-istante (per
    # giorno) sui MaterialeThread appena proiettati. Aggiunge warning
    # specifici "CAPACITY ETR526: 12 pezzi simultanei in data 2026-06-07
    # (dotazione = 11)" al `BuilderResult`.
    from colazione.domain.builder_giro.capacity_temporale import (
        verifica_capacity_temporale,
    )

    warnings_cap_temp = await verifica_capacity_temporale(
        session, programma_id=programma_id, dotazione=dotazione
    )
    warnings.extend(warnings_cap_temp)

    # 9. Stats: sui giri AGGREGATI per il count "giri creati", e sui
    #    giri ASSEGNATI (pre-aggregazione) per metriche di produzione
    #    (corse processate, residue, eventi).
    n_corse_processate = sum(
        len(gg.blocchi_assegnati) for g in giri_assegnati for gg in g.giornate
    )
    n_corse_residue = sum(len(g.corse_residue) for g in giri_assegnati)
    n_giri_chiusi = sum(1 for g in giri_aggregati if g.chiuso)
    n_giri_non_chiusi = sum(1 for g in giri_aggregati if not g.chiuso)
    n_giri_km_cap = sum(1 for g in giri_aggregati if g.motivo_chiusura == "km_cap")
    n_eventi = sum(len(gg.eventi_composizione) for g in giri_assegnati for gg in g.giornate)
    n_incompat = sum(len(g.incompatibilita_materiale) for g in giri_assegnati)

    # Sprint 7.9 MR 11C (entry 116): persiste l'esito del run per
    # esposizione "Ultimo run del builder" + copertura PdE in UI.
    # Anche i run a 0 giri vengono persistiti (sono i più importanti
    # da diagnosticare via warnings).
    run = BuilderRun(
        programma_id=programma_id,
        azienda_id=azienda_id,
        localita_codice=localita_codice,
        eseguito_da_user_id=eseguito_da_user_id,
        n_giri_creati=len(giro_ids),
        n_giri_chiusi=n_giri_chiusi,
        n_giri_non_chiusi=n_giri_non_chiusi,
        n_corse_processate=n_corse_processate,
        n_corse_residue=n_corse_residue,
        n_eventi_composizione=n_eventi,
        n_incompatibilita_materiale=n_incompat,
        warnings_json=list(warnings),
        force=force,
    )
    session.add(run)
    await session.commit()

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
