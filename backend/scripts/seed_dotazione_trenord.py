"""Seed dotazione fisica Trenord — Sprint 7.9 MR 7D.

Popola ``materiale_dotazione_azienda`` con i numeri di pezzi singoli
in dotazione a Trenord, comunicati dall'utente il 2026-05-03.

Mapping codice materiale ← seed `materiale_tipo`:

- ETR522, ETR421, ETR526, ETR425 → famiglie create dal seed Sprint 5.2.
- E464 → loco elettrico.
- ATR125, ATR115, ATR803 → diesel.
- ETR245 → vedi note: registrato come ``ALe245_treno`` nel seed
  (motrice + rimorchiata). Per ora mappato su ``ALe245_treno``.
- ALe711/710 → famiglie ALe711_3 + ALe711_4. Dotazione 60 cumulativa
  → split 30/30 per default (la granularità per variante richiede
  conferma utente).
- ETR521, ETR204, ETR103, ETR104 → famiglie.
- ETR524 (FLIRT TILO) → ``pezzi_disponibili = NULL`` (capacity
  illimitata sui turni TILO).

Uso::

    docker exec colazione_backend bash -c \\
        "cd /app && PYTHONPATH=src uv run python scripts/seed_dotazione_trenord.py"

Idempotente via ``ON CONFLICT (azienda_id, materiale_codice) DO UPDATE``.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from colazione.db import session_scope
from colazione.models.anagrafica import MaterialeDotazioneAzienda

logger = logging.getLogger("seed_dotazione")


# Numeri comunicati dall'utente 2026-05-03.
DOTAZIONE_TRENORD: list[tuple[str, int | None, str]] = [
    ("ETR522", 71, "FLIRT 5 casse"),
    ("ETR421", 44, "Caravaggio/Rock 4 casse"),
    ("ETR526", 11, "Coradia Meridian 6 casse"),
    ("ETR425", 18, "Coradia Meridian 5 casse"),
    ("E464", 18, "Locomotiva elettrica"),
    ("ATR125", 15, "Diesel"),
    ("ATR115", 6, "Diesel"),
    ("ALe245_treno", 12, "ETR245 — 12 treni completi (motrice+rimorchiata)"),
    # ALe711: 60 cumulativi, split 30/30 fra le 2 varianti per default.
    ("ALe711_3", 30, "TSR 3 casse — split di 60 cumulativi 711/710"),
    ("ALe711_4", 30, "TSR 4 casse — split di 60 cumulativi 711/710"),
    ("ATR803", 20, "Diesel"),
    ("ETR521", 5, "Caravaggio/Rock 5 casse — solo singola"),
    ("ETR204", 35, "Donizetti 4 casse"),
    ("ETR103", 10, "Donizetti 3 casse"),
    ("ETR104", 8, "Donizetti 4 casse"),
    # FLIRT TILO: numero non specificato → capacity illimitata.
    ("ETR524", None, "FLIRT TILO — copre tutti i turni TILO (capacity illimitata)"),
]


async def seed() -> None:
    async with session_scope() as session:
        # Trova azienda Trenord
        az_row = (
            await session.execute(text("SELECT id FROM azienda WHERE codice = 'trenord'"))
        ).first()
        if az_row is None:
            print("Azienda 'trenord' non trovata. Aborting.", file=sys.stderr)
            sys.exit(1)
        azienda_id = int(az_row[0])

        # Verifica che tutti i materiali esistano in materiale_tipo
        codici_richiesti = {r[0] for r in DOTAZIONE_TRENORD}
        stmt = select(text("codice")).select_from(text("materiale_tipo")).where(
            text("codice = ANY(:codici)").bindparams(codici=list(codici_richiesti))
        )
        codici_esistenti = {r[0] for r in (await session.execute(stmt)).all()}
        mancanti = codici_richiesti - codici_esistenti
        if mancanti:
            print(
                f"WARNING: codici materiale mancanti in materiale_tipo: {mancanti}. "
                "Esegui prima `seed_whitelist_e_accoppiamenti.py`.",
                file=sys.stderr,
            )

        n_inseriti = 0
        n_aggiornati = 0
        for codice, pezzi, note in DOTAZIONE_TRENORD:
            if codice in mancanti:
                print(f"  · skip {codice}: non esiste in materiale_tipo")
                continue
            stmt_ins = pg_insert(MaterialeDotazioneAzienda).values(
                azienda_id=azienda_id,
                materiale_codice=codice,
                pezzi_disponibili=pezzi,
                note=note,
            )
            stmt_ins = stmt_ins.on_conflict_do_update(
                index_elements=["azienda_id", "materiale_codice"],
                set_={
                    "pezzi_disponibili": pezzi,
                    "note": note,
                    "updated_at": text("NOW()"),
                },
            )
            await session.execute(stmt_ins)
            label = f"{pezzi} pezzi" if pezzi is not None else "capacity illimitata"
            print(f"  + {codice}: {label}")
            n_inseriti += 1

        await session.commit()
        print(f"\nSeed completato: {n_inseriti} righe upserted (azienda Trenord, id={azienda_id}).")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed())
