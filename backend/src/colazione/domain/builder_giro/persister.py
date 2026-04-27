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
from datetime import UTC, datetime
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
    """

    numero_turno: str
    giro: GiroAssegnato


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
) -> int:
    """Persiste i blocchi della giornata in ordine sequenziale.

    Sequenza: ``vuoto_testa? → [evento? → corsa]* → vuoto_coda?``.

    Returns:
        ``seq_vuoto_giro`` aggiornato (incrementa di 0/1/2 a seconda
        dei vuoti generati). Serve al caller per nominare i vuoti
        successivi senza collisioni.
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
                    f"Vuoto testa: {cat_pos.vuoto_testa.codice_origine} "
                    f"→ {cat_pos.vuoto_testa.codice_destinazione}"
                ),
                is_validato_utente=True,
                metadata_json={"motivo": cat_pos.vuoto_testa.motivo},
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
    return seq_vuoto


async def _persisti_un_giro(
    entry: GiroDaPersistere,
    session: AsyncSession,
    programma_id: int,
    azienda_id: int,
) -> int:
    """Persiste un singolo giro: GiroMateriale + giornate + varianti + blocchi."""
    loc = await _carica_localita(session, entry.giro.localita_codice, azienda_id)
    materiale_tipo = _primo_tipo_materiale(entry.giro)

    gm = GiroMateriale(
        azienda_id=azienda_id,
        numero_turno=entry.numero_turno,
        validita_codice=None,
        # `tipo_materiale` (TEXT obbligatorio) è denormalizzazione
        # leggibile (es. "ALe711") usata per UI/report. La FK reale è
        # `materiale_tipo_codice`. Se nessun blocco è assegnato (giro
        # tutto in residue) usiamo il placeholder "MISTO".
        tipo_materiale=materiale_tipo if materiale_tipo is not None else "MISTO",
        descrizione_materiale=None,
        materiale_tipo_codice=materiale_tipo,
        numero_giornate=len(entry.giro.giornate),
        km_media_giornaliera=None,  # calcolo km è scope 4.4.5b/futuro
        km_media_annua=None,
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
    for idx, giornata in enumerate(entry.giro.giornate, start=1):
        gg = GiroGiornata(giro_materiale_id=gm_id, numero_giornata=idx)
        session.add(gg)
        await session.flush()

        gv = GiroVariante(
            giro_giornata_id=gg.id,
            variant_index=0,
            validita_testo="GG",  # placeholder; pattern in scope futuro
            validita_dates_apply_json=[giornata.data.isoformat()],
            validita_dates_skip_json=[],
        )
        session.add(gv)
        await session.flush()

        seq_vuoto_giro = await _persisti_blocchi_giornata(
            giornata,
            gv.id,
            gm_id,
            azienda_id,
            entry.numero_turno,
            seq_vuoto_giro,
            session,
        )

    return gm_id


# =====================================================================
# API pubblica
# =====================================================================


async def persisti_giri(
    giri_da_persistere: list[GiroDaPersistere],
    session: AsyncSession,
    programma_id: int,
    azienda_id: int,
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
        gid = await _persisti_un_giro(entry, session, programma_id, azienda_id)
        giro_ids.append(gid)
    return giro_ids
