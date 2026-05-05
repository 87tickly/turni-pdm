"""MR 0 — pulizia dati di prova generati durante lo sviluppo.

Svuota le tabelle "downstream" (PdE importato + programmi + giri + turni
PdC + revisioni) lasciando intatti gli **anagrafici/seed** (azienda,
stazioni, materiali, depot, persone, festività, ecc.).

Esecuzione::

    # 1. DRY-RUN (default, non cancella nulla)
    railway run --service Postgres -- uv run python scripts/pulizia_dati_prova.py

    # 2. ESECUZIONE EFFETTIVA (richiede env var di conferma)
    CONFIRM_CLEANUP=YES railway run --service Postgres -- \\
        uv run python scripts/pulizia_dati_prova.py --esegui

Il DELETE è in **una sola transazione**: o riesce tutto o rollback completo.

Stesso fix driver psycopg3 + DATABASE_PUBLIC_URL del baseline_pre_pulizia.py.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

_url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL", "")
if _url.startswith("postgresql://"):
    _url = _url.replace("postgresql://", "postgresql+psycopg://", 1)
elif _url.startswith("postgres://"):
    _url = _url.replace("postgres://", "postgresql+psycopg://", 1)
os.environ["DATABASE_URL"] = _url

from sqlalchemy import text  # noqa: E402

from colazione.db import session_scope  # noqa: E402

# Ordine FK-safe: figli prima dei padri.
#
# IMPORTANTE — cosa NON svuotiamo (decisione utente 2026-05-05):
# il blocco PdE importato (``corsa_commerciale``, ``corsa_composizione``,
# ``corsa_materiale_vuoto``, ``corsa_import_run``) **resta intatto**.
# È la base autorevole da cui i nuovi programmi generano il materiale;
# re-importarlo ogni volta sarebbe spreco. I 259 ``corsa_materiale_vuoto``
# legati ai giri che cancelliamo restano in DB con
# ``giro_materiale_id = NULL`` (FK ON DELETE SET NULL): orfani innocui,
# il builder rigenera i propri vuoti al prossimo run.
TABELLE_ORDINATE: list[str] = [
    # Revisioni
    "revisione_provvisoria_pdc",
    "revisione_provvisoria_blocco",
    "revisione_provvisoria",
    # Turni PdC
    "turno_pdc_blocco",
    "turno_pdc_giornata",
    "turno_pdc",
    # Assegnazioni personale
    "assegnazione_giornata",
    # Giri materiale
    "giro_blocco",
    "giro_variante",
    "giro_giornata",
    "giro_finestra_validita",
    "versione_base_giro",
    "giro_materiale",
    # Builder runs
    "builder_run",
    # Programmi e regole correlate (di programma)
    "regola_invio_sosta",
    "localita_sosta",
    "programma_regola_assegnazione",
    "programma_materiale",
]


async def conta_righe(tabella: str) -> int | None:
    """Conta righe di una tabella. None se non esiste."""
    from sqlalchemy.exc import ProgrammingError

    async with session_scope() as session:
        try:
            result = await session.execute(text(f"SELECT COUNT(*) FROM {tabella}"))
            return int(result.scalar_one())
        except ProgrammingError as exc:
            if "UndefinedTable" in str(exc.orig.__class__.__name__):
                return None
            raise


async def esegui_pulizia(dry_run: bool) -> None:
    """Esegue la pulizia in transazione singola, oppure solo dry-run."""
    print("=" * 70)
    print("PULIZIA DATI DI PROVA — MR 0")
    print(f"Modalità: {'DRY-RUN (nessuna modifica)' if dry_run else 'ESECUZIONE'}")
    print("=" * 70)

    print("\n[1/3] Conta righe PRIMA:")
    pre_counts: dict[str, int | None] = {}
    totale_pre = 0
    for tabella in TABELLE_ORDINATE:
        n = await conta_righe(tabella)
        pre_counts[tabella] = n
        if n is not None:
            totale_pre += n
            print(f"  {tabella:<40} {n:>10}")
        else:
            print(f"  {tabella:<40} n/a")
    print(f"  TOTALE: {totale_pre}")

    if dry_run:
        print("\n[2/3] DRY-RUN — niente DELETE eseguito.")
        print("\nPer eseguire davvero: export CONFIRM_CLEANUP=YES e --esegui")
        return

    if os.environ.get("CONFIRM_CLEANUP") != "YES":
        print("\n❌ Variabile CONFIRM_CLEANUP=YES mancante. Aborto per sicurezza.")
        sys.exit(2)

    print("\n[2/3] Esecuzione DELETE in transazione singola...")
    async with session_scope() as session:
        for tabella in TABELLE_ORDINATE:
            if pre_counts[tabella] is None:
                continue
            await session.execute(text(f"DELETE FROM {tabella}"))
            print(f"  DELETE FROM {tabella}  ok")
        # commit implicito al __aexit__ del session_scope

    print("\n[3/3] Conta righe DOPO:")
    totale_post = 0
    for tabella in TABELLE_ORDINATE:
        n = await conta_righe(tabella)
        if n is not None:
            totale_post += n
            stato = "OK" if n == 0 else "⚠ NON A ZERO"
            print(f"  {tabella:<40} {n:>10}  {stato}")

    if totale_post == 0:
        print(f"\n✅ Pulizia completata. Da {totale_pre} → 0 righe.")
    else:
        print(f"\n⚠ Pulizia parziale: {totale_post} righe rimaste (atteso 0).")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pulizia dati di prova MR 0")
    parser.add_argument(
        "--esegui",
        action="store_true",
        help=(
            "Esegue il DELETE. Senza questo flag fa solo dry-run. "
            "Richiede anche env var CONFIRM_CLEANUP=YES."
        ),
    )
    args = parser.parse_args()
    asyncio.run(esegui_pulizia(dry_run=not args.esegui))


if __name__ == "__main__":
    main()
