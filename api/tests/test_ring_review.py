"""Doctor screens for the ring ML outputs: flags and live early warnings, weekly reports, personal bands."""
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import Settings
from app.main import create_app
from conftest import SUPABASE_URL, TEST_JWKS, assign, auth_header, new_user

pytestmark = pytest.mark.db
API = "/api/v1"
NOW = datetime.now(timezone.utc)


@pytest.fixture
def ring_api(session_factory):
    app = create_app(Settings(supabase_url=SUPABASE_URL, jwks=TEST_JWKS, demo_number="+213 555 12 34 56",
                              serve_ring_ml=True, ml_model_version="mbp-v1.1"))
    app.state.session_factory = session_factory
    return TestClient(app)


@pytest.fixture
def team(conn):
    patient, other = new_user(conn, "patient", "Karim H."), new_user(conn, "patient")
    doctor, colleague, stranger = (new_user(conn, "doctor") for _ in range(3))
    admin = new_user(conn, "admin")
    assign(conn, doctor, patient)
    assign(conn, colleague, patient)
    return dict(patient=patient, other=other, doctor=doctor, colleague=colleague, stranger=stranger, admin=admin)


def flag(conn, patient, kind="early_warning", metric="spo2", window_kind="forecast", minutes=10, value=93.1,
         score=0.82, basis="forecast:live-v1:reference:spo2<94:limit=94:P(cross<20min)", model="live-v1"):
    start = NOW - timedelta(minutes=minutes)
    return conn.execute(text(
        "insert into public.wearable_flags (patient_id, metric, kind, window_kind, window_start, window_end, value, "
        "score, reference_basis, model_version) values (:p, :m, :k, :w, :s, :e, :v, :sc, :b, :mv) returning id"),
        {"p": patient, "m": metric, "k": kind, "w": window_kind, "s": start, "e": start + timedelta(minutes=20),
         "v": value, "sc": score, "b": basis, "mv": model}).scalar_one()


def report(conn, patient, mbp_model="mbp-v1.1", target=None):
    summary = {"bp_home": {"valid_readings": 12, "mean_systolic": 141.2, "mean_diastolic": 88.0},
               "ring": {"flags": [{"kind": "early_warning", "review_status": "open", "count": 1}]},
               "reference": "home-BP category: ...; reviewed by the team's medical mentor",
               "mbp_estimate": {"target_date": (target or date.today() + timedelta(days=1)).isoformat(),
                                "systolic": 139.0, "diastolic": 87.0}}
    return conn.execute(text(
        "insert into public.weekly_reports (patient_id, week_start, home_bp_category, control_status, "
        "next_week_above_target_prob, model_versions, summary) values (:p, date '2026-10-19', 'stage_1_range', "
        "'above_target', 0.712, cast(:mv as jsonb), cast(:s as jsonb)) returning id"),
        {"p": patient, "mv": f'{{"mbp": "{mbp_model}", "ring": "ring-v1.1"}}',
         "s": __import__("json").dumps(summary)}).scalar_one()


def band(conn, patient, status="proposed", low=55, high=65, doctor=None):
    active = status == "active"
    return conn.execute(text(
        "insert into public.patient_bands (patient_id, metric, statistic, low, high, basis, status, "
        "proposed_model_version, approved_by, approved_at, effective_from) values (:p, 'heart_rate', 'night_median', "
        ":lo, :hi, 'model_proposal', :st, 'ring-v1.1', :d, case when :a then now() end, "
        "case when :a then current_date end) returning id"),
        {"p": patient, "lo": low, "hi": high, "st": status, "d": doctor if active else None, "a": active}).scalar_one()


# ---------------------------------------------------------------- switch and access
def test_off_by_default(api, conn, team):
    r = api.get(f"{API}/patients/{team['patient']}/wearable-flags", headers=auth_header(team["doctor"]))
    assert r.status_code == 404 and r.json()["error"]["code"] == "feature_disabled"


@pytest.mark.parametrize("who", ["patient", "other", "stranger", "admin"])
@pytest.mark.parametrize("path", ["wearable-flags", "weekly-reports", "bands"])
def test_only_the_assigned_doctor_reads(ring_api, team, who, path):
    r = ring_api.get(f"{API}/patients/{team['patient']}/{path}", headers=auth_header(team[who]))
    assert r.status_code == 403


# ---------------------------------------------------------------- flags and live early warnings
def test_doctor_sees_early_warnings_and_flags_newest_first(ring_api, conn, team):
    p = team["patient"]
    flag(conn, p, kind="outside_reference", metric="spo2", window_kind="live_10min", minutes=2, value=92.8,
         score=None, basis="reference:spo2", model="ring-v1")
    flag(conn, p, minutes=12)
    flag(conn, p, kind="multivariate_anomaly", metric="multivariate", window_kind="night", minutes=600, value=None,
         score=1.9, basis="isolation_forest:personal_z", model="ring-v1.1")
    rows = ring_api.get(f"{API}/patients/{p}/wearable-flags", headers=auth_header(team["doctor"])).json()
    assert [r["kind"] for r in rows] == ["outside_reference", "early_warning", "multivariate_anomaly"]
    ew = rows[1]
    assert (ew["window_kind"], ew["value"], ew["score"], ew["review_status"]) == ("forecast", 93.1, 0.82, "open")
    assert "never an alert" in ew["limitations"].lower()
    only = ring_api.get(f"{API}/patients/{p}/wearable-flags?kind=early_warning", headers=auth_header(team["doctor"]))
    assert [r["kind"] for r in only.json()] == ["early_warning"]


def test_flag_review_first_reviewer_stands(ring_api, conn, team):
    fid = flag(conn, team["patient"])
    r = ring_api.post(f"{API}/wearable-flags/{fid}/review", headers=auth_header(team["doctor"]),
                      json={"review_status": "confirmed", "review_note": "  called the patient  "})
    assert r.status_code == 200
    assert (r.json()["review_status"], r.json()["review_note"]) == ("confirmed", "called the patient")
    assert r.json()["reviewed_at"] is not None
    other = ring_api.post(f"{API}/wearable-flags/{fid}/review", headers=auth_header(team["colleague"]),
                          json={"review_status": "dismissed"})
    assert other.status_code == 409 and other.json()["error"]["code"] == "already_reviewed"
    again = ring_api.post(f"{API}/wearable-flags/{fid}/review", headers=auth_header(team["doctor"]),
                          json={"review_status": "dismissed"})
    assert again.status_code == 200 and again.json()["review_status"] == "dismissed"
    stranger = ring_api.post(f"{API}/wearable-flags/{fid}/review", headers=auth_header(team["stranger"]),
                             json={"review_status": "dismissed"})
    assert stranger.status_code == 403


# ---------------------------------------------------------------- weekly reports
def test_report_hides_the_reference_line_and_shows_only_a_served_current_estimate(ring_api, conn, team):
    report(conn, team["patient"])
    r = ring_api.get(f"{API}/patients/{team['patient']}/weekly-reports", headers=auth_header(team["doctor"]))
    rep = r.json()[0]
    assert "reference" not in rep["summary"] and rep["summary"]["mbp_estimate"]["systolic"] == 139.0
    assert (rep["control_status"], rep["next_week_above_target_prob"], rep["status"]) == ("above_target", 0.712, "ready")


@pytest.mark.parametrize("model,target", [("mbp-v1", None), ("mbp-v1.1", date.today() - timedelta(days=3))])
def test_report_never_shows_an_unserved_or_old_estimate(ring_api, conn, team, model, target):
    report(conn, team["patient"], mbp_model=model, target=target)
    rep = ring_api.get(f"{API}/patients/{team['patient']}/weekly-reports", headers=auth_header(team["doctor"])).json()[0]
    assert rep["summary"]["mbp_estimate"] is None


def test_report_review(ring_api, conn, team):
    rid = report(conn, team["patient"])
    r = ring_api.post(f"{API}/weekly-reports/{rid}/review", headers=auth_header(team["doctor"]),
                      json={"doctor_comment": "Discussed at the visit"})
    assert r.status_code == 200
    assert (r.json()["status"], r.json()["doctor_comment"]) == ("reviewed", "Discussed at the visit")
    other = ring_api.post(f"{API}/weekly-reports/{rid}/review", headers=auth_header(team["colleague"]), json={})
    assert other.status_code == 409


# ---------------------------------------------------------------- personal bands
def test_approve_edited_band_supersedes_the_active_one(ring_api, conn, team):
    p, d = team["patient"], team["doctor"]
    old = band(conn, p, status="active", low=50, high=70, doctor=d)
    new = band(conn, p, low=55, high=65)
    listed = ring_api.get(f"{API}/patients/{p}/bands", headers=auth_header(d)).json()
    assert [b["status"] for b in listed] == ["proposed", "active"]
    r = ring_api.post(f"{API}/bands/{new}/approve", headers=auth_header(d), json={"low": 54, "high": 66})
    assert r.status_code == 200, r.text
    b = r.json()
    assert (b["status"], b["low"], b["high"], b["basis"], b["supersedes_id"]) == ("active", 54.0, 66.0, "doctor",
                                                                                    str(old))
    assert conn.execute(text("select status from public.patient_bands where id = :i"), {"i": old}).scalar_one() == \
        "superseded"
    again = ring_api.post(f"{API}/bands/{new}/approve", headers=auth_header(d), json={})
    assert again.status_code == 409 and again.json()["error"]["code"] == "invalid_transition"


def test_approve_as_proposed_keeps_the_model_basis(ring_api, conn, team):
    new = band(conn, team["patient"])
    b = ring_api.post(f"{API}/bands/{new}/approve", headers=auth_header(team["doctor"]), json={}).json()
    assert (b["status"], b["basis"], b["low"], b["high"]) == ("active", "model_proposal", 55.0, 65.0)


def test_reject_only_a_proposal(ring_api, conn, team):
    p, d = team["patient"], team["doctor"]
    proposed, active = band(conn, p), band(conn, p, status="active", doctor=d)
    assert ring_api.post(f"{API}/bands/{proposed}/reject", headers=auth_header(d)).json()["status"] == "rejected"
    r = ring_api.post(f"{API}/bands/{active}/reject", headers=auth_header(d))
    assert r.status_code == 409
    assert ring_api.post(f"{API}/bands/{active}/reject", headers=auth_header(team["stranger"])).status_code == 403
