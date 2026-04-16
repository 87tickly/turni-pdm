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


def test_pdc_schema_v2_crud():
    """Turni PdC schema v2: insert + query + clear."""
    db, path = get_test_db()

    # Insert turno
    turn_id = db.insert_pdc_turn(
        codice="AROR_C", planning="65053", impianto="ARONA",
        profilo="Condotta", valid_from="2026-02-23",
        valid_to="2026-12-12", source_file="test.pdf",
    )
    assert turn_id > 0

    # Insert giornata (LMXGVSD)
    day_id = db.insert_pdc_turn_day(
        pdc_turn_id=turn_id, day_number=1, periodicita="LMXGVSD",
        start_time="18:20", end_time="00:25",
        lavoro_min=365, condotta_min=202, km=184,
        notturno=True, riposo_min=945, is_disponibile=False,
    )
    assert day_id > 0

    # Insert blocchi vari
    blocks = [
        ("coach_transfer", "", "2434", "ARON", "DOMO", "17:25", "18:04", False),
        ("meal", "", "", "DOMO", "", "18:40", "19:07", False),
        ("cv_partenza", "2434", "", "DOMO", "", "19:20", "", False),
        ("train", "10243", "", "DOMO", "Mlpg", "19:20", "22:24", False),
        ("train", "10246", "", "Mlpg", "ARON", "22:40", "23:45", True),  # accessori maggiorati
    ]
    for i, (bt, tr, vet, fr, to, st, et, acc) in enumerate(blocks):
        bid = db.insert_pdc_block(
            pdc_turn_day_id=day_id, seq=i, block_type=bt,
            train_id=tr, vettura_id=vet,
            from_station=fr, to_station=to,
            start_time=st, end_time=et, accessori_maggiorati=acc,
        )
        assert bid > 0

    # Insert giornata "Disponibile"
    disp_id = db.insert_pdc_turn_day(
        pdc_turn_id=turn_id, day_number=6, periodicita="LMXGVSD",
        is_disponibile=True, riposo_min=864,
    )
    assert disp_id > 0

    # Insert note periodicita' treno
    pt_id = db.insert_pdc_train_periodicity(
        pdc_turn_id=turn_id, train_id="10226",
        periodicita_text="Circola il sabato e la domenica",
        non_circola_dates=["2025-12-27", "2026-01-03"],
        circola_extra_dates=["2025-12-25"],
    )
    assert pt_id > 0

    # Query: stats
    stats = db.get_pdc_stats()
    assert stats["loaded"] is True
    assert stats["turni"] == 1
    assert stats["days"] == 2  # giorno 1 + giorno 6 disponibile
    assert stats["blocks"] == 5
    assert stats["trains"] == 2  # 10243, 10246
    assert stats["impianti"] == ["ARONA"]

    # Query: lista turni
    turns = db.list_pdc_turns(impianto="ARONA")
    assert len(turns) == 1
    assert turns[0]["codice"] == "AROR_C"

    # Query: giornate del turno
    days = db.get_pdc_turn_days(turn_id)
    assert len(days) == 2

    # Query: blocchi della giornata 1
    day1_blocks = db.get_pdc_blocks(day_id)
    assert len(day1_blocks) == 5
    assert day1_blocks[0]["block_type"] == "coach_transfer"
    assert day1_blocks[0]["vettura_id"] == "2434"
    assert day1_blocks[4]["accessori_maggiorati"] == 1  # pallino nero

    # Query: find by train
    found = db.find_pdc_train("10243")
    assert len(found) == 1
    assert found[0]["codice"] == "AROR_C"
    assert found[0]["day_number"] == 1

    found_none = db.find_pdc_train("99999")
    assert found_none == []

    # Query: periodicita' treni
    periodicity = db.get_pdc_train_periodicity(turn_id)
    assert len(periodicity) == 1
    assert periodicity[0]["train_id"] == "10226"
    assert periodicity[0]["non_circola_dates"] == ["2025-12-27", "2026-01-03"]
    assert periodicity[0]["circola_extra_dates"] == ["2025-12-25"]

    # Clear
    db.clear_pdc_data()
    stats_after = db.get_pdc_stats()
    assert stats_after["loaded"] is False
    assert stats_after["turni"] == 0

    db.close()
    os.unlink(path)


def test_pdc_old_tables_are_dropped():
    """Le vecchie tabelle scheletro pdc_turno/pdc_prog/pdc_prog_train
    non devono esistere piu' — sostituite da schema v2."""
    import sqlite3
    db, path = get_test_db()
    cur = db.conn.cursor()
    for old_table in ("pdc_turno", "pdc_prog", "pdc_prog_train"):
        try:
            cur.execute(f"SELECT COUNT(*) FROM {old_table}")
            raise AssertionError(f"{old_table} non dovrebbe esistere")
        except sqlite3.OperationalError:
            pass  # atteso: tabella sconosciuta
    db.close()
    os.unlink(path)


if __name__ == "__main__":
    test_create_tables()
    test_insert_and_query_segment()
    test_bulk_insert()
    test_segment_duration()
    test_clear_all()
    test_pdc_schema_v2_crud()
    test_pdc_old_tables_are_dropped()
    print("All database tests passed!")
