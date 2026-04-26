"""Orchestrator import PdE → DB con idempotenza SHA-256 e CLI — Sprint 3.6.

Architettura a 4 fasi (tutto in una **singola transazione**):

    1. Hash file + read rows           → fuori transazione (no DB)
    2. get_azienda_id + idempotency    → skip se SHA-256 già visto e niente --force
    3. open run + upsert stazioni      → bulk
    4. per ogni riga: upsert corsa     → INSERT (nuova) o UPDATE+REPLACE composizioni
    5. close run                       → completed_at, n_create, n_update, note

In caso di errore in 3-5: rollback completo (session_scope() gestisce).

## Idempotenza

`corsa_import_run.source_hash` traccia ogni file importato. Se un run con
stesso `source_hash` (e stessa `azienda_id`, `completed_at IS NOT NULL`)
esiste già, l'import si ferma e ritorna `ImportSummary(skipped=True)`.

Per forzare il re-import (es. dopo un fix nel parser): `--force`.

## Chiave upsert corsa

`(azienda_id, numero_treno, valido_da)` — corrisponde al constraint
`UNIQUE` su `corsa_commerciale`. Sopra questa chiave: UPDATE in-place
+ DELETE+REINSERT delle 9 `corsa_composizione`.

## CLI

    python -m colazione.importers.pde_importer \\
        --file data/pde-input/<file>.numbers \\
        --azienda trenord \\
        [--force]

Vedi `docs/IMPORT-PDE.md` §9 per il workflow operativo completo.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.db import session_scope
from colazione.importers.pde import (
    CorsaParsedRow,
    parse_corsa_row,
    read_pde_file,
)
from colazione.models.anagrafica import Azienda, Stazione
from colazione.models.corse import (
    CorsaCommerciale,
    CorsaComposizione,
    CorsaImportRun,
)

logger = logging.getLogger(__name__)


# =====================================================================
# Risultato dell'import
# =====================================================================


@dataclass
class ImportSummary:
    """Esito dell'import."""

    skipped: bool = False
    skip_reason: str | None = None
    run_id: int | None = None
    n_create: int = 0
    n_update: int = 0
    n_warnings: int = 0
    duration_s: float = 0.0


# =====================================================================
# Hash file
# =====================================================================


def compute_sha256(path: Path) -> str:
    """SHA-256 del contenuto di `path`. Streaming in chunk da 64KB."""
    sha = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


# =====================================================================
# Helpers DB
# =====================================================================


async def get_azienda_id(session: AsyncSession, codice: str) -> int:
    """Risolve `azienda.codice` → `azienda.id`. Solleva se non trovata."""
    stmt = select(Azienda.id).where(Azienda.codice == codice)
    result = await session.execute(stmt)
    azienda_id = result.scalar_one_or_none()
    if azienda_id is None:
        raise ValueError(
            f"Azienda con codice {codice!r} non trovata. "
            "Esegui le seed migrations (`uv run alembic upgrade head`) prima."
        )
    return azienda_id


async def find_existing_run(
    session: AsyncSession,
    source_hash: str,
    azienda_id: int,
) -> CorsaImportRun | None:
    """Cerca un run **completato** con stesso hash e azienda. Più recente prima."""
    stmt = (
        select(CorsaImportRun)
        .where(
            CorsaImportRun.source_hash == source_hash,
            CorsaImportRun.azienda_id == azienda_id,
            CorsaImportRun.completed_at.is_not(None),
        )
        .order_by(CorsaImportRun.id.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


# =====================================================================
# Stazioni — upsert dinamico dai (codice, nome) trovati nel file
# =====================================================================


def collect_stazioni(
    parsed_rows: list[CorsaParsedRow],
    raw_rows: list[dict[str, Any]],
) -> dict[str, str]:
    """Estrae il dizionario `codice → nome` di tutte le stazioni del file.

    Le 4 colonne PdE che riferiscono stazioni: Origine, Destinazione,
    Inizio CdS, Fine CdS. La prima occorrenza vince — duplicati con nome
    leggermente diverso vengono ignorati (raro nel PdE Trenord).
    """
    out: dict[str, str] = {}

    def _add(codice: str | None, nome_raw: Any) -> None:
        if not codice:
            return
        nome = str(nome_raw).strip() if nome_raw is not None and nome_raw != "" else codice
        out.setdefault(codice, nome)

    for parsed, raw in zip(parsed_rows, raw_rows, strict=True):
        _add(parsed.codice_origine, raw.get("Stazione Origine Treno"))
        _add(parsed.codice_destinazione, raw.get("Stazione Destinazione Treno"))
        _add(parsed.codice_inizio_cds, raw.get("Stazione Inizio CdS"))
        _add(parsed.codice_fine_cds, raw.get("Stazione Fine CdS"))

    return out


async def upsert_stazioni(
    session: AsyncSession,
    stazioni: dict[str, str],
    azienda_id: int,
) -> None:
    """Bulk upsert `stazione`. ON CONFLICT (codice) DO NOTHING.

    Il PdE può avere stazioni di altri operatori (RFI, FN ferrovie del
    nord) ma noi le associamo all'azienda corrente: l'import per Trenord
    crea/usa stazioni con `azienda_id=trenord`. Multi-tenant edge case
    (stessa stazione condivisa) sarà gestito separatamente in v1.x.
    """
    if not stazioni:
        return
    rows = [
        {"codice": codice, "nome": nome, "azienda_id": azienda_id}
        for codice, nome in stazioni.items()
    ]
    stmt = pg_insert(Stazione).values(rows).on_conflict_do_nothing(index_elements=["codice"])
    await session.execute(stmt)


# =====================================================================
# Upsert corsa + composizioni
# =====================================================================


def _corsa_payload(
    parsed: CorsaParsedRow,
    azienda_id: int,
    import_run_id: int,
) -> dict[str, Any]:
    """Mappa `CorsaParsedRow` → dict di colonne `corsa_commerciale`."""
    return {
        "azienda_id": azienda_id,
        "numero_treno": parsed.numero_treno,
        "rete": parsed.rete,
        "numero_treno_rfi": parsed.numero_treno_rfi,
        "numero_treno_fn": parsed.numero_treno_fn,
        "categoria": parsed.categoria,
        "codice_linea": parsed.codice_linea,
        "direttrice": parsed.direttrice,
        "codice_origine": parsed.codice_origine,
        "codice_destinazione": parsed.codice_destinazione,
        "codice_inizio_cds": parsed.codice_inizio_cds,
        "codice_fine_cds": parsed.codice_fine_cds,
        "ora_partenza": parsed.ora_partenza,
        "ora_arrivo": parsed.ora_arrivo,
        "ora_inizio_cds": parsed.ora_inizio_cds,
        "ora_fine_cds": parsed.ora_fine_cds,
        "min_tratta": parsed.min_tratta,
        "min_cds": parsed.min_cds,
        "km_tratta": parsed.km_tratta,
        "km_cds": parsed.km_cds,
        "valido_da": parsed.valido_da,
        "valido_a": parsed.valido_a,
        "codice_periodicita": parsed.codice_periodicita,
        "periodicita_breve": parsed.periodicita_breve,
        "is_treno_garantito_feriale": parsed.is_treno_garantito_feriale,
        "is_treno_garantito_festivo": parsed.is_treno_garantito_festivo,
        "fascia_oraria": parsed.fascia_oraria,
        "giorni_per_mese_json": parsed.giorni_per_mese_json,
        "valido_in_date_json": parsed.valido_in_date_json,
        "totale_km": parsed.totale_km,
        "totale_minuti": parsed.totale_minuti,
        "posti_km": parsed.posti_km,
        "velocita_commerciale": parsed.velocita_commerciale,
        "import_source": "pde",
        "import_run_id": import_run_id,
    }


def _composizione_rows(
    corsa_id: int,
    parsed: CorsaParsedRow,
) -> list[dict[str, Any]]:
    """Mappa le 9 `ComposizioneParsed` di una corsa → dict per insert."""
    return [
        {
            "corsa_commerciale_id": corsa_id,
            "stagione": c.stagione,
            "giorno_tipo": c.giorno_tipo,
            "categoria_posti": c.categoria_posti,
            "is_doppia_composizione": c.is_doppia_composizione,
            "tipologia_treno": c.tipologia_treno,
            "vincolo_dichiarato": c.vincolo_dichiarato,
            "categoria_bici": c.categoria_bici,
            "categoria_prm": c.categoria_prm,
        }
        for c in parsed.composizioni
    ]


async def upsert_corsa(
    session: AsyncSession,
    parsed: CorsaParsedRow,
    azienda_id: int,
    import_run_id: int,
) -> bool:
    """Upsert corsa + 9 composizioni. Ritorna True se INSERT, False se UPDATE."""
    stmt = select(CorsaCommerciale.id).where(
        CorsaCommerciale.azienda_id == azienda_id,
        CorsaCommerciale.numero_treno == parsed.numero_treno,
        CorsaCommerciale.valido_da == parsed.valido_da,
    )
    existing_id = (await session.execute(stmt)).scalar_one_or_none()

    payload = _corsa_payload(parsed, azienda_id, import_run_id)

    if existing_id is not None:
        await session.execute(
            update(CorsaCommerciale).where(CorsaCommerciale.id == existing_id).values(**payload)
        )
        # Replace composizioni: delete tutte le 9 esistenti + reinsert
        await session.execute(
            delete(CorsaComposizione).where(CorsaComposizione.corsa_commerciale_id == existing_id)
        )
        corsa_id = existing_id
        was_insert = False
    else:
        result = await session.execute(
            pg_insert(CorsaCommerciale).values(**payload).returning(CorsaCommerciale.id)
        )
        corsa_id = result.scalar_one()
        was_insert = True

    comp_rows = _composizione_rows(corsa_id, parsed)
    await session.execute(pg_insert(CorsaComposizione).values(comp_rows))

    return was_insert


# =====================================================================
# Top-level orchestration
# =====================================================================


async def importa_pde(
    file_path: Path,
    azienda_codice: str,
    *,
    force: bool = False,
) -> ImportSummary:
    """Importa il PdE nel DB per l'azienda specificata.

    Args:
        file_path: percorso al file `.numbers` o `.xlsx`.
        azienda_codice: `azienda.codice` (es. `'trenord'`).
        force: se True, salta il check di idempotenza (re-import forzato).

    Returns:
        `ImportSummary` con run_id, n_create, n_update, durata.
    """
    t0 = time.monotonic()

    # Step 1 — fuori transazione: hash + read file
    if not file_path.exists():
        raise FileNotFoundError(f"File PdE non trovato: {file_path}")
    file_hash = compute_sha256(file_path)
    raw_rows = read_pde_file(file_path)

    async with session_scope() as session:
        # Step 2 — risolve azienda + check idempotenza
        azienda_id = await get_azienda_id(session, azienda_codice)

        if not force:
            existing_run = await find_existing_run(session, file_hash, azienda_id)
            if existing_run is not None:
                return ImportSummary(
                    skipped=True,
                    skip_reason=(
                        f"file già importato (run {existing_run.id} il "
                        f"{existing_run.completed_at:%Y-%m-%d %H:%M})"
                    ),
                    run_id=existing_run.id,
                    duration_s=time.monotonic() - t0,
                )

        # Step 3 — apri run + upsert stazioni
        run = CorsaImportRun(
            source_file=file_path.name,
            source_hash=file_hash,
            azienda_id=azienda_id,
        )
        session.add(run)
        await session.flush()  # popola run.id
        run_id = run.id

        parsed_rows = [parse_corsa_row(r) for r in raw_rows]

        stazioni = collect_stazioni(parsed_rows, raw_rows)
        await upsert_stazioni(session, stazioni, azienda_id)

        # Step 4 — per ogni riga: upsert corsa + composizioni
        n_create = 0
        n_update = 0
        n_warnings = 0
        for parsed in parsed_rows:
            was_insert = await upsert_corsa(session, parsed, azienda_id, run_id)
            if was_insert:
                n_create += 1
            else:
                n_update += 1
            n_warnings += len(parsed.warnings)

        # Step 5 — chiudi run
        await session.execute(
            update(CorsaImportRun)
            .where(CorsaImportRun.id == run_id)
            .values(
                n_corse=n_create + n_update,
                n_corse_create=n_create,
                n_corse_update=n_update,
                completed_at=func.now(),
                note=f"{n_warnings} warning periodicità (cross-check Gg_*)",
            )
        )

    return ImportSummary(
        run_id=run_id,
        n_create=n_create,
        n_update=n_update,
        n_warnings=n_warnings,
        duration_s=time.monotonic() - t0,
    )


# =====================================================================
# CLI
# =====================================================================


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m colazione.importers.pde_importer",
        description="Importa un Programma di Esercizio (.numbers/.xlsx) nel DB COLAZIONE.",
    )
    parser.add_argument(
        "--file",
        type=Path,
        required=True,
        help="path al file PdE (.numbers o .xlsx)",
    )
    parser.add_argument(
        "--azienda",
        type=str,
        default="trenord",
        help="codice azienda (default: trenord)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-import anche se SHA-256 già visto",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Ritorna exit code (0 ok, 2 file non trovato, 1 errore)."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _build_arg_parser().parse_args(argv)

    file_path: Path = args.file
    if not file_path.exists():
        print(f"ERRORE: file non trovato: {file_path}", file=sys.stderr)
        return 2

    try:
        summary = asyncio.run(importa_pde(file_path, args.azienda, force=args.force))
    except Exception as exc:
        print(f"ERRORE durante l'import: {exc}", file=sys.stderr)
        return 1

    if summary.skipped:
        print(f"⊘ skip: {summary.skip_reason}")
        print(f"  durata: {summary.duration_s:.1f}s")
        print("  (usa --force per re-importare)")
        return 0

    print(
        f"✓ Run ID {summary.run_id}: {summary.n_create} create, "
        f"{summary.n_update} update, {summary.n_warnings} warning"
    )
    print(f"  durata: {summary.duration_s:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
