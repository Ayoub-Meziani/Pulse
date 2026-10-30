"""Contract v1: every route exists with its final schema; unbuilt routes answer 501 in the error format."""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.analysis.rules import RED_FLAG_SYMPTOMS
from app.config import Settings
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
    ("PUT", f"/patients/{PID}/profile", {"full_name": "Test"}),
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


@pytest.fixture
def client():
    return TestClient(create_app(Settings(demo_mode=True, demo_number="+213 555 12 34 56")))


def test_health(client):
    assert client.get(f"{API}/health").json() == {"status": "ok"}


@pytest.mark.parametrize("method,path,body", PROTECTED)
def test_protected_routes_require_token(client, method, path, body):
    r = client.request(method, API + path, json=body)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "not_authenticated"


@pytest.mark.parametrize("method,path,body", PROTECTED)
def test_unbuilt_routes_answer_501_in_error_format(client, method, path, body):
    r = client.request(method, API + path, json=body, headers=AUTH)
    assert r.status_code == 501, r.text
    assert r.json() == {"error": {"code": "not_implemented", "message": r.json()["error"]["message"], "details": None}}


@pytest.mark.parametrize("path", ["/auth/login", "/auth/refresh"])
def test_auth_routes_are_public_but_not_built(client, path):
    body = {"email": "a@b.c", "password": "x"} if path.endswith("login") else {"refresh_token": "x"}
    assert client.post(API + path, json=body).status_code == 501


def test_bad_ids_and_bodies_are_rejected_before_handlers(client):
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
