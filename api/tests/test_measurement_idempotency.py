"""Repeat-safe POST /patients/{id}/measurements with a client-generated id (sequential and concurrent retries)."""
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from conftest import SUPABASE_URL, TEST_JWKS, assign, auth_header, new_user

pytestmark = pytest.mark.db
API = "/api/v1"


def post(api, patient, who=None, **body):
    body = {"systolic": 120, "diastolic": 80} | body
    return api.post(f"{API}/patients/{patient}/measurements", json=body, headers=auth_header(who or patient))


def rows(conn, rid):
    return conn.execute(text("select count(*) from public.measurements where id = :id"), {"id": rid}).scalar()


def alerts_of(conn, patient):
    return conn.execute(text("select count(*) from public.alerts where patient_id = :p"), {"p": patient}).scalar()


@pytest.fixture
def patient(conn):
    return new_user(conn, "patient", "Nadia M.")


# ---------------------------------------------------------------- sequential retries (test transaction)
def test_without_an_id_nothing_changes(api, patient):
    r = post(api, patient)
    assert r.status_code == 201 and r.json()["measurement"]["id"]


def test_retry_with_the_same_id_returns_the_stored_reading_and_changes_no_alert(api, conn, patient):
    rid, at = str(uuid.uuid4()), (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    first = post(api, patient, id=rid, systolic=185, diastolic=125, measured_at=at)
    assert first.status_code == 201, first.text
    alerts_before = alerts_of(conn, patient)
    second = post(api, patient, id=rid, systolic=185, diastolic=125, measured_at=at)
    assert second.status_code == 200, second.text
    a, b = first.json(), second.json()
    assert b["measurement"] == a["measurement"] and b["measurement"]["quality_flags"] == []  # no duplicate row
    assert b["evaluation"] == a["evaluation"] and a["evaluation"]["rule_id"] == "R-SEV-1"  # not a recheck
    assert b["alert"] == a["alert"] and a["alert"]["level"] == "severe"
    assert rows(conn, rid) == 1 and alerts_of(conn, patient) == alerts_before


def test_retry_of_an_attached_recheck_replays_the_recheck(api, conn, patient):
    now = datetime.now(timezone.utc)
    post(api, patient, systolic=186, diastolic=110, measured_at=(now - timedelta(minutes=3)).isoformat())
    rid, at = str(uuid.uuid4()), (now - timedelta(minutes=1)).isoformat()
    first = post(api, patient, id=rid, systolic=184, diastolic=112, measured_at=at).json()
    second = post(api, patient, id=rid, systolic=184, diastolic=112, measured_at=at)
    assert second.status_code == 200
    assert first["evaluation"]["rule_id"] == "R-SEV-2" and second.json()["evaluation"] == first["evaluation"]
    assert second.json()["alert"] == first["alert"]


def test_retry_without_measured_at_matches_the_stored_reading(api, conn, patient):
    rid = str(uuid.uuid4())
    assert post(api, patient, id=rid).status_code == 201
    assert post(api, patient, id=rid).status_code == 200 and rows(conn, rid) == 1


def test_retry_of_an_invalid_reading_replays_data_invalid(api, conn, patient):
    rid = str(uuid.uuid4())
    first = post(api, patient, id=rid, systolic=80, diastolic=90).json()
    second = post(api, patient, id=rid, systolic=80, diastolic=90)
    assert second.status_code == 200 and second.json()["evaluation"] == first["evaluation"]
    assert first["evaluation"]["rule_id"] == "DATA-INVALID"


def test_same_id_with_other_values_is_409_and_nothing_changes(api, conn, patient):
    rid = str(uuid.uuid4())
    post(api, patient, id=rid, systolic=130, diastolic=85)
    r = post(api, patient, id=rid, systolic=131, diastolic=85)
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"
    assert "130" not in r.text and rows(conn, rid) == 1


def test_another_patients_id_is_409_and_never_reveals_their_reading(api, conn, patient):
    other = new_user(conn, "patient", "Other")
    rid = str(uuid.uuid4())
    post(api, other, id=rid, systolic=150, diastolic=95)
    r = post(api, patient, id=rid, systolic=150, diastolic=95)
    assert r.status_code == 409 and str(other) not in r.text and "150" not in r.text


def test_an_id_still_requires_the_patients_own_access(api, conn, patient):
    doctor = new_user(conn, "doctor", "Dr")
    assign(conn, doctor, patient)
    r = post(api, patient, who=doctor, id=str(uuid.uuid4()))
    assert r.status_code == 403


# ---------------------------------------------------------------- concurrent retries (committed data)
@pytest.fixture
def committed(engine):
    """App on real committed transactions, so two requests really race. Cleans up its own patient."""
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app
    with engine.begin() as c:
        patient = new_user(c, "patient", "Race Test")
    app = create_app(Settings(supabase_url=SUPABASE_URL, jwks=TEST_JWKS, demo_number="+213 555 12 34 56"))
    app.state.session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield app, TestClient, patient
    with engine.begin() as c:
        c.execute(text("delete from auth.users where id = :id"), {"id": patient})


def test_two_simultaneous_requests_with_one_id_store_one_reading_and_one_alert(engine, committed):
    app, client, patient = committed
    rid, at = str(uuid.uuid4()), (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    body = {"id": rid, "systolic": 190, "diastolic": 125, "measured_at": at}
    gate, results = threading.Barrier(2), []

    def send():
        c = client(app)
        gate.wait()
        results.append(c.post(f"{API}/patients/{patient}/measurements", json=body, headers=auth_header(patient)))

    threads = [threading.Thread(target=send) for _ in range(2)]
    [t.start() for t in threads]
    [t.join(120) for t in threads]
    assert not any(t.is_alive() for t in threads), "a request never finished"
    assert sorted(r.status_code for r in results) == [200, 201], [r.text for r in results]
    assert len({r.json()["measurement"]["id"] for r in results}) == 1
    assert len({r.json()["alert"]["id"] for r in results}) == 1
    with engine.connect() as c:
        assert rows(c, rid) == 1 and alerts_of(c, patient) == 1


def test_a_request_racing_an_uncommitted_insert_waits_and_replays(engine, committed):
    """Deterministic race: another transaction holds the same id uncommitted; the API insert must wait on the
    primary key, then return the committed reading instead of an error or a second row."""
    app, client, patient = committed
    rid, at = uuid.uuid4(), datetime.now(timezone.utc) - timedelta(minutes=1)
    holder = engine.connect()
    tx = holder.begin()
    holder.execute(text("insert into public.measurements (id, patient_id, systolic, diastolic, measured_at, "
                        "source, provenance, method) values (:id, :p, 128, 82, :at, 'manual', 'measured', 'unknown')"),
                   {"id": rid, "p": patient, "at": at})
    result = {}
    worker = threading.Thread(target=lambda: result.update(r=client(app).post(
        f"{API}/patients/{patient}/measurements", headers=auth_header(patient),
        json={"id": str(rid), "systolic": 128, "diastolic": 82, "measured_at": at.isoformat()})))
    worker.start()
    time.sleep(1.5)
    assert worker.is_alive(), "the request should be waiting on the uncommitted row"
    tx.commit()
    holder.close()
    worker.join(120)
    assert not worker.is_alive(), "the request never finished"
    r = result["r"]
    assert r.status_code == 200, r.text
    assert r.json()["measurement"]["id"] == str(rid) and r.json()["measurement"]["quality_flags"] == []
    with engine.connect() as c:
        assert rows(c, rid) == 1
