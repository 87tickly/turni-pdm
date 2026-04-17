"""Test end-to-end del builder manuale PdC + calendario."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient


def _make_client():
    """Crea un TestClient con DB SQLite temporaneo isolato."""
    fd, tmpdb = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ.pop("DATABASE_URL", None)

    from src.database.db import Database
    # Patch su tutti i moduli dove get_db e' importato staticamente
    import api.deps
    api.deps.get_db = lambda: Database(tmpdb)
    # Anche nei moduli che hanno gia' fatto `from api.deps import get_db`
    try:
        import api.pdc_builder
        api.pdc_builder.get_db = lambda: Database(tmpdb)
    except ImportError:
        pass
    try:
        import api.importers
        api.importers.get_db = lambda: Database(tmpdb)
    except ImportError:
        pass

    from server import app
    return TestClient(app), tmpdb


# ------------------------------------------------------------------
# POST /pdc-turn - creazione turno manuale
# ------------------------------------------------------------------

def test_create_turn_minimal():
    """Crea un turno minimale (solo header, zero giornate)."""
    client, tmpdb = _make_client()
    try:
        r = client.post("/pdc-turn", json={
            "codice": "TEST_C",
            "impianto": "ARONA",
            "profilo": "Condotta",
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "created"
        assert data["codice"] == "TEST_C"
        assert data["turn_id"] > 0

        # Verifica lo vedo in listing
        r = client.get("/pdc-turns")
        assert r.json()["count"] == 1
    finally:
        os.unlink(tmpdb)


def test_create_turn_with_days_and_blocks():
    """Crea un turno completo con 2 giornate e blocchi."""
    client, tmpdb = _make_client()
    try:
        payload = {
            "codice": "MYTURN_C",
            "planning": "99999",
            "impianto": "MILANO",
            "profilo": "Condotta",
            "valid_from": "2026-04-16",
            "valid_to": "2026-12-31",
            "days": [
                {
                    "day_number": 1,
                    "periodicita": "LMXGV",
                    "start_time": "06:00",
                    "end_time": "14:00",
                    "lavoro_min": 480,
                    "condotta_min": 330,
                    "km": 180,
                    "blocks": [
                        {
                            "seq": 0, "block_type": "train",
                            "train_id": "10000",
                            "from_station": "MILANO", "to_station": "BERGAMO",
                            "start_time": "06:30", "end_time": "07:45",
                        },
                        {
                            "seq": 1, "block_type": "meal",
                            "start_time": "11:30", "end_time": "12:00",
                        },
                        {
                            "seq": 2, "block_type": "train",
                            "train_id": "10001",
                            "from_station": "BERGAMO", "to_station": "MILANO",
                            "start_time": "12:30", "end_time": "13:45",
                        },
                    ],
                },
                {
                    "day_number": 2, "periodicita": "D",
                    "is_disponibile": True,
                },
            ],
            "notes": [
                {
                    "train_id": "10000",
                    "periodicita_text": "Circola tutti i giorni",
                    "non_circola_dates": ["2026-12-25"],
                },
            ],
        }
        r = client.post("/pdc-turn", json=payload)
        assert r.status_code == 200, r.text
        turn_id = r.json()["turn_id"]

        # Dettaglio
        r = client.get(f"/pdc-turn/{turn_id}")
        assert r.status_code == 200
        detail = r.json()
        assert detail["turn"]["codice"] == "MYTURN_C"
        assert len(detail["days"]) == 2
        assert len(detail["days"][0]["blocks"]) == 3
        assert detail["days"][0]["blocks"][0]["train_id"] == "10000"
        assert detail["days"][1]["is_disponibile"] == 1
        assert len(detail["notes"]) == 1
    finally:
        os.unlink(tmpdb)


def test_create_turn_rejects_invalid_profilo():
    client, tmpdb = _make_client()
    try:
        r = client.post("/pdc-turn", json={
            "codice": "X_C", "impianto": "MILANO",
            "profilo": "AltroProfilo",  # invalid
        })
        assert r.status_code == 400
        assert "Profilo" in r.json()["detail"]
    finally:
        os.unlink(tmpdb)


def test_create_turn_rejects_invalid_periodicita():
    client, tmpdb = _make_client()
    try:
        r = client.post("/pdc-turn", json={
            "codice": "X_C", "impianto": "MILANO", "profilo": "Condotta",
            "days": [{"day_number": 1, "periodicita": "ZZZZ"}],
        })
        assert r.status_code == 400
        assert "periodicita" in r.json()["detail"].lower()
    finally:
        os.unlink(tmpdb)


def test_create_turn_rejects_duplicate_day():
    client, tmpdb = _make_client()
    try:
        r = client.post("/pdc-turn", json={
            "codice": "X_C", "impianto": "MILANO", "profilo": "Condotta",
            "days": [
                {"day_number": 1, "periodicita": "LMXGV"},
                {"day_number": 1, "periodicita": "LMXGV"},  # duplicate
            ],
        })
        assert r.status_code == 400
        assert "Duplicato" in r.json()["detail"]
    finally:
        os.unlink(tmpdb)


def test_create_turn_rejects_invalid_block_type():
    client, tmpdb = _make_client()
    try:
        r = client.post("/pdc-turn", json={
            "codice": "X_C", "impianto": "MILANO", "profilo": "Condotta",
            "days": [{
                "day_number": 1, "periodicita": "LMXGV",
                "blocks": [{"block_type": "foobar"}],
            }],
        })
        assert r.status_code == 400
    finally:
        os.unlink(tmpdb)


def test_create_turn_missing_required_fields():
    client, tmpdb = _make_client()
    try:
        # manca codice
        r = client.post("/pdc-turn", json={
            "impianto": "MILANO", "profilo": "Condotta",
        })
        assert r.status_code == 422  # pydantic validation
    finally:
        os.unlink(tmpdb)


# ------------------------------------------------------------------
# PUT /pdc-turn/{id} - aggiornamento
# ------------------------------------------------------------------

def test_update_turn_replaces_content():
    client, tmpdb = _make_client()
    try:
        # Crea
        r = client.post("/pdc-turn", json={
            "codice": "ORIG_C", "impianto": "MILANO", "profilo": "Condotta",
            "days": [{"day_number": 1, "periodicita": "LMXGV"}],
        })
        turn_id = r.json()["turn_id"]

        # Aggiorna
        r = client.put(f"/pdc-turn/{turn_id}", json={
            "codice": "NEW_C", "impianto": "TORINO", "profilo": "Scorta",
            "days": [
                {"day_number": 1, "periodicita": "D"},
                {"day_number": 2, "periodicita": "SD"},
            ],
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "updated"
        new_id = data["new_turn_id"]

        # Verifica
        detail = client.get(f"/pdc-turn/{new_id}").json()
        assert detail["turn"]["codice"] == "NEW_C"
        assert detail["turn"]["profilo"] == "Scorta"
        assert len(detail["days"]) == 2

        # Il vecchio turno non deve piu' esistere
        r = client.get(f"/pdc-turn/{turn_id}")
        assert r.status_code == 404
    finally:
        os.unlink(tmpdb)


def test_update_turn_404_if_not_exists():
    client, tmpdb = _make_client()
    try:
        r = client.put("/pdc-turn/99999", json={
            "codice": "X_C", "impianto": "M", "profilo": "Condotta",
        })
        assert r.status_code == 404
    finally:
        os.unlink(tmpdb)


# ------------------------------------------------------------------
# DELETE /pdc-turn/{id}
# ------------------------------------------------------------------

def test_delete_turn_cascades():
    client, tmpdb = _make_client()
    try:
        r = client.post("/pdc-turn", json={
            "codice": "TO_DEL_C", "impianto": "MILANO", "profilo": "Condotta",
            "days": [{
                "day_number": 1, "periodicita": "LMXGV",
                "blocks": [{"block_type": "train", "train_id": "100"}],
            }],
        })
        turn_id = r.json()["turn_id"]

        r = client.delete(f"/pdc-turn/{turn_id}")
        assert r.status_code == 200
        assert r.json()["status"] == "deleted"

        # Verifica 404
        r = client.get(f"/pdc-turn/{turn_id}")
        assert r.status_code == 404
    finally:
        os.unlink(tmpdb)


def test_delete_turn_404_if_not_exists():
    client, tmpdb = _make_client()
    try:
        r = client.delete("/pdc-turn/99999")
        assert r.status_code == 404
    finally:
        os.unlink(tmpdb)


# ------------------------------------------------------------------
# GET /italian-calendar/periodicity
# ------------------------------------------------------------------

def test_calendar_periodicity_normal_monday():
    client, tmpdb = _make_client()
    try:
        r = client.get("/italian-calendar/periodicity", params={"date_str": "2026-04-20"})
        assert r.status_code == 200
        data = r.json()
        assert data["letter"] == "L"
        assert data["weekday"] == "Lunedi'"
        assert data["is_holiday"] is False
        assert data["holiday_name"] is None
    finally:
        os.unlink(tmpdb)


def test_calendar_periodicity_holiday_on_saturday():
    client, tmpdb = _make_client()
    try:
        # 25/04/2026 Liberazione su sabato -> D
        r = client.get("/italian-calendar/periodicity", params={"date_str": "2026-04-25"})
        data = r.json()
        assert data["letter"] == "D"
        assert data["weekday"] == "Sabato"
        assert data["is_holiday"] is True
        assert "Liberazione" in data["holiday_name"]
    finally:
        os.unlink(tmpdb)


def test_calendar_periodicity_easter():
    client, tmpdb = _make_client()
    try:
        r = client.get("/italian-calendar/periodicity", params={"date_str": "2026-04-05"})
        data = r.json()
        assert data["letter"] == "D"
        assert "Pasqua" == data["holiday_name"]
    finally:
        os.unlink(tmpdb)


def test_calendar_periodicity_local_patron():
    client, tmpdb = _make_client()
    try:
        # Sant'Ambrogio 7/12/2026 (lunedi) - solo se local=milano
        r = client.get("/italian-calendar/periodicity",
                       params={"date_str": "2026-12-07"})
        assert r.json()["letter"] == "L"  # senza local = lunedi normale

        r = client.get("/italian-calendar/periodicity",
                       params={"date_str": "2026-12-07", "local": "milano"})
        data = r.json()
        assert data["letter"] == "D"
        assert "Sant'Ambrogio" in data["holiday_name"]
    finally:
        os.unlink(tmpdb)


def test_calendar_periodicity_invalid_date():
    client, tmpdb = _make_client()
    try:
        r = client.get("/italian-calendar/periodicity", params={"date_str": "abc"})
        assert r.status_code == 400
    finally:
        os.unlink(tmpdb)


# ------------------------------------------------------------------
# GET /pdc-turn/{id}/apply-to-date
# ------------------------------------------------------------------

def test_apply_turn_to_date_selects_correct_variant():
    client, tmpdb = _make_client()
    try:
        r = client.post("/pdc-turn", json={
            "codice": "APPLY_C", "impianto": "MILANO", "profilo": "Condotta",
            "days": [
                {"day_number": 1, "periodicita": "LMXGV"},   # feriali
                {"day_number": 1, "periodicita": "SD"},      # weekend
            ],
        })
        turn_id = r.json()["turn_id"]

        # Lunedi 2026-04-20 -> variante LMXGV
        r = client.get(f"/pdc-turn/{turn_id}/apply-to-date",
                       params={"date_str": "2026-04-20"})
        data = r.json()
        assert data["letter"] == "L"
        assert data["match_count"] == 1
        assert data["matches"][0]["periodicita"] == "LMXGV"

        # Domenica 2026-04-19 -> variante SD
        r = client.get(f"/pdc-turn/{turn_id}/apply-to-date",
                       params={"date_str": "2026-04-19"})
        data = r.json()
        assert data["letter"] == "D"
        assert data["match_count"] == 1
        assert data["matches"][0]["periodicita"] == "SD"

        # Liberazione (sabato 25/04) -> D -> SD
        r = client.get(f"/pdc-turn/{turn_id}/apply-to-date",
                       params={"date_str": "2026-04-25"})
        data = r.json()
        assert data["letter"] == "D"
        assert data["is_holiday"] is True
        assert data["match_count"] == 1
        assert data["matches"][0]["periodicita"] == "SD"
    finally:
        os.unlink(tmpdb)


def test_apply_turn_to_date_404_if_no_turn():
    client, tmpdb = _make_client()
    try:
        r = client.get("/pdc-turn/99999/apply-to-date",
                       params={"date_str": "2026-04-20"})
        assert r.status_code == 404
    finally:
        os.unlink(tmpdb)


# ------------------------------------------------------------------
# GET /pdc-builder/lookup-train/{train_id}
# ------------------------------------------------------------------

def test_lookup_train_not_found():
    client, tmpdb = _make_client()
    try:
        r = client.get("/pdc-builder/lookup-train/99999")
        assert r.status_code == 200
        data = r.json()
        assert data["found"] is False
        assert data["train_id"] == "99999"
    finally:
        os.unlink(tmpdb)


def test_lookup_train_found_in_giro_materiale():
    """Lookup di un treno conosciuto nel giro materiale ritorna stazioni e orari."""
    client, tmpdb = _make_client()
    try:
        # Popolo il DB con un treno nel giro materiale
        from src.database.db import Database, TrainSegment
        db = Database(tmpdb)
        mt_id = db.insert_material_turn("1100", "test.pdf", 1)
        seg = TrainSegment(
            id=None, train_id="10600", from_station="MILANO",
            dep_time="06:30", to_station="BERGAMO", arr_time="07:45",
            material_turn_id=mt_id, day_index=1, seq=0, confidence=1.0,
            raw_text="", source_page=1,
        )
        db.insert_segment(seg)
        db.close()

        r = client.get("/pdc-builder/lookup-train/10600")
        assert r.status_code == 200
        data = r.json()
        assert data["found"] is True
        assert data["train_id"] == "10600"
        assert data["from_station"] == "MILANO"
        assert data["to_station"] == "BERGAMO"
        assert data["dep_time"] == "06:30"
        assert data["arr_time"] == "07:45"
        assert data["material_turn_id"] == mt_id
    finally:
        os.unlink(tmpdb)
