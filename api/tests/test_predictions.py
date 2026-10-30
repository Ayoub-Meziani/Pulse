"""Step 7: GET /patients/{id}/predictions/latest reads ml_predictions (doctor only, never used by the rules)."""
import sys
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import Settings
from app.main import create_app
from conftest import SUPABASE_URL, TEST_JWKS, assign, auth_header, new_user

pytestmark = pytest.mark.db
API = "/api/v1"
TODAY = datetime.now(timezone(timedelta(hours=1))).date()  # Africa/Algiers is UTC+1 all year


def prediction(conn, patient, *, target_date=None, status="ok", s=142.5, d=88.0, version="mbp-v1",
               interval=(132.2, 152.8, 81.1, 94.9), created_at=None):
    ok = status == "ok"
    lo_s, hi_s, lo_d, hi_d = interval if ok and interval else (None,) * 4
    conn.execute(text(
        "insert into public.ml_predictions (patient_id, target_date, target, status, predicted_systolic, "
        "predicted_diastolic, interval_systolic_low, interval_systolic_high, interval_diastolic_low, "
        "interval_diastolic_high, model_version, trained_on, features_until, n_readings_used, created_at) "
        "values (:p, :t, 'morning_mean_bp', :st, :s, :d, :ls, :hs, :ld, :hd, :v, 'synthetic:pulse-sim-v1', "
        "now(), :n, coalesce(:c, now()))"),
        dict(p=patient, t=target_date or TODAY + timedelta(days=1), st=status, s=s if ok else None,
             d=d if ok else None, ls=lo_s, hs=hi_s, ld=lo_d, hd=hi_d, v=version, n=12 if ok else 3, c=created_at))


@pytest.fixture
def team(conn):
    patient, doctor = new_user(conn, "patient"), new_user(conn, "doctor")
    stranger, former, admin = new_user(conn, "doctor"), new_user(conn, "doctor"), new_user(conn, "admin")
    assign(conn, doctor, patient)
    assign(conn, former, patient, status="ended")
    return dict(patient=patient, doctor=doctor, stranger=stranger, former=former, admin=admin)


def latest(api, team, who="doctor"):
    return api.get(f"{API}/patients/{team['patient']}/predictions/latest", headers=auth_header(team[who]))


def test_no_prediction_is_model_unavailable(api, team):
    r = latest(api, team)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "model_unavailable" and body["predicted_systolic"] is None and body["model_version"] is None
    assert body["limitations"].startswith("Experimental") and "synthetic" in body["limitations"]


def test_valid_prediction_with_interval_and_labels(api, conn, team):
    prediction(conn, team["patient"])
    body = latest(api, team).json()
    assert (body["status"], body["predicted_systolic"], body["predicted_diastolic"]) == ("ok", 142.5, 88.0)
    assert body["interval"] == {"systolic": [132.2, 152.8], "diastolic": [81.1, 94.9]}
    assert (body["model_version"], body["trained_on"], body["target"]) == ("mbp-v1", "synthetic:pulse-sim-v1", "morning_mean_bp")
    assert body["target_date"] == (TODAY + timedelta(days=1)).isoformat() and body["generated_at"]


def test_prediction_for_today_is_still_current(api, conn, team):
    prediction(conn, team["patient"], target_date=TODAY)
    assert latest(api, team).json()["status"] == "ok"


def test_insufficient_history_is_passed_through_without_values(api, conn, team):
    prediction(conn, team["patient"], status="insufficient_history")
    body = latest(api, team).json()
    assert body["status"] == "insufficient_history" and body["predicted_systolic"] is None and body["interval"] is None
    assert body["model_version"] == "mbp-v1"


def test_stale_prediction_is_never_shown_as_current(api, conn, team):
    prediction(conn, team["patient"], target_date=TODAY - timedelta(days=1))
    body = latest(api, team).json()
    assert body["status"] == "model_unavailable" and body["predicted_systolic"] is None and body["target_date"] is None


def test_newest_target_day_then_newest_run_wins(api, conn, team):
    p = team["patient"]
    prediction(conn, p, target_date=TODAY, s=130.0)
    prediction(conn, p, target_date=TODAY + timedelta(days=1), s=150.0,
               created_at=datetime.now(timezone.utc) - timedelta(hours=1))
    assert latest(api, team).json()["predicted_systolic"] == 150.0


def test_prediction_without_interval(api, conn, team):
    prediction(conn, team["patient"], interval=None)
    body = latest(api, team).json()
    assert body["status"] == "ok" and body["interval"] is None


def test_only_the_configured_model_version_is_served(conn, session_factory, team):
    prediction(conn, team["patient"], version="mbp-v2-experimental", s=170.0)
    for version, expected in (("mbp-v1", "model_unavailable"), ("mbp-v2-experimental", "ok")):
        app = create_app(Settings(supabase_url=SUPABASE_URL, jwks=TEST_JWKS, demo_number="+213 555 12 34 56",
                                  ml_model_version=version))
        app.state.session_factory = session_factory
        body = latest(TestClient(app), team).json()
        assert body["status"] == expected


@pytest.mark.parametrize("who,status", [("doctor", 200), ("patient", 403), ("stranger", 403),
                                        ("former", 403), ("admin", 403)])
def test_doctor_only_and_actively_assigned(api, conn, team, who, status):
    prediction(conn, team["patient"])
    assert latest(api, team, who).status_code == status


def test_predictions_never_influence_rules_alerts_or_guidance(api, conn, team):
    p = team["patient"]
    prediction(conn, p, s=210.0, d=125.0, interval=(200.0, 220.0, 120.0, 130.0))  # alarming estimate
    r = api.post(f"{API}/patients/{p}/measurements", json={"systolic": 118, "diastolic": 76}, headers=auth_header(p))
    body = r.json()
    assert body["evaluation"]["level"] == "none" and body["alert"] is None and body["trend_alert"] is None
    assert api.get(f"{API}/patients/{p}/alerts", headers=auth_header(p)).json() == []
    card = api.get(f"{API}/patients/{p}/emergency-card", headers=auth_header(p)).json()
    assert "210" not in str(card) and "predicted" not in str(card)
    assert not {"sklearn", "pandas", "numpy", "joblib"} & set(sys.modules)  # no inference anywhere in the API


def test_measurement_requests_never_write_predictions(api, conn, team):
    p = team["patient"]
    api.post(f"{API}/patients/{p}/measurements", json={"systolic": 150, "diastolic": 95}, headers=auth_header(p))
    assert conn.execute(text("select count(*) from public.ml_predictions where patient_id = :p"),
                        {"p": p}).scalar_one() == 0
