"""Builder MVP del turno PdC — Sprint 7.2.

Dato un `GiroMateriale` persistito, costruisce 1 turno PdC con N
giornate (una per giornata del giro). Per ogni giornata:

- presa servizio: 15' prima dell'ACCp
- ACCp: 40' prima del primo blocco condotta
- condotta: ogni blocco corsa_commerciale / materiale_vuoto del giro
- parking (PK): nei gap intermedi tra blocchi del giro
- refezione: se prestazione > 6h, sostituzione di un PK di ≥30' nella
  finestra 11:30-15:30 o 18:30-22:30
- ACCa: 40' dopo l'ultimo blocco condotta
- fine servizio: 15' dopo l'ACCa

Violazioni rilevate (segnalate ma non bloccanti per MVP):

- prestazione > 8h30 (cap 7h se presa servizio 01:00-04:59)
- condotta > 5h30
- refezione mancante con prestazione > 6h
- PdC che termina fuori dal deposito di partenza (FR — Sprint 7.4)

Sprint 7.9 MR η: il builder accetta ``deposito_pdc_id`` opzionale.
Quando valorizzato, la stazione di residenza per il calcolo FR è
``Depot.stazione_principale_codice`` (la sede del *macchinista*, non
del materiale). Il builder marca le dormite FR rispetto a quella e
applica i cap normativi (max 1 FR/settimana, 3 FR/28gg —
NORMATIVA-PDC §10.6) come violazioni di ciclo.

Scope rimandato: CV intermedi (chiuso 7.4), vettura passiva,
ciclo settimanale completo, S.COMP, assegnazione persone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.models.anagrafica import Depot, LocalitaManutenzione
from colazione.models.corse import CorsaCommerciale, CorsaMaterialeVuoto
from colazione.models.giri import GiroBlocco, GiroGiornata, GiroMateriale, GiroVariante
from colazione.models.turni_pdc import TurnoPdc, TurnoPdcBlocco, TurnoPdcGiornata

# Sprint 7.4 MR 2: split CV intermedio.
# Import deferred dentro le funzioni per evitare ciclo: `split_cv`
# importa `_build_giornata_pdc` e le costanti normative da questo
# modulo, e questo modulo lo richiama. L'import a livello funzione
# rompe la dipendenza al collection time.


# --- Parametri normativa MVP (vedi docs/NORMATIVA-PDC.md) ----------------

PRESA_SERVIZIO_MIN = 15
FINE_SERVIZIO_MIN = 15
ACCESSORI_MIN_STANDARD = 40
PRESTAZIONE_MAX_STANDARD = 510  # 8h30
PRESTAZIONE_MAX_NOTTURNO = 420  # 7h se presa 01:00-04:59
CONDOTTA_MAX_MIN = 330  # 5h30
REFEZIONE_MIN_DURATA = 30
REFEZIONE_SOGLIA_MIN = 360  # se prestazione > 6h serve refezione
REFEZIONE_FINESTRE: list[tuple[int, int]] = [
    (11 * 60 + 30, 15 * 60 + 30),  # 11:30 - 15:30
    (18 * 60 + 30, 22 * 60 + 30),  # 18:30 - 22:30
]
# Sprint 7.9 MR η — cap FR per PdC (NORMATIVA-PDC §10.6).
FR_MAX_PER_SETTIMANA = 1
FR_MAX_PER_28GG = 3


# --- Errori e risultati ---------------------------------------------------


class GiroNonTrovatoError(Exception):
    """Il giro indicato non esiste o non appartiene all'azienda."""


class GiroVuotoError(Exception):
    """Il giro non ha blocchi: niente da costruire."""


class DepositoPdcNonTrovatoError(Exception):
    """Il depot indicato non esiste o non appartiene all'azienda."""


@dataclass
class BuilderTurnoPdcResult:
    turno_pdc_id: int
    codice: str
    n_giornate: int
    prestazione_totale_min: int
    condotta_totale_min: int
    violazioni: list[str]
    warnings: list[str] = field(default_factory=list)
    # Sprint 7.4 MR 3: campi split CV intermedio.
    # `is_ramo_split=True` se il TurnoPdc è il ramo di una giornata-giro
    # splittata; `False` per il TurnoPdc principale (o per giri/giornate
    # che non richiedono split). Quando True, gli altri 3 campi sono
    # sempre valorizzati.
    is_ramo_split: bool = False
    split_origine_giornata: int | None = None
    split_ramo: int | None = None
    split_totale_rami: int | None = None
    # Sprint 7.9 MR η: associazione esplicita al deposito PdC.
    deposito_pdc_id: int | None = None
    deposito_pdc_codice: str | None = None
    n_dormite_fr: int = 0
    fr_cap_violazioni: list[str] = field(default_factory=list)


# --- Helper temporali -----------------------------------------------------


def _t(t: time) -> int:
    """Time → minuti dall'inizio giornata."""
    return t.hour * 60 + t.minute


def _from_min(m: int) -> time:
    """Minuti dall'inizio giornata → time. Wrap a 24h."""
    m = m % (24 * 60)
    return time(hour=m // 60, minute=m % 60)


def _diff(start: time, end: time) -> int:
    """Durata in minuti, gestendo (raramente) wrap-mezzanotte."""
    s = _t(start)
    e = _t(end)
    if e < s:
        e += 24 * 60
    return e - s


# --- Strutture intermedie --------------------------------------------------


@dataclass
class _BloccoPdcDraft:
    seq: int
    tipo_evento: str  # CONDOTTA, VETTURA, REFEZ, ACCp, ACCa, CVp, CVa, PK, SCOMP, PRESA, FINE
    ora_inizio: time
    ora_fine: time
    durata_min: int
    stazione_da_codice: str | None = None
    stazione_a_codice: str | None = None
    corsa_commerciale_id: int | None = None
    corsa_materiale_vuoto_id: int | None = None
    giro_blocco_id: int | None = None
    accessori_note: str | None = None


@dataclass
class _GiornataPdcDraft:
    numero_giornata: int
    variante_calendario: str
    blocchi: list[_BloccoPdcDraft]
    stazione_inizio: str | None
    stazione_fine: str | None
    inizio_prestazione: time
    fine_prestazione: time
    prestazione_min: int
    condotta_min: int
    refezione_min: int
    is_notturno: bool
    violazioni: list[str]


# --- Costruzione di una singola giornata PdC ------------------------------


def _build_giornata_pdc(
    numero_giornata: int,
    variante_calendario: str,
    blocchi_giro: list[GiroBlocco],
) -> _GiornataPdcDraft | None:
    """Costruisce una giornata PdC dai blocchi del giro materiale.

    Ritorna `None` se la giornata è vuota o priva di orari validi.
    """
    if not blocchi_giro:
        return None

    blocchi_validi = [b for b in blocchi_giro if b.ora_inizio is not None and b.ora_fine is not None]
    if not blocchi_validi:
        return None

    primo = blocchi_validi[0]
    ultimo = blocchi_validi[-1]
    assert primo.ora_inizio is not None and ultimo.ora_fine is not None

    primo_inizio = _t(primo.ora_inizio)
    ultimo_fine = _t(ultimo.ora_fine)

    ora_inizio_accp = (primo_inizio - ACCESSORI_MIN_STANDARD) % (24 * 60)
    ora_presa = (primo_inizio - ACCESSORI_MIN_STANDARD - PRESA_SERVIZIO_MIN) % (24 * 60)
    ora_fine_acca = (ultimo_fine + ACCESSORI_MIN_STANDARD) % (24 * 60)
    ora_fine_servizio = (ultimo_fine + ACCESSORI_MIN_STANDARD + FINE_SERVIZIO_MIN) % (24 * 60)

    drafts: list[_BloccoPdcDraft] = []
    seq = 1

    # 1. PRESA servizio
    drafts.append(
        _BloccoPdcDraft(
            seq=seq,
            tipo_evento="PRESA",
            ora_inizio=_from_min(ora_presa),
            ora_fine=_from_min(ora_inizio_accp),
            durata_min=PRESA_SERVIZIO_MIN,
            stazione_da_codice=primo.stazione_da_codice,
            stazione_a_codice=primo.stazione_da_codice,
        )
    )
    seq += 1

    # 2. ACCp
    drafts.append(
        _BloccoPdcDraft(
            seq=seq,
            tipo_evento="ACCp",
            ora_inizio=_from_min(ora_inizio_accp),
            ora_fine=primo.ora_inizio,
            durata_min=ACCESSORI_MIN_STANDARD,
            stazione_da_codice=primo.stazione_da_codice,
            stazione_a_codice=primo.stazione_da_codice,
        )
    )
    seq += 1

    # 3. Blocchi condotta + PK intermedi
    for i, b in enumerate(blocchi_validi):
        assert b.ora_inizio is not None and b.ora_fine is not None
        if i > 0:
            prec = blocchi_validi[i - 1]
            assert prec.ora_fine is not None
            gap = _diff(prec.ora_fine, b.ora_inizio)
            if gap > 0:
                drafts.append(
                    _BloccoPdcDraft(
                        seq=seq,
                        tipo_evento="PK",
                        ora_inizio=prec.ora_fine,
                        ora_fine=b.ora_inizio,
                        durata_min=gap,
                        stazione_da_codice=prec.stazione_a_codice,
                        stazione_a_codice=prec.stazione_a_codice,
                    )
                )
                seq += 1

        durata = _diff(b.ora_inizio, b.ora_fine)
        drafts.append(
            _BloccoPdcDraft(
                seq=seq,
                tipo_evento="CONDOTTA",
                ora_inizio=b.ora_inizio,
                ora_fine=b.ora_fine,
                durata_min=durata,
                stazione_da_codice=b.stazione_da_codice,
                stazione_a_codice=b.stazione_a_codice,
                corsa_commerciale_id=b.corsa_commerciale_id,
                corsa_materiale_vuoto_id=b.corsa_materiale_vuoto_id,
                giro_blocco_id=b.id,
            )
        )
        seq += 1

    # 4. ACCa
    drafts.append(
        _BloccoPdcDraft(
            seq=seq,
            tipo_evento="ACCa",
            ora_inizio=ultimo.ora_fine,
            ora_fine=_from_min(ora_fine_acca),
            durata_min=ACCESSORI_MIN_STANDARD,
            stazione_da_codice=ultimo.stazione_a_codice,
            stazione_a_codice=ultimo.stazione_a_codice,
        )
    )
    seq += 1

    # 5. FINE servizio
    drafts.append(
        _BloccoPdcDraft(
            seq=seq,
            tipo_evento="FINE",
            ora_inizio=_from_min(ora_fine_acca),
            ora_fine=_from_min(ora_fine_servizio),
            durata_min=FINE_SERVIZIO_MIN,
            stazione_da_codice=ultimo.stazione_a_codice,
            stazione_a_codice=ultimo.stazione_a_codice,
        )
    )
    seq += 1

    prestazione_min = (ora_fine_servizio - ora_presa) % (24 * 60)
    if prestazione_min == 0:
        prestazione_min = 24 * 60

    # 6. REFEZ se prestazione > 6h: cerca un PK >= 30' in finestra
    if prestazione_min > REFEZIONE_SOGLIA_MIN:
        drafts = _inserisci_refezione(drafts)

    # Renumera seq dopo eventuale split refezione
    for i, d in enumerate(drafts, start=1):
        d.seq = i

    condotta_min = sum(d.durata_min for d in drafts if d.tipo_evento == "CONDOTTA")
    refezione_min = sum(d.durata_min for d in drafts if d.tipo_evento == "REFEZ")

    is_notturno = ora_presa < 5 * 60 or ora_fine_servizio > 22 * 60 or ora_fine_servizio < ora_presa

    violazioni: list[str] = []
    cap_prestazione = (
        PRESTAZIONE_MAX_NOTTURNO
        if 60 <= ora_presa < 5 * 60
        else PRESTAZIONE_MAX_STANDARD
    )
    if prestazione_min > cap_prestazione:
        violazioni.append(
            f"prestazione_max:{prestazione_min}>{cap_prestazione}min"
        )
    if condotta_min > CONDOTTA_MAX_MIN:
        violazioni.append(f"condotta_max:{condotta_min}>{CONDOTTA_MAX_MIN}min")
    if prestazione_min > REFEZIONE_SOGLIA_MIN and refezione_min == 0:
        violazioni.append("refezione_mancante")

    return _GiornataPdcDraft(
        numero_giornata=numero_giornata,
        variante_calendario=variante_calendario,
        blocchi=drafts,
        stazione_inizio=primo.stazione_da_codice,
        stazione_fine=ultimo.stazione_a_codice,
        inizio_prestazione=_from_min(ora_presa),
        fine_prestazione=_from_min(ora_fine_servizio),
        prestazione_min=prestazione_min,
        condotta_min=condotta_min,
        refezione_min=refezione_min,
        is_notturno=is_notturno,
        violazioni=violazioni,
    )


def _inserisci_refezione(drafts: list[_BloccoPdcDraft]) -> list[_BloccoPdcDraft]:
    """Cerca un PK ≥30' in una finestra refezione.

    Se trovato, lo sostituisce con [PK pre, REFEZ 30, PK post] (omettendo
    i PK con durata 0). Se non trovato, ritorna invariato (la giornata
    risulterà con violazione "refezione_mancante").

    Strategia: scegli il PK candidato più lungo che cade per intero o in
    parte dentro una delle finestre. Posiziona la REFEZ:
    - ancorata al centro del PK se ci sta tutta dentro
    - altrimenti ancorata all'intersezione PK ∩ finestra
    """
    candidati: list[tuple[int, int, int]] = []  # (idx, finestra_idx, score)
    for i, d in enumerate(drafts):
        if d.tipo_evento != "PK":
            continue
        if d.durata_min < REFEZIONE_MIN_DURATA:
            continue
        ini = _t(d.ora_inizio)
        fin = ini + d.durata_min
        for fidx, (fa, fb) in enumerate(REFEZIONE_FINESTRE):
            overlap_start = max(ini, fa)
            overlap_end = min(fin, fb)
            overlap = overlap_end - overlap_start
            if overlap >= REFEZIONE_MIN_DURATA:
                candidati.append((i, fidx, overlap))
    if not candidati:
        return drafts

    # PK più lungo overlap-finestra vince
    candidati.sort(key=lambda x: -x[2])
    idx, fidx, _ = candidati[0]
    pk = drafts[idx]
    fa, fb = REFEZIONE_FINESTRE[fidx]
    ini = _t(pk.ora_inizio)
    fin = ini + pk.durata_min

    # ancoraggio: centro del PK se ci sta tutta dentro la finestra,
    # altrimenti il primo punto valido all'interno della finestra
    centro = ini + pk.durata_min // 2
    refez_start = centro - REFEZIONE_MIN_DURATA // 2
    refez_end = refez_start + REFEZIONE_MIN_DURATA
    if refez_start < max(fa, ini) or refez_end > min(fb, fin):
        refez_start = max(fa, ini)
        refez_end = refez_start + REFEZIONE_MIN_DURATA

    pre_durata = refez_start - ini
    post_durata = fin - refez_end

    sostituti: list[_BloccoPdcDraft] = []
    if pre_durata > 0:
        sostituti.append(
            _BloccoPdcDraft(
                seq=pk.seq,
                tipo_evento="PK",
                ora_inizio=pk.ora_inizio,
                ora_fine=_from_min(refez_start),
                durata_min=pre_durata,
                stazione_da_codice=pk.stazione_da_codice,
                stazione_a_codice=pk.stazione_a_codice,
            )
        )
    sostituti.append(
        _BloccoPdcDraft(
            seq=pk.seq,
            tipo_evento="REFEZ",
            ora_inizio=_from_min(refez_start),
            ora_fine=_from_min(refez_end),
            durata_min=REFEZIONE_MIN_DURATA,
            stazione_da_codice=pk.stazione_da_codice,
            stazione_a_codice=pk.stazione_a_codice,
        )
    )
    if post_durata > 0:
        sostituti.append(
            _BloccoPdcDraft(
                seq=pk.seq,
                tipo_evento="PK",
                ora_inizio=_from_min(refez_end),
                ora_fine=pk.ora_fine,
                durata_min=post_durata,
                stazione_da_codice=pk.stazione_da_codice,
                stazione_a_codice=pk.stazione_a_codice,
            )
        )

    return drafts[:idx] + sostituti + drafts[idx + 1 :]


# --- Entry point: persiste un turno PdC dal giro -------------------------


async def genera_turno_pdc(
    *,
    session: AsyncSession,
    azienda_id: int,
    giro_id: int,
    valido_da: date | None = None,
    force: bool = False,
    deposito_pdc_id: int | None = None,
) -> list[BuilderTurnoPdcResult]:
    """Genera (e persiste) i `TurnoPdc` per il giro indicato — uno per
    ogni combinazione di varianti calendario delle giornate-tipo.

    Sprint 7.5 MR 5 (decisione utente D1): un giro con N giornate-tipo,
    ognuna con M_k varianti, genera Π(M_k) turni PdC distinti. Codice:
    ``T-{giro.numero_turno}`` se 1 sola combinazione; con N>1
    combinazioni il suffisso `-V{idx:02d}` discrimina i turni
    (1-based: V01, V02, ...).

    Sprint 7.9 MR η: parametro ``deposito_pdc_id`` opzionale. Quando
    valorizzato:

    - La stazione di residenza usata per identificare i FR è la
      ``Depot.stazione_principale_codice`` (sede *del macchinista*),
      non più la ``LocalitaManutenzione.stazione_collegata`` (sede
      *del materiale*).
    - Il turno persiste con ``deposito_pdc_id`` valorizzato — la
      dashboard può raggrupparlo per deposito senza ambiguità.
    - I cap FR (1/settimana, 3/28gg — NORMATIVA-PDC §10.6) sono
      verificati e annotati come violazioni di ciclo.

    Quando ``None``, il builder mantiene il comportamento legacy
    (sede = stazione del materiale di partenza). Utile per script
    di migrazione o regressione.

    Codice del turno: con ``deposito_pdc_id`` valorizzato il prefisso
    diventa ``T-{depot.codice}-{giro.numero_turno}`` per evitare
    collisioni quando lo stesso giro genera turni per più depositi.

    Pre-MR 5 (Sprint 7.2 MVP): la funzione ritornava un `BuilderTurnoPdcResult`
    singolo, prendendo arbitrariamente la prima variante per giornata e
    ignorando le altre. MR 5 chiude il bug 5 lato PdC: ogni variante
    genera il proprio turno con il proprio calendario.

    A1 strict (MR 1) → di default ogni giornata-tipo ha 1 sola variante,
    quindi 1 sola combinazione → 1 solo turno (invariante di
    comportamento per i giri generati dal builder MR 4).

    Se esiste già un turno PdC per questo giro+deposito e ``force=False``,
    alza ``GiriEsistentiError``. Con ``force=True`` cancella tutti i
    turni PdC precedenti per questa coppia e ricrea da zero. Se
    ``deposito_pdc_id`` è None, il match anti-rigenerazione è solo
    su giro (legacy).

    Returns:
        ``list[BuilderTurnoPdcResult]`` ordinata per indice combinazione
        (deterministica). Sempre almeno 1 elemento se il giro è valido.

    Raises:
        GiroNonTrovatoError, GiroVuotoError, GiriEsistentiError,
        DepositoPdcNonTrovatoError.
    """
    giro = (
        await session.execute(
            select(GiroMateriale).where(
                GiroMateriale.id == giro_id,
                GiroMateriale.azienda_id == azienda_id,
            )
        )
    ).scalar_one_or_none()
    if giro is None:
        raise GiroNonTrovatoError(f"Giro {giro_id} non trovato per azienda {azienda_id}")

    # Sprint 7.9 MR η — risolvi deposito target (se richiesto). Il
    # caricamento serve sia per validare l'input (FK valida + scoping
    # azienda) sia per usare la `stazione_principale_codice` come
    # sede effettiva nel calcolo FR.
    depot_target: Depot | None = None
    if deposito_pdc_id is not None:
        depot_target = (
            await session.execute(
                select(Depot).where(
                    Depot.id == deposito_pdc_id,
                    Depot.azienda_id == azienda_id,
                    Depot.is_attivo,
                )
            )
        ).scalar_one_or_none()
        if depot_target is None:
            raise DepositoPdcNonTrovatoError(
                f"Deposito PdC {deposito_pdc_id} non trovato o non attivo "
                f"per azienda {azienda_id}"
            )

    # Carica giornate ordinate
    giornate_giro = list(
        (
            await session.execute(
                select(GiroGiornata)
                .where(GiroGiornata.giro_materiale_id == giro_id)
                .order_by(GiroGiornata.numero_giornata)
            )
        ).scalars()
    )
    if not giornate_giro:
        raise GiroVuotoError(f"Giro {giro_id} non ha giornate")

    giornata_ids = [gg.id for gg in giornate_giro]

    # Sprint 7.7 MR 5 (re-introduzione varianti A2): ogni giornata ha
    # M varianti calendariali. Il builder PdC genera il turno sulla
    # VARIANTE CANONICA (= ``variant_index=0``) di ciascuna giornata;
    # per il MVP è una scelta semplice e deterministica. In futuro il
    # pianificatore potrà scegliere quale variante usare per generare
    # il turno PdC, o generare N turni (uno per variante).
    canonica_per_giornata: dict[int, GiroVariante] = {}
    if giornata_ids:
        for v in (
            await session.execute(
                select(GiroVariante)
                .where(GiroVariante.giro_giornata_id.in_(giornata_ids))
                .order_by(GiroVariante.giro_giornata_id, GiroVariante.variant_index)
            )
        ).scalars():
            # Prima occorrenza per giornata = variant_index più basso
            # (= canonica) grazie al sort.
            canonica_per_giornata.setdefault(v.giro_giornata_id, v)

    blocchi_per_giornata: dict[int, list[GiroBlocco]] = {}
    canonica_ids = [v.id for v in canonica_per_giornata.values()]
    if canonica_ids:
        # Mapping inverso variante_id → giornata_id per riassegnare i
        # blocchi alla giornata d'origine.
        var_to_gg = {v.id: v.giro_giornata_id for v in canonica_per_giornata.values()}
        for b in (
            await session.execute(
                select(GiroBlocco)
                .where(GiroBlocco.giro_variante_id.in_(canonica_ids))
                .order_by(GiroBlocco.giro_variante_id, GiroBlocco.seq)
            )
        ).scalars():
            gg_id = var_to_gg[b.giro_variante_id]
            blocchi_per_giornata.setdefault(gg_id, []).append(b)

    # Stazione sede del PdC.
    # - Se è stato passato ``deposito_pdc_id`` (Sprint 7.9 MR η), la
    #   sede è la ``stazione_principale_codice`` del depot — sede *del
    #   macchinista*. È la semantica corretta per il calcolo FR.
    # - Altrimenti (legacy) ricade sulla stazione del materiale di
    #   partenza del giro.
    stazione_sede: str | None = None
    if depot_target is not None and depot_target.stazione_principale_codice is not None:
        stazione_sede = depot_target.stazione_principale_codice
    elif giro.localita_manutenzione_partenza_id is not None:
        loc = (
            await session.execute(
                select(LocalitaManutenzione).where(
                    LocalitaManutenzione.id == giro.localita_manutenzione_partenza_id
                )
            )
        ).scalar_one_or_none()
        if loc is not None and loc.stazione_collegata_codice is not None:
            stazione_sede = loc.stazione_collegata_codice

    # Anti-rigenerazione: cancella i turni PdC del giro+deposito se
    # force, altrimenti errore se uno esiste già. Sprint 7.9 MR η:
    # match per coppia (giro, deposito_pdc_id) — lo stesso giro può
    # generare turni distinti per depositi diversi.
    existing = list(
        (
            await session.execute(
                select(TurnoPdc).where(TurnoPdc.azienda_id == azienda_id)
            )
        ).scalars()
    )

    def _matches_giro_e_deposito(t: TurnoPdc) -> bool:
        if (t.generation_metadata_json or {}).get("giro_materiale_id") != giro_id:
            return False
        if deposito_pdc_id is None:
            # Legacy: il caller non ha specificato deposito → un turno
            # esistente conflitta indipendentemente dal proprio deposito.
            return True
        return t.deposito_pdc_id == deposito_pdc_id

    legati = [t for t in existing if _matches_giro_e_deposito(t)]
    if legati and not force:
        depot_label = (
            f" deposito {depot_target.codice}" if depot_target is not None else ""
        )
        raise GiriEsistentiError(
            f"Esistono già {len(legati)} turno/i PdC per giro {giro_id}{depot_label}: "
            f"{legati[0].codice}"
            + (f" ... +{len(legati)-1} altri" if len(legati) > 1 else "")
        )
    for t in legati:
        await session.delete(t)
    if legati:
        await session.flush()

    valido_da_eff = valido_da or date.today()

    # Sprint 7.4 MR 2: carica una sola volta l'insieme di stazioni
    # ammesse a CV per l'azienda (depositi PdC + deroghe).
    # Import deferred (vedi commento ai top-level imports).
    from colazione.domain.builder_pdc.split_cv import lista_stazioni_cv_ammesse

    stazioni_cv = await lista_stazioni_cv_ammesse(session, azienda_id)

    # Sprint 7.7 MR 5: 1 giro = 1 turno PdC (più eventuali rami split
    # CV). Il turno è generato sulla variante CANONICA di ogni giornata
    # (variant_index=0). Le altre varianti calendariali esistono ma per
    # ora non producono turni PdC distinti — futura estensione.
    validita_per_giornata: dict[int, str | None] = {
        gg_id: v.validita_testo for gg_id, v in canonica_per_giornata.items()
    }
    risultati = await _genera_un_turno_pdc(
        session=session,
        azienda_id=azienda_id,
        giro=giro,
        giornate_giro=giornate_giro,
        blocchi_per_giornata=blocchi_per_giornata,
        validita_per_giornata=validita_per_giornata,
        stazione_sede=stazione_sede,
        stazioni_cv=stazioni_cv,
        valido_da_eff=valido_da_eff,
        depot_target=depot_target,
    )

    if not risultati:
        raise GiroVuotoError(
            f"Giro {giro_id} non ha blocchi validi"
        )

    await session.commit()
    return risultati


async def _genera_un_turno_pdc(
    *,
    session: AsyncSession,
    azienda_id: int,
    giro: GiroMateriale,
    giornate_giro: list[GiroGiornata],
    blocchi_per_giornata: dict[int, list[GiroBlocco]],
    validita_per_giornata: dict[int, str | None],
    stazione_sede: str | None,
    stazioni_cv: set[str],
    valido_da_eff: date,
    depot_target: Depot | None = None,
) -> list[BuilderTurnoPdcResult]:
    """Persiste i `TurnoPdc` per il giro indicato.

    Sprint 7.7 MR 5 (re-introduzione varianti A2): per ogni giornata
    del giro, il turno PdC è generato sulla VARIANTE CANONICA
    (``variant_index=0``). ``validita_per_giornata`` associa a ogni
    ``giro_giornata.id`` il ``validita_testo`` della variante canonica,
    usato per popolare ``TurnoPdcGiornata.variante_calendario``.

    Sprint 7.4 MR 2 (split CV intermedio): produce in generale **N**
    TurnoPdc:

    - **TurnoPdc principale**: contiene tutte le giornate-giro che
      NON sono state splittate (= rispettano i limiti normativi senza
      bisogno di CV intermedio). Codice ``T-{numero_turno}``.
    - **TurnoPdc-ramo-split**: ogni ramo prodotto da una giornata
      splittata diventa un TurnoPdc autonomo. Codice
      ``T-{numero_turno}-G{n_giornata}-R{n_ramo}``.

    Se TUTTE le giornate sono splittate, il TurnoPdc principale non
    viene creato (lista vuota di drafts non-split).

    Args:
        stazioni_cv: insieme dei codici stazione ammessi a Cambio
            Volante per l'azienda corrente. Caricato una volta dal
            chiamante (`genera_turno_pdc`).

    Returns:
        Lista (eventualmente vuota se non c'è alcun draft valido) di
        ``BuilderTurnoPdcResult``: 0..1 elemento principale + 0..N
        rami split. Sempre almeno 1 elemento se almeno una giornata-
        giro produce un draft.
    """
    # 1. Costruisci i draft, applicando lo split CV per ogni giornata.
    # Import deferred per rompere il ciclo split_cv ↔ builder.
    from colazione.domain.builder_pdc.split_cv import split_e_build_giornata

    drafts_per_giornata: list[list[_GiornataPdcDraft]] = []
    for gg in giornate_giro:
        blocchi = blocchi_per_giornata.get(gg.id, [])
        # Sprint 7.7 MR 5: validita_testo dalla variante canonica
        # (era su giornata stessa pre-MR 5).
        validita = validita_per_giornata.get(gg.id) or "GG"
        rami = split_e_build_giornata(
            numero_giornata=gg.numero_giornata,
            variante_calendario=validita,
            blocchi_giro=blocchi,
            stazioni_cv=stazioni_cv,
        )
        if rami:
            drafts_per_giornata.append(rami)

    if not drafts_per_giornata:
        return []

    # 2. Separa giornate non-split (TurnoPdc principale) da giornate
    #    split (un TurnoPdc per ramo).
    drafts_principali: list[_GiornataPdcDraft] = []
    rami_split: list[list[_GiornataPdcDraft]] = []
    for rami in drafts_per_giornata:
        if len(rami) == 1:
            drafts_principali.append(rami[0])
        else:
            rami_split.append(rami)

    # 3. Codice base e variabili comuni.
    # Sprint 7.9 MR η: con deposito target il codice è
    # ``T-{depot_codice}-{numero_turno}`` (es. T-FIORENZA-001-ETR526).
    # Senza deposito (legacy) resta ``T-{numero_turno}``.
    codice_principale = _genera_codice_turno(giro, depot_target)

    primo_draft = (
        drafts_principali[0] if drafts_principali else rami_split[0][0]
    )
    stazione_sede_eff = (
        stazione_sede if stazione_sede is not None else primo_draft.stazione_inizio
    )

    giornate_ids_giro = [gg.id for gg in giornate_giro]

    risultati: list[BuilderTurnoPdcResult] = []

    # 4. TurnoPdc principale (solo se ha almeno 1 giornata non-split).
    if drafts_principali:
        fr_giornate = _aggiungi_dormite_fr(drafts_principali, stazione_sede_eff)
        # Sprint 7.9 MR η: cap normativi FR per PdC. Calcolati sul
        # ciclo del turno (n_giornate = ciclo del PdC), confrontati
        # con limiti settimana e 28gg. NORMATIVA-PDC §10.6.
        fr_cap_violazioni = _calcola_violazioni_cap_fr(
            n_dormite_fr=len(fr_giornate),
            ciclo_giorni=giro.numero_giornate,
        )
        violazioni_extra = list(fr_cap_violazioni)
        risultato = await _persisti_un_turno_pdc(
            session=session,
            azienda_id=azienda_id,
            giro=giro,
            drafts=drafts_principali,
            codice=codice_principale,
            stazione_sede=stazione_sede_eff,
            valido_da_eff=valido_da_eff,
            giornate_ids=giornate_ids_giro,
            extra_metadata={
                "fr_giornate": fr_giornate,
                "is_ramo_split": False,
                "fr_cap_violazioni": fr_cap_violazioni,
            },
            depot_target=depot_target,
            violazioni_ciclo_extra=violazioni_extra,
        )
        risultati.append(risultato)

    # 5. TurnoPdc-ramo-split: 1 per ramo. Niente FR fra rami della
    #    stessa giornata (sono frazioni dello stesso giorno calendario).
    for rami in rami_split:
        n_giornata_origine = rami[0].numero_giornata
        totale_rami = len(rami)
        for idx_ramo, ramo in enumerate(rami, start=1):
            codice_ramo = (
                f"{codice_principale}-G{n_giornata_origine:02d}-R{idx_ramo}"
            )
            ramo_renum = _GiornataPdcDraft(
                numero_giornata=1,  # sola giornata del TurnoPdc-ramo
                variante_calendario=ramo.variante_calendario,
                blocchi=ramo.blocchi,
                stazione_inizio=ramo.stazione_inizio,
                stazione_fine=ramo.stazione_fine,
                inizio_prestazione=ramo.inizio_prestazione,
                fine_prestazione=ramo.fine_prestazione,
                prestazione_min=ramo.prestazione_min,
                condotta_min=ramo.condotta_min,
                refezione_min=ramo.refezione_min,
                is_notturno=ramo.is_notturno,
                violazioni=ramo.violazioni,
            )
            risultato_ramo = await _persisti_un_turno_pdc(
                session=session,
                azienda_id=azienda_id,
                giro=giro,
                drafts=[ramo_renum],
                codice=codice_ramo,
                stazione_sede=stazione_sede_eff,
                valido_da_eff=valido_da_eff,
                giornate_ids=giornate_ids_giro,
                extra_metadata={
                    "fr_giornate": [],
                    "is_ramo_split": True,
                    "split_origine_giornata": n_giornata_origine,
                    "split_ramo": idx_ramo,
                    "split_totale_rami": totale_rami,
                    "split_parent_codice": codice_principale,
                    "fr_cap_violazioni": [],
                },
                depot_target=depot_target,
                violazioni_ciclo_extra=[],
            )
            risultati.append(risultato_ramo)

    return risultati


async def _persisti_un_turno_pdc(
    *,
    session: AsyncSession,
    azienda_id: int,
    giro: GiroMateriale,
    drafts: list[_GiornataPdcDraft],
    codice: str,
    stazione_sede: str | None,
    valido_da_eff: date,
    giornate_ids: list[int],
    extra_metadata: dict[str, Any],
    depot_target: Depot | None = None,
    violazioni_ciclo_extra: list[str] | None = None,
) -> BuilderTurnoPdcResult:
    """Helper: persiste un singolo TurnoPdc + le sue giornate + blocchi.

    Sprint 7.4 MR 2: estratto da `_genera_un_turno_pdc` per riutilizzo
    fra TurnoPdc "principale" (giornate non-split + FR) e TurnoPdc-
    ramo-split (1 sola giornata, niente FR).

    Sprint 7.9 MR η: ``depot_target`` valorizza ``TurnoPdc.deposito_pdc_id``
    (FK fisica) e ``TurnoPdc.impianto`` (display name del deposito,
    sostituendo il fallback ``tipo_materiale`` legacy quando un depot
    è disponibile). ``violazioni_ciclo_extra`` aggiunge violazioni
    a livello ciclo (es. ``"fr_max_settimanale"``) al campo metadata.

    `extra_metadata` viene fuso dentro `generation_metadata_json` e
    deve includere `fr_giornate` (lista, eventualmente vuota) e
    `is_ramo_split` (bool). Per i rami split aggiungere anche
    `split_origine_giornata`, `split_ramo`, `split_totale_rami`,
    `split_parent_codice`.
    """
    violazioni: list[str] = []
    for d in drafts:
        for v_str in d.violazioni:
            violazioni.append(f"giornata{d.numero_giornata}:{v_str}")
    if violazioni_ciclo_extra:
        violazioni.extend(violazioni_ciclo_extra)

    metadata: dict[str, Any] = {
        "giro_materiale_id": giro.id,
        "giro_numero_turno": giro.numero_turno,
        "violazioni": violazioni,
        "stazione_sede": stazione_sede,
        "generato_at": datetime.utcnow().isoformat(),
        "builder_version": "mvp-7.9-eta",
        # Sprint 7.7 MR 3: il giro materiale è ora UN pattern
        # calendariale specifico (etichetta_tipo) — niente più
        # combinazioni di varianti. ``giornate_ids`` traccia le
        # giornate del giro che alimentano questo TurnoPdc per
        # tracciabilità in audit.
        "giornate_giro_ids": giornate_ids,
        # Sprint 7.9 MR η: traccia identità deposito sia in metadata
        # (per compat strumenti di audit / dump JSON) sia in colonna
        # FK (per query indicizzate).
        "deposito_pdc_codice": depot_target.codice if depot_target is not None else None,
        "deposito_pdc_display": (
            depot_target.display_name if depot_target is not None else None
        ),
    }
    metadata.update(extra_metadata)

    # Impianto: con depot esplicito è il display name del deposito;
    # altrimenti (legacy) il tipo_materiale del giro per non rompere
    # la dashboard "Distribuzione per impianto" pre-MR η.
    if depot_target is not None:
        impianto = depot_target.display_name[:80]
    else:
        impianto = giro.tipo_materiale[:80] if giro.tipo_materiale else "ND"

    turno = TurnoPdc(
        azienda_id=azienda_id,
        codice=codice,
        impianto=impianto,
        profilo="Condotta",
        ciclo_giorni=max(1, min(14, giro.numero_giornate)),
        valido_da=valido_da_eff,
        valido_a=None,
        source_file=None,
        deposito_pdc_id=depot_target.id if depot_target is not None else None,
        generation_metadata_json=metadata,
        stato="bozza",
    )
    session.add(turno)
    await session.flush()

    prestazione_totale = 0
    condotta_totale = 0
    for d in drafts:
        gg_orm = TurnoPdcGiornata(
            turno_pdc_id=turno.id,
            numero_giornata=d.numero_giornata,
            variante_calendario=(d.variante_calendario or "GG")[:20],
            stazione_inizio=d.stazione_inizio,
            stazione_fine=d.stazione_fine,
            inizio_prestazione=d.inizio_prestazione,
            fine_prestazione=d.fine_prestazione,
            prestazione_min=d.prestazione_min,
            condotta_min=d.condotta_min,
            refezione_min=d.refezione_min,
            km=0,
            is_notturno=d.is_notturno,
            is_riposo=False,
            is_disponibile=False,
            riposo_min=0,
        )
        session.add(gg_orm)
        await session.flush()
        prestazione_totale += d.prestazione_min
        condotta_totale += d.condotta_min

        for b in d.blocchi:
            session.add(
                TurnoPdcBlocco(
                    turno_pdc_giornata_id=gg_orm.id,
                    seq=b.seq,
                    tipo_evento=b.tipo_evento,
                    corsa_commerciale_id=b.corsa_commerciale_id,
                    corsa_materiale_vuoto_id=b.corsa_materiale_vuoto_id,
                    giro_blocco_id=b.giro_blocco_id,
                    stazione_da_codice=b.stazione_da_codice,
                    stazione_a_codice=b.stazione_a_codice,
                    ora_inizio=b.ora_inizio,
                    ora_fine=b.ora_fine,
                    durata_min=b.durata_min,
                    is_accessori_maggiorati=False,
                    cv_parent_blocco_id=None,
                    accessori_note=b.accessori_note,
                    fonte_orario="builder",
                )
            )

    fr_giornate_meta = extra_metadata.get("fr_giornate") or []
    fr_cap_meta = extra_metadata.get("fr_cap_violazioni") or []
    return BuilderTurnoPdcResult(
        turno_pdc_id=turno.id,
        codice=turno.codice,
        n_giornate=len(drafts),
        prestazione_totale_min=prestazione_totale,
        condotta_totale_min=condotta_totale,
        violazioni=violazioni,
        is_ramo_split=bool(extra_metadata.get("is_ramo_split", False)),
        split_origine_giornata=extra_metadata.get("split_origine_giornata"),
        split_ramo=extra_metadata.get("split_ramo"),
        split_totale_rami=extra_metadata.get("split_totale_rami"),
        deposito_pdc_id=depot_target.id if depot_target is not None else None,
        deposito_pdc_codice=depot_target.codice if depot_target is not None else None,
        n_dormite_fr=len(fr_giornate_meta),
        fr_cap_violazioni=list(fr_cap_meta),
    )


def _aggiungi_dormite_fr(
    drafts: list[_GiornataPdcDraft],
    stazione_sede: str | None,
) -> list[dict[str, Any]]:
    """Identifica pernottamenti FR fra giornate consecutive e prepende
    un blocco DORMITA alla giornata successiva.

    Una dormita FR esiste se:
    - la giornata N termina in una stazione X
    - la giornata N+1 inizia da X
    - X è diversa dalla stazione sede del PdC

    Ritorna la lista delle dormite create (per metadata): ogni elemento
    è ``{"giornata": numero_giornata_arrivo, "stazione": codice,
    "ore": float}``.

    Limiti settimanali (max 1/sett, max 3/28gg) NON enforced nel MVP.
    """
    fr_log: list[dict[str, Any]] = []
    for i in range(1, len(drafts)):
        prec = drafts[i - 1]
        curr = drafts[i]
        if prec.stazione_fine is None or curr.stazione_inizio is None:
            continue
        if prec.stazione_fine != curr.stazione_inizio:
            continue
        if stazione_sede is not None and prec.stazione_fine == stazione_sede:
            continue

        # Calcolo durata pernotto: dal fine prestazione N a inizio
        # prestazione N+1 (assumendo giorno calendario successivo).
        # Se la giornata N termina dopo mezzanotte (notturna), `fine_n`
        # è già nel giorno calendario N+1, quindi il gap si calcola
        # diversamente.
        fine_n = _t(prec.fine_prestazione)
        inizio_n1 = _t(curr.inizio_prestazione)
        if prec.is_notturno and fine_n < _t(prec.inizio_prestazione):
            # fine_n è dopo mezzanotte, stesso giorno calendario di N+1
            durata_pernotto = max(0, inizio_n1 - fine_n)
        else:
            durata_pernotto = (24 * 60 - fine_n) + inizio_n1

        # Blocco DORMITA: rappresentazione MVP, copre 00:00→ora_presa
        # della giornata N+1 (la parte residua di giorno N è implicita
        # nella durata totale annotata).
        nuovo_blocco = _BloccoPdcDraft(
            seq=0,  # rinumerato sotto
            tipo_evento="DORMITA",
            ora_inizio=time(0, 0),
            ora_fine=curr.inizio_prestazione,
            durata_min=inizio_n1,
            stazione_da_codice=curr.stazione_inizio,
            stazione_a_codice=curr.stazione_inizio,
            accessori_note=f"FR a {curr.stazione_inizio} (pernotto {durata_pernotto}min)",
        )
        curr.blocchi.insert(0, nuovo_blocco)
        for j, b in enumerate(curr.blocchi, start=1):
            b.seq = j

        # Aggiorna inizio prestazione: la dormita anticipa l'orario
        # ufficiale di servizio (la PRESA resta dove era, ma il PdC
        # è "in carico" dalla fine giornata precedente). Per il MVP
        # NON aggiorniamo inizio_prestazione: prestazione_min resta
        # quella della giornata operativa, la dormita è informativa.

        fr_log.append(
            {
                "giornata": curr.numero_giornata,
                "stazione": curr.stazione_inizio,
                "ore": round(durata_pernotto / 60, 1),
            }
        )

    return fr_log


def _genera_codice_turno(
    giro: GiroMateriale, depot: Depot | None = None
) -> str:
    """Codice turno PdC derivato dal giro.

    - Senza ``depot``: ``T-<giro.numero_turno>`` (legacy MVP).
    - Con ``depot``: ``T-<depot.codice>-<giro.numero_turno>``. Permette
      a uno stesso giro di avere turni distinti per depositi diversi
      senza conflitto di chiave (Sprint 7.9 MR η).

    Il troncamento finale a 48 char rispetta il VARCHAR(50) di
    ``turno_pdc.codice`` (-2 char per ``T-``).
    """
    base = (giro.numero_turno or f"GIRO{giro.id}")
    if depot is not None:
        composto = f"{depot.codice}-{base}"
    else:
        composto = base
    return f"T-{composto[:48]}"


def _calcola_violazioni_cap_fr(
    *, n_dormite_fr: int, ciclo_giorni: int
) -> list[str]:
    """Calcola violazioni dei cap FR (NORMATIVA-PDC §10.6).

    I cap normativi sono **per PdC** (1/settimana, 3/28gg), non per
    turno. Tuttavia, dentro un singolo turno-ciclo, il numero di FR
    fissi (= dormite incorporate nel pattern del turno) può già da
    solo eccedere il limite settimanale o mensile, perché ciascun PdC
    assegnato a quel turno le subisce per quel ciclo.

    Conversione conservativa applicata qui:

    - se ``ciclo_giorni <= 7`` → tetto = ``FR_MAX_PER_SETTIMANA`` (1).
      Eccedere significa che il singolo PdC, in una settimana di
      lavoro, supererebbe il cap.
    - per cicli più lunghi (più settimane) il tetto cresce
      proporzionalmente: ``ceil(ciclo / 7) * FR_MAX_PER_SETTIMANA``,
      a meno che non venga prima superato il cap mensile
      (``FR_MAX_PER_28GG = 3``) per cicli ≥ 28 giorni.

    Output: lista vuota se tutto in regola; altrimenti tag descrittivi
    pronti per il pannello "Vincoli ciclo" della UI.
    """
    if n_dormite_fr <= 0 or ciclo_giorni <= 0:
        return []

    out: list[str] = []
    settimane = max(1, (ciclo_giorni + 6) // 7)
    tetto_settimanale = settimane * FR_MAX_PER_SETTIMANA
    if n_dormite_fr > tetto_settimanale:
        out.append(
            f"fr_cap_settimanale:{n_dormite_fr}>{tetto_settimanale}"
            f"(ciclo {ciclo_giorni}gg, max {FR_MAX_PER_SETTIMANA}/sett)"
        )
    if ciclo_giorni <= 28 and n_dormite_fr > FR_MAX_PER_28GG:
        out.append(
            f"fr_cap_28gg:{n_dormite_fr}>{FR_MAX_PER_28GG}"
            f"(ciclo {ciclo_giorni}gg)"
        )
    return out


class GiriEsistentiError(Exception):
    """Esiste già un turno PdC per questo giro (serve force=True)."""
