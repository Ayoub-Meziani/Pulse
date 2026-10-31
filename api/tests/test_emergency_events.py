"""Step 8: emergency events (incident records). Patient writes their own; patient and assigned doctor read."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text

from conftest import assign, auth_header, new_user

pytestmark = pytest.mark.db
API = "/api/v1"


def now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def team(conn):
    patient, other = new_user(conn, "patient"), new_user(conn, "patient")
    doctor, stranger, former, admin = (new_user(conn, "doctor", "Dr Assigned"), new_user(conn, "doctor"),
                                       new_user(conn, "doctor"), new_user(conn, "admin"))
    assign(conn, doctor, patient)
    assign(conn, former, patient, status="ended")
    return dict(patient=patient, other=other, doctor=doctor, stranger=stranger, former=former, admin=admin)


def event_body(**kw):
    return {"id": str(uuid4()), "trigger_reason": "manual", "started_at": (now() - timedelta(minutes=2)).isoformat(),
            **kw}


def open_event(api, patient, **kw):
    r = api.post(f"{API}/patients/{patient}/emergency-events", json=event_body(**kw), headers=auth_header(patient))
    assert r.status_code == 201, r.text
    return r.json()


def action(kind="emergency_call_tapped", at=None, cid=None, detail=None):
    return {"client_action_id": cid or str(uuid4()), "action": kind, "at": (at or now()).isoformat(), "detail": detail}


def add(api, who, eid, *actions):
    return api.post(f"{API}/emergency-events/{eid}/actions", json={"actions": list(actions)}, headers=auth_header(who))


def patch(api, who, eid, body):
    return api.patch(f"{API}/emergency-events/{eid}", json=body, headers=auth_header(who))


# ---------------------------------------------------------------- create, idempotency, timestamps
def test_create_preserves_client_timestamp_and_context(api, team):
    started = (now() - timedelta(hours=3)).replace(microsecond=0)  # queued offline, sent later
    body = event_body(trigger_reason="symptom", symptoms_snapshot=["chest_pain", "chest_pain", "confusion"],
                      started_at=started.isoformat())
    r = api.post(f"{API}/patients/{team['patient']}/emergency-events", json=body, headers=auth_header(team["patient"]))
    assert r.status_code == 201
    e = r.json()
    assert e["id"] == body["id"] and e["patient_id"] == str(team["patient"]) and e["trigger_reason"] == "symptom"
    assert datetime.fromisoformat(e["started_at"]) == started
    assert e["symptoms_snapshot"] == ["chest_pain", "confusion"]
    assert (e["actions"], e["location"], e["ended_at"], e["reported_outcome"]) == ([], None, None, None)


def test_retry_with_same_id_returns_stored_event_unchanged(api, team):
    p = team["patient"]
    body = event_body(trigger_reason="severe_reading")
    first = api.post(f"{API}/patients/{p}/emergency-events", json=body, headers=auth_header(p))
    retry = api.post(f"{API}/patients/{p}/emergency-events", json={**body, "trigger_reason": "manual"},
                     headers=auth_header(p))
    assert (first.status_code, retry.status_code) == (201, 200)
    assert retry.json() == first.json() and retry.json()["trigger_reason"] == "severe_reading"
    assert len(api.get(f"{API}/patients/{p}/emergency-events", headers=auth_header(p)).json()) == 1


def test_reusing_another_patients_event_id_never_returns_their_event(api, team):
    theirs = open_event(api, team["other"], trigger_reason="symptom", symptoms_snapshot=["chest_pain"])
    r = api.post(f"{API}/patients/{team['patient']}/emergency-events", json=event_body(id=theirs["id"]),
                 headers=auth_header(team["patient"]))
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"
    assert theirs["id"] not in r.text.replace(f"/{theirs['id']}", "") and "chest_pain" not in r.text


def test_future_start_is_rejected(api, team):
    p = team["patient"]
    r = api.post(f"{API}/patients/{p}/emergency-events",
                 json=event_body(started_at=(now() + timedelta(hours=1)).isoformat()), headers=auth_header(p))
    assert r.status_code == 422 and r.json()["error"]["details"][0]["code"] == "in_future"


def test_alert_link_must_be_the_patients_own_alert(api, team):
    other = team["other"]
    alert = api.post(f"{API}/patients/{other}/measurements", json={"systolic": 185, "diastolic": 100},
                     headers=auth_header(other)).json()["alert"]
    r = api.post(f"{API}/patients/{team['patient']}/emergency-events", json=event_body(alert_id=alert["id"]),
                 headers=auth_header(team["patient"]))
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_reference"
    r = api.post(f"{API}/patients/{team['patient']}/emergency-events", json=event_body(alert_id=str(uuid4())),
                 headers=auth_header(team["patient"]))
    assert r.status_code == 422


# ---------------------------------------------------------------- actions: attempts, never confirmations
def test_actions_are_attempts_never_confirmed_and_deduplicated(api, team):
    p = team["patient"]
    e = open_event(api, p)
    tap, share = action("emergency_call_tapped"), action("share_opened", at=now() - timedelta(seconds=30))
    r = add(api, p, e["id"], tap, share)
    assert r.status_code == 200
    again = add(api, p, e["id"], {**tap, "action": "share_failed"}, action("contact_call_tapped"))  # tap is a retry
    acts = again.json()["actions"]
    assert [a["action"] for a in acts] == ["share_opened", "emergency_call_tapped", "contact_call_tapped"]
    assert all(a["confirmed"] is False for a in acts)


def test_actions_are_ordered_by_time_whatever_the_offset(api, team):
    p = team["patient"]
    e = open_event(api, p)
    base = now().replace(microsecond=0) - timedelta(minutes=1)
    algiers = timezone(timedelta(hours=1))
    late_utc, early_local = action("share_opened", at=base + timedelta(seconds=30)), action(at=base.astimezone(algiers))
    acts = add(api, p, e["id"], late_utc, early_local).json()["actions"]
    assert [a["action"] for a in acts] == ["emergency_call_tapped", "share_opened"]
    assert datetime.fromisoformat(acts[0]["at"]) == base


def test_action_vocabulary_has_no_sent_delivered_or_dispatch_claims(api, team):
    p = team["patient"]
    e = open_event(api, p)
    for claim in ("sms_sent", "message_delivered", "ambulance_dispatched", "call_connected"):
        assert add(api, p, e["id"], action(claim)).status_code == 422
    r = add(api, p, e["id"], {**action(), "confirmed": True})  # a client cannot mark an action confirmed
    assert r.status_code == 200 and r.json()["actions"][0]["confirmed"] is False


def test_future_action_time_is_rejected_and_nothing_stored(api, team):
    p = team["patient"]
    e = open_event(api, p)
    r = add(api, p, e["id"], action(), action(at=now() + timedelta(hours=2)))
    assert r.status_code == 422
    assert api.get(f"{API}/patients/{p}/emergency-events", headers=auth_header(p)).json()[0]["actions"] == []


def test_actions_are_capped_per_event(api, conn, team):
    p = team["patient"]
    e = open_event(api, p)
    conn.execute(text("update public.emergency_events set actions_attempted = (select jsonb_agg(jsonb_build_object("
                      "'client_action_id', gen_random_uuid()::text, 'action', 'screen_opened', 'at', now()::text, "
                      "'detail', null, 'confirmed', false)) from generate_series(1, 500)) where id = :id"), {"id": e["id"]})
    r = add(api, p, e["id"], action())
    assert r.status_code == 422 and r.json()["error"]["details"][0]["code"] == "too_many_actions"


# ---------------------------------------------------------------- patch: consent, outcome, end
def test_location_needs_consent_in_the_same_request(api, conn, team):
    p = team["patient"]
    e = open_event(api, p)
    r = patch(api, p, e["id"], {"location": {"lat": 36.75, "lon": 3.06}})
    assert r.status_code == 422 and r.json()["error"]["code"] == "consent_required"
    r = patch(api, p, e["id"], {"location": {"lat": 36.75, "lon": 3.06}, "location_shared_with_consent": False})
    assert r.status_code == 422
    row = conn.execute(text("select location_lat, location_shared_with_consent from public.emergency_events "
                            "where id = :id"), {"id": e["id"]}).one()
    assert tuple(row) == (None, False)
    r = patch(api, p, e["id"], {"location": {"lat": 36.75, "lon": 3.06}, "location_shared_with_consent": True})
    assert r.status_code == 200 and r.json()["location"] == {"lat": 36.75, "lon": 3.06}


def test_withdrawing_consent_removes_the_location(api, conn, team):
    p = team["patient"]
    e = open_event(api, p)
    patch(api, p, e["id"], {"location": {"lat": 36.75, "lon": 3.06}, "location_shared_with_consent": True})
    r = patch(api, p, e["id"], {"location_shared_with_consent": False})
    assert r.status_code == 200 and r.json()["location"] is None
    row = conn.execute(text("select location_lat, location_lon from public.emergency_events where id = :id"),
                       {"id": e["id"]}).one()
    assert tuple(row) == (None, None)


def test_outcome_and_end_time(api, team):
    p = team["patient"]
    e = open_event(api, p)
    end = now().replace(microsecond=0)
    r = patch(api, p, e["id"], {"reported_outcome": "felt better, rested", "ended_at": end.isoformat()})
    assert r.status_code == 200
    assert r.json()["reported_outcome"] == "felt better, rested"
    assert datetime.fromisoformat(r.json()["ended_at"]) == end
    before = (datetime.fromisoformat(e["started_at"]) - timedelta(minutes=1)).isoformat()
    r = patch(api, p, e["id"], {"ended_at": before})
    assert r.status_code == 422 and r.json()["error"]["details"][0]["code"] == "before_start"
    r = patch(api, p, e["id"], {"ended_at": (now() + timedelta(hours=1)).isoformat()})
    assert r.status_code == 422


# ---------------------------------------------------------------- permissions
@pytest.mark.parametrize("who,status", [("patient", 200), ("doctor", 200), ("stranger", 403), ("former", 403),
                                        ("admin", 403), ("other", 403)])
def test_list_access(api, team, who, status):
    open_event(api, team["patient"])
    assert api.get(f"{API}/patients/{team['patient']}/emergency-events",
                   headers=auth_header(team[who])).status_code == status


@pytest.mark.parametrize("who", ["doctor", "stranger", "admin", "other"])
def test_only_the_patient_writes_their_events(api, team, who):
    p = team["patient"]
    assert api.post(f"{API}/patients/{p}/emergency-events", json=event_body(),
                    headers=auth_header(team[who])).status_code == 403
    e = open_event(api, p)
    assert add(api, team[who], e["id"], action()).status_code == 403
    assert patch(api, team[who], e["id"], {"reported_outcome": "x"}).status_code == 403
    stored = api.get(f"{API}/patients/{p}/emergency-events", headers=auth_header(p)).json()[0]
    assert stored["actions"] == [] and stored["reported_outcome"] is None


@pytest.mark.parametrize("who,status", [("patient", 200), ("doctor", 200), ("stranger", 403), ("former", 403),
                                        ("admin", 403), ("other", 403)])
def test_report_access(api, team, who, status):
    e = open_event(api, team["patient"])
    assert api.get(f"{API}/emergency-events/{e['id']}/report", headers=auth_header(team[who])).status_code == status


def test_unknown_event_is_404(api, team):
    p = team["patient"]
    assert api.get(f"{API}/emergency-events/{uuid4()}/report", headers=auth_header(p)).status_code == 404
    assert add(api, p, uuid4(), action()).status_code == 404


# ---------------------------------------------------------------- report: own data only, ±24 h
def test_report_holds_only_this_patients_data_within_24h(api, conn, team):
    p, other = team["patient"], team["other"]
    r = api.post(f"{API}/patients/{p}/measurements", json={"systolic": 182, "diastolic": 112}, headers=auth_header(p))
    alert = r.json()["alert"]
    api.post(f"{API}/patients/{p}/symptom-reports", json={"symptoms": ["severe_headache"]}, headers=auth_header(p))
    old = (now() - timedelta(days=3)).isoformat()
    api.post(f"{API}/patients/{p}/measurements", json={"systolic": 150, "diastolic": 95, "measured_at": old},
             headers=auth_header(p))
    api.post(f"{API}/patients/{other}/measurements", json={"systolic": 199, "diastolic": 119}, headers=auth_header(other))
    api.post(f"{API}/patients/{other}/symptom-reports", json={"symptoms": ["chest_pain"]}, headers=auth_header(other))
    e = open_event(api, p, trigger_reason="severe_reading", alert_id=alert["id"])
    rep = api.get(f"{API}/emergency-events/{e['id']}/report", headers=auth_header(team["doctor"])).json()
    assert rep["event"]["id"] == e["id"] and rep["alert"]["id"] == alert["id"]
    assert [(m["systolic"], m["diastolic"]) for m in rep["readings"]] == [(182, 112)]
    assert [s["symptoms"] for s in rep["symptom_reports"]] == [["severe_headache"]]
    assert {m["patient_id"] for m in rep["readings"]} | {s["patient_id"] for s in rep["symptom_reports"]} == {str(p)}
    # the other patient's id, not their values: "199" can occur by chance inside a UUID or a timestamp
    assert str(other) not in str(rep) and "chest_pain" not in str(rep)


# ---------------------------------------------------------------- safety: events never touch alerts
def test_events_never_create_or_change_alerts(api, conn, team):
    p = team["patient"]
    alert = api.post(f"{API}/patients/{p}/measurements", json={"systolic": 185, "diastolic": 100},
                     headers=auth_header(p)).json()["alert"]
    before = conn.execute(text("select * from public.alerts where patient_id = :p"),
                          {"p": p}).all()
    e = open_event(api, p, trigger_reason="symptom", alert_id=alert["id"], symptoms_snapshot=["chest_pain"])
    add(api, p, e["id"], action(), action("outcome_reported", detail="ok"))
    patch(api, p, e["id"], {"reported_outcome": "fine", "ended_at": now().isoformat()})
    after = conn.execute(text("select * from public.alerts where patient_id = :p"),
                         {"p": p}).all()
    assert after == before
    q = api.get(f"{API}/patients/{p}/emergency-events", headers=auth_header(p))
    assert "wearable" not in q.text and "predict" not in q.text
