"""Step 5: alert episodes, symptom reports (R-EMG-1) and alert transitions on the real schema."""
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from conftest import assign, auth_header, new_user

pytestmark = pytest.mark.db
API = "/api/v1"


def ago(**kw) -> str:
    return (datetime.now(timezone.utc) - timedelta(**kw)).isoformat()


def reading(api, patient, s, d, **body):
    r = api.post(f"{API}/patients/{patient}/measurements", json={"systolic": s, "diastolic": d} | body,
                 headers=auth_header(patient))
    assert r.status_code == 201, r.text
    return r.json()


def symptoms(api, patient, codes, who=None, **body):
    return api.post(f"{API}/patients/{patient}/symptom-reports", json={"symptoms": codes} | body,
                    headers=auth_header(who or patient))


def detail(api, alert_id, who):
    return api.get(f"{API}/alerts/{alert_id}", headers=auth_header(who))


def move(api, alert_id, who, to, note=None):
    body = {"to": to} | ({"note": note} if note is not None else {})
    return api.post(f"{API}/alerts/{alert_id}/transition", json=body, headers=auth_header(who))


@pytest.fixture
def people(conn):
    patient, other = new_user(conn, "patient", "Karim B."), new_user(conn, "patient")
    doctor, stranger, former = (new_user(conn, "doctor") for _ in range(3))
    assign(conn, doctor, patient)
    assign(conn, former, patient, status="ended")
    return dict(patient=patient, other=other, doctor=doctor, stranger=stranger, former=former)


# ---------------------------------------------------------------- the crisis flow (conception demo)
def test_severe_then_red_flag_raises_the_same_alert_to_emergency(api, conn, people):
    p = people["patient"]
    r1 = reading(api, p, 186, 118)
    alert = r1["alert"]
    assert (alert["level"], alert["rule_id"], alert["status"]) == ("severe", "R-SEV-1", "open")

    r2 = symptoms(api, p, ["chest_pain"], measurement_id=r1["measurement"]["id"])
    assert r2.status_code == 201
    ev = r2.json()["evaluation"]
    assert (ev["level"], ev["rule_id"], ev["show_emergency"]) == ("emergency", "R-EMG-1", True)
    assert "Call emergency services now" in ev["next_step"]
    assert r2.json()["alert"]["id"] == alert["id"] and r2.json()["alert"]["level"] == "emergency"

    d = detail(api, alert["id"], people["doctor"]).json()
    assert d["level"] == "emergency" and d["symptom_report_id"] == r2.json()["report"]["id"]
    assert d["measurement_id"] == r1["measurement"]["id"] and "chest pain" in d["reason"]
    # The database audit trail records the creation and the escalation, with the patient as actor.
    rows = conn.execute(text("select action, actor, new_data->>'alert_class' from public.audit_log "
                             "where table_name = 'alerts' and row_id = :id order by changed_at, id"),
                        {"id": alert["id"]}).all()
    assert [(r[0], r[2]) for r in rows] == [("INSERT", "severely_high"), ("UPDATE", "possible_emergency")]
    assert {r[1] for r in rows} == {p}


def test_red_flag_with_normal_blood_pressure_is_an_emergency(api, people):
    p = people["patient"]
    reading(api, p, 118, 76)
    r = symptoms(api, p, ["difficulty_speaking"]).json()
    assert r["evaluation"]["show_emergency"] is True
    assert (r["alert"]["level"], r["alert"]["rule_id"]) == ("emergency", "R-EMG-1")


def test_red_flag_long_after_a_severe_reading_opens_a_new_alert(api, people):
    p = people["patient"]
    old = reading(api, p, 190, 100, measured_at=ago(hours=2))["alert"]
    r = symptoms(api, p, ["weakness"]).json()
    assert r["alert"]["id"] != old["id"] and r["alert"]["rule_id"] == "R-EMG-1"


@pytest.mark.parametrize("codes", [["dizziness", "nausea"], []])
def test_non_red_flag_or_none_is_stored_without_alert(api, conn, people, codes):
    r = symptoms(api, people["patient"], codes)
    assert r.status_code == 201
    body = r.json()
    assert body["evaluation"]["level"] == "none" and body["evaluation"]["show_emergency"] is False
    assert body["alert"] is None and body["report"]["symptoms"] == codes and body["report"]["measurement_id"] is None
    stored = conn.execute(text("select symptoms from public.symptom_reports where id = :id"),
                          {"id": body["report"]["id"]}).scalar_one()
    assert stored == codes  # "none of these" is recorded (M3)


# ---------------------------------------------------------------- repeat readings (episodes)
def test_recheck_still_severe_attaches_and_marks_persistent_then_lower_reading_attaches(api, people):
    p = people["patient"]
    first = reading(api, p, 185, 110, measured_at=ago(minutes=3))
    second = reading(api, p, 188, 112, measured_at=ago(minutes=1))
    assert second["evaluation"]["rule_id"] == "R-SEV-2" and second["alert"]["id"] == first["alert"]["id"]
    assert second["alert"]["persistent"] is True and second["evaluation"]["requires_symptom_check"]
    third = reading(api, p, 150, 92)
    assert third["evaluation"]["rule_id"] == "R-SEV-3" and third["alert"]["id"] == first["alert"]["id"]
    assert "doctor will still see" in third["evaluation"]["next_step"]
    d = detail(api, first["alert"]["id"], p).json()
    assert d["status"] == "open" and len(d["measurements"]) == 3


def test_severe_reading_after_the_recheck_window_opens_a_new_episode(api, people):
    p = people["patient"]
    a = reading(api, p, 185, 110, measured_at=ago(minutes=40))["alert"]
    b = reading(api, p, 186, 111)["alert"]
    assert b["id"] != a["id"] and b["rule_id"] == "R-SEV-1"


def test_one_open_notice_collects_above_target_readings(api, people):
    p = people["patient"]
    a = reading(api, p, 145, 88, measured_at=ago(hours=2))
    b = reading(api, p, 147, 91)
    assert a["alert"]["rule_id"] == "R-TGT-1" and b["alert"]["id"] == a["alert"]["id"]


def test_one_open_low_alert_collects_low_readings_and_the_doctor_sees_it(api, conn, people):
    p = people["patient"]
    a = reading(api, p, 85, 55, measured_at=ago(hours=2))["alert"]
    b = reading(api, p, 82, 54)["alert"]
    assert (a["level"], a["rule_id"]) == ("low", "R-LOW-1") and b["id"] == a["id"]
    assert conn.execute(text("select alert_class from public.alerts where id = :id"),
                        {"id": a["id"]}).scalar() == "follow_up"
    assert [x["level"] for x in api.get(f"{API}/patients/{p}/alerts", headers=auth_header(p)).json()] == ["low"]
    mine = api.get(f"{API}/patients", headers=auth_header(people["doctor"])).json()
    assert [(x["highest_active_alert"], x["active_alert_count"]) for x in mine] == [("low", 1)]


def test_weekly_trend_alert_after_three_readings_above_target(api, people):
    p = people["patient"]
    results = [reading(api, p, 150, 95, measured_at=ago(days=d)) for d in (3, 2, 1)]
    assert results[0]["trend_alert"] is None and results[1]["trend_alert"] is None
    trend = results[2]["trend_alert"]
    assert (trend["level"], trend["rule_id"]) == ("trend", "R-TRD-1")
    again = reading(api, p, 152, 96)
    assert again["trend_alert"]["id"] == trend["id"]


def test_invalid_reading_never_creates_or_changes_alerts(api, people):
    p = people["patient"]
    open_alert = reading(api, p, 185, 110)["alert"]
    r = reading(api, p, 120, 130)
    assert r["alert"] is None and r["trend_alert"] is None
    assert len(detail(api, open_alert["id"], p).json()["measurements"]) == 1


# ---------------------------------------------------------------- alerts list / detail permissions
def test_alert_list_filters_and_permissions(api, people):
    p = people["patient"]
    alert = reading(api, p, 186, 118)["alert"]
    url = f"{API}/patients/{p}/alerts"
    assert [a["id"] for a in api.get(url, headers=auth_header(p)).json()] == [alert["id"]]
    assert api.get(url, headers=auth_header(people["doctor"])).status_code == 200
    for who in ("other", "stranger", "former"):
        assert api.get(url, headers=auth_header(people[who])).status_code == 403
        assert detail(api, alert["id"], people[who]).status_code == 403
    assert detail(api, uuid.uuid4(), p).status_code == 404


# ---------------------------------------------------------------- transitions
def test_full_lifecycle_of_a_severe_alert(api, people):
    p, doc = people["patient"], people["doctor"]
    alert_id = reading(api, p, 186, 118)["alert"]["id"]
    plain = move(api, alert_id, p, "acknowledged")  # a patient confirms severe alerts with the password
    assert plain.status_code == 403 and plain.json()["error"]["code"] == "password_confirmation_required"
    ack = move(api, alert_id, doc, "acknowledged")
    assert ack.status_code == 200 and ack.json()["status"] == "acknowledged" and ack.json()["acknowledged_at"]
    assert move(api, alert_id, doc, "reviewed").json()["status"] == "reviewed"
    no_note = move(api, alert_id, doc, "resolved")
    assert no_note.status_code == 422 and no_note.json()["error"]["details"][0]["field"] == "note"
    done = move(api, alert_id, doc, "resolved", note="Called the patient; follow-up visit booked.")
    assert done.json()["status"] == "resolved" and done.json()["resolution_note"].startswith("Called")
    assert api.get(f"{API}/patients/{p}/alerts", headers=auth_header(p)).json() == []          # no longer active
    assert len(api.get(f"{API}/patients/{p}/alerts", params={"status": "all"}, headers=auth_header(p)).json()) == 1
    again = move(api, alert_id, p, "acknowledged")
    assert again.status_code == 409 and again.json()["error"]["code"] == "invalid_transition"


def test_notice_can_be_resolved_without_note(api, people):
    alert_id = reading(api, people["patient"], 145, 88)["alert"]["id"]
    move(api, alert_id, people["doctor"], "reviewed")
    assert move(api, alert_id, people["doctor"], "resolved").json()["status"] == "resolved"


@pytest.mark.parametrize("who,to,status", [
    ("patient", "reviewed", 403), ("patient", "resolved", 409),  # resolve needs reviewed first
    ("stranger", "acknowledged", 403), ("former", "reviewed", 403), ("other", "acknowledged", 403),
    ("doctor", "acknowledged", 200),
])
def test_transition_permissions(api, people, who, to, status):
    alert_id = reading(api, people["patient"], 186, 118)["alert"]["id"]
    assert move(api, alert_id, people[who], to).status_code == status


def test_note_is_refused_when_it_cannot_be_stored(api, people):
    alert_id = reading(api, people["patient"], 145, 88)["alert"]["id"]
    r = move(api, alert_id, people["patient"], "acknowledged", note="seen")
    assert r.status_code == 422 and r.json()["error"]["details"][0]["code"] == "not_stored"


# ---------------------------------------------------------------- symptom report validation and permissions
def test_symptom_link_to_another_patients_reading_is_refused(api, people):
    foreign = reading(api, people["other"], 120, 80)["measurement"]["id"]
    r = symptoms(api, people["patient"], ["chest_pain"], measurement_id=foreign)
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_reference"


def test_symptom_onset_in_the_future_is_refused(api, people):
    r = symptoms(api, people["patient"], ["dizziness"], onset_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat())
    assert r.status_code == 422


@pytest.mark.parametrize("who", ["doctor", "other", "stranger"])
def test_only_the_patient_reports_symptoms(api, people, who):
    assert symptoms(api, people["patient"], ["chest_pain"], who=people[who]).status_code == 403


def test_emergency_path_loads_no_ml_library(api, people):
    symptoms(api, people["patient"], ["chest_pain"])
    assert not {"sklearn", "pandas", "numpy", "joblib"} & set(sys.modules)
