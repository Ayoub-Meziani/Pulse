"""Step 4: POST/GET /patients/{id}/measurements on the real schema (pulse-v1 trigger, permissions, rules)."""
import sys
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.errors import database_error
from conftest import assign, auth_header, new_user

pytestmark = pytest.mark.db
API = "/api/v1"


def iso(dt):
    return dt.isoformat()


def post(api, patient, who=None, **body):
    body = {"systolic": 120, "diastolic": 80} | body
    return api.post(f"{API}/patients/{patient}/measurements", json=body, headers=auth_header(who or patient))


@pytest.fixture
def patient(conn):
    return new_user(conn, "patient", "Nadia M.")


# ---------------------------------------------------------------- recording and the database's validation
def test_normal_reading_is_stored_with_provenance_and_validated_by_the_database(api, conn, patient):
    r = post(api, patient, systolic=122, diastolic=78, pulse=70, body_position="sitting", arm="left",
             rested_5_min=True, context="before breakfast")
    assert r.status_code == 201, r.text
    m, ev = r.json()["measurement"], r.json()["evaluation"]
    assert (m["source"], m["provenance"], m["method"]) == ("manual", "measured", "unknown")
    assert (m["validation_status"], m["quality_flags"], m["validation_policy_version"]) == ("valid", [], "pulse-v1")
    assert m["measured_tz"] == "Africa/Algiers" and m["rested_5_min"] is True and m["patient_id"] == str(patient)
    assert ev == {"level": "none", "rule_id": None, "reason": "Below target.", "next_step": "Reading saved.",
                  "requires_symptom_check": False, "recheck_after_seconds": None, "show_emergency": False}
    assert r.json()["alert"] is None and r.json()["trend_alert"] is None  # alert persistence = step 5
    row = conn.execute(text("select created_by, systolic, source from public.measurements where id = :id"),
                       {"id": m["id"]}).one()
    assert (row.created_by, row.systolic, row.source) == (patient, 122, "manual")


def test_severe_reading_returns_symptom_check_and_recheck_in_the_same_response(api, patient):
    ev = post(api, patient, systolic=186, diastolic=118).json()["evaluation"]
    assert (ev["level"], ev["rule_id"], ev["requires_symptom_check"], ev["recheck_after_seconds"]) == \
           ("severe", "R-SEV-1", True, 60)
    assert ev["show_emergency"] is False  # emergency comes from the symptom check (R-EMG-1)
    assert "call emergency services" in ev["next_step"]


def test_severe_diastolic_alone_is_severe(api, patient):
    assert post(api, patient, systolic=150, diastolic=120).json()["evaluation"]["rule_id"] == "R-SEV-1"


def test_above_default_target(api, patient):
    ev = post(api, patient, systolic=145, diastolic=85).json()["evaluation"]
    assert ev["level"] == "notice" and "the general target (140/90)" in ev["reason"]


def test_above_doctor_target_uses_the_active_care_plan(api, conn, patient):
    doctor = new_user(conn, "doctor")
    conn.execute(text("insert into public.care_plans (patient_id, clinician_id, effective_from, target_systolic, "
                      "target_diastolic, clinician_guidance) values (:p, :d, current_date, 130, 80, 'Home readings')"),
                 {"p": patient, "d": doctor})
    ev = post(api, patient, systolic=135, diastolic=78).json()["evaluation"]
    assert ev["level"] == "notice" and "your target (130/80)" in ev["reason"]


def test_needs_review_reading_is_still_evaluated_by_the_safety_rules(api, patient):
    r = post(api, patient, systolic=260, diastolic=150).json()   # above 250: unusual, but plausible
    assert r["measurement"]["validation_status"] == "needs_review"
    assert "unusual_value_recheck" in r["measurement"]["quality_flags"]
    assert r["evaluation"]["rule_id"] == "R-SEV-1" and r["evaluation"]["requires_symptom_check"]


def test_invalid_reading_is_stored_flagged_and_not_evaluated(api, patient):
    r = post(api, patient, systolic=120, diastolic=130)
    assert r.status_code == 201
    m, ev = r.json()["measurement"], r.json()["evaluation"]
    assert m["validation_status"] == "invalid" and m["quality_flags"] == ["systolic_not_above_diastolic"]
    assert (ev["level"], ev["rule_id"], ev["requires_symptom_check"]) == ("none", "DATA-INVALID", False)
    assert "top number must be higher" in ev["reason"] and "Urgence" in ev["next_step"]


def test_implausibly_high_reading_still_asks_for_the_symptom_check(api, patient):
    ev = post(api, patient, systolic=310, diastolic=150).json()["evaluation"]
    assert ev["rule_id"] == "DATA-INVALID" and ev["requires_symptom_check"] is True


def test_reading_too_low_to_be_real_is_invalid_but_asks_for_the_symptom_check(api, patient):
    r = post(api, patient, systolic=1, diastolic=1, pulse=1).json()
    m, ev = r["measurement"], r["evaluation"]
    assert m["validation_status"] == "invalid" and "systolic_implausible" in m["quality_flags"]
    assert (ev["level"], ev["rule_id"], ev["requires_symptom_check"]) == ("none", "DATA-INVALID", True)
    assert "too low to be a real measurement" in ev["next_step"] and r["alert"] is None


@pytest.mark.parametrize("s,d,rule,symptom_check", [(85, 55, "R-LOW-1", False), (65, 40, "R-LOW-2", True)])
def test_low_blood_pressure_is_flagged_with_an_alert(api, patient, s, d, rule, symptom_check):
    r = post(api, patient, systolic=s, diastolic=d).json()
    ev = r["evaluation"]
    assert (ev["level"], ev["rule_id"], ev["requires_symptom_check"]) == ("low", rule, symptom_check)
    assert (r["alert"]["level"], r["alert"]["rule_id"]) == ("low", rule)


def test_reading_in_the_future_is_invalid(api, patient):
    r = post(api, patient, measured_at=iso(datetime.now(timezone.utc) + timedelta(hours=1))).json()
    assert r["measurement"]["quality_flags"] == ["measured_in_future"] and r["evaluation"]["rule_id"] == "DATA-INVALID"


def test_retry_of_the_same_reading_is_kept_flagged_and_still_gets_guidance(api, patient):
    at = iso(datetime.now(timezone.utc) - timedelta(minutes=1))
    first = post(api, patient, systolic=190, diastolic=110, measured_at=at).json()
    second = post(api, patient, systolic=190, diastolic=110, measured_at=at).json()
    assert first["measurement"]["validation_status"] == "valid"
    assert second["measurement"]["quality_flags"] == ["possible_duplicate"]
    assert second["measurement"]["id"] != first["measurement"]["id"]
    # a duplicate never suppresses safety guidance ...
    assert second["evaluation"]["level"] == "severe" and second["evaluation"]["requires_symptom_check"]
    # ... but a retry is not a recheck: no alert change, the episode is not marked persistent
    assert second["alert"] is None and first["alert"]["persistent"] is False
    detail = api.get(f"{API}/alerts/{first['alert']['id']}", headers=auth_header(patient)).json()
    assert detail["persistent"] is False and [m["id"] for m in detail["measurements"]] == [first["measurement"]["id"]]


def test_explicit_and_invalid_time_zones(api, patient):
    assert post(api, patient, measured_tz="Europe/Paris").json()["measurement"]["measured_tz"] == "Europe/Paris"
    r = post(api, patient, measured_tz="Mars/Olympus")
    assert r.status_code == 422 and r.json()["error"]["details"][0]["field"] == "measured_tz"


def test_naive_timestamp_is_rejected(api, patient):
    r = post(api, patient, measured_at="2026-10-30T10:00:00")
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"


def test_no_ml_library_is_loaded_by_the_measurement_path(api, patient):
    post(api, patient)
    assert not {"sklearn", "pandas", "numpy", "joblib"} & set(sys.modules)


# ---------------------------------------------------------------- permissions (A8)
@pytest.fixture
def team(conn, patient):
    other, doctor, stranger, former, admin = (new_user(conn, r) for r in
                                               ("patient", "doctor", "doctor", "doctor", "admin"))
    assign(conn, doctor, patient)
    assign(conn, former, patient, status="ended")
    return dict(other=other, doctor=doctor, stranger=stranger, former=former, admin=admin)


@pytest.mark.parametrize("who", ["other", "doctor", "stranger", "former", "admin"])
def test_only_the_patient_can_post(api, patient, team, who):
    r = post(api, patient, who=team[who])
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize("who,status", [("doctor", 200), ("other", 403), ("stranger", 403),
                                        ("former", 403), ("admin", 403)])
def test_reading_access(api, patient, team, who, status):
    post(api, patient)
    r = api.get(f"{API}/patients/{patient}/measurements", headers=auth_header(team[who]))
    assert r.status_code == status


def test_posting_without_a_token_is_401(api, patient):
    r = api.post(f"{API}/patients/{patient}/measurements", json={"systolic": 120, "diastolic": 80})
    assert r.status_code == 401


# ---------------------------------------------------------------- listing
def test_list_newest_first_with_filters_and_invalid_hidden(api, patient):
    now = datetime.now(timezone.utc)
    for days, (s, d) in enumerate([(121, 79), (132, 84), (120, 130), (140, 88)]):
        post(api, patient, systolic=s, diastolic=d, measured_at=iso(now - timedelta(days=days)))
    url = f"{API}/patients/{patient}/measurements"
    h = auth_header(patient)
    default = api.get(url, headers=h).json()
    assert [m["systolic"] for m in default] == [121, 132, 140]          # invalid 120/130 hidden
    assert len(api.get(url, params={"include_invalid": "true"}, headers=h).json()) == 4
    window = api.get(url, params={"from": iso(now - timedelta(days=1, hours=1)), "limit": 1}, headers=h).json()
    assert [m["systolic"] for m in window] == [121]
    assert api.get(url, params={"from": "2026-10-30T10:00:00"}, headers=h).status_code == 422


def test_other_patients_readings_never_leak_into_a_list(api, conn, patient):
    other = new_user(conn)
    post(api, other, systolic=150, diastolic=95)
    assert api.get(f"{API}/patients/{patient}/measurements", headers=auth_header(patient)).json() == []


# ---------------------------------------------------------------- database error mapping
def test_database_errors_map_to_the_error_format_without_values(conn, patient):
    with pytest.raises(IntegrityError) as exc:
        with conn.begin_nested():
            conn.execute(text("insert into public.measurements (patient_id, source, systolic, diastolic, measured_at) "
                              "values (:p, 'manual', 999, 80, now())"), {"p": patient})
    status, code, _, details = database_error(exc.value)
    assert (status, code, details["sqlstate"]) == (422, "validation_failed", "23514")
    assert details["constraint"] == "measurements_systolic_check" and "999" not in str(details)


@pytest.mark.parametrize("body", [{"systolic": 0, "diastolic": 80}, {"systolic": 401, "diastolic": 80},
                                  {"systolic": "high", "diastolic": 80}, {"diastolic": 80}])
def test_with_a_database_invalid_bodies_are_422_before_anything_is_stored(api, conn, patient, body):
    r = api.post(f"{API}/patients/{patient}/measurements", json=body, headers=auth_header(patient))
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"
    assert conn.execute(text("select count(*) from public.measurements where patient_id = :p"),
                        {"p": patient}).scalar_one() == 0
