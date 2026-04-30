"""Split CV intermedio per il builder turno PdC — Sprint 7.4.

Quando una giornata di giro materiale produce un turno PdC che sfora
i limiti normativi (prestazione 510/420 min, condotta 330 min),
questo modulo individua un punto di "cambio volante" in una stazione
ammessa e divide la giornata in N rami che rispettano i limiti.

Decisioni di scope per Sprint 7.4 MR 1 (TN-UPDATE entry pendente):

- Ricorsione max 5 livelli per safety: una giornata di 17h può
  produrre fino a 5 rami consecutivi.
- Stazioni CV ammesse = depositi PdC dell'azienda
  (`Depot.stazione_principale_codice` per `tipi_personale_ammessi
  == 'PdC'` + `is_attivo`) PIÙ deroghe hardcoded
  `{MORTARA, TIRANO}` (vedi `docs/NORMATIVA-PDC.md:701-717`).
  Refactor a regola configurabile per programma è in iterazioni
  successive.
- Output: 1 giornata splittata → N `_GiornataPdcDraft` distinti, che
  diventeranno N `TurnoPdc` separati nel persister (MR 2).

L'algoritmo NON modifica le strutture intermedie del builder ma
ricostruisce ogni ramo richiamando `_build_giornata_pdc()` su
sotto-liste dei blocchi giro originali. Vantaggio: ogni ramo è
autonomo, validato indipendentemente, con i propri
PRESA/ACCp/.../ACCa/FINE.

Limitazione MVP: non viene applicato il pattern CV no-overhead
(gap < 65' → CVa/CVp che sostituiscono ACCa/ACCp risparmiando 80').
Ogni ramo paga il costo accessori standard. Vedi
`docs/NORMATIVA-PDC.md:440-476` per la regola: questa ottimizzazione
sarà un MR successivo se l'utente la chiede; per ora l'obiettivo
prioritario è chiudere le violazioni di prestazione/condotta.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.domain.builder_pdc.builder import (
    CONDOTTA_MAX_MIN,
    PRESTAZIONE_MAX_NOTTURNO,
    PRESTAZIONE_MAX_STANDARD,
    _build_giornata_pdc,
    _GiornataPdcDraft,
)
from colazione.models.anagrafica import Depot
from colazione.models.giri import GiroBlocco

# Cap di sicurezza sulla profondità di ricorsione. Una giornata di
# 17h con punti CV ben distribuiti richiede tipicamente 2-3 split.
# Cinque livelli coprono casi patologici senza rischio di esplosione.
MAX_LIVELLI_SPLIT = 5

# Deroghe normativa: stazioni non-deposito ma esplicitamente ammesse a
# CV (vedi `docs/NORMATIVA-PDC.md:701-717`). Hardcoded per MVP Sprint
# 7.4; refactor a regola configurabile per programma in iterazioni
# successive. Codici stazione attesi nel DB Trenord standard.
STAZIONI_CV_DEROGA: frozenset[str] = frozenset({"MORTARA", "TIRANO"})


async def lista_stazioni_cv_ammesse(
    session: AsyncSession, azienda_id: int
) -> set[str]:
    """Calcola l'insieme dei codici stazione ammessi a CV per l'azienda.

    Sorgenti:

    - `Depot.stazione_principale_codice` per i depositi PdC attivi
      dell'azienda.
    - Deroghe hardcoded `STAZIONI_CV_DEROGA`.

    Le deroghe sono ammesse anche se non corrispondono a depositi PdC
    dell'azienda corrente (tipicamente stazioni capolinea con
    inversione, es. TIRANO, oppure deroghe esplicite NORMATIVA come
    MORTARA).
    """
    stmt = select(Depot.stazione_principale_codice).where(
        Depot.azienda_id == azienda_id,
        Depot.tipi_personale_ammessi == "PdC",
        Depot.is_attivo.is_(True),
        Depot.stazione_principale_codice.is_not(None),
    )
    res = await session.execute(stmt)
    stazioni: set[str] = {row[0] for row in res.all() if row[0] is not None}
    stazioni.update(STAZIONI_CV_DEROGA)
    return stazioni


def split_e_build_giornata(
    numero_giornata: int,
    variante_calendario: str,
    blocchi_giro: list[GiroBlocco],
    stazioni_cv: set[str],
    livello: int = 0,
) -> list[_GiornataPdcDraft]:
    """Costruisce una giornata PdC, splittando se eccede i limiti.

    Strategia:

    1. Costruisce un draft con `_build_giornata_pdc` (logica MVP).
    2. Se il draft è entro i limiti normativi → ritorna `[draft]`.
    3. Se eccede e si è sotto `MAX_LIVELLI_SPLIT`, cerca un punto di
       split greedy (primo punto valido nei blocchi giro), divide
       i blocchi e ricorre su entrambi i rami.
    4. Se non si trova un punto valido, ritorna comunque `[draft]`
       con la violazione marcata: la decomposizione conserva
       l'onestà del MVP entry 42.

    Ritorna lista vuota solo se il segmento di blocchi è vuoto
    (es. dopo uno split degenere).
    """
    draft = _build_giornata_pdc(numero_giornata, variante_calendario, blocchi_giro)
    if draft is None:
        return []
    if not _eccede_limiti(draft):
        return [draft]
    if livello >= MAX_LIVELLI_SPLIT:
        # Cap di sicurezza raggiunto: il ramo resta con violazione.
        return [draft]
    punto = _trova_punto_split(
        numero_giornata, variante_calendario, blocchi_giro, stazioni_cv
    )
    if punto is None:
        # Nessuna stazione CV ammessa lungo la tratta: violazione resta.
        return [draft]
    blocchi_a = blocchi_giro[: punto + 1]
    blocchi_b = blocchi_giro[punto + 1 :]
    rami_a = split_e_build_giornata(
        numero_giornata, variante_calendario, blocchi_a, stazioni_cv, livello + 1
    )
    rami_b = split_e_build_giornata(
        numero_giornata, variante_calendario, blocchi_b, stazioni_cv, livello + 1
    )
    return rami_a + rami_b


def _eccede_limiti(draft: _GiornataPdcDraft) -> bool:
    """True se prestazione o condotta del draft sforano i limiti.

    Allinea il cap di prestazione al regime applicabile (notturno se
    `is_notturno`, altrimenti standard). Il calcolo replica la logica
    di validazione interna di `_build_giornata_pdc`, così che la
    soglia di trigger split coincida con il flag di violazione.

    Refezione mancante NON è motivo di split: una refezione si può
    sempre inserire dentro un ramo che rispetta i limiti di
    prestazione, e il builder già lo fa quando trova un PK ≥30' in
    finestra.
    """
    cap_prestazione = (
        PRESTAZIONE_MAX_NOTTURNO if draft.is_notturno else PRESTAZIONE_MAX_STANDARD
    )
    return (
        draft.prestazione_min > cap_prestazione
        or draft.condotta_min > CONDOTTA_MAX_MIN
    )


def _trova_punto_split(
    numero_giornata: int,
    variante_calendario: str,
    blocchi_giro: list[GiroBlocco],
    stazioni_cv: set[str],
) -> int | None:
    """Indice del blocco dopo cui tagliare la giornata (None se nessuno).

    Strategia greedy "primo punto valido":

    - Itera i blocchi giro 0..N-2 (l'ultimo non può essere punto di
      taglio, deve esserci almeno un blocco nel ramo B).
    - Per ogni indice `i`, considera `blocchi_giro[i]
      .stazione_a_codice` come candidato di cambio volante.
    - Se la stazione è in `stazioni_cv`, costruisci il ramo A
      (= `blocchi_giro[:i+1]`) chiamando `_build_giornata_pdc` e
      verifica che non ecceda i limiti.
    - Primo `i` che produce un ramo A entro limiti → return i.

    Il ramo B è validato dalla ricorsione di `split_e_build_giornata`,
    quindi qui non serve verificarlo.

    Trade-off: la strategia greedy può lasciare il ramo B
    sproporzionato (lungo) e quindi richiedere ulteriori split
    nidificati. La ricorsione fino a `MAX_LIVELLI_SPLIT` gestisce il
    caso. Una versione "punto più bilanciato" (es. quello più vicino
    alla metà della prestazione) è un raffinamento successivo se i
    test su dati reali mostreranno vantaggi misurabili.
    """
    if len(blocchi_giro) < 2:
        return None
    for i in range(len(blocchi_giro) - 1):
        stazione_a = blocchi_giro[i].stazione_a_codice
        if stazione_a is None or stazione_a not in stazioni_cv:
            continue
        ramo_a = _build_giornata_pdc(
            numero_giornata, variante_calendario, blocchi_giro[: i + 1]
        )
        if ramo_a is None:
            continue
        if not _eccede_limiti(ramo_a):
            return i
    return None
