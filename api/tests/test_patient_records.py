"""Read endpoints added for backend integration: symptom reports, devices, wearable samples; and the rule that
simulated readings never feed the clinical trend alert (R-TRD-1)."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from conftest import assign, auth_header, new_user

pytestmark = pytest.mark.db
API = "/api/v1"
NOW = datetime.now(timezone.utc)


@pytest.fixture
def patient(conn):
    return new_user(conn, "patient", "Nadia M.")


@pytest.fixture
def team(conn, patient):
    other, doctor, stranger, former, admin = (new_user(conn, r) for r in
                                               ("patient", "doctor", "doctor", "doctor", "admin"))
    assign(conn, doctor, patient)
    assign(conn, former, patient, status="ended")
    return dict(patient=patient, other=other, doctor=doctor, stranger=stranger, former=former, admin=admin)


def reading(api, patient, s, d, at):
    r = api.post(f"{API}/patients/{patient}/measurements", headers=auth_header(patient),
                 json={"systolic": s, "diastolic": d, "measured_at": at.isoformat()})
    assert r.status_code == 201, r.text
    return r.json()


def simulated(conn, patient, s, d, at):
    conn.execute(text("insert into public.measurements (patient_id, systolic, diastolic, measured_at, source, "
                      "provenance, method) values (:p, :s, :d, :at, 'simulated', 'simulated', 'unknown')"),
                 {"p": patient, "s": s, "d": d, "at": at})


def device(conn, patient, kind="simulator"):
    did = uuid.uuid4()
    conn.execute(text("insert into public.devices (id, patient_id, device_type, bp_capability, label) "
                      "values (:id, :p, :t, :b, :l)"),
                 {"id": did, "p": patient, "t": kind, "b": "simulated" if kind == "simulator" else "none",
                  "l": "Simulated ring" if kind == "simulator" else "Ring"})
    return did


def sample(conn, patient, did, metric, value, unit, at, source="simulated"):
    conn.execute(text("insert into public.wearable_samples (patient_id, device_id, metric, value, unit, measured_at, "
                      "source) values (:p, :d, :m, :v, :u, :at, :s)"),
                 {"p": patient, "d": did, "m": metric, "v": value, "u": unit, "at": at, "s": source})


def alert_count(conn, patient):
    return conn.execute(text("select count(*) from public.alerts where patient_id = :p"), {"p": patient}).scalar()


# ---------------------------------------------------------------- symptom reports
def test_symptom_reports_are_listed_newest_first_without_an_invented_link(api, patient):
    m = reading(api, patient, 185, 125, NOW - timedelta(minutes=5))
    h = auth_header(patient)
    api.post(f"{API}/patients/{patient}/symptom-reports", headers=h,
             json={"symptoms": [], "measurement_id": m["measurement"]["id"]})
    api.post(f"{API}/patients/{patient}/symptom-reports", headers=h, json={"symptoms": ["dizziness", "nausea"]})
    r = api.get(f"{API}/patients/{patient}/symptom-reports", headers=h)
    assert r.status_code == 200
    reports = r.json()
    assert [x["symptoms"] for x in reports] == [["dizziness", "nausea"], []]
    assert all(x["measurement_id"] is None for x in reports)  # B24: the link is not stored
    assert all(x["source"] == "patient_reported" for x in reports)
    assert len(api.get(f"{API}/patients/{patient}/symptom-reports", params={"limit": 1}, headers=h).json()) == 1


def test_listing_symptoms_changes_no_alert(api, conn, patient):
    api.post(f"{API}/patients/{patient}/symptom-reports", headers=auth_header(patient), json={"symptoms": ["chest_pain"]})
    before = alert_count(conn, patient)
    api.get(f"{API}/patients/{patient}/symptom-reports", headers=auth_header(patient))
    assert alert_count(conn, patient) == before


@pytest.mark.parametrize("path", ["symptom-reports", "devices", "wearable-samples"])
@pytest.mark.parametrize("who,status", [("patient", 200), ("doctor", 200), ("other", 403), ("stranger", 403),
                                        ("former", 403), ("admin", 403)])
def test_read_access_matches_the_other_patient_records(api, patient, team, path, who, status):
    r = api.get(f"{API}/patients/{patient}/{path}", headers=auth_header(team[who]))
    assert r.status_code == status


@pytest.mark.parametrize("path", ["symptom-reports", "devices", "wearable-samples"])
def test_reads_without_a_token_are_401(api, patient, path):
    assert api.get(f"{API}/patients/{patient}/{path}").status_code == 401


def test_other_patients_records_never_leak(api, conn, patient):
    other = new_user(conn)
    did = device(conn, other)
    sample(conn, other, did, "spo2", 97, "percent", NOW)
    api.post(f"{API}/patients/{other}/symptom-reports", headers=auth_header(other), json={"symptoms": ["nausea"]})
    h = auth_header(patient)
    for path in ("symptom-reports", "devices", "wearable-samples"):
        assert api.get(f"{API}/patients/{patient}/{path}", headers=h).json() == []


# ---------------------------------------------------------------- devices and wearable samples
def test_a_patient_without_a_wearable_gets_empty_lists_not_errors(api, patient):
    h = auth_header(patient)
    assert api.get(f"{API}/patients/{patient}/devices", headers=h).json() == []
    assert api.get(f"{API}/patients/{patient}/wearable-samples", headers=h).json() == []


def test_devices_and_samples_carry_their_provenance(api, conn, patient):
    ring, real = device(conn, patient), device(conn, patient, kind="wearable")
    sample(conn, patient, ring, "heart_rate", 61, "bpm", NOW - timedelta(hours=3))
    sample(conn, patient, ring, "spo2", 95.5, "percent", NOW - timedelta(hours=2))
    sample(conn, patient, real, "heart_rate", 64, "bpm", NOW - timedelta(hours=1), source="device_sync")
    h = auth_header(patient)
    devices = {d["id"]: d for d in api.get(f"{API}/patients/{patient}/devices", headers=h).json()}
    assert (devices[str(ring)]["is_simulated"], devices[str(ring)]["bp_capability"]) == (True, "simulated")
    assert (devices[str(real)]["is_simulated"], devices[str(real)]["bp_capability"]) == (False, "none")
    samples = api.get(f"{API}/patients/{patient}/wearable-samples", headers=h).json()
    assert [(s["metric"], s["value"], s["source"]) for s in samples] == [
        ("heart_rate", 64.0, "device_sync"), ("spo2", 95.5, "simulated"), ("heart_rate", 61.0, "simulated")]
    url = f"{API}/patients/{patient}/wearable-samples"
    assert [s["value"] for s in api.get(url, params={"metric": "spo2"}, headers=h).json()] == [95.5]
    assert len(api.get(url, params={"device_id": str(ring)}, headers=h).json()) == 2
    assert len(api.get(url, params={"from": (NOW - timedelta(minutes=90)).isoformat()}, headers=h).json()) == 1
    assert api.get(url, params={"metric": "systolic"}, headers=h).status_code == 422


def test_wearable_samples_never_become_readings_or_alerts(api, conn, patient):
    ring = device(conn, patient)
    for minutes in (30, 20, 10):  # values that would alarm anyone if read as vital signs
        sample(conn, patient, ring, "spo2", 80, "percent", NOW - timedelta(minutes=minutes))
        sample(conn, patient, ring, "heart_rate", 170, "bpm", NOW - timedelta(minutes=minutes))
    result = reading(api, patient, 122, 78, NOW)
    assert result["evaluation"]["level"] == "none" and not result["evaluation"]["show_emergency"]
    assert result["alert"] is None and result["trend_alert"] is None and alert_count(conn, patient) == 0
    readings = api.get(f"{API}/patients/{patient}/measurements", headers=auth_header(patient)).json()
    assert [(m["systolic"], m["source"]) for m in readings] == [(122, "manual")]


# ---------------------------------------------------------------- R-TRD-1 ignores simulated readings
def test_simulated_history_alone_never_raises_a_clinical_trend_alert(api, conn, patient):
    for days in range(1, 6):
        simulated(conn, patient, 160, 100, NOW - timedelta(days=days))
    result = reading(api, patient, 150, 95, NOW)
    assert result["evaluation"]["rule_id"] == "R-TGT-1"  # the reading itself is still evaluated
    assert result["trend_alert"] is None
    levels = conn.execute(text("select alert_class from public.alerts where patient_id = :p"), {"p": patient}).scalars()
    assert "above_target_trend" not in list(levels)


def test_simulated_readings_stay_visible_and_labelled(api, conn, patient):
    simulated(conn, patient, 160, 100, NOW - timedelta(days=1))
    reading(api, patient, 150, 95, NOW)
    rows = api.get(f"{API}/patients/{patient}/measurements", headers=auth_header(patient)).json()
    assert [(m["source"], m["provenance"]) for m in rows] == [("manual", "measured"), ("simulated", "simulated")]


def test_measured_readings_still_raise_the_trend_alert(api, conn, patient):
    for days in range(1, 6):
        simulated(conn, patient, 120, 75, NOW - timedelta(days=days))  # low simulated values do not dilute it
    for hours in (50, 26):
        reading(api, patient, 150, 95, NOW - timedelta(hours=hours))
    third = reading(api, patient, 150, 95, NOW)
    assert third["trend_alert"] is not None and third["trend_alert"]["rule_id"] == "R-TRD-1"
