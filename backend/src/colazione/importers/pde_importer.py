"""Orchestrator import PdE → DB con **delta-sync** + idempotenza SHA-256 + CLI.

Sprint 3.7: refactor da "upsert per chiave business" a "delta-sync per
row_hash". La chiave business `(azienda_id, numero_treno, valido_da)`
collassava silenziosamente fino a 53 righe del PdE Trenord reale —
**perdita dati inaccettabile** per un sistema di pianificazione
ferroviaria. La nuova strategia garantisce **ogni riga PdE = una riga
in DB**.

## Architettura delta-sync (multiset)

Ogni riga del PdE ha una `row_hash` (SHA-256 dei campi grezzi). Identità
naturale, deterministica, stabile fra re-import. Il PdE può avere righe
**completamente identiche** (osservate 8 coppie sul file 2025-2026):
**non vengono deduplicate**, ognuna è una riga in DB. Identità =
multiset di hash.

Algoritmo per import:

    1. Hash file → check idempotenza (SHA-256 globale del file)
    2. Read + parse → calcola row_hash per ogni riga (10579 hash)
    3. Bulk SELECT (id, row_hash) per azienda
    4. Diff multiset (Counter):
       - per ogni riga del file: se esiste un'istanza non-matchata
         in DB con quel hash → kept (id stabile). Altrimenti → INSERT.
       - esistenti che eccedono il count del file → DELETE.
    5. Bulk DELETE righe sparite (cascade su composizioni)
    6. Bulk INSERT righe nuove + 9 composizioni ciascuna
    7. **INVARIANTE FORTE**: COUNT(*) corse post-import == righe nel
       file. Se diverso → raise + rollback transazione.
    8. Close run

Tutto in **una transazione**. Errore in 3-7 → rollback completo.

## Stabilità id

Re-import del PdE invariato: tutti gli id stabili.
Re-import file con N righe modificate: solo le N hanno nuovo id.
Re-import file con righe duplicate: ordine arbitrario tra i duplicati,
ma il count totale è preservato.
Compatibile con Sprint 4+ (giri materiali pinned a corsa.id).

## Idempotenza

`corsa_import_run.source_hash` traccia il file. Stesso hash + azienda
+ run completato → skip totale (ImportSummary.skipped=True).

## CLI

    python -m colazione.importers.pde_importer \\
        --file data/pde-input/<file>.numbers \\
        --azienda trenord \\
        [--force]

Vedi `docs/IMPORT-PDE.md` §9 per il workflow operativo.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import sys
import time
from collections import Counter, defaultdict
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
# Risultato dell'import (semantica delta-sync)
# =====================================================================


@dataclass
class ImportSummary:
    """Esito dell'import con conteggi delta-sync.

    - `n_total`: totale corse in DB per quell'azienda dopo l'import.
    - `n_create`: righe nuove inserite (hash non presente prima).
    - `n_delete`: righe rimosse (presenti prima, non più nel file).
    - `n_kept`: righe invariate (hash matcha → id stabile, no-op).
    - `n_warnings`: cross-check Gg_* falliti (info, non bloccanti).
    """

    skipped: bool = False
    skip_reason: str | None = None
    run_id: int | None = None
    n_total: int = 0
    n_create: int = 0
    n_delete: int = 0
    n_kept: int = 0
    n_warnings: int = 0
    duration_s: float = 0.0


# =====================================================================
# Hash file + hash riga
# =====================================================================


def compute_sha256(path: Path) -> str:
    """SHA-256 del contenuto di `path`. Streaming in chunk da 64KB."""
    sha = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def compute_row_hash(raw_row: dict[str, Any]) -> str:
    """SHA-256 deterministico di una riga grezza del PdE.

    I 124 campi della riga sono serializzati in JSON ordinato per chiave.
    Valori `None` → `null` JSON. Tipi non JSON-serializzabili
    (datetime, Decimal, time) → `str()`. Stabile fra esecuzioni: stessa
    riga PdE produce sempre lo stesso hash.

    NB: il `_` come terzo arg di `json.dumps` (separators) elimina spazi
    spurî → la stringa canonica è byte-stable.
    """
    serializable: dict[str, str | None] = {
        k: (None if v is None or v == "" else str(v)) for k, v in raw_row.items()
    }
    canonical = json.dumps(serializable, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
    """Estrae il dizionario `codice → nome` di tutte le stazioni del file."""
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
    """Bulk upsert `stazione`. ON CONFLICT (codice) DO NOTHING."""
    if not stazioni:
        return
    rows = [
        {"codice": codice, "nome": nome, "azienda_id": azienda_id}
        for codice, nome in stazioni.items()
    ]
    stmt = pg_insert(Stazione).values(rows).on_conflict_do_nothing(index_elements=["codice"])
    await session.execute(stmt)


# =====================================================================
# Payload mappers
# =====================================================================


def _corsa_payload(
    parsed: CorsaParsedRow,
    azienda_id: int,
    import_run_id: int,
    row_hash: str,
) -> dict[str, Any]:
    """Mappa `CorsaParsedRow` → dict di colonne `corsa_commerciale`.

    Include `row_hash` (Sprint 3.7): identità naturale per delta-sync.
    """
    return {
        "azienda_id": azienda_id,
        "row_hash": row_hash,
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


# =====================================================================
# Top-level orchestration (delta-sync)
# =====================================================================


async def importa_pde(
    file_path: Path,
    azienda_codice: str,
    *,
    force: bool = False,
) -> ImportSummary:
    """Importa il PdE nel DB per l'azienda specificata, con delta-sync.

    Args:
        file_path: percorso al file `.numbers` o `.xlsx`.
        azienda_codice: `azienda.codice` (es. `'trenord'`).
        force: se True, salta il check di idempotenza (re-import forzato).

    Returns:
        `ImportSummary` con conteggi delta (create / delete / kept).

    Raises:
        FileNotFoundError: file non esiste.
        ValueError: azienda non trovata.
        RuntimeError: invariante post-import fallita (rollback).
    """
    t0 = time.monotonic()

    if not file_path.exists():
        raise FileNotFoundError(f"File PdE non trovato: {file_path}")
    file_hash = compute_sha256(file_path)
    raw_rows = read_pde_file(file_path)

    async with session_scope() as session:
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

        # Step 1 — parse + compute row_hash per ogni riga
        # NB: il PdE Trenord può avere righe completamente identiche
        # (8 coppie osservate sul file 2025-2026). NON le deduplichiamo:
        # principio "no train left behind". Identità DB = multiset di
        # row_hash — N righe con stesso hash = N righe in DB.
        parsed_rows = [parse_corsa_row(r) for r in raw_rows]
        row_hashes = [compute_row_hash(r) for r in raw_rows]
        n_total_file = len(parsed_rows)

        # Step 2 — open run + upsert stazioni
        run = CorsaImportRun(
            source_file=file_path.name,
            source_hash=file_hash,
            azienda_id=azienda_id,
        )
        session.add(run)
        await session.flush()
        run_id = run.id

        stazioni = collect_stazioni(parsed_rows, raw_rows)
        await upsert_stazioni(session, stazioni, azienda_id)

        # Step 3 — delta-sync (multiset): bulk SELECT esistenti per azienda
        # Per ogni hash, raccolgo TUTTI gli id esistenti (può essere >1
        # se ci sono righe identiche nel PdE).
        result = await session.execute(
            select(CorsaCommerciale.id, CorsaCommerciale.row_hash)
            .where(CorsaCommerciale.azienda_id == azienda_id)
            .order_by(CorsaCommerciale.id)
        )
        existing_ids_by_hash: dict[str, list[int]] = defaultdict(list)
        for cid, h in result.all():
            existing_ids_by_hash[h].append(cid)

        # Step 4 — calcola diff multiset
        # Per ogni riga del file: se esiste un'istanza non-matchata in DB
        # con quel hash → kept (id stabile). Altrimenti → INSERT.
        # Esistenti che eccedono il count del file → DELETE.
        file_hash_count: Counter[str] = Counter(row_hashes)
        matched_count: Counter[str] = Counter()
        to_insert: list[tuple[CorsaParsedRow, str]] = []
        for parsed, h in zip(parsed_rows, row_hashes, strict=True):
            if matched_count[h] < len(existing_ids_by_hash.get(h, [])):
                matched_count[h] += 1  # kept (id stabile)
            else:
                to_insert.append((parsed, h))  # nuovo o duplicato non in DB

        to_delete_ids: list[int] = []
        for h, ids in existing_ids_by_hash.items():
            n_in_file = file_hash_count.get(h, 0)
            if len(ids) > n_in_file:
                # Cancella le ultime (per id) — semantica arbitraria ma stabile
                to_delete_ids.extend(ids[n_in_file:])

        n_kept = sum(matched_count.values())
        n_create = len(to_insert)
        n_delete = len(to_delete_ids)
        n_warnings = sum(len(p.warnings) for p in parsed_rows)

        # Step 5 — bulk DELETE righe sparite (composizioni cascade via FK)
        if to_delete_ids:
            await session.execute(
                delete(CorsaCommerciale).where(CorsaCommerciale.id.in_(to_delete_ids))
            )

        # Step 6 — INSERT righe nuove + 9 composizioni ciascuna
        # (Sprint 3.7.2 farà bulk; qui per chiarezza algoritmica)
        for parsed, row_hash in to_insert:
            payload = _corsa_payload(parsed, azienda_id, run_id, row_hash)
            ins_result = await session.execute(
                pg_insert(CorsaCommerciale).values(**payload).returning(CorsaCommerciale.id)
            )
            corsa_id = ins_result.scalar_one()
            comp_rows = _composizione_rows(corsa_id, parsed)
            await session.execute(pg_insert(CorsaComposizione).values(comp_rows))

        # Step 7 — INVARIANTE FORTE: post-import COUNT(*) == righe nel file
        # Garanzia "no train left behind": ogni riga del PdE ha una riga in DB.
        n_total_db = await session.scalar(
            select(func.count())
            .select_from(CorsaCommerciale)
            .where(CorsaCommerciale.azienda_id == azienda_id)
        )
        if n_total_db != n_total_file:
            raise RuntimeError(
                f"INVARIANTE FALLITA: corse in DB={n_total_db}, "
                f"righe nel file={n_total_file}. Rollback transazione. "
                f"(diff: kept={n_kept} create={n_create} delete={n_delete})"
            )

        # Step 8 — close run
        await session.execute(
            update(CorsaImportRun)
            .where(CorsaImportRun.id == run_id)
            .values(
                n_corse=n_total_db,
                n_corse_create=n_create,
                n_corse_update=n_delete,  # riusato come "delta deleted" — vedi note
                completed_at=func.now(),
                note=(
                    f"delta-sync: kept={n_kept} delete={n_delete} create={n_create}, "
                    f"warnings={n_warnings} (cross-check Gg_*)"
                ),
            )
        )

        return ImportSummary(
            run_id=run_id,
            n_total=int(n_total_db),
            n_create=n_create,
            n_delete=n_delete,
            n_kept=n_kept,
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
        f"✓ Run ID {summary.run_id}: total={summary.n_total} "
        f"(kept={summary.n_kept} create={summary.n_create} delete={summary.n_delete}), "
        f"warnings={summary.n_warnings}"
    )
    print(f"  durata: {summary.duration_s:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
