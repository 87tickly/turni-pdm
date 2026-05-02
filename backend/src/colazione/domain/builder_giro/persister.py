"""Persister Sprint 4.4.5a — bridge dataclass dominio → ORM giri.

Funzione async che mappa una lista di `GiroAssegnato` (output della
pipeline pure 4.4.1→4.4.4) sulle entità ORM persistenti:

- ``GiroMateriale`` (top-level)
- ``GiroGiornata`` (1 per giornata)
- ``GiroVariante`` (1 per giornata, ``variant_index=0`` con
  ``validita_dates_apply_json=[giornata.data]`` — istanze 1:1)
- ``GiroBlocco`` (sequenza: vuoto_testa? + [evento? + corsa]* + vuoto_coda?)
- ``CorsaMaterialeVuoto`` (1 per ogni `BloccoMaterialeVuoto` testa/coda)

Spec: ``docs/SCHEMA-DATI-NATIVO.md`` §5 (entità giro), ``docs/PROGRAMMA-MATERIALE.md``
§5.4 (eventi composizione persistenza).

Limiti del sub-sprint 4.4.5a:

- **Solo INSERT**: niente UPDATE/DELETE. Se chiamato su programma con
  giri già persistiti, li affianca. La strategia di rigenerazione
  (errore 409 senza ``?force=true``) è in 4.4.5b.
- **`numero_turno` è parametro**: il persister non sa come si chiamano
  i giri. La convenzione ``G-{LOC_BREVE}-{SEQ:03d}`` è in 4.4.5b.
- **Istanze 1:1**: ogni `GiroVariante` ha ``validita_dates_apply_json``
  con UNA sola data (giornata.data). Pattern ricorrenza è scope futuro.
- **Niente commit**: il persister fa solo `add` + `flush`. Il caller
  (4.4.5b) decide quando committare la transazione.

Si **assume** che ogni ``corsa`` in `BloccoAssegnato.corsa` sia un ORM
``CorsaCommerciale`` con `.id` valorizzato (caricato dal loader 4.4.5b).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.domain.builder_giro.composizione import (
    EventoComposizione,
    GiornataAssegnata,
    GiroAssegnato,
)
from colazione.domain.builder_giro.posizionamento import BloccoMaterialeVuoto
from colazione.models.anagrafica import LocalitaManutenzione
from colazione.models.corse import CorsaMaterialeVuoto
from colazione.models.giri import (
    GiroBlocco,
    GiroGiornata,
    GiroMateriale,
    GiroVariante,
)

# Versione persister, salvata in `generation_metadata_json` per
# tracciabilità (utile quando bumperemo l'algoritmo).
PERSISTER_VERSION = "4.4.5a"


# =====================================================================
# Errori
# =====================================================================


class LocalitaNonTrovataError(LookupError):
    """La località riferita da ``GiroAssegnato.localita_codice`` non
    esiste nel DB per l'azienda data.

    Indica errore di config: il programma materiale ha generato giri
    per una località che non è in anagrafica. Va corretta config o
    aggiunta la località prima di rigenerare.
    """

    def __init__(self, codice: str, azienda_id: int) -> None:
        super().__init__(
            f"Località manutenzione {codice!r} non trovata per "
            f"azienda_id={azienda_id}. Verifica anagrafica."
        )
        self.codice = codice
        self.azienda_id = azienda_id


# =====================================================================
# Input dataclass
# =====================================================================


@dataclass(frozen=True)
class GiroDaPersistere:
    """Coppia ``(numero_turno, GiroAssegnato)`` da persistere.

    Il caller (4.4.5b loader) genera il ``numero_turno`` con la
    convenzione ``G-{LOC_BREVE}-{SEQ:03d}``. Il persister lo accetta
    come opaco.

    Sprint 5.6 Feature 4: ``genera_rientro_sede`` (default False) attiva
    la creazione automatica della corsa virtuale 9XXXX a fine giro
    quando ``motivo_chiusura='naturale'`` e l'ultima dest != stazione
    collegata sede. Settato a True dal builder.py orchestrator nel
    "modo dinamico" (programma con km_max_ciclo configurato).
    """

    numero_turno: str
    giro: GiroAssegnato
    genera_rientro_sede: bool = False


# =====================================================================
# Helpers privati
# =====================================================================


async def _carica_localita(
    session: AsyncSession, codice: str, azienda_id: int
) -> LocalitaManutenzione:
    stmt = (
        select(LocalitaManutenzione)
        .where(
            LocalitaManutenzione.codice == codice,
            LocalitaManutenzione.azienda_id == azienda_id,
        )
        .limit(1)
    )
    loc = (await session.execute(stmt)).scalar_one_or_none()
    if loc is None:
        raise LocalitaNonTrovataError(codice, azienda_id)
    return loc


def _km_totali_giro(giro: GiroAssegnato) -> float:
    """Somma ``km_tratta`` di tutte le corse di tutte le giornate del giro.

    Sprint 5.6 (km fondamentali): popola ``GiroMateriale.km_media_giornaliera``.
    Conta SOLO le corse commerciali (i vuoti tecnici non hanno km del PdE).
    Corse senza ``km_tratta`` contribuiscono 0 (duck-typed).
    """
    total = 0.0
    for giornata in giro.giornate:
        total += _km_giornata(giornata)
    return total


def _km_giornata(giornata: GiornataAssegnata) -> float:
    """Somma ``km_tratta`` delle corse commerciali di una singola giornata.

    Sprint 7.6 MR 3.2 (migration 0013): popola
    ``GiroGiornata.km_giornata`` per il riepilogo per-giornata nella
    vista dettaglio del giro. Stessa convenzione di `_km_totali_giro`
    (vuoti tecnici esclusi, corse senza km contribuiscono 0).
    """
    total = 0.0
    for c in giornata.catena_posizionata.catena.corse:
        km = getattr(c, "km_tratta", None)
        if km is not None:
            total += float(km)
    return total


def _estrai_validita_giornata(
    giornata: GiornataAssegnata,
) -> tuple[str, list[str]]:
    """Estrae validità testuale + date concrete applicabili a una giornata.

    **Testo** (``validita_testo``): ``periodicita_breve`` della prima
    corsa della giornata che ne abbia una valorizzata, oppure ``"GG"``
    fallback. Coerente con feedback utente "PdE testo Periodicità =
    verità letterale" (memoria persistente
    ``feedback_pde_periodicita_verita.md``): mostriamo letteralmente
    quello che il PdE dice, niente parser DSL.

    **Date** (``validita_dates_apply_json``): Sprint 7.5 (refactor bug 5
    MR 3) — usa ``giornata.dates_apply_or_data``, che dopo il
    clustering A1 (MR 1) contiene le date REALI in cui la giornata-
    tipo si applica (= date di partenza dei filoni del cluster).
    Pre-cluster fallback a ``(giornata.data,)`` via property.

    Vecchia logica (pre-MR 3) calcolava l'intersezione di
    ``valido_in_date_json`` di tutte le corse della giornata,
    "menzogna" perché:

    1. Le corse possono essere valide in date in cui la SEQUENZA
       (con la specifica cross-notte) non lo è.
    2. Non considera che giornata k+1 può essere valida in un
       sottoinsieme delle date di giornata k.
    3. Una corsa valida in 365 giorni non implica che la giornata
       in cui appare sia valida in 365 giorni.

    Il dato post-cluster è **per costruzione** corretto: contiene
    tutte e sole le date in cui il pattern intero del giro
    (sequenza A1-strict di catene cross-notte) è realizzato.

    Returns:
        Coppia ``(testo, dates_iso)``. ``testo`` è String/Text
        compatibile con ``GiroVariante.validita_testo``. ``dates_iso``
        è lista ordinata di stringhe ``YYYY-MM-DD``.
    """
    corse = giornata.catena_posizionata.catena.corse
    if not corse:
        return ("GG", [giornata.data.isoformat()])

    testo = "GG"
    for c in corse:
        p = getattr(c, "periodicita_breve", None)
        if p is not None and str(p).strip():
            testo = str(p).strip()
            break

    # Sprint 7.5 (MR 3): leggi le date dal pass-through del clustering A1
    # invece di calcolare un'intersezione "menzogna" sulle valido_in_date
    # delle singole corse. `dates_apply_or_data` torna `(giornata.data,)`
    # se il clustering non è stato applicato (es. test diretti del
    # persister con GiornataAssegnata costruita a mano), preservando il
    # comportamento legacy con singola data.
    dates_iso = [d.isoformat() for d in giornata.dates_apply_or_data]
    return (testo, sorted(set(dates_iso)))


def _km_media_annua_giro(
    giro: GiroAssegnato,
    valido_da: date,
    valido_a: date,
) -> float | None:
    """Stima km annui del giro materiale (Sprint 5.6 R3).

    Algoritmo:
    1. Per ogni giornata K del giro, prendi la prima corsa e leggi il
       suo ``valido_in_date_json`` (lista di date in cui la corsa è
       applicabile).
    2. Conta le date che cadono nel periodo
       ``[valido_da, valido_a]`` del programma → ``n_giorni_K``.
    3. Stima km annui di K = ``km_giornata_K * n_giorni_K``.
    4. Somma su tutte le giornate.

    Approssimazione: assume che la prima corsa di K sia
    rappresentativa della periodicità di tutta la giornata. Per
    giornate con corse a periodicità mista, è una stima al rialzo
    o al ribasso a seconda del mix. Sufficiente per dashboard
    manutenzione (Sprint 7); raffinabile.

    Returns:
        Stima `float` km/anno del giro. ``None`` se nessuna corsa
        ha ``valido_in_date_json``, oppure se nessuna data cade in
        ``[valido_da, valido_a]``.
    """
    valido_da_iso = valido_da.isoformat()
    valido_a_iso = valido_a.isoformat()
    km_anno = 0.0
    qualcosa_calcolato = False
    for giornata in giro.giornate:
        corse = giornata.catena_posizionata.catena.corse
        if not corse:
            continue
        prima = corse[0]
        valido_dates = getattr(prima, "valido_in_date_json", None)
        if not valido_dates:
            continue
        n_giorni = sum(1 for d in valido_dates if valido_da_iso <= str(d) <= valido_a_iso)
        if n_giorni == 0:
            continue
        km_giornata = sum(
            float(c.km_tratta) for c in corse if getattr(c, "km_tratta", None) is not None
        )
        km_anno += km_giornata * n_giorni
        qualcosa_calcolato = True

    return km_anno if qualcosa_calcolato else None


async def _next_numero_rientro_sede(session: AsyncSession) -> str:
    """Prossimo `numero_treno_vuoto` per la corsa rientro a sede.

    Sprint 5.6 Feature 4: convenzione **5 cifre, prefisso 9** (placeholder
    Trenord; in produzione RFI/FNM emette i numeri reali). Sequenziale
    globale su `corsa_materiale_vuoto` (lookup MAX numero_treno_vuoto
    matching ``9NNNN``).
    """
    from sqlalchemy import text

    stmt = text(
        "SELECT COALESCE(MAX(SUBSTRING(numero_treno_vuoto FROM 2)::int), 0) "
        "FROM corsa_materiale_vuoto "
        "WHERE numero_treno_vuoto ~ '^9[0-9]{4}$'"
    )
    last = (await session.execute(stmt)).scalar_one()
    return f"9{(int(last) + 1):04d}"


def _primo_tipo_materiale(giro: GiroAssegnato) -> str | None:
    """Primo ``materiale_tipo_codice`` usato dal giro, ``None`` se nessun
    blocco assegnato (giro tutto in corse residue).

    Sprint 5.5: legge il primo elemento della ``composizione`` del primo
    blocco. Per regole single-material la lista ha 1 elemento; per
    composizioni doppie prende il primo (es. ETR526 da [ETR526, ETR425]).
    Usato per popolare ``GiroMateriale.tipo_materiale`` (denormalizzato
    leggibile per UI).
    """
    for giornata in giro.giornate:
        for blocco in giornata.blocchi_assegnati:
            if blocco.assegnazione.composizione:
                return blocco.assegnazione.composizione[0].materiale_tipo_codice
    return None


def _build_metadata_giro(
    numero_turno: str, programma_id: int, giro: GiroAssegnato
) -> dict[str, Any]:
    """Metadata di tracciabilità salvati su ``generation_metadata_json``.

    Permette debug/audit: chi ha generato il giro, con quale algoritmo,
    quando, con quanti warning.
    """
    return {
        "persister_version": PERSISTER_VERSION,
        "generato_at": datetime.now(UTC).isoformat(),
        "numero_turno": numero_turno,
        "programma_id": programma_id,
        "motivo_chiusura": giro.motivo_chiusura,
        "chiuso": giro.chiuso,
        "n_corse_residue": len(giro.corse_residue),
        "n_incompatibilita_materiale": len(giro.incompatibilita_materiale),
    }


def _build_metadata_evento(ev: EventoComposizione) -> dict[str, Any]:
    """Metadata di un blocco aggancio/sgancio (vedi PROGRAMMA-MATERIALE.md §5.4).

    Sprint 5.5: include ``materiale_tipo_codice`` per identificare quale
    rotabile entra/esce nell'evento (utile per editor giro UI).
    """
    return {
        "materiale_tipo_codice": ev.materiale_tipo_codice,
        "pezzi_delta": ev.pezzi_delta,
        "note_builder": ev.note_builder,
        "stazione_proposta_originale": ev.stazione_proposta,
        # `stazione_finale` parte uguale all'originale; l'editor giro
        # la cambia se l'utente sposta l'evento in un'altra stazione.
        "stazione_finale": ev.stazione_proposta,
    }


async def _crea_corsa_materiale_vuoto(
    blocco_vuoto: BloccoMaterialeVuoto,
    giro_materiale_id: int,
    azienda_id: int,
    numero_turno: str,
    seq_vuoto_giro: int,
    session: AsyncSession,
) -> int:
    """Inserisce ``CorsaMaterialeVuoto`` ORM e ritorna il suo id.

    ``numero_treno_vuoto`` è generato come ``V-{numero_turno}-{NNN}``.
    """
    cmv = CorsaMaterialeVuoto(
        azienda_id=azienda_id,
        numero_treno_vuoto=f"V-{numero_turno}-{seq_vuoto_giro:03d}",
        codice_origine=blocco_vuoto.codice_origine,
        codice_destinazione=blocco_vuoto.codice_destinazione,
        ora_partenza=blocco_vuoto.ora_partenza,
        ora_arrivo=blocco_vuoto.ora_arrivo,
        min_tratta=None,  # stima non disponibile in 4.4.2
        km_tratta=None,
        origine="generato_da_giro_materiale",
        giro_materiale_id=giro_materiale_id,
        valido_in_date_json=[],
        valido_da=None,
        valido_a=None,
    )
    session.add(cmv)
    await session.flush()
    cmv_id: int = cmv.id
    return cmv_id


async def _persisti_blocchi_giornata(
    giornata: GiornataAssegnata,
    giro_variante_id: int,
    giro_materiale_id: int,
    azienda_id: int,
    numero_turno: str,
    seq_vuoto_giro_inizio: int,
    session: AsyncSession,
) -> tuple[int, int]:
    """Persiste i blocchi della giornata in ordine sequenziale.

    Sequenza: ``vuoto_testa? → [evento? → corsa]* → vuoto_coda?``.

    Returns:
        ``(seq_vuoto_giro, seq_blocco_next)``. ``seq_vuoto_giro``
        aggiornato (incrementa di 0/1/2 a seconda dei vuoti generati).
        ``seq_blocco_next`` è il prossimo seq libero dentro la variante
        (utile per inserire blocchi extra come il rientro 9XXXX dopo).
    """
    seq_blocco = 1  # progressivo dentro la giro_variante (CHECK seq >= 1)
    seq_vuoto = seq_vuoto_giro_inizio  # progressivo per CorsaMaterialeVuoto del giro
    cat_pos = giornata.catena_posizionata

    # ---- Vuoto di testa ----
    if cat_pos.vuoto_testa is not None:
        cmv_id = await _crea_corsa_materiale_vuoto(
            cat_pos.vuoto_testa,
            giro_materiale_id,
            azienda_id,
            numero_turno,
            seq_vuoto,
            session,
        )
        seq_vuoto += 1
        session.add(
            GiroBlocco(
                giro_variante_id=giro_variante_id,
                seq=seq_blocco,
                tipo_blocco="materiale_vuoto",
                corsa_commerciale_id=None,
                corsa_materiale_vuoto_id=cmv_id,
                stazione_da_codice=cat_pos.vuoto_testa.codice_origine,
                stazione_a_codice=cat_pos.vuoto_testa.codice_destinazione,
                ora_inizio=cat_pos.vuoto_testa.ora_partenza,
                ora_fine=cat_pos.vuoto_testa.ora_arrivo,
                descrizione=(
                    f"Vuoto testa{' (uscita serale K-1)' if cat_pos.vuoto_testa.cross_notte_giorno_precedente else ''}: "
                    f"{cat_pos.vuoto_testa.codice_origine} "
                    f"→ {cat_pos.vuoto_testa.codice_destinazione}"
                ),
                is_validato_utente=True,
                metadata_json={
                    "motivo": cat_pos.vuoto_testa.motivo,
                    # Sprint 5.6 R2: il vuoto è materializzato la sera prima
                    # (es. parte 23:30 di K-1) per essere pronto a inizio
                    # servizio di K. Solo per vuoti di USCITA dal deposito.
                    "cross_notte_giorno_precedente": cat_pos.vuoto_testa.cross_notte_giorno_precedente,
                },
            )
        )
        seq_blocco += 1

    # ---- Eventi composizione: indicizzati per "posizione_dopo_blocco" ----
    eventi_per_pos = {e.posizione_dopo_blocco: e for e in giornata.eventi_composizione}

    # ---- Blocchi corsa con eventi inseriti PRIMA del blocco corrente ----
    for idx, blocco in enumerate(giornata.blocchi_assegnati):
        # Evento "dopo blocco idx-1" → va inserito PRIMA del blocco idx
        if (idx - 1) in eventi_per_pos:
            ev = eventi_per_pos[idx - 1]
            session.add(
                GiroBlocco(
                    giro_variante_id=giro_variante_id,
                    seq=seq_blocco,
                    tipo_blocco=ev.tipo,  # 'aggancio' | 'sgancio'
                    corsa_commerciale_id=None,
                    corsa_materiale_vuoto_id=None,
                    stazione_da_codice=ev.stazione_proposta,
                    stazione_a_codice=ev.stazione_proposta,
                    ora_inizio=blocco.corsa.ora_partenza,
                    ora_fine=blocco.corsa.ora_partenza,
                    descrizione=ev.note_builder,
                    # is_validato_utente=False: PROPOSTA del builder, va
                    # confermata in editor giro UI (PROGRAMMA-MATERIALE.md §5.2).
                    is_validato_utente=ev.is_validato_utente,
                    metadata_json=_build_metadata_evento(ev),
                )
            )
            seq_blocco += 1

        # Blocco corsa commerciale
        session.add(
            GiroBlocco(
                giro_variante_id=giro_variante_id,
                seq=seq_blocco,
                tipo_blocco="corsa_commerciale",
                corsa_commerciale_id=blocco.corsa.id,
                corsa_materiale_vuoto_id=None,
                stazione_da_codice=blocco.corsa.codice_origine,
                stazione_a_codice=blocco.corsa.codice_destinazione,
                ora_inizio=blocco.corsa.ora_partenza,
                ora_fine=blocco.corsa.ora_arrivo,
                descrizione=str(blocco.corsa.numero_treno),
                is_validato_utente=True,
                metadata_json={
                    # Sprint 5.5: composizione completa serializzata,
                    # sostituisce i campi singoli legacy.
                    "composizione": [
                        {
                            "materiale_tipo_codice": item.materiale_tipo_codice,
                            "n_pezzi": item.n_pezzi,
                        }
                        for item in blocco.assegnazione.composizione
                    ],
                    "is_composizione_manuale": blocco.assegnazione.is_composizione_manuale,
                    "regola_id": blocco.assegnazione.regola_id,
                },
            )
        )
        seq_blocco += 1

    # ---- Vuoto di coda ----
    if cat_pos.vuoto_coda is not None:
        cmv_id = await _crea_corsa_materiale_vuoto(
            cat_pos.vuoto_coda,
            giro_materiale_id,
            azienda_id,
            numero_turno,
            seq_vuoto,
            session,
        )
        seq_vuoto += 1
        session.add(
            GiroBlocco(
                giro_variante_id=giro_variante_id,
                seq=seq_blocco,
                tipo_blocco="materiale_vuoto",
                corsa_commerciale_id=None,
                corsa_materiale_vuoto_id=cmv_id,
                stazione_da_codice=cat_pos.vuoto_coda.codice_origine,
                stazione_a_codice=cat_pos.vuoto_coda.codice_destinazione,
                ora_inizio=cat_pos.vuoto_coda.ora_partenza,
                ora_fine=cat_pos.vuoto_coda.ora_arrivo,
                descrizione=(
                    f"Vuoto coda: {cat_pos.vuoto_coda.codice_origine} "
                    f"→ {cat_pos.vuoto_coda.codice_destinazione}"
                ),
                is_validato_utente=True,
                metadata_json={"motivo": cat_pos.vuoto_coda.motivo},
            )
        )
        seq_blocco += 1

    await session.flush()
    return seq_vuoto, seq_blocco


async def _persisti_un_giro(
    entry: GiroDaPersistere,
    session: AsyncSession,
    programma_id: int,
    azienda_id: int,
    *,
    periodo_valido_da: date | None = None,
    periodo_valido_a: date | None = None,
) -> int:
    """Persiste un singolo giro: GiroMateriale + giornate + varianti + blocchi.

    Sprint 5.6:
    - Popola ``km_media_giornaliera`` (Feature 2): somma km_tratta /
      numero_giornate.
    - Se ``motivo_chiusura='naturale'`` E l'ultima corsa NON arriva alla
      ``stazione_collegata`` della sede, aggiunge un blocco
      ``materiale_vuoto`` con numero ``9NNNN`` (placeholder rientro
      manutentivo, Feature 4).
    """
    loc = await _carica_localita(session, entry.giro.localita_codice, azienda_id)
    materiale_tipo = _primo_tipo_materiale(entry.giro)

    n_giornate = len(entry.giro.giornate)
    km_totali = _km_totali_giro(entry.giro)
    km_media_giornaliera = round(km_totali / n_giornate, 2) if n_giornate > 0 else 0.0

    # Sprint 5.6 R3: km_media_annua = intersezione `valido_in_date_json`
    # delle prime corse di ogni giornata × km giornaliera. Richiede il
    # periodo del programma (fornito dal builder.py orchestrator).
    km_media_annua: float | None = None
    if periodo_valido_da is not None and periodo_valido_a is not None:
        km_media_annua = _km_media_annua_giro(
            entry.giro, periodo_valido_da, periodo_valido_a
        )

    gm = GiroMateriale(
        azienda_id=azienda_id,
        programma_id=programma_id,
        numero_turno=entry.numero_turno,
        validita_codice=None,
        tipo_materiale=materiale_tipo if materiale_tipo is not None else "MISTO",
        descrizione_materiale=None,
        materiale_tipo_codice=materiale_tipo,
        numero_giornate=n_giornate,
        km_media_giornaliera=km_media_giornaliera,
        km_media_annua=km_media_annua,
        posti_1cl=0,
        posti_2cl=0,
        localita_manutenzione_partenza_id=loc.id,
        localita_manutenzione_arrivo_id=loc.id,
        stato="bozza",
        generation_metadata_json=_build_metadata_giro(entry.numero_turno, programma_id, entry.giro),
    )
    session.add(gm)
    await session.flush()
    gm_id: int = gm.id

    seq_vuoto_giro = 0  # progressivo per CorsaMaterialeVuoto del giro intero
    last_gv_id: int | None = None
    last_seq_blocco: int = 1
    for idx, giornata in enumerate(entry.giro.giornate, start=1):
        km_g = _km_giornata(giornata)
        gg = GiroGiornata(
            giro_materiale_id=gm_id,
            numero_giornata=idx,
            km_giornata=round(km_g, 2) if km_g > 0 else None,
        )
        session.add(gg)
        await session.flush()

        # Sprint 7.3 fix periodicità: estrai validità dalla prima corsa
        # della giornata e dall'intersezione di `valido_in_date_json`.
        # Il testo è la `periodicita_breve` (verità letterale del PdE,
        # niente parser DSL); le date sono il set di giorni calendario
        # in cui questa stessa sequenza di blocchi è effettivamente
        # valida (intersezione di tutte le corse della giornata).
        testo_val, dates_val = _estrai_validita_giornata(giornata)
        gv = GiroVariante(
            giro_giornata_id=gg.id,
            variant_index=0,
            validita_testo=testo_val,
            validita_dates_apply_json=dates_val,
            validita_dates_skip_json=[],
        )
        session.add(gv)
        await session.flush()
        last_gv_id = gv.id

        seq_vuoto_giro, last_seq_blocco = await _persisti_blocchi_giornata(
            giornata,
            gv.id,
            gm_id,
            azienda_id,
            entry.numero_turno,
            seq_vuoto_giro,
            session,
        )

    # Sprint 5.6 Feature 4: corsa rientro a sede 9XXXX. Si attiva solo se
    # il caller ha richiesto esplicitamente (`genera_rientro_sede=True`,
    # tipico modo dinamico) e la chiusura è naturale e non si è già a
    # destinazione sede.
    if (
        entry.genera_rientro_sede
        and entry.giro.motivo_chiusura == "naturale"
        and last_gv_id is not None
        and loc.stazione_collegata_codice is not None
    ):
        ultima_giornata = entry.giro.giornate[-1]
        ultima_corsa = ultima_giornata.catena_posizionata.catena.corse[-1]
        ultima_dest = ultima_corsa.codice_destinazione
        if ultima_dest != loc.stazione_collegata_codice:
            await _crea_blocco_rientro_sede(
                session=session,
                giro_variante_id=last_gv_id,
                giro_materiale_id=gm_id,
                azienda_id=azienda_id,
                seq=last_seq_blocco,
                stazione_da=ultima_dest,
                stazione_a=loc.stazione_collegata_codice,
                ora_inizio=ultima_corsa.ora_arrivo,
            )

    return gm_id


async def _crea_blocco_rientro_sede(
    *,
    session: AsyncSession,
    giro_variante_id: int,
    giro_materiale_id: int,
    azienda_id: int,
    seq: int,
    stazione_da: str,
    stazione_a: str,
    ora_inizio: Any,
) -> None:
    """Crea CorsaMaterialeVuoto + GiroBlocco per il rientro 9XXXX a sede.

    Sprint 5.6 Feature 4: convenzione Trenord placeholder
    (5 cifre, prefisso 9). Si appoggia all'ultima variante dell'ultima
    giornata come blocco aggiuntivo dopo la coda commerciale.
    """
    from datetime import time as _time

    numero = await _next_numero_rientro_sede(session)
    # Per `ora_arrivo` non abbiamo stima: usiamo ora_inizio + 30' come
    # default (sostituibile dal pianificatore in editor giro).
    h, m = ora_inizio.hour, ora_inizio.minute
    arrivo_min = (h * 60 + m + 30) % (24 * 60)
    ora_fine = _time(arrivo_min // 60, arrivo_min % 60)

    cmv = CorsaMaterialeVuoto(
        azienda_id=azienda_id,
        numero_treno_vuoto=numero,
        codice_origine=stazione_da,
        codice_destinazione=stazione_a,
        ora_partenza=ora_inizio,
        ora_arrivo=ora_fine,
        min_tratta=30,
        km_tratta=None,
        origine="generato_da_giro_materiale",
        giro_materiale_id=giro_materiale_id,
        valido_in_date_json=[],
        valido_da=None,
        valido_a=None,
    )
    session.add(cmv)
    await session.flush()

    session.add(
        GiroBlocco(
            giro_variante_id=giro_variante_id,
            seq=seq,
            tipo_blocco="materiale_vuoto",
            corsa_commerciale_id=None,
            corsa_materiale_vuoto_id=cmv.id,
            stazione_da_codice=stazione_da,
            stazione_a_codice=stazione_a,
            ora_inizio=ora_inizio,
            ora_fine=ora_fine,
            descrizione=f"Rientro sede {numero}: {stazione_da} → {stazione_a}",
            is_validato_utente=False,  # placeholder, RFI/FNM emette numero reale
            metadata_json={"motivo": "rientro_sede", "numero_treno_placeholder": numero},
        )
    )
    await session.flush()


# =====================================================================
# API pubblica
# =====================================================================


async def persisti_giri(
    giri_da_persistere: list[GiroDaPersistere],
    session: AsyncSession,
    programma_id: int,
    azienda_id: int,
    *,
    periodo_valido_da: date | None = None,
    periodo_valido_a: date | None = None,
) -> list[int]:
    """Persiste una lista di giri assegnati nel DB. Ritorna i loro ``id``.

    Algoritmo:

    1. Per ogni giro: crea ``GiroMateriale`` + N ``GiroGiornata`` +
       N ``GiroVariante`` + M ``GiroBlocco`` (sequenza:
       ``vuoto_testa? → [evento? → corsa]* → vuoto_coda?``) +
       eventuali ``CorsaMaterialeVuoto``.
    2. Il persister fa solo ``add`` + ``flush``: **nessun commit**.
       Il caller (4.4.5b) gestisce la transazione.

    Args:
        giri_da_persistere: lista di ``GiroDaPersistere`` (numero_turno
            generato dal caller + ``GiroAssegnato`` dalla pipeline pure).
        session: ``AsyncSession`` SQLAlchemy.
        programma_id: id del ``ProgrammaMateriale`` di riferimento (per
            tracciabilità in metadata).
        azienda_id: id dell'``Azienda`` (per FK su località e vuoti).

    Returns:
        Lista ``GiroMateriale.id`` creati (nello stesso ordine
        dell'input).

    Raises:
        LocalitaNonTrovataError: località riferita non esiste in
            anagrafica per quell'azienda.
    """
    if not giri_da_persistere:
        return []

    giro_ids: list[int] = []
    for entry in giri_da_persistere:
        gid = await _persisti_un_giro(
            entry,
            session,
            programma_id,
            azienda_id,
            periodo_valido_da=periodo_valido_da,
            periodo_valido_a=periodo_valido_a,
        )
        giro_ids.append(gid)
    return giro_ids
