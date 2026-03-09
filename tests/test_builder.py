"""Test turn builder automatico."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.db import Database, TrainSegment
from src.turn_builder.auto_builder import AutoBuilder


def setup_test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(db_path=path)

    mt_id = db.insert_material_turn("TEST", "test.pdf", 5)

    segments = [
        TrainSegment(None, "10001", "MILANO CENTRALE", "06:00",
                     "BERGAMO", "07:15", mt_id, 1, 0, 1.0, "", 1),
        TrainSegment(None, "10002", "BERGAMO", "07:45",
                     "BRESCIA", "08:30", mt_id, 1, 1, 1.0, "", 1),
        TrainSegment(None, "10003", "BRESCIA", "09:00",
                     "CREMONA", "09:50", mt_id, 1, 2, 1.0, "", 1),
        TrainSegment(None, "10004", "CREMONA", "10:30",
                     "MILANO CENTRALE", "11:45", mt_id, 1, 3, 1.0, "", 1),
        TrainSegment(None, "10005", "MILANO CENTRALE", "12:30",
                     "MONZA", "13:00", mt_id, 1, 4, 1.0, "", 1),
    ]
    db.bulk_insert_segments(segments)
    return db, path


def test_auto_build_day():
    db, path = setup_test_db()
    builder = AutoBuilder(db, deposito="MILANO CENTRALE")
    summary = builder.build_day(day_index=1)

    assert len(summary.segments) > 0
    assert summary.condotta_min > 0
    assert summary.condotta_min <= 330  # Rispetta vincolo

    db.close()
    os.unlink(path)


def test_auto_build_schedule():
    db, path = setup_test_db()
    builder = AutoBuilder(db, deposito="MILANO CENTRALE")
    calendar = builder.build_schedule(n_workdays=5)

    turns = [e for e in calendar if e["type"] == "TURN"]
    rests = [e for e in calendar if e["type"] == "REST"]
    assert len(turns) == 5
    assert len(rests) == 2  # Un blocco di riposo

    db.close()
    os.unlink(path)


def test_auto_build_empty_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(db_path=path)

    builder = AutoBuilder(db)
    summary = builder.build_day()
    assert len(summary.segments) == 0

    db.close()
    os.unlink(path)


if __name__ == "__main__":
    test_auto_build_day()
    test_auto_build_schedule()
    test_auto_build_empty_db()
    print("All builder tests passed!")
