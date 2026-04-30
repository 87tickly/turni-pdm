"""Sprint 7.5 — smoke che dimostra il bug 5 chiuso (MR 7/7).

Crea un programma di test con 2 corse commerciali ricorrenti
lunedì-venerdì:

- corsa A (S99001 → S99002, 08:00→09:00): valida tutti i giorni
  feriali del 2026 TRANNE 5 festività lavorative — pattern "circola
  tranne festività"
- corsa B (S99002 → S99001, 10:00→11:00): valida tutti i giorni
  feriali del 2026 — pattern "circola sempre"

Lancia ``genera_giri()`` con default (periodo intero, decisione
utente C3 di Sprint 7.5 MR 4) e stampa i numeri DB.

**Atteso post-refactor bug 5** (MR 1 clustering A1 + MR 3 persister):

- 2 giri distinti (cluster A1 separa pattern):
  1. "AB" giro con sequenza [A, B] chiuso a sede:
     dates_apply ≈ 256 date (feriali tranne 5 festività)
  2. "B-only" giro con sequenza [B] preceduta da vuoto S99001→S99002:
     dates_apply ≈ 5 date (le 5 festività in cui A non circola)
- Ogni giornata ha 1 sola variante (variant_index=0, A1 strict)
- ``validita_dates_apply_json`` contiene le date REALI in cui il
  pattern è applicabile (no più "intersezione menzogna" su 261/261)

**Pre-refactor (entry 45 TN-UPDATE)**, sullo stesso input avrebbe
prodotto:

- N giri = 261 (uno per ogni data calendaristica del periodo
  osservato)
- ogni giornata con 1 variante e ``validita_dates_apply_json`` =
  intersezione di valid_in_date delle corse del giorno (256 date per
  pattern AB, 261 per pattern B-only) — date sbagliate
- pattern festività VS feriale silenzialmente non distinti

Lo script lascia i dati in DB (no wipe finale) per consentire la
verifica visuale via preview frontend (`/pianificatore-giro/giri/<id>`).
Puoi pulire con `make smoke-bug5-clean` o eseguire i test
integration (i wipe `LIKE 'TEST_%'` rimuovono il programma).
"""

from __future__ import annotations

import asyncio
from datetime import date, time, timedelta

from sqlalchemy import select, text

from colazione.db import session_scope
from colazione.domain.builder_giro.builder import genera_giri
from colazione.models.anagrafica import LocalitaManutenzione, Stazione
from colazione.models.corse import CorsaCommerciale
from colazione.models.giri import GiroGiornata, GiroMateriale, GiroVariante
from colazione.models.programmi import (
    ProgrammaMateriale,
    ProgrammaRegolaAssegnazione,
)

AZIENDA_ID = 2  # trenord (id seed)
PROGRAMMA_NOME = "TEST_SMOKE_BUG5_CHIUSO"
LOCALITA_CODICE = "TEST_LOC_BUG5"
LOCALITA_BREVE = "TBUG"
STAZIONE_SEDE = "S99001"
STAZIONE_FUORI = "S99002"
MATERIALE_TIPO = "ALe711"  # esiste nel seed Trenord


# Periodo programma: 1 anno
VALIDO_DA = date(2026, 1, 1)
VALIDO_A = date(2026, 12, 31)


def _genera_lavorativi(anno_da: date, anno_a: date) -> list[str]:
    """Ritorna lista ISO date dei giorni lunedì-venerdì nel range."""
    out: list[str] = []
    d = anno_da
    while d <= anno_a:
        if d.weekday() < 5:  # lun=0, ven=4
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


# 5 festività lavorative-tipo del 2026 (cadono di lun-ven, ipotetiche)
FESTIVITA_LAVORATIVE_2026 = [
    "2026-01-06",  # Epifania (martedì)
    "2026-04-03",  # Venerdì santo (venerdì)
    "2026-04-06",  # Pasquetta (lunedì)
    "2026-12-08",  # Immacolata (martedì)
    "2026-12-25",  # Natale (venerdì)
]


async def setup_dati() -> int:
    """Crea programma + stazioni + località + corse + regola. Ritorna programma_id."""
    lavorativi = _genera_lavorativi(VALIDO_DA, VALIDO_A)
    valid_a = [d for d in lavorativi if d not in FESTIVITA_LAVORATIVE_2026]
    valid_b = lavorativi  # tutti i feriali

    print(
        f"[setup] feriali totali nel 2026: {len(lavorativi)}; "
        f"corsa A circola in {len(valid_a)} date (5 festività escluse), "
        f"corsa B in {len(valid_b)}"
    )

    async with session_scope() as session:
        # Stazioni
        for cod in (STAZIONE_SEDE, STAZIONE_FUORI):
            existing = (
                await session.execute(
                    select(Stazione).where(
                        Stazione.codice == cod, Stazione.azienda_id == AZIENDA_ID
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(Stazione(codice=cod, nome=cod, azienda_id=AZIENDA_ID))
        await session.flush()

        # Località
        loc = (
            await session.execute(
                select(LocalitaManutenzione).where(
                    LocalitaManutenzione.codice == LOCALITA_CODICE,
                    LocalitaManutenzione.azienda_id == AZIENDA_ID,
                )
            )
        ).scalar_one_or_none()
        if loc is None:
            loc = LocalitaManutenzione(
                codice=LOCALITA_CODICE,
                codice_breve=LOCALITA_BREVE,
                nome_canonico="Test Località Bug 5",
                stazione_collegata_codice=STAZIONE_SEDE,
                azienda_id=AZIENDA_ID,
            )
            session.add(loc)
            await session.flush()

        # Programma (cancella eventuale precedente per ripartire pulito)
        existing_prog = (
            await session.execute(
                select(ProgrammaMateriale).where(
                    ProgrammaMateriale.nome == PROGRAMMA_NOME
                )
            )
        ).scalar_one_or_none()
        if existing_prog is not None:
            print(f"[setup] programma '{PROGRAMMA_NOME}' esiste (id={existing_prog.id}), rimuovo")
            await session.execute(
                text(
                    "DELETE FROM giro_materiale WHERE programma_id = :pid"
                ),
                {"pid": existing_prog.id},
            )
            await session.execute(
                text(
                    "DELETE FROM programma_regola_assegnazione WHERE programma_id = :pid"
                ),
                {"pid": existing_prog.id},
            )
            await session.delete(existing_prog)
            await session.flush()

        prog = ProgrammaMateriale(
            azienda_id=AZIENDA_ID,
            nome=PROGRAMMA_NOME,
            valido_da=VALIDO_DA,
            valido_a=VALIDO_A,
            stato="attivo",
            n_giornate_default=30,
            km_max_ciclo=10000,
            fascia_oraria_tolerance_min=30,
            strict_options_json={
                "no_corse_residue": False,
                "no_overcapacity": False,
                "no_aggancio_non_validato": False,
                "no_orphan_blocks": False,
                "no_giro_appeso": False,
                "no_km_eccesso": False,
            },
            stazioni_sosta_extra_json=[STAZIONE_FUORI],
        )
        session.add(prog)
        await session.flush()
        prog_id = int(prog.id)

        # Regola: cattura tutte le corse delle stazioni S99* del setup
        regola = ProgrammaRegolaAssegnazione(
            programma_id=prog_id,
            filtri_json=[
                {
                    "campo": "codice_origine",
                    "op": "in",
                    "valore": [STAZIONE_SEDE, STAZIONE_FUORI],
                },
            ],
            composizione_json=[{"materiale_tipo_codice": MATERIALE_TIPO, "n_pezzi": 3}],
            materiale_tipo_codice=MATERIALE_TIPO,
            numero_pezzi=3,
            priorita=10,
        )
        session.add(regola)

        # Corse
        # corsa A: sede → fuori, valida feriali tranne festività
        session.add(
            CorsaCommerciale(
                azienda_id=AZIENDA_ID,
                row_hash="test_smoke_bug5_A".ljust(64, "0")[:64],
                numero_treno="TEST_A",
                codice_origine=STAZIONE_SEDE,
                codice_destinazione=STAZIONE_FUORI,
                ora_partenza=time(8, 0),
                ora_arrivo=time(9, 0),
                valido_da=VALIDO_DA,
                valido_a=VALIDO_A,
                valido_in_date_json=valid_a,
                periodicita_breve="LV escluse 5 festività",
            )
        )
        # corsa B: fuori → sede, valida tutti i feriali
        session.add(
            CorsaCommerciale(
                azienda_id=AZIENDA_ID,
                row_hash="test_smoke_bug5_B".ljust(64, "0")[:64],
                numero_treno="TEST_B",
                codice_origine=STAZIONE_FUORI,
                codice_destinazione=STAZIONE_SEDE,
                ora_partenza=time(10, 0),
                ora_arrivo=time(11, 0),
                valido_da=VALIDO_DA,
                valido_a=VALIDO_A,
                valido_in_date_json=valid_b,
                periodicita_breve="LV",
            )
        )
        await session.flush()
        return prog_id


async def lancia_builder(prog_id: int) -> None:
    """Genera giri default (periodo intero) e stampa stats."""
    print(f"\n[builder] lancio genera_giri(programma_id={prog_id}, default=periodo intero)")
    async with session_scope() as session:
        result = await genera_giri(
            programma_id=prog_id,
            localita_codice=LOCALITA_CODICE,
            session=session,
            azienda_id=AZIENDA_ID,
            force=True,
        )
    print(f"[builder] BuilderResult:")
    print(f"  giri_ids                  = {result.giri_ids}")
    print(f"  n_giri_creati             = {result.n_giri_creati}")
    print(f"  n_corse_processate        = {result.n_corse_processate}")
    print(f"  n_corse_residue           = {result.n_corse_residue}")
    print(f"  n_giri_chiusi             = {result.n_giri_chiusi}")
    print(f"  n_giri_non_chiusi         = {result.n_giri_non_chiusi}")
    print(f"  warnings                  = {result.warnings}")


async def stampa_struttura_db(prog_id: int) -> None:
    """Stampa numero giri/giornate/varianti + dates_apply per giornata."""
    print(f"\n[verifica DB] struttura post-cluster del programma {prog_id}:")
    async with session_scope() as session:
        giri = list(
            (
                await session.execute(
                    select(GiroMateriale)
                    .where(GiroMateriale.programma_id == prog_id)
                    .order_by(GiroMateriale.id)
                )
            ).scalars()
        )
        print(f"  giri totali               = {len(giri)}")
        for g in giri:
            giornate = list(
                (
                    await session.execute(
                        select(GiroGiornata)
                        .where(GiroGiornata.giro_materiale_id == g.id)
                        .order_by(GiroGiornata.numero_giornata)
                    )
                ).scalars()
            )
            print(
                f"\n  giro id={g.id} numero_turno={g.numero_turno} "
                f"numero_giornate={g.numero_giornate} "
                f"motivo_chiusura={g.generation_metadata_json.get('motivo_chiusura')}"
            )
            for gg in giornate:
                varianti = list(
                    (
                        await session.execute(
                            select(GiroVariante)
                            .where(GiroVariante.giro_giornata_id == gg.id)
                            .order_by(GiroVariante.variant_index)
                        )
                    ).scalars()
                )
                for v in varianti:
                    n_dates = len(v.validita_dates_apply_json)
                    prima = v.validita_dates_apply_json[0] if n_dates > 0 else "?"
                    ultima = v.validita_dates_apply_json[-1] if n_dates > 0 else "?"
                    print(
                        f"    G{gg.numero_giornata} v{v.variant_index} "
                        f"validita_testo='{v.validita_testo}' "
                        f"dates_apply.length={n_dates} "
                        f"({prima} → {ultima})"
                    )


async def main() -> None:
    print("=" * 80)
    print("SMOKE Sprint 7.5 — bug 5 chiuso (MR 7/7)")
    print("=" * 80)
    prog_id = await setup_dati()
    await lancia_builder(prog_id)
    await stampa_struttura_db(prog_id)
    print("\n" + "=" * 80)
    print("OK — dati lasciati in DB per verifica visuale frontend.")
    print(f"   /pianificatore-giro/giri/<giro_id>  (vedi BuilderResult.giri_ids)")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
