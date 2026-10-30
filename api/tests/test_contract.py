"""Contract v1: every route exists with its final schema; unbuilt routes answer 501 in the error format.

No database here: `client` replaces the current-user dependency with a fake patient so the
route shapes can be checked; `anon_client` keeps the real dependency for the 401 checks.
Authentication itself is tested against the test database in test_auth.py.
"""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.analysis.rules import RED_FLAG_SYMPTOMS
from app.auth import CurrentUser, current_user
from app.config import Settings
from app.db import require_session
from app.main import create_app

API = "/api/v1"
PID, AID, EID, CID, JID = (uuid4() for _ in range(5))
AUTH = {"Authorization": "Bearer test-token"}

# (method, path, json body) for every protected route in contract v1.
PROTECTED = [
    ("GET", "/me", None),
    ("GET", "/patients", None),
    ("POST", f"/patients/{PID}/measurements", {"systolic": 186, "diastolic": 118}),
    ("GET", f"/patients/{PID}/measurements", None),
    ("GET", f"/patients/{PID}/summary", None),
    ("GET", f"/patients/{PID}/daily", None),
    ("POST", f"/patients/{PID}/symptom-reports", {"symptoms": ["chest_pain"]}),
    ("GET", f"/patients/{PID}/alerts", None),
    ("GET", f"/patients/{PID}/predictions/latest", None),
    ("GET", f"/patients/{PID}/profile", None),
    ("PUT", f"/patients/{PID}/profile", {
        "full_name": "Test", "timezone": "Africa/Algiers", "birth_year": None, "relevant_conditions": [],
        "allergies": None, "medication_context": None, "regular_clinic": None, "consent_location": False}),
    ("GET", f"/patients/{PID}/trusted-contacts", None),
    ("POST", f"/patients/{PID}/trusted-contacts", {"name": "A", "phone": "+213 555 00 00 00", "contact_consented": True}),
    ("PATCH", f"/trusted-contacts/{CID}", {"active": False}),
    ("DELETE", f"/trusted-contacts/{CID}", None),
    ("GET", f"/patients/{PID}/care-plan", None),
    ("PUT", f"/patients/{PID}/care-plan", {"target_systolic": 135, "target_diastolic": 85, "clinician_guidance": "x"}),
    ("GET", f"/alerts/{AID}", None),
    ("POST", f"/alerts/{AID}/transition", {"to": "acknowledged"}),
    ("GET", f"/patients/{PID}/emergency-card", None),
    ("POST", f"/patients/{PID}/emergency-events",
     {"id": str(uuid4()), "trigger_reason": "manual", "started_at": "2026-10-30T10:00:00+01:00"}),
    ("GET", f"/patients/{PID}/emergency-events", None),
    ("POST", f"/emergency-events/{EID}/actions",
     {"actions": [{"client_action_id": str(uuid4()), "action": "emergency_call_tapped", "at": "2026-10-30T10:00:05+01:00"}]}),
    ("PATCH", f"/emergency-events/{EID}", {"reported_outcome": "felt better"}),
    ("GET", f"/emergency-events/{EID}/report", None),
    ("GET", f"/patients/{PID}/notes", None),
    ("POST", f"/patients/{PID}/notes", {"note": "x"}),
    ("GET", f"/patients/{PID}/journal", None),
    ("POST", f"/patients/{PID}/journal", {"category": "question", "entry_text": "x"}),
    ("POST", f"/journal/{JID}/review", None),
]


SETTINGS = Settings(demo_mode=True, demo_number="+213 555 12 34 56")
FAKE_PATIENT = CurrentUser(id=PID, role="patient", full_name="Test", email="t@pulse.test", timezone="Africa/Algiers")
# Implemented and tested against the database (test_auth.py, test_measurements.py).
BUILT = {("GET", "/me"), ("POST", f"/patients/{PID}/measurements"), ("GET", f"/patients/{PID}/measurements"),
         ("POST", f"/patients/{PID}/symptom-reports"), ("GET", f"/patients/{PID}/alerts"),
         ("GET", f"/alerts/{AID}"), ("POST", f"/alerts/{AID}/transition"),  # test_alerts.py
         ("GET", "/patients"), ("GET", f"/patients/{PID}/summary"), ("GET", f"/patients/{PID}/profile"),
         ("PUT", f"/patients/{PID}/profile"), ("GET", f"/patients/{PID}/trusted-contacts"),
         ("POST", f"/patients/{PID}/trusted-contacts"), ("PATCH", f"/trusted-contacts/{CID}"),
         ("DELETE", f"/trusted-contacts/{CID}"), ("GET", f"/patients/{PID}/care-plan"),
         ("PUT", f"/patients/{PID}/care-plan"), ("GET", f"/patients/{PID}/emergency-card"),  # test_patient_data.py
         ("GET", f"/patients/{PID}/predictions/latest"),  # test_predictions.py
         ("POST", f"/patients/{PID}/emergency-events"), ("GET", f"/patients/{PID}/emergency-events"),
         ("POST", f"/emergency-events/{EID}/actions"), ("PATCH", f"/emergency-events/{EID}"),
         ("GET", f"/emergency-events/{EID}/report"),  # test_emergency_events.py
         ("GET", f"/patients/{PID}/notes"), ("POST", f"/patients/{PID}/notes")}  # test_notes.py
UNBUILT = [p for p in PROTECTED if (p[0], p[1]) not in BUILT]


@pytest.fixture
def client():
    app = create_app(SETTINGS)
    app.dependency_overrides[current_user] = lambda: FAKE_PATIENT
    return TestClient(app)


@pytest.fixture
def anon_client():
    return TestClient(create_app(SETTINGS))


@pytest.fixture
def validating_client():
    """For request-validation checks only: the session dependency returns a sentinel, so validation
    (which FastAPI runs after dependencies) decides. A handler reached with the sentinel would 500."""
    app = create_app(SETTINGS)
    app.dependency_overrides[current_user] = lambda: FAKE_PATIENT
    app.dependency_overrides[require_session] = lambda: object()
    return TestClient(app)


def test_health(client):
    assert client.get(f"{API}/health").json() == {"status": "ok"}


@pytest.mark.parametrize("method,path,body", PROTECTED)
def test_protected_routes_require_token(anon_client, method, path, body):
    r = anon_client.request(method, API + path, json=body)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "not_authenticated"


@pytest.mark.parametrize("method,path,body", UNBUILT)
def test_unbuilt_routes_answer_501_in_error_format(client, method, path, body):
    r = client.request(method, API + path, json=body, headers=AUTH)
    assert r.status_code == 501, r.text
    assert r.json() == {"error": {"code": "not_implemented", "message": r.json()["error"]["message"], "details": None}}


def test_token_without_database_is_503_not_a_crash(anon_client):
    r = anon_client.get(f"{API}/me", headers=AUTH)
    assert r.status_code == 503 and r.json()["error"]["code"] == "database_unavailable"


@pytest.mark.parametrize("method,path,body", [p for p in PROTECTED if (p[0], p[1]) in BUILT and p[1] != "/me"])
def test_built_routes_without_database_answer_503_not_a_crash(client, method, path, body):
    r = client.request(method, API + path, json=body, headers=AUTH)
    assert r.status_code == 503 and r.json()["error"]["code"] == "database_unavailable"


@pytest.mark.parametrize("path", ["/auth/login", "/auth/refresh"])
def test_auth_routes_without_supabase_config_answer_503(anon_client, path):
    body = {"email": "a@b.c", "password": "x"} if path.endswith("login") else {"refresh_token": "x"}
    r = anon_client.post(API + path, json=body)
    assert r.status_code == 503 and r.json()["error"]["code"] == "auth_unavailable"


def test_bad_ids_and_bodies_are_rejected_before_handlers(validating_client):
    client = validating_client
    assert client.get(f"{API}/patients/123/summary", headers=AUTH).status_code == 422
    r = client.post(f"{API}/patients/{PID}/symptom-reports", headers=AUTH, json={"symptoms": ["short_breath"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"
    r = client.post(f"{API}/patients/{PID}/trusted-contacts", headers=AUTH,
                    json={"name": "A", "phone": "not a phone", "contact_consented": True})
    assert r.status_code == 422
    r = client.post(f"{API}/patients/{PID}/measurements", headers=AUTH,
                    json={"systolic": 120, "diastolic": 80, "measured_at": "2026-10-30T10:00:00"})
    assert r.status_code == 422  # timestamps must carry a timezone


def test_every_contract_route_is_covered_by_these_tests(client):
    spec = client.get(f"{API}/openapi.json").json()
    routes = {(m.upper(), p.removeprefix(API)) for p, ops in spec["paths"].items() for m in ops}
    routes -= {("GET", "/health"), ("GET", "/config/emergency"), ("POST", "/auth/login"), ("POST", "/auth/refresh")}
    covered = {(m, p.replace(str(PID), "{patient_id}").replace(str(AID), "{alert_id}")
                .replace(str(EID), "{event_id}").replace(str(CID), "{contact_id}").replace(str(JID), "{entry_id}"))
               for m, p, _ in PROTECTED}
    assert routes == covered


# ---------------------------------------------------------------- emergency config (implemented)
def test_emergency_config_demo_mode_never_points_at_a_real_number(client):
    r = client.get(f"{API}/config/emergency")
    assert r.status_code == 200
    cfg = r.json()
    primary = next(n for n in cfg["numbers"] if n["id"] == cfg["primary_number_id"])
    assert cfg["demo_mode"] is True and primary["id"] == "demo" and primary["number"] == "+213 555 12 34 56"
    assert all(n["verified"] is False for n in cfg["numbers"])  # D3 still open


def test_emergency_config_fallback_matches_the_rules(client):
    fb = client.get(f"{API}/config/emergency").json()["client_fallback"]
    assert (fb["severe_systolic"], fb["severe_diastolic"]) == (180, 120)
    assert set(fb["red_flag_symptoms"]) == RED_FLAG_SYMPTOMS


def test_emergency_config_without_demo_mode_uses_configured_primary():
    c = TestClient(create_app(Settings(demo_mode=False, primary_number_id="dz-1021")))
    cfg = c.get(f"{API}/config/emergency").json()
    assert cfg["primary_number_id"] == "dz-1021" and all(n["id"] != "demo" for n in cfg["numbers"])


def test_demo_mode_requires_a_demo_number_outside_dev(monkeypatch):
    from app.config import load_settings
    monkeypatch.setenv("PULSE_ENV", "prod")
    monkeypatch.setenv("PULSE_DEMO_MODE", "true")
    monkeypatch.delenv("PULSE_DEMO_NUMBER", raising=False)
    with pytest.raises(RuntimeError):
        load_settings()


# ---------------------------------------------------------------- review fixes (C1-C5, S1, S3)
def _cfg(**kw):
    return create_app(Settings(**kw)).state.emergency_config


def test_c1_demo_mode_without_number_reports_null_not_empty_string():
    c = TestClient(create_app(Settings(demo_mode=True, demo_number=None)))
    cfg = c.get(f"{API}/config/emergency").json()
    demo = next(n for n in cfg["numbers"] if n["id"] == "demo")
    assert cfg["primary_number_id"] == "demo" and demo["number"] is None


def test_c2_unknown_primary_number_id_stops_startup():
    with pytest.raises(RuntimeError, match="matches none"):
        _cfg(demo_mode=False, primary_number_id="nope")


def test_c2_malformed_numbers_stop_startup():
    with pytest.raises(RuntimeError, match="Invalid PULSE_EMERGENCY_NUMBERS"):
        _cfg(demo_mode=False, emergency_numbers=({"id": "x"},))
    with pytest.raises(RuntimeError, match="Duplicate"):
        _cfg(demo_mode=False, primary_number_id="a", emergency_numbers=(
            {"id": "a", "label_fr": "A", "label_ar": "A", "number": "1", "verified": False, "source": "s"},
            {"id": "a", "label_fr": "B", "label_ar": "B", "number": "2", "verified": False, "source": "s"}))


def test_c2_primary_without_number_outside_demo_stops_startup():
    with pytest.raises(RuntimeError, match="has no number"):
        _cfg(demo_mode=False, primary_number_id="a", emergency_numbers=(
            {"id": "a", "label_fr": "A", "label_ar": "A", "number": None, "verified": False, "source": "s"},))


def test_c2_demo_mode_without_number_stops_startup_outside_dev():
    with pytest.raises(RuntimeError, match="PULSE_DEMO_NUMBER"):
        _cfg(env="prod", demo_mode=True, demo_number=None)


def test_c2_invalid_json_env_stops_startup(monkeypatch):
    from app.config import load_settings
    monkeypatch.setenv("PULSE_EMERGENCY_NUMBERS", "{not json")
    with pytest.raises(RuntimeError, match="not valid JSON"):
        load_settings()


def _schema(client, name):
    return client.get(f"{API}/openapi.json").json()["components"]["schemas"][name]


def test_c3_care_plan_effective_from_is_a_date(client):
    prop = _schema(client, "CarePlanOut")["properties"]["effective_from"]
    assert {"type": "string", "format": "date"} in prop["anyOf"]


def test_c4_journal_category_matches_database_values(client):
    cats = set(_schema(client, "JournalIn")["properties"]["category"]["enum"])
    assert cats == {"symptoms", "food", "activity", "medication", "question", "other"}
    r = client.post(f"{API}/patients/{PID}/journal", headers=AUTH, json={"category": "worry", "entry_text": "x"})
    assert r.status_code == 422


def test_c5_profile_put_rejects_partial_bodies(validating_client):
    client = validating_client
    r = client.put(f"{API}/patients/{PID}/profile", headers=AUTH, json={"full_name": "Only a name"})
    assert r.status_code == 422
    missing = {d["field"] for d in r.json()["error"]["details"]}
    assert {"allergies", "relevant_conditions", "consent_location", "timezone"} <= missing


def test_s1_evaluation_and_event_replay_are_documented(client):
    spec = client.get(f"{API}/openapi.json").json()
    ev = spec["components"]["schemas"]["EvaluationOut"]
    assert "DATA-INVALID" in ev["description"] and "requires_symptom_check" in ev["description"]
    responses = spec["paths"][f"{API}/patients/{{patient_id}}/emergency-events"]["post"]["responses"]
    assert {"200", "201"} <= set(responses)


@pytest.mark.parametrize("body", [
    {"systolic": 0, "diastolic": 80}, {"systolic": 401, "diastolic": 80},
    {"systolic": 120, "diastolic": 0}, {"systolic": 120, "diastolic": 301},
    {"systolic": 120, "diastolic": 80, "pulse": 0}, {"systolic": 120, "diastolic": 80, "pulse": 401},
])
def test_s3_values_outside_database_storage_limits_get_invalid_request(validating_client, body):
    r = validating_client.post(f"{API}/patients/{PID}/measurements", headers=AUTH, json=body)
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"


@pytest.mark.parametrize("body", [
    {"systolic": 400, "diastolic": 300, "pulse": 400},  # storable; the DB marks it invalid, rules still prompt
    {"systolic": 310, "diastolic": 205},                # implausible but storable -> DATA-INVALID + symptom check
    {"systolic": 250, "diastolic": 150},                # severe, needs_review -> still evaluated by the rules
])
def test_s3_storable_extreme_readings_pass_request_validation(client, body):
    # Passes validation and reaches the handler (503 here: no database). The clinical behaviour of these
    # readings (DATA-INVALID + symptom check, R-SEV-1 on needs_review) is tested in test_measurements.py.
    r = client.post(f"{API}/patients/{PID}/measurements", headers=AUTH, json=body)
    assert r.status_code == 503 and r.json()["error"]["code"] == "database_unavailable"


def test_m3_live_symptom_report_is_always_returned(client):
    s = _schema(client, "SymptomResult")
    assert "report" in s["required"] and "anyOf" not in s["properties"]["report"]
