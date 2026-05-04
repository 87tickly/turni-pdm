"""Sprint 7.9 MR β2-4 — proiezione thread materiale dal giro aggregato.

Funzione **DB-async** (richiede session per persistere) che, dato un
``GiroAggregato`` appena persistito (con i suoi `GiroBlocco`),
proietta N ``MaterialeThread`` con i loro ``MaterialeThreadEvento``,
uno per ogni "pezzo logico" della composizione massima del giro.

Algoritmo MVP (versione semplificata β2-4 step 1):

1. Per ogni giro aggregato, considera la **variante canonica**
   (variant_index=0) di ogni giornata.
2. Calcola il numero massimo di pezzi simultanei della giornata
   (es. composizione [(ETR526, 2)] → 2 thread, [(ETR421, 3)] → 3
   thread). Materiali multipli (es. [(ETR526, 2), (ETR425, 1)]) →
   thread per ciascun materiale-pezzo.
3. Per ogni slot pezzo (es. ETR526 #1, ETR526 #2):
   - Crea 1 ``MaterialeThread`` agganciato al giro.
   - Per ogni blocco corsa della variante canonica, se la
     composizione contiene >= slot_idx pezzi del materiale, aggiunge
     un ``MaterialeThreadEvento`` di tipo ``corsa_doppia_pos{idx}``
     (o ``corsa_singolo`` se composizione=1).
   - Aggiunge eventi ``vuoto_solo`` per i blocchi materiale_vuoto
     "individuali" (= il pezzo si sposta da solo, es. testa/coda).
   - Aggiunge eventi marker ``aggancio``/``sgancio`` (puntatori al
     giro_blocco corrispondente).
   - Aggrega ``km_totali`` e ``minuti_servizio``.

**Limitazioni MVP**:

- Solo variante canonica. Le altre varianti calendariali generano
  thread aggiuntivi solo se la sequenza è diversa (β2-4 step 2 +
  futuro).
- Sosta tra sgancio/riaggancio non modellata esplicitamente come
  evento (= scope futuro β2-4 step 3 / β2-7).
- ``matricola_id`` sempre NULL (assegnamento Manutenzione futuro).
- Cross-thread (= 2 giri che si scambiano un thread via aggancio
  da catena esterna) non tracciato — il sourcing β2-3 lo descrive
  testualmente ma il thread resta interno al giro origine.

**Stat aggregate per thread**: km_totali = somma km_tratta delle
corse commerciali a cui il pezzo partecipa.
"""

from __future__ import annotations

from datetime import date as date_t
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from colazione.models.anagrafica import (
    MaterialeThread,
    MaterialeThreadEvento,
)
from colazione.models.giri import GiroBlocco, GiroGiornata, GiroVariante


# =====================================================================
# Helpers
# =====================================================================


async def _carica_blocchi_variante_canonica(
    session: AsyncSession, giro_materiale_id: int
) -> list[tuple[GiroGiornata, GiroBlocco]]:
    """Carica i blocchi della variante CANONICA (variant_index=0) di
    ogni giornata del giro, ordinati per giornata + seq.

    Restituisce la lista [(giornata, blocco), ...].
    """
    from sqlalchemy import select

    stmt = (
        select(GiroGiornata, GiroBlocco)
        .join(
            GiroVariante,
            GiroVariante.giro_giornata_id == GiroGiornata.id,
        )
        .join(GiroBlocco, GiroBlocco.giro_variante_id == GiroVariante.id)
        .where(
            GiroGiornata.giro_materiale_id == giro_materiale_id,
            GiroVariante.variant_index == 0,
        )
        .order_by(GiroGiornata.numero_giornata, GiroBlocco.seq)
    )
    result = await session.execute(stmt)
    rows = list(result.all())
    return [(g, b) for g, b in rows]


def _composizione_da_blocco(blocco: GiroBlocco) -> list[tuple[str, int]]:
    """Estrae la composizione [(materiale, n_pezzi), ...] dal
    metadata_json di un blocco ``corsa_commerciale``.

    Per blocchi non-commerciali ritorna lista vuota.
    """
    if blocco.tipo_blocco != "corsa_commerciale":
        return []
    meta = blocco.metadata_json or {}
    comp = meta.get("composizione")
    if not isinstance(comp, list):
        return []
    out: list[tuple[str, int]] = []
    for item in comp:
        if not isinstance(item, dict):
            continue
        mat = item.get("materiale_tipo_codice")
        n = item.get("n_pezzi")
        if isinstance(mat, str) and isinstance(n, int):
            out.append((mat, n))
    return out


def _composizione_max_giro(
    blocchi_canonici: list[tuple[GiroGiornata, GiroBlocco]],
) -> list[tuple[str, int]]:
    """Composizione massima usata in TUTTO il giro: per ogni materiale,
    il MAX n_pezzi visto in qualunque corsa di qualunque giornata.

    Esempio: giro con corsa1=[(ETR526, 2)], corsa2=[(ETR526, 1),
    (ETR425, 1)] → max = [(ETR526, 2), (ETR425, 1)] = 3 thread totali.
    """
    max_per_mat: dict[str, int] = {}
    for _g, b in blocchi_canonici:
        for mat, n in _composizione_da_blocco(b):
            if n > max_per_mat.get(mat, 0):
                max_per_mat[mat] = n
    return [(m, n) for m, n in sorted(max_per_mat.items())]


def _tipo_evento_per_pezzo(
    composizione_blocco: list[tuple[str, int]],
    materiale_thread: str,
    slot_idx: int,
) -> str | None:
    """Decide il tipo di evento per il pezzo (materiale, slot_idx) in
    una corsa con composizione data.

    Restituisce:
    - None se il materiale non è presente (= il pezzo non partecipa
      a questa corsa).
    - None se slot_idx > pezzi di quel materiale (= il pezzo non c'è).
    - "corsa_singolo" se totale pezzi = 1.
    - "corsa_doppia_pos1"/"_pos2" se totale = 2.
    - "corsa_tripla_pos1"/"_pos2"/"_pos3" se totale = 3.
    - "corsa_multipla_pos{N}" se totale > 3 (composizioni rare).
    """
    pezzi_materiale = next(
        (n for m, n in composizione_blocco if m == materiale_thread), 0
    )
    if pezzi_materiale == 0 or slot_idx > pezzi_materiale:
        return None
    totale = sum(n for _m, n in composizione_blocco)
    if totale == 1:
        return "corsa_singolo"
    if totale == 2:
        return f"corsa_doppia_pos{slot_idx}"
    if totale == 3:
        return f"corsa_tripla_pos{slot_idx}"
    return f"corsa_multipla_pos{slot_idx}"


# =====================================================================
# API pubblica
# =====================================================================


async def proietta_thread_giro(
    session: AsyncSession,
    *,
    giro_materiale_id: int,
    azienda_id: int,
    programma_id: int,
) -> list[int]:
    """Proietta N ``MaterialeThread`` per il giro indicato.

    Idempotente per giro: cancella i thread esistenti del giro prima
    di proiettarli (gli eventi cascade automaticamente). Sicuro da
    chiamare in fase di rigenerazione giri (β2-4 wiped i thread con
    cascade FK ``giro_materiale_id_origine``).

    Returns:
        Lista degli ``id`` dei nuovi thread creati.
    """
    from sqlalchemy import delete, select

    # Cleanup thread esistenti per questo giro (idempotenza).
    await session.execute(
        delete(MaterialeThread).where(
            MaterialeThread.giro_materiale_id_origine == giro_materiale_id
        )
    )

    blocchi_canonici = await _carica_blocchi_variante_canonica(
        session, giro_materiale_id
    )
    if not blocchi_canonici:
        return []

    composizione_max = _composizione_max_giro(blocchi_canonici)
    if not composizione_max:
        return []

    # Genera 1 thread per ogni (materiale, slot 1..N_max).
    thread_ids: list[int] = []
    for materiale, n_max in composizione_max:
        for slot_idx in range(1, n_max + 1):
            thread = MaterialeThread(
                azienda_id=azienda_id,
                programma_id=programma_id,
                giro_materiale_id_origine=giro_materiale_id,
                tipo_materiale_codice=materiale,
                matricola_id=None,
                km_totali=0,
                minuti_servizio=0,
                n_corse_commerciali=0,
            )
            session.add(thread)
            await session.flush()
            thread_id: int = thread.id

            # Itera blocchi e proietta gli eventi a cui il pezzo
            # partecipa.
            ordine = 1
            km_tot = Decimal("0")
            min_tot = 0
            n_corse = 0
            for giornata, b in blocchi_canonici:
                evento_tipo: str | None = None
                if b.tipo_blocco == "corsa_commerciale":
                    comp = _composizione_da_blocco(b)
                    evento_tipo = _tipo_evento_per_pezzo(
                        comp, materiale, slot_idx
                    )
                    if evento_tipo is None:
                        continue
                    # Recupera km della corsa dal payload di
                    # CorsaCommerciale (FK già caricata via
                    # giro_blocco.corsa_commerciale_id, ma servirebbe
                    # un join — semplifico leggendo dal metadata se
                    # presente, altrimenti km=NULL).
                    km_corsa = await _km_corsa_commerciale(
                        session, b.corsa_commerciale_id
                    )
                    if km_corsa is not None:
                        km_tot += km_corsa
                    min_corsa = _minuti_blocco(b)
                    if min_corsa is not None:
                        min_tot += min_corsa
                    n_corse += 1
                    km_evento: float | None = (
                        float(km_corsa) if km_corsa is not None else None
                    )
                elif b.tipo_blocco == "materiale_vuoto":
                    # Vuoto = il pezzo si sposta solo (di norma 1 pezzo
                    # per vuoto, ma se composizione doppia il vuoto è
                    # condiviso). Per MVP assumiamo che il vuoto si
                    # applichi a TUTTI gli slot del materiale che
                    # erano in linea — popoliamo solo se è uscita
                    # ciclo, rientro deposito, o intra-area.
                    meta = b.metadata_json or {}
                    tipo_v = meta.get("tipo_vuoto")
                    if tipo_v == "uscita_deposito":
                        evento_tipo = "uscita_deposito"
                    elif tipo_v == "rientro_deposito":
                        evento_tipo = "rientro_deposito"
                    else:
                        evento_tipo = "vuoto_solo"
                    km_evento = None
                elif b.tipo_blocco in ("aggancio", "sgancio"):
                    # Marker dell'evento composizione: lo includiamo
                    # nel thread se il pezzo è coinvolto. Per MVP
                    # includiamo solo se delta riguarda il materiale
                    # del thread.
                    meta = b.metadata_json or {}
                    if (
                        meta.get("materiale_tipo_codice") != materiale
                    ):
                        continue
                    evento_tipo = b.tipo_blocco
                    km_evento = None
                else:
                    continue

                evento = MaterialeThreadEvento(
                    thread_id=thread_id,
                    ordine=ordine,
                    tipo=evento_tipo,
                    giro_blocco_id=b.id,
                    stazione_da_codice=b.stazione_da_codice,
                    stazione_a_codice=b.stazione_a_codice,
                    ora_inizio=b.ora_inizio,
                    ora_fine=b.ora_fine,
                    data_giorno=_data_giornata(giornata),
                    km_tratta=km_evento,
                    numero_treno=_numero_treno_blocco(b),
                    note=None,
                )
                session.add(evento)
                ordine += 1

            # Aggiorna le metriche del thread
            thread.km_totali = float(km_tot)
            thread.minuti_servizio = min_tot
            thread.n_corse_commerciali = n_corse
            await session.flush()
            thread_ids.append(thread_id)

    return thread_ids


# =====================================================================
# Helpers query
# =====================================================================


async def _km_corsa_commerciale(
    session: AsyncSession, corsa_commerciale_id: int | None
) -> Decimal | None:
    """Carica km_tratta da CorsaCommerciale (FK opzionale)."""
    if corsa_commerciale_id is None:
        return None
    from sqlalchemy import select

    from colazione.models.corse import CorsaCommerciale

    stmt = select(CorsaCommerciale.km_tratta).where(
        CorsaCommerciale.id == corsa_commerciale_id
    )
    val = (await session.execute(stmt)).scalar_one_or_none()
    if val is None:
        return None
    return Decimal(val)


def _minuti_blocco(blocco: GiroBlocco) -> int | None:
    """Calcola minuti di durata di un blocco (gestisce cross-mezzanotte)."""
    if blocco.ora_inizio is None or blocco.ora_fine is None:
        return None
    inizio = blocco.ora_inizio.hour * 60 + blocco.ora_inizio.minute
    fine = blocco.ora_fine.hour * 60 + blocco.ora_fine.minute
    if fine < inizio:
        fine += 24 * 60
    return fine - inizio


def _data_giornata(giornata: GiroGiornata) -> date_t | None:
    """Estrae la data canonica dalla giornata.

    Per ora ritorniamo None (campo non presente sul modello GiroGiornata
    — è derivato dal contesto ProgrammaMateriale.valido_da +
    numero_giornata). Sufficiente per la versione MVP.
    """
    _ = giornata
    return None


def _numero_treno_blocco(blocco: GiroBlocco) -> str | None:
    """Estrae il numero treno dal blocco se identificabile.

    Per ``corsa_commerciale`` usa la ``descrizione`` (= numero treno
    persistito da ``persister._persisti_blocchi_variante``).
    Per ``materiale_vuoto`` usa ``metadata_json.numero_treno_virtuale``
    (parlante 9XXXX, MR β2-2).
    """
    if blocco.tipo_blocco == "corsa_commerciale" and blocco.descrizione:
        return str(blocco.descrizione)
    meta = blocco.metadata_json or {}
    nt = meta.get("numero_treno_virtuale") or meta.get(
        "numero_treno_placeholder"
    )
    return str(nt) if nt is not None else None


__all__ = ["proietta_thread_giro"]
