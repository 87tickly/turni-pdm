"""Diagnostica giri sotto n_min nel DB attuale.

Per ogni giro sotto n_min, mostra:
- numero_turno, n_giornate, generation_metadata (motivo_chiusura ecc.)
- prima/ultima corsa per ogni giornata: stazioni, ore, treno
- gap fra l'ultima corsa di una giornata e la prima della successiva

Uso: cd backend && PYTHONPATH=src uv run python scripts/diag_giri_sotto_min.py [programma_id=17]
"""

from __future__ import annotations

import asyncio
import json
import sys

from sqlalchemy import select, text

from colazione.db import session_scope
from colazione.models.programmi import ProgrammaMateriale


async def main(programma_id: int = 17) -> None:
    async with session_scope() as session:
        prog = (
            await session.execute(
                select(ProgrammaMateriale).where(ProgrammaMateriale.id == programma_id)
            )
        ).scalar_one_or_none()
        if prog is None:
            print(f"Programma {programma_id} non trovato")
            return

        n_min = prog.n_giornate_min
        print(f"=== DIAGNOSI giri sotto n_min={n_min} per programma {programma_id} '{prog.nome}'")
        print(f"    builder_mode={prog.builder_mode!r}, periodo {prog.valido_da} → {prog.valido_a}")

        # Tutti i giri con # giornate
        q = text("""
            SELECT
              g.id,
              g.numero_turno,
              g.numero_giornate,
              g.generation_metadata_json,
              g.km_media_giornaliera,
              g.km_media_annua,
              g.localita_manutenzione_partenza_id,
              g.materiale_tipo_codice
            FROM giro_materiale g
            WHERE g.programma_id = :pid
            ORDER BY g.id
        """)
        rows = (await session.execute(q, {"pid": programma_id})).all()

        sotto = [r for r in rows if r.numero_giornate < n_min]
        print(f"\nTotali: {len(rows)} giri, {len(sotto)} sotto n_min={n_min}\n")

        # Distribuzione motivo_chiusura sui sotto-min
        motivi: dict[str, int] = {}
        for r in sotto:
            md = r.generation_metadata_json
            if isinstance(md, str):
                md = json.loads(md)
            mot = md.get("motivo_chiusura") if md else None
            motivi[mot or "?"] = motivi.get(mot or "?", 0) + 1
        print(f"Motivi chiusura giri sotto-min: {motivi}\n")

        for r in sotto:
            md = r.generation_metadata_json
            if isinstance(md, str):
                md = json.loads(md)
            mot = (md or {}).get("motivo_chiusura", "?")
            km_tot = (md or {}).get("km_totali_ciclo", "?")
            print(f"--- giro id={r.id} ({r.numero_turno}) {r.materiale_tipo_codice} ---")
            print(f"    n_giornate={r.numero_giornate}, motivo={mot!r}, km_tot={km_tot}, "
                  f"km_media_g={r.km_media_giornaliera}")

            # Prima e ultima corsa per ogni giornata
            cs = await session.execute(
                text("""
                    SELECT
                      gg.numero_giornata,
                      gv.id AS variante_id,
                      gv.dates_apply_json,
                      gb.seq,
                      gb.tipo_blocco,
                      gb.stazione_da_codice,
                      gb.stazione_a_codice,
                      gb.ora_inizio,
                      gb.ora_fine,
                      cc.numero_treno
                    FROM giro_giornata gg
                    JOIN giro_variante gv ON gv.giro_giornata_id = gg.id
                    JOIN giro_blocco gb ON gb.giro_variante_id = gv.id
                    LEFT JOIN corsa_commerciale cc ON cc.id = gb.corsa_commerciale_id
                    WHERE gg.giro_materiale_id = :gid
                    ORDER BY gg.numero_giornata, gv.id, gb.seq
                """),
                {"gid": r.id},
            )
            blocchi = cs.all()
            # Raggruppa per (numero_giornata, variante_id)
            from collections import defaultdict
            by_g: dict = defaultdict(list)
            for b in blocchi:
                by_g[(b.numero_giornata, b.variante_id)].append(b)
            for (g, vid), bb in sorted(by_g.items()):
                corse_blocchi = [b for b in bb if b.tipo_blocco == "corsa_commerciale"]
                n_dates = len(json.loads(bb[0].dates_apply_json) if isinstance(bb[0].dates_apply_json, str) else bb[0].dates_apply_json)
                if not corse_blocchi:
                    print(f"    g{g} var={vid} ({n_dates}d): NESSUNA CORSA — solo {len(bb)} blocchi")
                    continue
                pri = corse_blocchi[0]
                ult = corse_blocchi[-1]
                trains = " | ".join(b.numero_treno or "?" for b in corse_blocchi)
                print(f"    g{g} var={vid} ({n_dates}d, {len(corse_blocchi)}corse): "
                      f"{pri.stazione_da_codice}@{pri.ora_inizio}→{ult.stazione_a_codice}@{ult.ora_fine} "
                      f"[treni: {trains[:80]}]")
            print()


if __name__ == "__main__":
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else 17
    asyncio.run(main(pid))
