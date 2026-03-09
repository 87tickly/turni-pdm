"""Test database SQLite."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.db import Database, TrainSegment


def get_test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return Database(db_path=path), path


def test_create_tables():
    db, path = get_test_db()
    assert db.segment_count() == 0
    db.close()
    os.unlink(path)


def test_insert_and_query_segment():
    db, path = get_test_db()

    mt_id = db.insert_material_turn("1001", "test.pdf", 1)
    assert mt_id > 0

    seg = TrainSegment(
        id=None,
        train_id="10020",
        from_station="MILANO CENTRALE",
        dep_time="06:30",
        to_station="BERGAMO",
        arr_time="07:45",
        material_turn_id=mt_id,
        day_index=1,
        seq=0,
        confidence=1.0,
        raw_text="test raw",
        source_page=1,
    )
    seg_id = db.insert_segment(seg)
    assert seg_id > 0
    assert db.segment_count() == 1

    # Query treno
    results = db.query_train("10020")
    assert len(results) == 1
    assert results[0]["from_station"] == "MILANO CENTRALE"
    assert results[0]["arr_time"] == "07:45"

    # Query stazione partenze
    deps = db.query_station_departures("MILANO CENTRALE")
    assert len(deps) == 1

    # Query stazione arrivi
    arrs = db.query_station_arrivals("BERGAMO")
    assert len(arrs) == 1

    db.close()
    os.unlink(path)


def test_bulk_insert():
    db, path = get_test_db()
    mt_id = db.insert_material_turn("2001", "test2.pdf", 3)

    segments = [
        TrainSegment(None, "20001", "MILANO ROGOREDO", "05:00",
                     "BRESCIA", "06:20", mt_id, 1, 0, 1.0, "", 1),
        TrainSegment(None, "20002", "BRESCIA", "06:40",
                     "CREMONA", "07:30", mt_id, 1, 1, 1.0, "", 1),
        TrainSegment(None, "20003", "CREMONA", "08:00",
                     "MILANO ROGOREDO", "09:10", mt_id, 1, 2, 1.0, "", 1),
    ]
    db.bulk_insert_segments(segments)
    assert db.segment_count() == 3

    # Query treno specifico
    r = db.query_train("20002")
    assert len(r) == 1
    assert r[0]["from_station"] == "BRESCIA"

    db.close()
    os.unlink(path)


def test_segment_duration():
    seg = TrainSegment(
        None, "100", "A", "06:00", "B", "07:30",
        None, 0, 0, 1.0, "", 1,
    )
    assert seg.duration_min == 90

    # Attraversamento mezzanotte
    seg2 = TrainSegment(
        None, "101", "A", "23:30", "B", "00:30",
        None, 0, 0, 1.0, "", 1,
    )
    assert seg2.duration_min == 60


def test_clear_all():
    db, path = get_test_db()
    mt_id = db.insert_material_turn("3001", "test3.pdf")
    seg = TrainSegment(
        None, "30001", "A", "06:00", "B", "07:00",
        mt_id, 0, 0, 1.0, "", 1,
    )
    db.insert_segment(seg)
    assert db.segment_count() == 1

    db.clear_all()
    assert db.segment_count() == 0

    db.close()
    os.unlink(path)


if __name__ == "__main__":
    test_create_tables()
    test_insert_and_query_segment()
    test_bulk_insert()
    test_segment_duration()
    test_clear_all()
    print("All database tests passed!")
