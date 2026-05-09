"""MR-A7 — validazione end-to-end builder esplorativo.

Misura i 3 sintomi reali su programmi reali Trenord (dump Railway):

1. **150 corse del PdE non coperte** (programma 17, ETR522 FIO 3 direttrici)
2. **~50% giri da 1g sotto n_min=4** (programma 17)
3. **Programma R11 (Colico-Chiavenna) FIO → 0 giri** (programma 16, ETR204 FIO)

Per ogni programma:
- Snapshot **PRE** (builder_mode='rigido', stato attuale del DB)
- Switch a `'esplorativo'` + rigenera con `force=True` per ogni sede
- Snapshot **POST**
- Confronto: i 3 sintomi sono risolti? quanto?

Eseguire con:
    cd backend && PYTHONPATH=src uv run python scripts/test_a7_validation.py
"""

from __future__ import annotations

import asyncio
from collections import Counter
from typing import Any

from sqlalchemy import func, select, update

from colazione.db import session_scope
from colazione.domain.builder_giro.builder import genera_giri
from colazione.models.giri import GiroGiornata, GiroMateriale, GiroVariante
from colazione.models.programmi import (
    ProgrammaMateriale,
    ProgrammaRegolaAssegnazione,
)


# Programmi target (id da dump Railway 2026-05-08)
# HIGH-2 SEVERO MR-A7 chiusura: validazione completa su entrambi prog 16
# (8 regole / 4 sedi attive: LECCO, FIORENZA, NOVATE, TILO) + prog 17 (1
# regola, 1 sede). Pre-fix HIGH-1 il backtracking esplorativo si bloccava
# su prog 16 LECCO per >5 min. Post-fix MR-A3-quater il pool è ridotto
# a Tier 0 quando non vuoto → backtracking veloce.
TARGETS = [
    {"id": 16, "label": "prog 16 (giugno 2026, 8 regole, R11 + 7 altre)"},
    {"id": 17, "label": "prog 17 (ultima prova, ETR522 FIO 3 direttrici)"},
]


async def diagnostica_giri_sotto_min(programma_id: int) -> list[dict[str, Any]]:
    """Per ogni giro sotto n_min=4, raccoglie info per diagnosi:
    - n_giornate
    - prima corsa (data, treno, origine→destinazione, ora)
    - ultima corsa (data, treno, origine→destinazione, ora)
    - motivo_chiusura
    - km totali
    - sede whitelist match (last in?)
    """
    from sqlalchemy import text

    async with session_scope() as session:
        prog = (
            await session.execute(
                select(ProgrammaMateriale).where(ProgrammaMateriale.id == programma_id)
            )
        ).scalar_one_or_none()
        if prog is None:
            return []

        # Carica giri programma con n_giornate < n_min
        query = text("""
            SELECT
              g.id,
              g.numero_turno,
              g.motivo_chiusura,
              g.km_totali_ciclo,
              (SELECT COUNT(*) FROM giro_giornata gg WHERE gg.giro_materiale_id = g.id) AS n_giornate
            FROM giro_materiale g
            WHERE g.programma_id = :pid
            ORDER BY g.id
        """)
        rows = (await session.execute(query, {"pid": programma_id})).all()
        sotto_min = [r for r in rows if r.n_giornate < prog.n_giornate_min]

        out: list[dict[str, Any]] = []
        for r in sotto_min:
            # Prima e ultima corsa del giro: query giro_giornata + giro_variante + composizione
            corse_q = text("""
                SELECT
                  gg.numero_giornata,
                  gv.id AS variante_id,
                  gv.composizione_json::text AS comp_json,
                  gv.dates_apply_json::text AS dates_json
                FROM giro_giornata gg
                JOIN giro_variante gv ON gv.giro_giornata_id = gg.id
                WHERE gg.giro_materiale_id = :gid
                ORDER BY gg.numero_giornata, gv.id
            """)
            cs = (await session.execute(corse_q, {"gid": r.id})).all()
            varianti_brief = [
                {
                    "g": c.numero_giornata,
                    "var_id": c.variante_id,
                    "dates_count": len(c.dates_json or "[]"),
                    "comp_preview": (c.comp_json or "")[:300],
                }
                for c in cs
            ]
            out.append({
                "giro_id": r.id,
                "numero_turno": r.numero_turno,
                "n_giornate": r.n_giornate,
                "motivo_chiusura": r.motivo_chiusura,
                "km_totali_ciclo": r.km_totali_ciclo,
                "varianti": varianti_brief,
            })
        return out


async def snapshot_programma(programma_id: int) -> dict[str, Any]:
    """Raccoglie metriche programma + giri."""
    async with session_scope() as session:
        prog = (
            await session.execute(
                select(ProgrammaMateriale).where(ProgrammaMateriale.id == programma_id)
            )
        ).scalar_one_or_none()
        if prog is None:
            return {"error": f"programma {programma_id} non trovato"}

        # Regole
        regole = (
            await session.execute(
                select(ProgrammaRegolaAssegnazione).where(
                    ProgrammaRegolaAssegnazione.programma_id == programma_id
                )
            )
        ).scalars().all()

        # Giri
        giri = (
            await session.execute(
                select(GiroMateriale).where(GiroMateriale.programma_id == programma_id)
            )
        ).scalars().all()

        # Distribuzione n_giornate per giro
        lung_distrib: Counter[int] = Counter()
        giro_id_to_n: dict[int, int] = {}
        for g in giri:
            n_giornate = (
                await session.execute(
                    select(func.count())
                    .select_from(GiroGiornata)
                    .where(GiroGiornata.giro_materiale_id == g.id)
                )
            ).scalar_one()
            lung_distrib[n_giornate] += 1
            giro_id_to_n[g.id] = n_giornate

        # Conta corse coperte: union di assegnazioni in giri
        # (per programma); via giro_giornata → giro_variante → composizione
        corse_coperte_count = (
            await session.execute(
                select(func.count(func.distinct(GiroVariante.id)))
                .select_from(GiroVariante)
                .join(GiroGiornata, GiroGiornata.id == GiroVariante.giro_giornata_id)
                .join(GiroMateriale, GiroMateriale.id == GiroGiornata.giro_materiale_id)
                .where(GiroMateriale.programma_id == programma_id)
            )
        ).scalar_one()

        return {
            "programma_id": programma_id,
            "nome": prog.nome,
            "builder_mode": prog.builder_mode,
            "builder_version": prog.builder_version,
            "valido_da": prog.valido_da.isoformat(),
            "valido_a": prog.valido_a.isoformat(),
            "stato": prog.stato,
            "n_giornate_min": prog.n_giornate_min,
            "n_giornate_max": prog.n_giornate_max,
            "n_giri": len(giri),
            "n_regole": len(regole),
            "regole": [
                {
                    "id": r.id,
                    "priorita": r.priorita,
                    "materiale": r.materiale_tipo_codice,
                    "localita": r.localita_codice,
                    "filtri": r.filtri_json,
                }
                for r in regole
            ],
            "lunghezza_distrib": dict(sorted(lung_distrib.items())),
            "giri_1g": lung_distrib.get(1, 0),
            "giri_sotto_min": sum(
                v for k, v in lung_distrib.items() if k < prog.n_giornate_min
            ),
            "n_varianti_totali": corse_coperte_count,
        }


def fmt_snapshot(s: dict[str, Any], titolo: str) -> str:
    if "error" in s:
        return f"\n=== {titolo} ===\nERRORE: {s['error']}"
    pct_1g = (s["giri_1g"] / s["n_giri"] * 100) if s["n_giri"] else 0.0
    pct_sotto = (s["giri_sotto_min"] / s["n_giri"] * 100) if s["n_giri"] else 0.0
    out = f"""
=== {titolo} ===
Programma {s['programma_id']}: '{s['nome']}'
  builder_mode={s['builder_mode']!r}, builder_version={s['builder_version']!r}, stato={s['stato']!r}
  periodo: {s['valido_da']} → {s['valido_a']}
  n_giornate_min={s['n_giornate_min']}, n_giornate_max={s['n_giornate_max']}
  N regole: {s['n_regole']}"""
    for r in s["regole"]:
        out += f"\n    - regola id={r['id']} prio={r['priorita']} mat={r['materiale']} loc={r['localita']} filtri={r['filtri']}"
    out += f"""
  N giri totali: {s['n_giri']}
  Distribuzione lunghezza: {s['lunghezza_distrib']}
  Giri da 1 giornata: {s['giri_1g']}/{s['n_giri']} ({pct_1g:.1f}%)
  Giri sotto n_min={s['n_giornate_min']}: {s['giri_sotto_min']}/{s['n_giri']} ({pct_sotto:.1f}%)
  N varianti totali (proxy copertura): {s['n_varianti_totali']}
"""
    return out


async def switch_a_esplorativo(programma_id: int) -> None:
    async with session_scope() as session:
        await session.execute(
            update(ProgrammaMateriale)
            .where(ProgrammaMateriale.id == programma_id)
            .values(builder_mode="esplorativo")
        )
        await session.commit()


async def switch_a_rigido(programma_id: int) -> None:
    async with session_scope() as session:
        await session.execute(
            update(ProgrammaMateriale)
            .where(ProgrammaMateriale.id == programma_id)
            .values(builder_mode="rigido")
        )
        await session.commit()


async def rigenera_per_programma(programma_id: int) -> dict[str, Any]:
    """Rigenera giri per ogni località distinta delle regole.

    Forza temporaneamente ``stato='attivo'`` durante il test, poi
    ripristina lo stato originale (necessario per programmi
    'archiviato' come prog 16).
    """
    async with session_scope() as session:
        prog = (
            await session.execute(
                select(ProgrammaMateriale).where(ProgrammaMateriale.id == programma_id)
            )
        ).scalar_one_or_none()
        if prog is None:
            return {"error": f"programma {programma_id} non trovato"}
        azienda_id = prog.azienda_id
        stato_originale = prog.stato

        regole = (
            await session.execute(
                select(ProgrammaRegolaAssegnazione).where(
                    ProgrammaRegolaAssegnazione.programma_id == programma_id
                )
            )
        ).scalars().all()
        sedi = sorted({r.localita_codice for r in regole if r.localita_codice})

        # Forza 'attivo' se necessario (per programmi 'archiviato')
        if stato_originale != "attivo":
            await session.execute(
                update(ProgrammaMateriale)
                .where(ProgrammaMateriale.id == programma_id)
                .values(stato="attivo")
            )
            await session.commit()

    out: dict[str, Any] = {"sedi": [], "stato_originale": stato_originale}
    try:
        for sede in sedi:
            async with session_scope() as session:
                try:
                    res = await genera_giri(
                        programma_id=programma_id,
                        localita_codice=sede,
                        session=session,
                        azienda_id=azienda_id,
                        force=True,
                        confirm_delete_pdc=True,
                    )
                    await session.commit()
                    out["sedi"].append({
                        "sede": sede,
                        "ok": True,
                        "n_giri_creati": res.n_giri_creati,
                        "n_corse_processate": res.n_corse_processate,
                        "n_corse_residue": res.n_corse_residue,
                        "n_giri_chiusi": res.n_giri_chiusi,
                        "n_giri_non_chiusi": res.n_giri_non_chiusi,
                        "n_giri_km_cap": res.n_giri_km_cap,
                        "warnings": res.warnings[:8] if res.warnings else [],
                        "n_warnings": len(res.warnings) if res.warnings else 0,
                    })
                except Exception as exc:  # noqa: BLE001
                    await session.rollback()
                    out["sedi"].append({
                        "sede": sede,
                        "ok": False,
                        "errore": f"{type(exc).__name__}: {exc}",
                    })
    finally:
        # Ripristina stato originale
        if stato_originale != "attivo":
            async with session_scope() as session:
                await session.execute(
                    update(ProgrammaMateriale)
                    .where(ProgrammaMateriale.id == programma_id)
                    .values(stato=stato_originale)
                )
                await session.commit()
    return out


async def main() -> None:
    print("=" * 78)
    print("MR-A7 — Validazione end-to-end builder esplorativo")
    print("=" * 78)

    pre_snapshots: dict[int, dict[str, Any]] = {}
    post_snapshots: dict[int, dict[str, Any]] = {}

    # === FASE 0: ripristina builder_mode='rigido' + rigenera per snapshot pre coerente
    print("\n--- Fase 0: rigenera in modalità rigida (baseline) ---")
    for tgt in TARGETS:
        pid = tgt["id"]
        await switch_a_rigido(pid)
        rigen = await rigenera_per_programma(pid)
        for r in rigen.get("sedi", []):
            if r["ok"]:
                tot_corse = r["n_corse_processate"] + r["n_corse_residue"]
                pct_cov = (r["n_corse_processate"] / tot_corse * 100) if tot_corse else 0.0
                print(
                    f"  prog {pid} sede {r['sede']}: rigido OK — "
                    f"n_giri={r['n_giri_creati']}, "
                    f"corse {r['n_corse_processate']}/{tot_corse} ({pct_cov:.1f}%), "
                    f"residue={r['n_corse_residue']}"
                )
            else:
                print(f"  prog {pid} sede {r['sede']}: ERRORE — {r['errore']}")

    # === FASE 1: snapshot pre (rigido)
    for tgt in TARGETS:
        pid = tgt["id"]
        s = await snapshot_programma(pid)
        pre_snapshots[pid] = s
        print(fmt_snapshot(s, f"PRE rigido — {tgt['label']}"))

    # === FASE 2: switch a esplorativo + rigenera
    for tgt in TARGETS:
        pid = tgt["id"]
        print(f"\n--- Switch a esplorativo + rigenera (force=True) prog {pid} ---")
        await switch_a_esplorativo(pid)
        rigen = await rigenera_per_programma(pid)
        for r in rigen.get("sedi", []):
            if r["ok"]:
                tot_corse = r["n_corse_processate"] + r["n_corse_residue"]
                pct_cov = (r["n_corse_processate"] / tot_corse * 100) if tot_corse else 0.0
                print(
                    f"  sede {r['sede']}: OK — "
                    f"n_giri={r['n_giri_creati']} (chiusi={r['n_giri_chiusi']}, non_chiusi={r['n_giri_non_chiusi']}, km_cap={r['n_giri_km_cap']}), "
                    f"corse processate={r['n_corse_processate']}/{tot_corse} ({pct_cov:.1f}%), "
                    f"residue={r['n_corse_residue']}, "
                    f"warnings={r['n_warnings']}"
                )
                for w in r["warnings"]:
                    print(f"    warn: {w[:200]}")
            else:
                print(f"  sede {r['sede']}: ERRORE — {r['errore']}")

    # === FASE 3: snapshot post (esplorativo)
    for tgt in TARGETS:
        pid = tgt["id"]
        s = await snapshot_programma(pid)
        post_snapshots[pid] = s
        print(fmt_snapshot(s, f"POST esplorativo — {tgt['label']}"))

    # === FASE 3.5: diagnostica giri sotto min — SKIP (script diag separato)
    # Vedi `scripts/diag_giri_sotto_min.py [pid]` per dettagli giri sotto-min.

    # === FASE 4: confronto
    print("\n" + "=" * 78)
    print("CONFRONTO PRE/POST")
    print("=" * 78)
    for tgt in TARGETS:
        pid = tgt["id"]
        pre = pre_snapshots[pid]
        post = post_snapshots[pid]
        if "error" in pre or "error" in post:
            print(f"prog {pid}: errore snapshot, skip")
            continue
        delta_giri = post["n_giri"] - pre["n_giri"]
        delta_1g = post["giri_1g"] - pre["giri_1g"]
        delta_sotto = post["giri_sotto_min"] - pre["giri_sotto_min"]
        delta_var = post["n_varianti_totali"] - pre["n_varianti_totali"]
        print(f"\nprog {pid} '{pre['nome']}':")
        print(f"  n_giri:     {pre['n_giri']} → {post['n_giri']} (Δ {delta_giri:+d})")
        print(f"  giri_1g:    {pre['giri_1g']} → {post['giri_1g']} (Δ {delta_1g:+d})")
        print(f"  giri<min={pre['n_giornate_min']}: {pre['giri_sotto_min']} → {post['giri_sotto_min']} (Δ {delta_sotto:+d})")
        print(f"  varianti:   {pre['n_varianti_totali']} → {post['n_varianti_totali']} (Δ {delta_var:+d})")
        print(f"  lunghezza pre:  {pre['lunghezza_distrib']}")
        print(f"  lunghezza post: {post['lunghezza_distrib']}")


if __name__ == "__main__":
    asyncio.run(main())
