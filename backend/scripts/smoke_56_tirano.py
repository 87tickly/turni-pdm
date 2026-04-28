"""Sprint 5.6 — smoke test reale Mi.Centrale↔Tirano.

Crea il programma "Trenord 2025-2026 invernale Mi.Centrale-Tirano" con
1 regola (direttrice="TIRANO-SONDRIO-LECCO-MILANO", composizione=
[ETR526+ETR425]) e lancia ``genera_giri()`` su una settimana
lun-dom (5 feriali + 2 festivi) dalla sede FIORENZA.

Stampa: BuilderResult + analisi (multi-giornata, dorme a Tirano,
vuoti whitelist, eventi composizione).
"""

from __future__ import annotations

import asyncio
from datetime import date

from sqlalchemy import select, text

from colazione.db import session_scope
from colazione.domain.builder_giro.builder import genera_giri
from colazione.models.programmi import (
    ProgrammaMateriale,
    ProgrammaRegolaAssegnazione,
)

AZIENDA_ID = 2  # trenord
PROGRAMMA_NOME = "Trenord 2025-2026 invernale Mi.Centrale-Tirano"
DIRETTRICE = "TIRANO-SONDRIO-LECCO-MILANO"
LOCALITA_CODICE = "IMPMAN_MILANO_FIORENZA"
DATA_INIZIO = date(2026, 1, 19)  # lunedì 19 gennaio 2026
N_GIORNATE = 14  # 2 settimane: ampliato per test cap km in modo dinamico Sprint 5.6
TIRANO_CODICE = "S01440"
WL_FIO = {"S01645", "S01700", "S01701", "S01820", "S01326"}  # Garibaldi, Centrale, Lambrate, Rogoredo, Greco-Pirelli
SOSTA_EXTRA = ["S01440", "S01430", "S01520", "S01420", "S01400"]  # Tirano, Sondrio, Lecco, Colico, Chiavenna


async def crea_o_riusa_programma() -> int:
    async with session_scope() as session:
        existing = (
            await session.execute(
                select(ProgrammaMateriale).where(
                    ProgrammaMateriale.azienda_id == AZIENDA_ID,
                    ProgrammaMateriale.nome == PROGRAMMA_NOME,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            print(f"[programma] esiste già id={existing.id}, riuso")
            return int(existing.id)

        prog = ProgrammaMateriale(
            azienda_id=AZIENDA_ID,
            nome=PROGRAMMA_NOME,
            stagione="invernale",
            valido_da=date(2025, 12, 14),
            valido_a=date(2026, 12, 12),
            stato="attivo",
            n_giornate_default=30,  # safety net, vero termine = km_cap (Sprint 5.6)
            km_max_ciclo=10000,
            stazioni_sosta_extra_json=SOSTA_EXTRA,
        )
        session.add(prog)
        await session.flush()
        prog_id = int(prog.id)

        regola = ProgrammaRegolaAssegnazione(
            programma_id=prog_id,
            filtri_json=[
                {"campo": "direttrice", "op": "eq", "valore": DIRETTRICE},
                {"campo": "codice_origine", "op": "in", "valore": ["S01700", "S01440"]},
                {"campo": "codice_destinazione", "op": "in", "valore": ["S01700", "S01440"]},
            ],
            composizione_json=[
                {"materiale_tipo_codice": "ETR526", "n_pezzi": 1},
                {"materiale_tipo_codice": "ETR425", "n_pezzi": 1},
            ],
            is_composizione_manuale=False,
            materiale_tipo_codice="ETR526",
            numero_pezzi=1,
            priorita=80,
            note="Smoke 5.6 — solo diretti Mi.CLE↔Tirano + doppia ETR526+ETR425",
        )
        session.add(regola)
        await session.flush()
        print(f"[programma] creato id={prog_id} (regola id={regola.id})")
        return prog_id


async def run_builder(programma_id: int) -> None:
    async with session_scope() as session:
        result = await genera_giri(
            programma_id=programma_id,
            data_inizio=DATA_INIZIO,
            n_giornate=N_GIORNATE,
            localita_codice=LOCALITA_CODICE,
            session=session,
            azienda_id=AZIENDA_ID,
            force=True,
        )

    print()
    print("=== BUILDER RESULT ===")
    print(f"giri creati:           {result.n_giri_creati}")
    print(f"corse processate:      {result.n_corse_processate}")
    print(f"corse residue:         {result.n_corse_residue}")
    print(f"giri chiusi naturale:  {result.n_giri_chiusi}")
    print(f"giri NON chiusi:       {result.n_giri_non_chiusi}")
    print(f"  di cui km_cap:       {result.n_giri_km_cap}")
    print(f"eventi composizione:   {result.n_eventi_composizione}")
    print(f"incompatib. materiale: {result.n_incompatibilita_materiale}")
    if result.warnings:
        print(f"warnings ({len(result.warnings)}):")
        for w in result.warnings[:20]:
            print(f"  - {w}")
        if len(result.warnings) > 20:
            print(f"  ... +{len(result.warnings) - 20} altri")


_FILTER_PROG = (
    "((generation_metadata_json->>'programma_id')::bigint = :pid)"
)


async def analisi_giri(programma_id: int) -> None:
    async with session_scope() as session:
        # Distribuzione per numero_giornate + motivo_chiusura
        rows = (
            await session.execute(
                text(
                    f"""
                    SELECT numero_giornate,
                           generation_metadata_json->>'motivo_chiusura' AS motivo,
                           COUNT(*) AS n
                    FROM giro_materiale
                    WHERE {_FILTER_PROG}
                    GROUP BY numero_giornate, motivo
                    ORDER BY numero_giornate, motivo
                    """
                ),
                {"pid": programma_id},
            )
        ).all()
        print()
        print("=== DISTRIBUZIONE giri per (n_giornate, motivo) ===")
        for r in rows:
            print(f"  {r.numero_giornate}g {r.motivo:14}: {r.n}")

        # Stats aggregate
        rows = (
            await session.execute(
                text(
                    f"""
                    SELECT
                      COUNT(*) AS totale,
                      SUM(CASE WHEN numero_giornate >= 2 THEN 1 ELSE 0 END) AS multi_g,
                      SUM(CASE WHEN numero_giornate >= 5 THEN 1 ELSE 0 END) AS lunghi_5p,
                      MAX(numero_giornate) AS max_g,
                      ROUND(AVG(km_media_giornaliera * numero_giornate)::numeric, 1) AS km_giro_media,
                      MAX(km_media_giornaliera * numero_giornate) AS km_giro_max
                    FROM giro_materiale
                    WHERE {_FILTER_PROG}
                    """
                ),
                {"pid": programma_id},
            )
        ).all()
        print()
        print("=== STATS GIRI ===")
        for r in rows:
            print(f"  totale={r.totale} multi_g≥2={r.multi_g} lunghi≥5g={r.lunghi_5p} max_g={r.max_g}")
            print(f"  km/giro: media={r.km_giro_media} max={r.km_giro_max}")

        # Località manutenzione partenza/arrivo (sono tutti FIO?)
        rows = (
            await session.execute(
                text(
                    f"""
                    SELECT lp.codice_breve AS partenza, la.codice_breve AS arrivo,
                           COUNT(*) AS n
                    FROM giro_materiale g
                    LEFT JOIN localita_manutenzione lp ON lp.id = g.localita_manutenzione_partenza_id
                    LEFT JOIN localita_manutenzione la ON la.id = g.localita_manutenzione_arrivo_id
                    WHERE {_FILTER_PROG}
                    GROUP BY lp.codice_breve, la.codice_breve
                    ORDER BY n DESC
                    """
                ),
                {"pid": programma_id},
            )
        ).all()
        print()
        print("=== Sede partenza/arrivo dei giri ===")
        for r in rows:
            print(f"  {r.partenza}→{r.arrivo}: {r.n}")

        # Quanti giri toccano Tirano
        rows = (
            await session.execute(
                text(
                    f"""
                    SELECT COUNT(DISTINCT g.id) AS n
                    FROM giro_materiale g
                    JOIN giro_giornata gg ON gg.giro_materiale_id = g.id
                    JOIN giro_variante gv ON gv.giro_giornata_id = gg.id
                    JOIN giro_blocco b ON b.giro_variante_id = gv.id
                    WHERE {_FILTER_PROG}
                      AND b.tipo_blocco = 'corsa_commerciale'
                      AND (b.stazione_da_codice = :tir OR b.stazione_a_codice = :tir)
                    """
                ),
                {"pid": programma_id, "tir": TIRANO_CODICE},
            )
        ).all()
        print(f"\n=== Giri che toccano TIRANO: {rows[0].n} ===")

        # Quanti giri "dormono a Tirano" tra una giornata e la successiva
        # = ultima corsa di giornata K arriva a Tirano AND prima corsa di K+1 parte da Tirano
        rows = (
            await session.execute(
                text(
                    f"""
                    WITH ultimi AS (
                      SELECT g.id AS giro_id, gg.numero_giornata,
                             (
                               SELECT b.stazione_a_codice
                               FROM giro_blocco b
                               JOIN giro_variante gv2 ON gv2.id = b.giro_variante_id
                               WHERE gv2.giro_giornata_id = gg.id
                                 AND b.tipo_blocco IN ('corsa_commerciale','materiale_vuoto')
                               ORDER BY gv2.variant_index, b.seq DESC
                               LIMIT 1
                             ) AS arrivo_giornata
                      FROM giro_materiale g
                      JOIN giro_giornata gg ON gg.giro_materiale_id = g.id
                      WHERE {_FILTER_PROG}
                    )
                    SELECT arrivo_giornata, COUNT(*) AS n
                    FROM ultimi
                    GROUP BY arrivo_giornata
                    ORDER BY n DESC
                    LIMIT 15
                    """
                ),
                {"pid": programma_id},
            )
        ).all()
        print()
        print("=== Stazione di chiusura (arrivo ultima corsa) per giornata ===")
        for r in rows:
            mark = "  ★ TIRANO" if r.arrivo_giornata == TIRANO_CODICE else ""
            print(f"  {r.arrivo_giornata or '?':>6}: {r.n}{mark}")

        # Vuoti tecnici
        rows = (
            await session.execute(
                text(
                    f"""
                    SELECT b.stazione_da_codice AS o, b.stazione_a_codice AS d,
                           COUNT(*) AS n
                    FROM giro_blocco b
                    JOIN giro_variante gv ON gv.id = b.giro_variante_id
                    JOIN giro_giornata gg ON gg.id = gv.giro_giornata_id
                    JOIN giro_materiale g ON g.id = gg.giro_materiale_id
                    WHERE {_FILTER_PROG} AND b.tipo_blocco = 'materiale_vuoto'
                    GROUP BY o, d
                    ORDER BY n DESC
                    """
                ),
                {"pid": programma_id},
            )
        ).all()
        totale_vuoti = sum(r.n for r in rows)
        print()
        print(f"=== VUOTI TECNICI: {totale_vuoti} totali, {len(rows)} coppie distinte ===")
        for r in rows[:20]:
            ok = "✓" if (r.o in WL_FIO and r.d in WL_FIO) or (r.o == "FIO" or r.d == "FIO") else "?"
            in_wl_o = r.o in WL_FIO or r.o == "FIO"
            in_wl_d = r.d in WL_FIO or r.d == "FIO"
            mark = "✓ wl" if in_wl_o and in_wl_d else "⚠️ FUORI WL"
            print(f"  {r.o or '??':>6} → {r.d or '??':<6}: {r.n}  [{mark}]")

        # Eventi composizione
        rows = (
            await session.execute(
                text(
                    f"""
                    SELECT b.tipo_blocco AS tipo,
                           b.metadata_json->>'materiale_tipo_codice' AS materiale,
                           COUNT(*) AS n
                    FROM giro_blocco b
                    JOIN giro_variante gv ON gv.id = b.giro_variante_id
                    JOIN giro_giornata gg ON gg.id = gv.giro_giornata_id
                    JOIN giro_materiale g ON g.id = gg.giro_materiale_id
                    WHERE {_FILTER_PROG}
                      AND b.tipo_blocco IN ('aggancio','sgancio')
                    GROUP BY tipo, materiale
                    ORDER BY tipo, n DESC
                    """
                ),
                {"pid": programma_id},
            )
        ).all()
        print()
        print(f"=== EVENTI COMPOSIZIONE: {sum(r.n for r in rows)} totali ===")
        for r in rows:
            print(f"  {r.tipo:8} {r.materiale}: {r.n}")

        # Sample: il giro PIÙ RICCO (più blocchi) tra i lunghi
        rows_g = (
            await session.execute(
                text(
                    f"""
                    SELECT g.id, g.numero_turno, g.numero_giornate,
                           g.generation_metadata_json->>'motivo_chiusura' AS motivo,
                           (SELECT COUNT(*) FROM giro_blocco b
                            JOIN giro_variante gv ON gv.id = b.giro_variante_id
                            JOIN giro_giornata gg ON gg.id = gv.giro_giornata_id
                            WHERE gg.giro_materiale_id = g.id) AS n_blocchi
                    FROM giro_materiale g
                    WHERE {_FILTER_PROG}
                    ORDER BY n_blocchi DESC, g.numero_giornate DESC
                    LIMIT 1
                    """
                ),
                {"pid": programma_id},
            )
        ).all()

        # Mappa codice stazione → nome (per leggibilità)
        stazioni_map = dict(
            (
                await session.execute(text("SELECT codice, nome FROM stazione"))
            ).all()
        )

        def label(s: str | None) -> str:
            if not s:
                return "??"
            nome = stazioni_map.get(s, s)
            return f"{s} {nome[:18]}"

        if rows_g:
            g = rows_g[0]
            print()
            print(f"=== MOCKUP giro {g.numero_turno} ({g.numero_giornate} giornate, "
                  f"{g.n_blocchi} blocchi, motivo={g.motivo}) ===")
            blocchi = (
                await session.execute(
                    text(
                        """
                        SELECT gg.numero_giornata, gv.variant_index, b.seq,
                               b.tipo_blocco, b.stazione_da_codice AS o,
                               b.stazione_a_codice AS d,
                               b.ora_inizio, b.ora_fine,
                               b.descrizione AS treno,
                               b.metadata_json->'composizione' AS comp,
                               b.metadata_json->>'materiale_tipo_codice' AS mat_evento
                        FROM giro_giornata gg
                        JOIN giro_variante gv ON gv.giro_giornata_id = gg.id
                        JOIN giro_blocco b ON b.giro_variante_id = gv.id
                        WHERE gg.giro_materiale_id = :gid
                        ORDER BY gg.numero_giornata, gv.variant_index, b.seq
                        """
                    ),
                    {"gid": g.id},
                )
            ).all()
            cur = -1
            for b in blocchi:
                if b.numero_giornata != cur:
                    print(f"  ─── giornata {b.numero_giornata} ───")
                    cur = b.numero_giornata
                hp = str(b.ora_inizio)[:5] if b.ora_inizio else "  -  "
                ha = str(b.ora_fine)[:5] if b.ora_fine else "  -  "
                if b.tipo_blocco == "corsa_commerciale":
                    comp_str = "?"
                    if b.comp:
                        comp_str = "+".join(
                            f"{c['materiale_tipo_codice']}×{c['n_pezzi']}"
                            for c in b.comp
                        )
                    print(
                        f"    {b.seq:>2}. CORSA   {b.treno or '?':>6} "
                        f"{hp}→{ha}  {label(b.o):<28}→ {label(b.d):<28} [{comp_str}]"
                    )
                elif b.tipo_blocco == "materiale_vuoto":
                    print(
                        f"    {b.seq:>2}. VUOTO          "
                        f"{hp}→{ha}  {label(b.o):<28}→ {label(b.d):<28}"
                    )
                elif b.tipo_blocco in ("aggancio", "sgancio"):
                    icon = "⊕" if b.tipo_blocco == "aggancio" else "⊖"
                    print(f"    {b.seq:>2}. {b.tipo_blocco:<7} {icon} {b.mat_evento}")
                else:
                    print(f"    {b.seq:>2}. {b.tipo_blocco}")


async def main() -> None:
    print("=== SMOKE 5.6 Mi.Centrale↔Tirano ===")
    print(f"data_inizio={DATA_INIZIO} (lun), n_giornate={N_GIORNATE}")
    print(f"sede={LOCALITA_CODICE}, direttrice={DIRETTRICE!r}")
    print()
    prog_id = await crea_o_riusa_programma()
    await run_builder(prog_id)
    await analisi_giri(prog_id)


if __name__ == "__main__":
    asyncio.run(main())
