"""Sprint 5.6 R5 — dimostrazione Cremona ATR803.

Dimostra che il modello generico (algoritmo + dato) gestisce un
programma materiale completamente diverso da Tirano:

- direttrice: ``MANTOVA-CREMONA-LODI-MILANO``
- composizione: ``[ATR803]`` (singola, no accoppiamenti)
- sede: ``IMPMAN_CREMONA`` (CRE)
- whitelist sede: solo CREMONA (S01915)
- stazioni sosta extra: nessuna oltre i depot PdC
- km_max_ciclo: 5000 (ATR diesel, ciclo più corto)

Output atteso: 1-2 giri ATR803 multi-giornata che coprono le ~35 corse
direttrice nel periodo richiesto, finestra orari naturale.
"""

from __future__ import annotations

import asyncio
from datetime import date

from sqlalchemy import select

from colazione.db import session_scope
from colazione.domain.builder_giro.builder import genera_giri
from colazione.models.programmi import (
    ProgrammaMateriale,
    ProgrammaRegolaAssegnazione,
)

AZIENDA_ID = 2
PROGRAMMA_NOME = "Trenord 2025-2026 invernale Cremona ATR803"
DIRETTRICE = "MANTOVA-CREMONA-LODI-MILANO"
LOCALITA_CODICE = "IMPMAN_CREMONA"
DATA_INIZIO = date(2026, 1, 19)
N_GIORNATE = 14


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
            n_giornate_default=30,
            km_max_ciclo=5000,  # ATR diesel
            stazioni_sosta_extra_json=[],  # solo depot PdC (CREMONA via depot)
        )
        session.add(prog)
        await session.flush()
        prog_id = int(prog.id)

        regola = ProgrammaRegolaAssegnazione(
            programma_id=prog_id,
            filtri_json=[
                {"campo": "direttrice", "op": "eq", "valore": DIRETTRICE}
            ],
            composizione_json=[
                {"materiale_tipo_codice": "ATR803", "n_pezzi": 1},
            ],
            is_composizione_manuale=False,
            materiale_tipo_codice="ATR803",
            numero_pezzi=1,
            priorita=80,
            note="Smoke 5.6 R5 — direttrice MANTOVA-CREMONA-LODI-MILANO + ATR803 singolo",
        )
        session.add(regola)
        await session.flush()
        print(f"[programma] creato id={prog_id} (regola id={regola.id})")
        return prog_id


async def main() -> None:
    print("=== SMOKE 5.6 R5 — Cremona ATR803 ===")
    print(f"data_inizio={DATA_INIZIO} (lun), n_giornate={N_GIORNATE}")
    print(f"sede={LOCALITA_CODICE}, direttrice={DIRETTRICE!r}")
    print()

    prog_id = await crea_o_riusa_programma()

    async with session_scope() as session:
        result = await genera_giri(
            programma_id=prog_id,
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
    print(f"warnings ({len(result.warnings)}):")
    for w in result.warnings[:5]:
        print(f"  - {w}")


if __name__ == "__main__":
    asyncio.run(main())
