"""Check integrità grafo migration alembic — Sprint 8.3 S3.

Risponde a una lezione meta dolorosa entry 283: ho assegnato a migration
0046 una revision ID già usata in 0029 → "Cycle is detected in revisions"
→ deploy Railway crashato → rollback automatico → NULLA del piano α
in prod finché non scoperto + hotfix entry 286.

Questo script va lanciato PRIMA di ogni commit con migration alembic
nuove. Verifica:

1. Nessuna ``revision: str = "..."`` duplicata fra file diversi.
2. Ogni ``down_revision`` (eccetto la base ``None``) deve puntare a una
   ``revision`` esistente in qualche altro file.
3. Esiste **1 sola head** (file con ``revision`` mai citata come
   ``down_revision`` di altri).
4. Nessun ciclo nel grafo (DFS).

Uso CLI:

.. code-block:: bash

    uv run python backend/scripts/check_alembic_revisions.py
    # Exit 0 se OK, exit 1 se problemi rilevati.

Integrazione futura: aggiungere a ``.pre-commit-config.yaml`` quando
verrà introdotto il framework ``pre-commit``, o a CI GitHub Actions.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

VERSIONS_DIR = (
    Path(__file__).resolve().parent.parent / "alembic" / "versions"
)

_REVISION_RE = re.compile(
    r'^revision\s*(?::\s*str)?\s*=\s*"([^"]+)"', re.MULTILINE
)
_DOWN_REVISION_RE = re.compile(
    r'^down_revision\s*(?::\s*[^=]*)?\s*=\s*"([^"]+)"', re.MULTILINE
)


def parse_migration(path: Path) -> tuple[str, str | None]:
    """Estrae (revision, down_revision) da un file migration.

    Returns:
        Tupla (revision, down_revision). ``down_revision`` può essere
        ``None`` per la base.

    Raises:
        ValueError: se il file non ha ``revision: str = "..."``.
    """
    content = path.read_text()
    rev_match = _REVISION_RE.search(content)
    if rev_match is None:
        raise ValueError(f"{path.name}: missing 'revision: str = \"...\"'")
    revision = rev_match.group(1)
    down_match = _DOWN_REVISION_RE.search(content)
    down_revision = down_match.group(1) if down_match else None
    return revision, down_revision


def check_no_duplicate_revisions(
    parsed: list[tuple[Path, str, str | None]],
) -> list[str]:
    """Verifica che nessuna revision sia duplicata."""
    by_revision: dict[str, list[Path]] = {}
    for path, rev, _ in parsed:
        by_revision.setdefault(rev, []).append(path)
    errors: list[str] = []
    for rev, paths in by_revision.items():
        if len(paths) > 1:
            files = ", ".join(p.name for p in paths)
            errors.append(
                f"DUPLICATE revision '{rev}' in {len(paths)} files: {files}"
            )
    return errors


def check_no_dangling_down_revisions(
    parsed: list[tuple[Path, str, str | None]],
) -> list[str]:
    """Verifica che ogni down_revision punti a una revision esistente."""
    revisions = {rev for _, rev, _ in parsed}
    errors: list[str] = []
    for path, _, down_rev in parsed:
        if down_rev is None:
            continue  # base
        if down_rev not in revisions:
            errors.append(
                f"DANGLING down_revision in {path.name}: '{down_rev}' "
                f"not found in any other migration"
            )
    return errors


def check_single_head(
    parsed: list[tuple[Path, str, str | None]],
) -> list[str]:
    """Verifica che esista 1 sola head (revision non citata come
    down_revision di nessun altro file)."""
    revisions = {rev for _, rev, _ in parsed}
    cited_as_down = {dr for _, _, dr in parsed if dr is not None}
    heads = revisions - cited_as_down
    if len(heads) > 1:
        return [
            "MULTIPLE HEADS detected (1 expected): "
            + ", ".join(sorted(heads))
        ]
    if len(heads) == 0:
        return ["NO HEAD detected (= cycle in graph)"]
    return []


def check_no_cycles(
    parsed: list[tuple[Path, str, str | None]],
) -> list[str]:
    """DFS per detection ciclo nel grafo down_revision → revision."""
    by_revision: dict[str, str | None] = {rev: dr for _, rev, dr in parsed}
    errors: list[str] = []
    for start_rev in by_revision:
        visited: set[str] = set()
        cur: str | None = start_rev
        while cur is not None:
            if cur in visited:
                errors.append(
                    f"CYCLE detected starting from '{start_rev}': "
                    f"reached '{cur}' twice"
                )
                break
            visited.add(cur)
            cur = by_revision.get(cur)
    return list(set(errors))  # de-dup


def main() -> int:
    if not VERSIONS_DIR.is_dir():
        print(f"ERROR: versions dir not found: {VERSIONS_DIR}", file=sys.stderr)
        return 2

    files = sorted(VERSIONS_DIR.glob("*.py"))
    if not files:
        print(f"WARNING: no migration files in {VERSIONS_DIR}")
        return 0

    parsed: list[tuple[Path, str, str | None]] = []
    parse_errors: list[str] = []
    for f in files:
        try:
            rev, down = parse_migration(f)
            parsed.append((f, rev, down))
        except ValueError as e:
            parse_errors.append(str(e))

    all_errors: list[str] = list(parse_errors)
    all_errors.extend(check_no_duplicate_revisions(parsed))
    all_errors.extend(check_no_dangling_down_revisions(parsed))
    all_errors.extend(check_single_head(parsed))
    all_errors.extend(check_no_cycles(parsed))

    if all_errors:
        print("=" * 70)
        print("ALEMBIC MIGRATION CHECK FAILED")
        print("=" * 70)
        for err in all_errors:
            print(f"  ❌ {err}")
        print()
        print(f"Found {len(all_errors)} issue(s) in {len(files)} migrations")
        return 1

    print(f"✅ alembic migrations check passed ({len(files)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
