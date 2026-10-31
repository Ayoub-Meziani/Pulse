"""Patient password confirmation of an alert, and the doctor's list of unresolved severe/emergency alerts."""
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from conftest import SUPABASE_URL, TEST_JWKS, assign, auth_header, new_user
from test_auth import PASSWORD, FakeGoTrue

pytestmark = pytest.mark.db
API = "/api/v1"


class RevokingGoTrue(FakeGoTrue):
    """Also answers /logout, so the session created to check the password can be revoked."""

    def __init__(self):
        super().__init__()
        self.revoked = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/logout"):
            self.revoked += 1
            return httpx.Response(204)
        return super().handler(request)


@pytest.fixture
def gotrue():
    return RevokingGoTrue()


@pytest.fixture
def api(session_factory, gotrue):
    from app.config import Settings
    from app.gotrue import GoTrue
    from app.main import create_app
    app = create_app(Settings(supabase_url=SUPABASE_URL, supabase_anon_key="anon-test-key", jwks=TEST_JWKS,
                              demo_number="+213 555 12 34 56"))
    app.state.session_factory = session_factory
    app.state.gotrue = GoTrue(SUPABASE_URL, "anon-test-key", transport=httpx.MockTransport(gotrue.handler))
    return TestClient(app)


@pytest.fixture
def people(conn, gotrue):
    patient, other = new_user(conn, "patient", "Karim B."), new_user(conn, "patient", "Other")
    doctor, stranger = new_user(conn, "doctor", "Dr Amrani"), new_user(conn, "doctor")
    assign(conn, doctor, patient)
    for uid in (patient, other):
        email = conn.execute(text("select email from auth.users where id = :id"), {"id": uid}).scalar_one()
        gotrue.users[email] = uid
    return dict(patient=patient, other=other, doctor=doctor, stranger=stranger)


def reading(api, p, s, d):
    r = api.post(f"{API}/patients/{p}/measurements", json={"systolic": s, "diastolic": d}, headers=auth_header(p))
    assert r.status_code == 201, r.text
    return r.json()["alert"]


def confirm(api, alert_id, who, password=PASSWORD):
    return api.post(f"{API}/alerts/{alert_id}/patient-confirmation", json={"password": password},
                    headers=auth_header(who))


def test_correct_password_acknowledges_and_the_alert_stays_for_the_doctor(api, people, gotrue):
    p, doc = people["patient"], people["doctor"]
    alert = reading(api, p, 186, 118)
    r = confirm(api, alert["id"], p)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "acknowledged" and r.json()["acknowledged_at"]
    assert gotrue.revoked == 1  # the session created only to check the password is ended
    mine = api.get(f"{API}/doctor/alerts", headers=auth_header(doc)).json()
    assert [(a["id"], a["status"]) for a in mine] == [(alert["id"], "acknowledged")]
    assert confirm(api, alert["id"], p).status_code == 200  # repeat: unchanged


def test_wrong_password_changes_nothing_and_never_echoes_it(api, people):
    p = people["patient"]
    alert = reading(api, p, 186, 118)
    r = confirm(api, alert["id"], p, password="wrong-secret-123")
    assert r.status_code == 403 and r.json()["error"]["code"] == "reauthentication_failed"
    assert "wrong-secret-123" not in r.text
    assert api.get(f"{API}/alerts/{alert['id']}", headers=auth_header(p)).json()["status"] == "open"
    bad = api.post(f"{API}/alerts/{alert['id']}/patient-confirmation", json={"password": ""}, headers=auth_header(p))
    assert bad.status_code == 422


def test_another_patients_password_cannot_confirm(api, people, gotrue):
    p, other = people["patient"], people["other"]
    alert = reading(api, p, 186, 118)
    assert confirm(api, alert["id"], other).status_code == 403  # not their alert
    assert confirm(api, alert["id"], people["doctor"]).status_code == 403  # doctors use the doctor workflow


def test_plain_acknowledgement_of_a_severe_alert_needs_the_password(api, people):
    p, doc = people["patient"], people["doctor"]
    alert = reading(api, p, 186, 118)
    r = api.post(f"{API}/alerts/{alert['id']}/transition", json={"to": "acknowledged"}, headers=auth_header(p))
    assert r.status_code == 403 and r.json()["error"]["code"] == "password_confirmation_required"
    notice = reading(api, people["other"], 145, 88)  # notices keep the one-tap acknowledgement
    ok = api.post(f"{API}/alerts/{notice['id']}/transition", json={"to": "acknowledged"},
                  headers=auth_header(people["other"]))
    assert ok.status_code == 200
    assert api.post(f"{API}/alerts/{alert['id']}/transition", json={"to": "acknowledged"},
                    headers=auth_header(doc)).status_code == 200  # the doctor is unchanged


def test_auth_down_is_503_and_changes_nothing(api, people, gotrue):
    p = people["patient"]
    alert = reading(api, p, 186, 118)
    gotrue.down = True
    assert confirm(api, alert["id"], p).status_code == 503
    assert api.get(f"{API}/alerts/{alert['id']}", headers=auth_header(p)).json()["status"] == "open"


def test_reviewed_or_resolved_alerts_cannot_be_confirmed(api, people):
    p, doc = people["patient"], people["doctor"]
    alert = reading(api, p, 186, 118)
    api.post(f"{API}/alerts/{alert['id']}/transition", json={"to": "reviewed"}, headers=auth_header(doc))
    r = confirm(api, alert["id"], p)
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_transition"


def test_doctor_list_has_values_and_hides_resolved_notice_and_trend(api, people):
    p, doc = people["patient"], people["doctor"]
    reading(api, p, 145, 88)  # notice: never listed
    severe = reading(api, p, 186, 118)
    mine = api.get(f"{API}/doctor/alerts", headers=auth_header(doc)).json()
    assert len(mine) == 1
    a = mine[0]
    assert (a["id"], a["level"], a["status"], a["patient_name"]) == (severe["id"], "severe", "open", "Karim B.")
    assert (a["reading"]["systolic"], a["reading"]["diastolic"], a["reading"]["source"]) == (186, 118, "manual")
    api.post(f"{API}/alerts/{severe['id']}/transition", json={"to": "reviewed"}, headers=auth_header(doc))
    assert api.get(f"{API}/doctor/alerts", headers=auth_header(doc)).json()[0]["status"] == "reviewed"  # still shown
    api.post(f"{API}/alerts/{severe['id']}/transition", json={"to": "resolved", "note": "Seen at the clinic."},
             headers=auth_header(doc))
    assert api.get(f"{API}/doctor/alerts", headers=auth_header(doc)).json() == []


def test_doctor_list_is_limited_to_assigned_patients(api, people):
    reading(api, people["patient"], 186, 118)
    assert api.get(f"{API}/doctor/alerts", headers=auth_header(people["stranger"])).json() == []
    assert api.get(f"{API}/doctor/alerts", headers=auth_header(people["patient"])).status_code == 403


def test_a_confirmed_severe_alert_raised_to_emergency_rings_again_until_confirmed(api, conn, people):
    p = people["patient"]
    alert = reading(api, p, 186, 118)
    assert confirm(api, alert["id"], p).json()["status"] == "acknowledged"
    r = api.post(f"{API}/patients/{p}/symptom-reports", json={"symptoms": ["chest_pain"]}, headers=auth_header(p))
    assert r.status_code == 201 and r.json()["alert"]["id"] == alert["id"]
    row = conn.execute(text("select alert_class, status, acknowledged_at from public.alerts where id = :id"),
                       {"id": alert["id"]}).one()
    assert tuple(row) == ("possible_emergency", "open", None)       # the patient never confirmed the emergency
    listed = api.get(f"{API}/doctor/alerts", headers=auth_header(people["doctor"])).json()
    assert [(a["id"], a["level"], a["status"]) for a in listed] == [(alert["id"], "emergency", "open")]
    assert confirm(api, alert["id"], p).json()["status"] == "acknowledged"


def test_a_doctor_review_made_during_the_password_check_is_kept(api, conn, people, monkeypatch):
    p = people["patient"]
    alert = reading(api, p, 186, 118)
    auth = api.app.state.gotrue
    check = auth.password

    def review_meanwhile(email, password):   # the doctor reviews while Supabase Auth checks the password
        conn.execute(text("update public.alerts set status = 'reviewed', reviewed_at = now() where id = :id"),
                     {"id": alert["id"]})
        return check(email, password)
    monkeypatch.setattr(auth, "password", review_meanwhile)
    r = confirm(api, alert["id"], p)
    assert r.status_code == 409 and r.json()["error"]["details"]["from"] == "reviewed"
    # Never overwritten to acknowledged. (On the shared test connection the refused request also rolls back the
    # simulated review; in real use the doctor's review is its own committed transaction.)
    assert conn.execute(text("select status from public.alerts where id = :id"),
                        {"id": alert["id"]}).scalar_one() != "acknowledged"


def test_a_still_severe_recheck_after_the_patient_confirmed_rings_again(api, conn, people):
    p = people["patient"]
    alert = reading(api, p, 186, 118)
    confirm(api, alert["id"], p)
    recheck = api.post(f"{API}/patients/{p}/measurements", json={"systolic": 184, "diastolic": 121},
                       headers=auth_header(p)).json()
    assert recheck["evaluation"]["rule_id"] == "R-SEV-2" and recheck["alert"]["id"] == alert["id"]
    assert recheck["alert"]["status"] == "open" and recheck["alert"]["persistent"] is True
    lower = api.post(f"{API}/patients/{p}/measurements", json={"systolic": 150, "diastolic": 95},
                     headers=auth_header(p)).json()                     # R-SEV-3: not a new bad reading
    confirm(api, alert["id"], p)
    assert lower["evaluation"]["rule_id"] == "R-SEV-3"
    assert conn.execute(text("select status from public.alerts where id = :id"),
                        {"id": alert["id"]}).scalar_one() == "acknowledged"
