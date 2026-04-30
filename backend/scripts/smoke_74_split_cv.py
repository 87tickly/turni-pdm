"""Sprint 7.4 — smoke che dimostra il split CV intermedio (MR 4/4).

Costruisce un giro materiale "lungo" con una sola giornata che ha 4
corse commerciali consecutive (08:00→15:30, totale 8h di condotta su
4 blocchi). Il punto centrale del giro tocca la stazione `MORTARA`
(deroga normativa hardcoded in `STAZIONI_CV_DEROGA`).

Pre-Sprint 7.4, lo stesso giro sarebbe stato persistito come **1
TurnoPdc** con la giornata che mostra:

- prestazione totale ≈ 9h25 = 565 min > cap 510 → violazione
  ``prestazione_max:565>510min``
- condotta totale = 480 min > cap 330 → violazione
  ``condotta_max:480>330min``
- 0 split → debito normativo onesto (entry 42 TN-UPDATE).

Post-Sprint 7.4 (MR 1+2+3) lo stesso giro deve produrre **2
TurnoPdc-ramo-split distinti**:

- ramo R1: corsa A + corsa B (S99001 → ... → MORTARA), prestazione
  e condotta entro limiti.
- ramo R2: corsa C + corsa D (MORTARA → ... → S99001), prestazione
  e condotta entro limiti.
- 0 violazioni in entrambi i rami.

Lo script lascia i dati in DB per la verifica visuale frontend
(`/pianificatore-giro/giri/<id>/turni-pdc`).
"""

from __future__ import annotations

import asyncio
from datetime import date, time, timedelta

from sqlalchemy import select, text

from colazione.db import session_scope
from colazione.domain.builder_giro.builder import genera_giri
from colazione.domain.builder_pdc.builder import genera_turno_pdc
from colazione.models.anagrafica import LocalitaManutenzione, Stazione
from colazione.models.corse import CorsaCommerciale
from colazione.models.giri import GiroMateriale
from colazione.models.programmi import (
    ProgrammaMateriale,
    ProgrammaRegolaAssegnazione,
)
from colazione.models.turni_pdc import TurnoPdc, TurnoPdcGiornata

AZIENDA_ID = 2  # trenord (id seed)
PROGRAMMA_NOME = "TEST_SMOKE_SPLIT_CV"
LOCALITA_CODICE = "TEST_LOC_74CV"
LOCALITA_BREVE = "TCV"  # vincolo DB: ^[A-Z]{2,8}$

# Stazione sede del giro (= sede materiale = sede PdC nei test).
STAZIONE_SEDE = "S99011"
# Stazione intermedia esterna: appoggio fra le due metà del giro.
STAZIONE_ESTERNA = "S99012"
# Stazione che è in `STAZIONI_CV_DEROGA` (NORMATIVA-PDC.md:701-717).
# Il builder PdC la riconosce come ammessa al cambio volante anche se
# non è un Depot esplicito dell'azienda.
STAZIONE_CV = "MORTARA"

MATERIALE_TIPO = "ALe711"

# Periodo programma: 1 anno.
VALIDO_DA = date(2026, 1, 1)
VALIDO_A = date(2026, 12, 31)


def _giorni_lavorativi(da: date, a: date) -> list[str]:
    out: list[str] = []
    d = da
    while d <= a:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


async def setup_dati() -> int:
    valid_dates = _giorni_lavorativi(VALIDO_DA, VALIDO_A)
    print(
        f"[setup] feriali totali nel 2026 = {len(valid_dates)} date "
        f"(corse commerciali tutte valide nei feriali)"
    )

    async with session_scope() as session:
        # Stazioni di test (eventuali pre-esistenti vengono mantenute).
        for cod in (STAZIONE_SEDE, STAZIONE_ESTERNA, STAZIONE_CV):
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

        # Località manutenzione (sede materiale del giro).
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
                nome_canonico="Test Località Split CV",
                stazione_collegata_codice=STAZIONE_SEDE,
                azienda_id=AZIENDA_ID,
            )
            session.add(loc)
            await session.flush()

        # Programma test: cancella il precedente per ripartire pulito.
        existing_prog = (
            await session.execute(
                select(ProgrammaMateriale).where(
                    ProgrammaMateriale.nome == PROGRAMMA_NOME
                )
            )
        ).scalar_one_or_none()
        if existing_prog is not None:
            print(
                f"[setup] programma '{PROGRAMMA_NOME}' esiste (id="
                f"{existing_prog.id}), rimuovo"
            )
            await session.execute(
                text(
                    "DELETE FROM turno_pdc "
                    "WHERE (generation_metadata_json->>'giro_materiale_id')::bigint IN ("
                    "  SELECT id FROM giro_materiale WHERE programma_id = :pid"
                    ")"
                ),
                {"pid": existing_prog.id},
            )
            await session.execute(
                text("DELETE FROM giro_materiale WHERE programma_id = :pid"),
                {"pid": existing_prog.id},
            )
            await session.execute(
                text(
                    "DELETE FROM programma_regola_assegnazione "
                    "WHERE programma_id = :pid"
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
            stazioni_sosta_extra_json=[STAZIONE_ESTERNA, STAZIONE_CV],
        )
        session.add(prog)
        await session.flush()
        prog_id = int(prog.id)

        # Cattura tutte le corse delle stazioni S99* + MORTARA.
        regola = ProgrammaRegolaAssegnazione(
            programma_id=prog_id,
            filtri_json=[
                {
                    "campo": "codice_origine",
                    "op": "in",
                    "valore": [STAZIONE_SEDE, STAZIONE_ESTERNA, STAZIONE_CV],
                },
            ],
            composizione_json=[
                {"materiale_tipo_codice": MATERIALE_TIPO, "n_pezzi": 3}
            ],
            materiale_tipo_codice=MATERIALE_TIPO,
            numero_pezzi=3,
            priorita=10,
        )
        session.add(regola)

        # 4 corse commerciali consecutive che totalizzano 8h di condotta:
        #   A: SEDE → ESTERNA          06:00 → 08:00 (2h)
        #   B: ESTERNA → CV (MORTARA)  08:30 → 10:30 (2h)
        #   C: CV (MORTARA) → ESTERNA  11:00 → 13:00 (2h)
        #   D: ESTERNA → SEDE          13:30 → 15:30 (2h)
        #
        # Senza split: prestazione ≈ 11h20 (PRESA 05:05 → FINE 16:25),
        # condotta = 8h. Sforamento 510/330 → violazioni.
        #
        # Con split a MORTARA:
        #   ramo R1 = A+B (06:00-10:30): prestazione ~6h20, condotta 4h
        #   ramo R2 = C+D (11:00-15:30): prestazione ~6h20, condotta 4h
        # Entrambi i rami entro i limiti normativi.
        corse = [
            ("TEST_SPLIT_A", STAZIONE_SEDE, STAZIONE_ESTERNA, time(6, 0), time(8, 0)),
            ("TEST_SPLIT_B", STAZIONE_ESTERNA, STAZIONE_CV, time(8, 30), time(10, 30)),
            ("TEST_SPLIT_C", STAZIONE_CV, STAZIONE_ESTERNA, time(11, 0), time(13, 0)),
            ("TEST_SPLIT_D", STAZIONE_ESTERNA, STAZIONE_SEDE, time(13, 30), time(15, 30)),
        ]
        for numero, da_stz, a_stz, h_in, h_out in corse:
            session.add(
                CorsaCommerciale(
                    azienda_id=AZIENDA_ID,
                    row_hash=f"smoke_74_{numero}".ljust(64, "0")[:64],
                    numero_treno=numero,
                    codice_origine=da_stz,
                    codice_destinazione=a_stz,
                    ora_partenza=h_in,
                    ora_arrivo=h_out,
                    valido_da=VALIDO_DA,
                    valido_a=VALIDO_A,
                    valido_in_date_json=valid_dates,
                    periodicita_breve="LV",
                )
            )
        await session.flush()
        return prog_id


async def lancia_builder_giro(prog_id: int) -> int:
    print(
        f"\n[builder/giro] lancio genera_giri(programma_id={prog_id}, "
        "default=periodo intero)"
    )
    async with session_scope() as session:
        result = await genera_giri(
            programma_id=prog_id,
            localita_codice=LOCALITA_CODICE,
            session=session,
            azienda_id=AZIENDA_ID,
            force=True,
        )
    print(f"[builder/giro] giri_ids = {result.giri_ids}")
    print(f"[builder/giro] n_corse_processate = {result.n_corse_processate}")
    if not result.giri_ids:
        raise RuntimeError("Nessun giro creato dal builder; smoke abortito.")
    return int(result.giri_ids[0])


async def lancia_builder_pdc(giro_id: int) -> None:
    print(f"\n[builder/pdc] lancio genera_turno_pdc(giro_id={giro_id})")
    async with session_scope() as session:
        results = await genera_turno_pdc(
            session=session,
            azienda_id=AZIENDA_ID,
            giro_id=giro_id,
            valido_da=VALIDO_DA,
            force=True,
        )
    print(f"[builder/pdc] {len(results)} TurnoPdc creati:")
    for r in results:
        marker = "🔀 RAMO" if r.is_ramo_split else "  PRINC."
        ramo_info = ""
        if r.is_ramo_split:
            ramo_info = (
                f" (R{r.split_ramo}/{r.split_totale_rami} di "
                f"giornata {r.split_origine_giornata})"
            )
        print(
            f"  {marker} {r.codice}{ramo_info}\n"
            f"           n_giornate={r.n_giornate} | "
            f"prestazione={r.prestazione_totale_min}min | "
            f"condotta={r.condotta_totale_min}min | "
            f"violazioni={len(r.violazioni)}"
        )
        if r.violazioni:
            for v in r.violazioni:
                print(f"             ⚠ {v}")


async def stampa_riepilogo(giro_id: int) -> None:
    print("\n[riepilogo DB]")
    async with session_scope() as session:
        giro = (
            await session.execute(
                select(GiroMateriale).where(GiroMateriale.id == giro_id)
            )
        ).scalar_one()
        print(f"  giro id={giro.id} numero_turno={giro.numero_turno}")

        turni = list(
            (
                await session.execute(
                    select(TurnoPdc).where(
                        TurnoPdc.azienda_id == AZIENDA_ID,
                        text(
                            "(generation_metadata_json->>'giro_materiale_id')::bigint = :gid"
                        ),
                    ),
                    {"gid": giro_id},
                )
            ).scalars()
        )
        print(f"  turni_pdc associati = {len(turni)}")
        for t in turni:
            meta = t.generation_metadata_json or {}
            giornate = list(
                (
                    await session.execute(
                        select(TurnoPdcGiornata).where(
                            TurnoPdcGiornata.turno_pdc_id == t.id
                        )
                    )
                ).scalars()
            )
            presta = sum(g.prestazione_min for g in giornate)
            cond = sum(g.condotta_min for g in giornate)
            tag = "RAMO" if meta.get("is_ramo_split") else "PRINC."
            extra = ""
            if meta.get("is_ramo_split"):
                extra = (
                    f" R{meta.get('split_ramo')}/"
                    f"{meta.get('split_totale_rami')} g{meta.get('split_origine_giornata')}"
                )
            n_viol = len(meta.get("violazioni", []) or [])
            print(
                f"    [{tag}{extra}] {t.codice} | n_giornate={len(giornate)} | "
                f"prestazione={presta} | condotta={cond} | violazioni={n_viol}"
            )


async def main() -> None:
    print("=" * 80)
    print("SMOKE Sprint 7.4 — split CV intermedio (MR 4/4)")
    print("=" * 80)
    prog_id = await setup_dati()
    giro_id = await lancia_builder_giro(prog_id)
    await lancia_builder_pdc(giro_id)
    await stampa_riepilogo(giro_id)
    print("\n" + "=" * 80)
    print("OK — dati lasciati in DB per verifica visuale frontend.")
    print(f"   /pianificatore-giro/giri/{giro_id}/turni-pdc")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
