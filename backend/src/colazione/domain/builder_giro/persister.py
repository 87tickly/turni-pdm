"""Persister — bridge dataclass dominio → ORM giri.

Sprint 7.7 MR 5 (decisione utente "B1"): scrive ``GiroAggregato``
(output di ``aggregazione_a2``) sulle entità ORM:

- ``GiroMateriale`` (top-level, 1 per chiave A2)
- ``GiroGiornata`` (1 per numero giornata 1..N)
- ``GiroVariante`` (1+ per giornata, ognuna con la sua sequenza di
  blocchi e ``dates_apply``)
- ``GiroBlocco`` (sequenza per variante: ``vuoto_testa? → [evento? →
  corsa]* → vuoto_coda? → eventuale rientro 9XXXX``)
- ``CorsaMaterialeVuoto`` (1 per ogni vuoto tecnico)

Spec: ``docs/SCHEMA-DATI-NATIVO.md`` §5,
``docs/PROGRAMMA-MATERIALE.md`` §5.4.

Limiti:

- **Solo INSERT**: niente UPDATE/DELETE. Il caller (``builder.py``) si
  occupa del wipe pre-rigenerazione.
- **`numero_turno` è parametro**: il persister non sa come si chiamano
  i giri. La convenzione ``G-{LOC_BREVE}-{SEQ:03d}-{MAT}`` è nel
  caller (Sprint 7.7 MR 4).
- **Niente commit**: ``add`` + ``flush`` solo. Il caller gestisce la
  transazione.

Helper ``wrap_assegnato_in_aggregato()`` esposto per i test diretti
del persister che operano con un singolo ``GiroAssegnato``: lo
trasforma in ``GiroAggregato`` con 1 sola variante per giornata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.domain.builder_giro.aggregazione_a2 import (
    GiornataAggregata,
    GiroAggregato,
    VarianteGiornata,
)
from colazione.domain.builder_giro.composizione import (
    EventoComposizione,
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
# tracciabilità.
PERSISTER_VERSION = "7.7.5"


# =====================================================================
# Errori
# =====================================================================


class LocalitaNonTrovataError(LookupError):
    """La località riferita da ``GiroAggregato.localita_codice`` non
    esiste nel DB per l'azienda data."""

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
    """Coppia ``(numero_turno, GiroAggregato)`` da persistere.

    Il caller (``builder.py``) genera il ``numero_turno`` nel formato
    ``G-{LOC_BREVE}-{SEQ:03d}-{materiale_tipo_codice}`` (Sprint 7.7
    MR 4) e l'aggregato dal clustering A2 (Sprint 7.7 MR 5).

    Sprint 5.6 Feature 4 + Sprint 7.7 MR 1 (Fix C "rientro
    intelligente"): ``genera_rientro_sede=True`` attiva il vuoto di
    rientro 9XXXX a fine giro, ma SOLO se l'ultima destinazione della
    variante CANONICA è in ``whitelist_sede``.
    """

    numero_turno: str
    giro: GiroAggregato
    genera_rientro_sede: bool = False
    whitelist_sede: frozenset[str] = field(default_factory=frozenset)


# =====================================================================
# Helper di conversione (per test legacy e callers che hanno solo un
# GiroAssegnato singolo a disposizione)
# =====================================================================


def wrap_assegnato_in_aggregato(giro: GiroAssegnato) -> GiroAggregato:
    """Wrappa un singolo ``GiroAssegnato`` in ``GiroAggregato`` (1 sola
    variante per giornata).

    Utile per:
    - test diretti del persister che costruiscono manualmente
      ``GiroAssegnato`` (la maggior parte dei test esistenti).
    - call-site che producono giri non aggregati (es. test
      end-to-end pre-A2 mantenuti per regressione).
    """
    materiale = _primo_tipo_materiale(giro)
    if materiale is None:
        # Caso degenere: giro senza composizione → fallback "MISTO".
        # Non dovrebbe arrivare al persister, ma se ci arriva manteniamo
        # un valore plausibile.
        materiale = "MISTO"
    giornate_agg: list[GiornataAggregata] = []
    for k, gnata in enumerate(giro.giornate, start=1):
        variante = VarianteGiornata(
            catena_posizionata=gnata.catena_posizionata,
            blocchi_assegnati=gnata.blocchi_assegnati,
            eventi_composizione=gnata.eventi_composizione,
            dates_apply=gnata.dates_apply_or_data,
        )
        giornate_agg.append(
            GiornataAggregata(numero_giornata=k, varianti=(variante,))
        )
    return GiroAggregato(
        localita_codice=giro.localita_codice,
        materiale_tipo_codice=materiale,
        giornate=tuple(giornate_agg),
        chiuso=giro.chiuso,
        motivo_chiusura=giro.motivo_chiusura,
        km_cumulati=giro.km_cumulati,
        corse_residue=giro.corse_residue,
        incompatibilita_materiale=giro.incompatibilita_materiale,
        n_cluster_a1=1,
    )


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


def _km_variante(variante: VarianteGiornata) -> float:
    """Somma ``km_tratta`` delle corse commerciali di una variante."""
    total = 0.0
    for c in variante.catena_posizionata.catena.corse:
        km = getattr(c, "km_tratta", None)
        if km is not None:
            total += float(km)
    return total


def _km_totali_canonica(giro: GiroAggregato) -> float:
    """Somma km_tratta di tutte le giornate del giro, prendendo per
    ciascuna la VARIANTE CANONICA (variant_index=0).

    Usato per popolare ``GiroMateriale.km_media_giornaliera``.
    Approssimazione: i giri con varianti multiple per giornata avranno
    km medio basato sulla canonica; raffinamento (media ponderata su
    `dates_apply`) rimandato a MR successivo.
    """
    total = 0.0
    for giornata in giro.giornate:
        if giornata.varianti:
            total += _km_variante(giornata.varianti[0])
    return total


def _km_giornata_canonica(giornata: GiornataAggregata) -> float:
    """Somma km_tratta della variante canonica della giornata."""
    if not giornata.varianti:
        return 0.0
    return _km_variante(giornata.varianti[0])


def _estrai_validita_variante(
    variante: VarianteGiornata,
) -> tuple[str | None, list[str]]:
    """Estrae validità testuale + date concrete da una variante.

    **Testo** (``validita_testo``): ``periodicita_breve`` della prima
    corsa della variante con valore non vuoto, oppure ``None``.
    Letterale dal PdE (memoria ``feedback_pde_periodicita_verita.md``).

    **Date** (``dates_apply_json``): ``variante.dates_apply`` come
    lista ordinata di stringhe ISO ``YYYY-MM-DD``.
    """
    corse = variante.catena_posizionata.catena.corse
    testo: str | None = None
    for c in corse:
        p = getattr(c, "periodicita_breve", None)
        if p is not None and str(p).strip():
            testo = str(p).strip()
            break

    dates_iso = sorted({d.isoformat() for d in variante.dates_apply})
    return (testo, dates_iso)


def _km_media_annua_giro(
    giro: GiroAggregato,
    valido_da: date,
    valido_a: date,
) -> float | None:
    """Stima km annui del giro materiale.

    Sprint 7.7 MR 5: per ciascuna giornata, somma sui contributi di
    TUTTE le varianti (ogni variante porta `km_giornata * len(dates_apply ∩ periodo)`).

    Returns:
        Stima `float` km/anno del giro. ``None`` se nessuna variante
        ha date di applicazione nel periodo richiesto.
    """
    valido_da_iso = valido_da.isoformat()
    valido_a_iso = valido_a.isoformat()
    km_anno = 0.0
    qualcosa_calcolato = False
    for giornata in giro.giornate:
        for variante in giornata.varianti:
            n_giorni = sum(
                1
                for d in variante.dates_apply
                if valido_da_iso <= d.isoformat() <= valido_a_iso
            )
            if n_giorni == 0:
                continue
            km = _km_variante(variante)
            km_anno += km * n_giorni
            qualcosa_calcolato = True

    return km_anno if qualcosa_calcolato else None


async def _next_numero_rientro_sede(session: AsyncSession) -> str:
    """Prossimo `numero_treno_vuoto` per la corsa rientro a sede.

    Sprint 5.6 Feature 4: convenzione **5 cifre, prefisso 9** (placeholder
    Trenord). Sequenziale globale su `corsa_materiale_vuoto`.
    """
    from sqlalchemy import text

    stmt = text(
        "SELECT COALESCE(MAX(SUBSTRING(numero_treno_vuoto FROM 2)::int), 0) "
        "FROM corsa_materiale_vuoto "
        "WHERE numero_treno_vuoto ~ '^9[0-9]{4}$'"
    )
    last = (await session.execute(stmt)).scalar_one()
    return f"9{(int(last) + 1):04d}"


def primo_tipo_materiale(giro: GiroAssegnato) -> str | None:
    """Primo ``materiale_tipo_codice`` usato dal giro, ``None`` se nessun
    blocco assegnato.

    Sprint 7.7 MR 4: usato dal builder per costruire ``numero_turno``
    con suffisso materiale.
    """
    for giornata in giro.giornate:
        for blocco in giornata.blocchi_assegnati:
            if blocco.assegnazione.composizione:
                return blocco.assegnazione.composizione[0].materiale_tipo_codice
    return None


# Alias privato per backward-compat con i call-site interni del modulo.
_primo_tipo_materiale = primo_tipo_materiale


def _build_metadata_giro(
    numero_turno: str, programma_id: int, giro: GiroAggregato
) -> dict[str, Any]:
    """Metadata di tracciabilità su ``generation_metadata_json``."""
    n_varianti_per_giornata = [len(g.varianti) for g in giro.giornate]
    return {
        "persister_version": PERSISTER_VERSION,
        "generato_at": datetime.now(UTC).isoformat(),
        "numero_turno": numero_turno,
        "programma_id": programma_id,
        "motivo_chiusura": giro.motivo_chiusura,
        "chiuso": giro.chiuso,
        "n_corse_residue": len(giro.corse_residue),
        "n_incompatibilita_materiale": len(giro.incompatibilita_materiale),
        # Sprint 7.7 MR 5: tracciabilità clustering A2.
        "n_cluster_a1": giro.n_cluster_a1,
        "n_varianti_per_giornata": n_varianti_per_giornata,
    }


def _build_metadata_evento(ev: EventoComposizione) -> dict[str, Any]:
    """Metadata di un blocco aggancio/sgancio."""
    return {
        "materiale_tipo_codice": ev.materiale_tipo_codice,
        "pezzi_delta": ev.pezzi_delta,
        "note_builder": ev.note_builder,
        "stazione_proposta_originale": ev.stazione_proposta,
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
    """Inserisce ``CorsaMaterialeVuoto`` ORM e ritorna il suo id."""
    cmv = CorsaMaterialeVuoto(
        azienda_id=azienda_id,
        numero_treno_vuoto=f"V-{numero_turno}-{seq_vuoto_giro:03d}",
        codice_origine=blocco_vuoto.codice_origine,
        codice_destinazione=blocco_vuoto.codice_destinazione,
        ora_partenza=blocco_vuoto.ora_partenza,
        ora_arrivo=blocco_vuoto.ora_arrivo,
        min_tratta=None,
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


async def _persisti_blocchi_variante(
    variante: VarianteGiornata,
    giro_variante_id: int,
    giro_materiale_id: int,
    azienda_id: int,
    numero_turno: str,
    seq_vuoto_giro_inizio: int,
    session: AsyncSession,
    seq_blocco_inizio: int = 1,
) -> tuple[int, int]:
    """Persiste i blocchi di una variante in ordine sequenziale.

    Sprint 7.7 MR 5: ogni variante ha la sua sequenza di blocchi
    (vuoto_testa? → [evento? → corsa]* → vuoto_coda?). La FK punta a
    ``giro_variante_id``.

    Sprint 7.9 MR 7C: ``seq_blocco_inizio`` (default 1) consente al
    chiamante di pre-inserire un blocco "uscita_sede" sintetico con
    seq=1 e far partire la sequenza canonica da seq=2.

    Returns:
        ``(seq_vuoto_giro, seq_blocco_next)`` per propagazione fra
        varianti dello stesso giro.
    """
    seq_blocco = seq_blocco_inizio  # progressivo dentro la variante (CHECK seq >= 1)
    seq_vuoto = seq_vuoto_giro_inizio
    cat_pos = variante.catena_posizionata

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
                    "cross_notte_giorno_precedente": cat_pos.vuoto_testa.cross_notte_giorno_precedente,
                },
            )
        )
        seq_blocco += 1

    # ---- Eventi composizione: indicizzati per "posizione_dopo_blocco" ----
    eventi_per_pos = {
        e.posizione_dopo_blocco: e for e in variante.eventi_composizione
    }

    # ---- Blocchi corsa con eventi inseriti PRIMA del blocco corrente ----
    for idx, blocco in enumerate(variante.blocchi_assegnati):
        if (idx - 1) in eventi_per_pos:
            ev = eventi_per_pos[idx - 1]
            session.add(
                GiroBlocco(
                    giro_variante_id=giro_variante_id,
                    seq=seq_blocco,
                    tipo_blocco=ev.tipo,
                    corsa_commerciale_id=None,
                    corsa_materiale_vuoto_id=None,
                    stazione_da_codice=ev.stazione_proposta,
                    stazione_a_codice=ev.stazione_proposta,
                    ora_inizio=blocco.corsa.ora_partenza,
                    ora_fine=blocco.corsa.ora_partenza,
                    descrizione=ev.note_builder,
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
    """Persiste un singolo giro aggregato.

    Schema scritto:
    GiroMateriale → N GiroGiornata → M GiroVariante per giornata →
    K GiroBlocco per variante.
    """
    loc = await _carica_localita(session, entry.giro.localita_codice, azienda_id)
    materiale_tipo = entry.giro.materiale_tipo_codice
    # Sprint 7.7 MR 5: ``"MISTO"`` è la sentinella usata da
    # ``wrap_assegnato_in_aggregato`` quando il giro non ha alcuna
    # composizione assegnata (= tutto in corse residue). In DB:
    # ``tipo_materiale = "MISTO"`` (text, leggibile in UI) ma
    # ``materiale_tipo_codice = NULL`` (FK su ``materiale_tipo``).
    materiale_tipo_codice_db: str | None = (
        None if materiale_tipo == "MISTO" else materiale_tipo
    )

    n_giornate = len(entry.giro.giornate)
    km_totali_canonica = _km_totali_canonica(entry.giro)
    km_media_giornaliera = (
        round(km_totali_canonica / n_giornate, 2) if n_giornate > 0 else 0.0
    )

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
        tipo_materiale=materiale_tipo,
        descrizione_materiale=None,
        materiale_tipo_codice=materiale_tipo_codice_db,
        numero_giornate=n_giornate,
        km_media_giornaliera=km_media_giornaliera,
        km_media_annua=km_media_annua,
        posti_1cl=0,
        posti_2cl=0,
        localita_manutenzione_partenza_id=loc.id,
        localita_manutenzione_arrivo_id=loc.id,
        stato="bozza",
        generation_metadata_json=_build_metadata_giro(
            entry.numero_turno, programma_id, entry.giro
        ),
    )
    session.add(gm)
    await session.flush()
    gm_id: int = gm.id

    seq_vuoto_giro = 0  # progressivo per CorsaMaterialeVuoto del giro
    last_gv_id: int | None = None  # ultima variante dell'ultima giornata
    last_seq_blocco: int = 1
    for giornata in entry.giro.giornate:
        km_g = _km_giornata_canonica(giornata)
        gg = GiroGiornata(
            giro_materiale_id=gm_id,
            numero_giornata=giornata.numero_giornata,
            km_giornata=round(km_g, 2) if km_g > 0 else None,
        )
        session.add(gg)
        await session.flush()

        # Sprint 7.7 MR 5: persisti N varianti per la giornata.
        is_prima_giornata = giornata.numero_giornata == 1
        for variant_index, variante in enumerate(giornata.varianti):
            testo_val, dates_val = _estrai_validita_variante(variante)
            gv = GiroVariante(
                giro_giornata_id=gg.id,
                variant_index=variant_index,
                validita_testo=testo_val,
                dates_apply_json=dates_val,
                dates_skip_json=[],
            )
            session.add(gv)
            await session.flush()

            # Sprint 7.9 MR 7C → MR 7C-rollback (decisione utente
            # 2026-05-03): generavamo un blocco "uscita_sede" sintetico
            # per la prima giornata anche quando la prima corsa partiva
            # da una stazione FUORI whitelist (es. LECCO). Risultato:
            # vuoti tecnici da 30+ minuti per 50+ km (Fiorenza → Lecco)
            # — operativamente Trenord non li fa così. Rollback: il
            # vuoto di testa NATURALE generato in `posizionamento.py`
            # (solo se la prima corsa parte da una stazione in
            # whitelist sede) resta l'unico meccanismo. Stazioni fuori
            # whitelist significano cross-notte K-1: il convoglio era
            # già lì dalla notte precedente — non un vuoto sintetico.
            seq_blocco_inizio = 1
            # NOTA: la funzione `_crea_blocco_uscita_sede` resta nel
            # modulo come builder block riusabile per scenari futuri
            # (es. inizio assoluto ciclo da prima generazione + uscita
            # operativa coerente con flotta), ma non è più chiamata
            # automaticamente qui.
            _ = is_prima_giornata  # reserved per futuri scenari

            seq_vuoto_giro, last_seq_blocco = await _persisti_blocchi_variante(
                variante,
                gv.id,
                gm_id,
                azienda_id,
                entry.numero_turno,
                seq_vuoto_giro,
                session,
                seq_blocco_inizio=seq_blocco_inizio,
            )
            last_gv_id = gv.id

    # Sprint 5.6 Feature 4 + Sprint 7.7 MR 1 (Fix C): rientro 9XXXX a
    # sede. Il rientro si attacca all'ULTIMA variante dell'ULTIMA
    # giornata (= variante che chiude effettivamente il ciclo). Sprint
    # 7.7 MR 5: nel modello A2 la "variante canonica" della giornata N
    # è quella con variant_index più alto NON necessariamente — ma
    # tutte le varianti della giornata N rappresentano modi diversi
    # di chiudere il ciclo, quindi attaccare il rientro all'ULTIMA
    # creata è il pattern più conservativo.
    # NB: questo è un raffinamento del modello — in futuro il rientro
    # potrebbe essere replicato su OGNI variante dell'ultima giornata,
    # con variazione della destinazione in base all'ultima corsa di
    # quella variante. Per il MR 5 manteniamo la logica MR 1: rientro
    # solo se l'ultima dest della variante FINALE è in whitelist.
    if (
        entry.genera_rientro_sede
        and last_gv_id is not None
        and loc.stazione_collegata_codice is not None
        and entry.giro.giornate
    ):
        ultima_giornata = entry.giro.giornate[-1]
        if ultima_giornata.varianti:
            ultima_variante = ultima_giornata.varianti[-1]
            corse_ultima = ultima_variante.catena_posizionata.catena.corse
            if corse_ultima:
                ultima_dest = corse_ultima[-1].codice_destinazione
                if (
                    ultima_dest != loc.stazione_collegata_codice
                    and ultima_dest in entry.whitelist_sede
                ):
                    await _crea_blocco_rientro_sede(
                        session=session,
                        giro_variante_id=last_gv_id,
                        giro_materiale_id=gm_id,
                        azienda_id=azienda_id,
                        seq=last_seq_blocco,
                        stazione_da=ultima_dest,
                        stazione_a=loc.stazione_collegata_codice,
                        ora_inizio=corse_ultima[-1].ora_arrivo,
                    )

    return gm_id


async def _crea_blocco_uscita_sede(
    *,
    session: AsyncSession,
    giro_variante_id: int,
    giro_materiale_id: int,
    azienda_id: int,
    seq: int,
    stazione_da: str,
    stazione_a: str,
    ora_arrivo: Any,
) -> None:
    """Sprint 7.9 MR 7C: blocco "uscita_sede" simmetrico al rientro.

    Crea un ``materiale_vuoto`` sintetico per rappresentare l'uscita
    del convoglio dal deposito ``stazione_da`` (sede) verso
    ``stazione_a`` (prima stazione commerciale del ciclo). L'orario
    di arrivo coincide con la partenza della prima corsa; la
    partenza è 30 minuti prima.

    Differenza dal vuoto_testa di ``posizionamento.py``: questo è
    SEMPRE generato per la prima giornata del ciclo se la prima
    stazione è diversa dalla sede, anche se la prima stazione è
    fuori whitelist (= linee lontane es. Bergamo, Brescia, Tirano).
    """
    from datetime import time as _time

    h, m = ora_arrivo.hour, ora_arrivo.minute
    partenza_min = (h * 60 + m - 30) % (24 * 60)
    ora_partenza = _time(partenza_min // 60, partenza_min % 60)
    numero = await _next_numero_rientro_sede(session)

    cmv = CorsaMaterialeVuoto(
        azienda_id=azienda_id,
        numero_treno_vuoto=numero,
        codice_origine=stazione_da,
        codice_destinazione=stazione_a,
        ora_partenza=ora_partenza,
        ora_arrivo=ora_arrivo,
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
            ora_inizio=ora_partenza,
            ora_fine=ora_arrivo,
            descrizione=f"Uscita sede {numero}: {stazione_da} → {stazione_a}",
            is_validato_utente=False,
            metadata_json={"motivo": "uscita_sede", "numero_treno_placeholder": numero},
        )
    )
    await session.flush()


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
    """Crea CorsaMaterialeVuoto + GiroBlocco per il rientro 9XXXX a sede."""
    from datetime import time as _time

    numero = await _next_numero_rientro_sede(session)
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
            is_validato_utente=False,
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
    """Persiste una lista di giri aggregati nel DB. Ritorna i loro ``id``.

    Schema: GiroMateriale + N GiroGiornata + M GiroVariante per giornata
    + K GiroBlocco per variante + eventuali CorsaMaterialeVuoto.

    Args:
        giri_da_persistere: lista di ``GiroDaPersistere`` (numero_turno
            + ``GiroAggregato`` dal clustering A2).
        session: ``AsyncSession`` SQLAlchemy.
        programma_id: id ``ProgrammaMateriale`` (per tracciabilità).
        azienda_id: id ``Azienda`` (per FK su località e vuoti).
        periodo_valido_da, periodo_valido_a: opzionali, per stima km
            annua.

    Returns:
        Lista ``GiroMateriale.id`` creati (nello stesso ordine).

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
