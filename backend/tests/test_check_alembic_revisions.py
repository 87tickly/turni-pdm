"""Test script check_alembic_revisions — Sprint 8.3 S3."""

from __future__ import annotations

from pathlib import Path

import pytest

# Import diretto dello script (non modulo, è uno standalone)
import sys

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import check_alembic_revisions as checker  # type: ignore[import-not-found]


def _write_migration(
    tmp_path: Path,
    name: str,
    revision: str,
    down_revision: str | None,
    *,
    typed: bool = True,
) -> Path:
    """Scrive un file migration fittizio in tmp_path."""
    if typed:
        rev_line = f'revision: str = "{revision}"'
        down_line = (
            f'down_revision: str | None = "{down_revision}"'
            if down_revision is not None
            else 'down_revision: str | None = None'
        )
    else:
        rev_line = f'revision = "{revision}"'
        down_line = (
            f'down_revision = "{down_revision}"'
            if down_revision is not None
            else 'down_revision = None'
        )
    p = tmp_path / name
    p.write_text(f'"""mock migration"""\n{rev_line}\n{down_line}\n')
    return p


class TestParseMigration:
    def test_parse_typed_format(self, tmp_path: Path) -> None:
        p = _write_migration(tmp_path, "0001.py", "abc123", "def456", typed=True)
        rev, down = checker.parse_migration(p)
        assert rev == "abc123"
        assert down == "def456"

    def test_parse_untyped_format(self, tmp_path: Path) -> None:
        p = _write_migration(tmp_path, "0001.py", "abc123", "def456", typed=False)
        rev, down = checker.parse_migration(p)
        assert rev == "abc123"
        assert down == "def456"

    def test_parse_base_no_down_revision(self, tmp_path: Path) -> None:
        p = _write_migration(tmp_path, "0001.py", "abc123", None, typed=True)
        rev, down = checker.parse_migration(p)
        assert rev == "abc123"
        assert down is None

    def test_parse_missing_revision_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "broken.py"
        p.write_text('"""no revision here"""\n')
        with pytest.raises(ValueError, match="missing"):
            checker.parse_migration(p)


class TestCheckNoDuplicateRevisions:
    def test_no_duplicates_ok(self, tmp_path: Path) -> None:
        parsed = [
            (tmp_path / "0001.py", "rev_a", None),
            (tmp_path / "0002.py", "rev_b", "rev_a"),
        ]
        assert checker.check_no_duplicate_revisions(parsed) == []

    def test_duplicate_detected(self, tmp_path: Path) -> None:
        # Bug analogo a entry 283: 0046 collideva con 0029
        parsed = [
            (tmp_path / "0029.py", "b7c8d9e0f1a2", None),
            (tmp_path / "0046.py", "b7c8d9e0f1a2", "a6b7c8d9e0f1"),  # DUPLICATE
        ]
        errors = checker.check_no_duplicate_revisions(parsed)
        assert len(errors) == 1
        assert "DUPLICATE revision 'b7c8d9e0f1a2'" in errors[0]
        assert "0029.py" in errors[0]
        assert "0046.py" in errors[0]


class TestCheckNoDanglingDownRevisions:
    def test_no_dangling_ok(self, tmp_path: Path) -> None:
        parsed = [
            (tmp_path / "0001.py", "rev_a", None),
            (tmp_path / "0002.py", "rev_b", "rev_a"),
        ]
        assert checker.check_no_dangling_down_revisions(parsed) == []

    def test_dangling_detected(self, tmp_path: Path) -> None:
        parsed = [
            (tmp_path / "0001.py", "rev_a", None),
            (tmp_path / "0002.py", "rev_b", "FANTASMA"),
        ]
        errors = checker.check_no_dangling_down_revisions(parsed)
        assert len(errors) == 1
        assert "DANGLING" in errors[0]
        assert "FANTASMA" in errors[0]


class TestCheckSingleHead:
    def test_single_head_ok(self, tmp_path: Path) -> None:
        parsed = [
            (tmp_path / "0001.py", "rev_a", None),
            (tmp_path / "0002.py", "rev_b", "rev_a"),
        ]
        assert checker.check_single_head(parsed) == []

    def test_multiple_heads_detected(self, tmp_path: Path) -> None:
        parsed = [
            (tmp_path / "0001.py", "rev_a", None),
            (tmp_path / "0002.py", "rev_b", "rev_a"),
            (tmp_path / "0003.py", "rev_c", "rev_a"),  # branch parallelo
        ]
        errors = checker.check_single_head(parsed)
        assert len(errors) == 1
        assert "MULTIPLE HEADS" in errors[0]
        assert "rev_b" in errors[0]
        assert "rev_c" in errors[0]


class TestCheckNoCycles:
    def test_no_cycle_ok(self, tmp_path: Path) -> None:
        parsed = [
            (tmp_path / "0001.py", "rev_a", None),
            (tmp_path / "0002.py", "rev_b", "rev_a"),
            (tmp_path / "0003.py", "rev_c", "rev_b"),
        ]
        assert checker.check_no_cycles(parsed) == []

    def test_cycle_detected(self, tmp_path: Path) -> None:
        # rev_a → rev_b → rev_c → rev_a (ciclo)
        parsed = [
            (tmp_path / "0001.py", "rev_a", "rev_c"),
            (tmp_path / "0002.py", "rev_b", "rev_a"),
            (tmp_path / "0003.py", "rev_c", "rev_b"),
        ]
        errors = checker.check_no_cycles(parsed)
        assert len(errors) > 0
        assert any("CYCLE" in e for e in errors)


def test_real_alembic_versions_passes() -> None:
    """Smoke test: il check su tutto backend/alembic/versions/ passa."""
    files = sorted(checker.VERSIONS_DIR.glob("*.py"))
    parsed: list[tuple[Path, str, str | None]] = []
    for f in files:
        rev, down = checker.parse_migration(f)
        parsed.append((f, rev, down))
    errors: list[str] = []
    errors.extend(checker.check_no_duplicate_revisions(parsed))
    errors.extend(checker.check_no_dangling_down_revisions(parsed))
    errors.extend(checker.check_single_head(parsed))
    errors.extend(checker.check_no_cycles(parsed))
    assert errors == [], f"Real alembic versions has errors: {errors}"
