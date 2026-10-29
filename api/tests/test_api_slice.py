"""End-to-end slice: patient reading -> validation -> persistence -> rules -> alert -> doctor view."""
from datetime import timedelta

from conftest import NOW, login

API = "/api/v1"


def pid(client, email):
    return client.ids["patients"][email]


def test_health(client):
    assert client.get(f"{API}/health").json() == {"status": "ok"}


def test_login_rejects_wrong_password(client):
    r = client.post(f"{API}/auth/login", json={"email": "karim@pulse.demo", "password": "nope"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_credentials"


def test_requires_token(client):
    r = client.get(f"{API}/patients/{pid(client, 'karim@pulse.demo')}/measurements")
    assert r.status_code == 401 and r.json()["error"]["code"] == "not_authenticated"


def test_a1_a2_reading_persists_and_doctor_sees_it(client, clock):
    karim = pid(client, "karim@pulse.demo")
    h = login(client, "karim@pulse.demo")
    r = client.post(f"{API}/patients/{karim}/measurements", headers=h,
                    json={"systolic": 152, "diastolic": 94, "pulse": 80, "source": "manual",
                          "context": {"rested_5_min": True, "position": "sitting"}})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["measurement"]["source"] == "manual"
    assert body["measurement"]["validation_status"] == "valid"
    assert body["evaluation"]["level"] == "notice" and body["evaluation"]["rule_id"] == "R-TGT-1"
    assert body["alert"]["level"] == "notice"
    mid = body["measurement"]["id"]

    # A1: persisted (a fresh request returns it)
    listed = client.get(f"{API}/patients/{karim}/measurements?limit=5", headers=h).json()
    assert listed[0]["id"] == mid

    # A2: the assigned doctor sees the same record
    hd = login(client, "amina@pulse.demo")
    patients = client.get(f"{API}/patients", headers=hd).json()
    k = next(p for p in patients if p["id"] == karim)
    assert k["latest_measurement"]["id"] == mid
    doc_list = client.get(f"{API}/patients/{karim}/measurements?limit=1", headers=hd).json()
    assert doc_list[0]["id"] == mid


def test_severe_then_symptom_raises_same_alert_with_audit_trail(client, clock):
    nadia = pid(client, "nadia@pulse.demo")
    h = login(client, "nadia@pulse.demo")
    r = client.post(f"{API}/patients/{nadia}/measurements", headers=h,
                    json={"systolic": 186, "diastolic": 118, "source": "simulated", "source_ref": "demo:crisis"})
    ev = r.json()["evaluation"]
    assert ev["level"] == "severe" and ev["requires_symptom_check"] and ev["recheck_after_seconds"] == 60
    alert_id = r.json()["alert"]["id"]

    clock.t = NOW + timedelta(seconds=90)
    r2 = client.post(f"{API}/patients/{nadia}/measurements", headers=h,
                     json={"systolic": 184, "diastolic": 121, "source": "simulated"})
    assert r2.json()["evaluation"]["rule_id"] == "R-SEV-2"
    assert r2.json()["alert"] == {"id": alert_id, "level": "severe", "rule_id": "R-SEV-1",
                                  "state": "new", "persistent": True}

    r3 = client.post(f"{API}/patients/{nadia}/symptom-reports", headers=h, json={"symptoms": ["chest_pain"]})
    assert r3.status_code == 201
    assert r3.json()["evaluation"]["show_emergency"] is True
    assert r3.json()["alert"]["id"] == alert_id and r3.json()["alert"]["level"] == "emergency"

    detail = client.get(f"{API}/alerts/{alert_id}", headers=h).json()
    assert [e["type"] for e in detail["events"]] == ["state_change", "measurement_attached", "level_raised"]

    # doctor list: Nadia now first (emergency)
    hd = login(client, "amina@pulse.demo")
    assert client.get(f"{API}/patients", headers=hd).json()[0]["id"] == nadia


def test_a4_symptom_with_normal_reading_is_emergency(client):
    samir = pid(client, "samir@pulse.demo")
    h = login(client, "samir@pulse.demo")
    r = client.post(f"{API}/patients/{samir}/symptom-reports", headers=h, json={"symptoms": ["speech_difficulty"]})
    assert r.json()["evaluation"]["level"] == "emergency" and r.json()["alert"]["level"] == "emergency"


def test_invalid_reading_rejected_with_error_format(client):
    karim = pid(client, "karim@pulse.demo")
    h = login(client, "karim@pulse.demo")
    r = client.post(f"{API}/patients/{karim}/measurements", headers=h, json={"systolic": 120, "diastolic": 130})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_failed" and err["details"][0]["code"] == "not_above_diastolic"
    r = client.post(f"{API}/patients/{karim}/measurements", headers=h, json={"systolic": "abc", "diastolic": 80})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"
    r = client.post(f"{API}/patients/{karim}/symptom-reports", headers=h, json={"symptoms": ["made_up"]})
    assert r.status_code == 422


def test_duplicate_external_id_rejected(client):
    karim = pid(client, "karim@pulse.demo")
    h = login(client, "karim@pulse.demo")
    body = {"systolic": 130, "diastolic": 82, "source": "imported", "source_ref": "cuff.csv", "external_id": "row-7"}
    assert client.post(f"{API}/patients/{karim}/measurements", headers=h, json=body).status_code == 201
    r = client.post(f"{API}/patients/{karim}/measurements", headers=h, json=body)
    assert r.status_code == 409 and r.json()["error"]["code"] == "duplicate_measurement"


def test_a8_permissions(client):
    karim = pid(client, "karim@pulse.demo")
    samir = pid(client, "samir@pulse.demo")
    hk = login(client, "karim@pulse.demo")
    hd = login(client, "amina@pulse.demo")
    # patient cannot read another patient
    for path in ("measurements", "summary", "alerts"):
        assert client.get(f"{API}/patients/{samir}/{path}", headers=hk).status_code == 403
    # doctor cannot read an unassigned patient
    assert client.get(f"{API}/patients/{samir}/measurements", headers=hd).status_code == 403
    # doctor cannot write a patient's reading
    r = client.post(f"{API}/patients/{karim}/measurements", headers=hd, json={"systolic": 130, "diastolic": 80})
    assert r.status_code == 403
    # patient cannot use the doctor list
    assert client.get(f"{API}/patients", headers=hk).status_code == 403
    # alert detail is protected too
    samir_alerts = client.post(f"{API}/patients/{samir}/symptom-reports", headers=login(client, "samir@pulse.demo"),
                               json={"symptoms": ["weakness"]}).json()["alert"]["id"]
    assert client.get(f"{API}/alerts/{samir_alerts}", headers=hk).status_code == 403
    assert client.get(f"{API}/alerts/{samir_alerts}", headers=hd).status_code == 403


def test_seed_story_and_summary(client):
    hd = login(client, "amina@pulse.demo")
    patients = client.get(f"{API}/patients", headers=hd).json()
    assert {p["full_name"] for p in patients} == {"Karim B.", "Nadia M.", "Youssef T."}
    youssef = next(p for p in patients if p["full_name"] == "Youssef T.")
    assert youssef["highest_active_alert"] == "severe"
    assert patients[0]["full_name"] == "Youssef T."  # most urgent first
    karim = pid(client, "karim@pulse.demo")
    s = client.get(f"{API}/patients/{karim}/summary", headers=hd).json()
    assert s["trend"] in ("rising", "stable") and s["count_7d"] > 0 and s["target"]["is_default"] is True
    m = client.get(f"{API}/patients/{karim}/measurements?limit=1", headers=hd).json()[0]
    assert m["source"] == "simulated" and m["source_ref"] == "seed:rising"
