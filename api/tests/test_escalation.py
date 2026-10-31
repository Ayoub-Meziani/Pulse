"""Emergency escalation (migration M11): eligibility, ladder, state machine, worker, idempotency, honesty."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from conftest import SUPABASE_URL, TEST_JWKS, assign, auth_header, new_user
from app.services import escalation

pytestmark = pytest.mark.db
API = "/api/v1"


def now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def make_api(session_factory):
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app

    def build(enabled=True):
        app = create_app(Settings(supabase_url=SUPABASE_URL, jwks=TEST_JWKS, demo_number="+213 555 12 34 56",
                                  escalation_enabled=enabled))
        app.state.session_factory = session_factory
        return TestClient(app)
    return build


@pytest.fixture
def api(make_api):
    return make_api(True)


@pytest.fixture
def team(conn):
    patient, other = new_user(conn, "patient", "Karim"), new_user(conn, "patient")
    doctor, doctor2, stranger = new_user(conn, "doctor", "Dr Amrani"), new_user(conn, "doctor", "Dr Benali"), new_user(conn, "doctor")
    assign(conn, doctor, patient)
    conn.execute(text("insert into public.trusted_contacts (patient_id, name, phone, priority) values "
                      "(:p, 'Amina', '+213 555 00 00 01', 1), (:p, 'Yacine', '+213 555 00 00 02', 2)"), {"p": patient})
    return dict(patient=patient, other=other, doctor=doctor, doctor2=doctor2, stranger=stranger)


def open_event(api, patient, status=201, **kw):
    body = {"id": str(uuid4()), "trigger_reason": "manual", "started_at": now().isoformat()} | kw
    r = api.post(f"{API}/patients/{patient}/emergency-events", json=body, headers=auth_header(patient))
    assert r.status_code == status, r.text
    return r.json()


def esc(api, event_id, who):
    r = api.get(f"{API}/emergency-events/{event_id}/escalation", headers=auth_header(who))
    assert r.status_code == 200, r.text
    return r.json()


def timeline(api, event_id, who):
    return [t["kind"] for t in api.get(f"{API}/emergency-events/{event_id}/timeline", headers=auth_header(who)).json()]


def run(db, seconds):
    return escalation.run_once(db, now() + timedelta(seconds=seconds))


def doctor_step(api, event_id, who):
    return next(s for s in esc(api, event_id, who)["steps"] if s["stage"] == "doctor")


def reading(api, patient, s, d):
    r = api.post(f"{API}/patients/{patient}/measurements", json={"systolic": s, "diastolic": d},
                 headers=auth_header(patient))
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------- eligibility
def test_manual_button_starts_an_emergency_ladder(api, team):
    e = open_event(api, team["patient"])
    assert (e["severity"], e["evidence_provenance"], e["escalation_status"]) == ("emergency", "patient_reported", "created")
    x = esc(api, e["id"], team["patient"])
    assert x["enabled"] and x["eligible"] and x["policy"] == "emergency-v1" and x["emergency_services_notified"] is False
    stages = {(s["stage"], s["target_label"], s["channel"], s["status"], s["skip_reason"]) for s in x["steps"]}
    assert stages == {("doctor", "Dr Amrani", "in_app", "scheduled", None),
                      ("contact", "Amina", "none", "skipped", "no_channel"),
                      ("contact", "Yacine", "none", "skipped", "no_channel"),
                      ("emergency_services", None, "none", "skipped", "no_official_channel")}
    assert "+213" not in str(x)  # never phone numbers


def test_disabled_escalation_records_why_and_sends_nothing(make_api, db, team):
    api = make_api(False)
    e = open_event(api, team["patient"])
    assert e["severity"] == "emergency" and e["escalation_status"] is None
    x = esc(api, e["id"], team["patient"])
    assert not x["enabled"] and not x["eligible"] and x["steps"] == []
    assert timeline(api, e["id"], team["patient"]) == ["escalation_disabled"]
    assert run(db, 3600) == 0


def test_severe_reading_without_red_flag_is_an_urgent_review_for_the_doctor_only(api, db, team):
    alert = reading(api, team["patient"], 186, 118)["alert"]
    e = open_event(api, team["patient"], trigger_reason="severe_reading", alert_id=alert["id"])
    assert (e["severity"], e["evidence_provenance"]) == ("urgent", "manual")
    steps = esc(api, e["id"], team["patient"])["steps"]
    assert [s["stage"] for s in steps] == ["doctor"]  # never contacts or emergency services


@pytest.mark.parametrize("source,stored,provenance", [("simulated", "simulated", "simulated"),
                                                       ("csv_import", "measured", "imported")])
def test_simulated_or_imported_readings_never_escalate(api, conn, team, source, stored, provenance):
    alert = reading(api, team["patient"], 186, 118)["alert"]
    conn.execute(text("update public.measurements set source = :s, provenance = :v where patient_id = :p"),
                 {"s": source, "v": stored, "p": team["patient"]})
    e = open_event(api, team["patient"], trigger_reason="severe_reading", alert_id=alert["id"])
    assert e["severity"] is None and e["evidence_provenance"] == provenance and e["escalation_status"] is None


def test_mixed_provenance_never_escalates(api, conn, team):
    p = team["patient"]
    alert = reading(api, p, 186, 118)["alert"]
    reading(api, p, 184, 117)  # attached to the same episode
    conn.execute(text("update public.measurements set source = 'simulated', provenance = 'simulated' where id = ("
                      "select measurement_id from public.alert_measurements where alert_id = :a limit 1)"), {"a": alert["id"]})
    e = open_event(api, p, trigger_reason="severe_reading", alert_id=alert["id"])
    assert e["evidence_provenance"] == "mixed" and e["escalation_status"] is None


def test_database_refuses_an_eligible_episode_from_simulated_evidence(api, conn, team):
    e = open_event(api, team["patient"])
    with pytest.raises(DBAPIError):
        with conn.begin_nested():
            conn.execute(text("update public.emergency_events set evidence_provenance = 'simulated' where id = :id"),
                         {"id": e["id"]})


def test_red_flag_symptom_report_makes_a_symptom_trigger_eligible(api, team):
    p = team["patient"]
    api.post(f"{API}/patients/{p}/symptom-reports", json={"symptoms": ["chest_pain"]}, headers=auth_header(p))
    e = open_event(api, p, trigger_reason="symptom", symptoms_snapshot=["chest_pain"])
    assert e["severity"] == "emergency"
    other = open_event(api, team["other"], trigger_reason="symptom", symptoms_snapshot=["chest_pain"])
    assert other["severity"] is None  # the client snapshot alone is never enough


def test_episode_synced_late_is_recorded_but_not_escalated(api, team):
    e = open_event(api, team["patient"], started_at=(now() - timedelta(hours=2)).isoformat())
    assert e["escalation_status"] is None
    assert timeline(api, e["id"], team["patient"]) == ["not_eligible"]


# ---------------------------------------------------------------- idempotency and duplicates
def test_repeating_the_client_id_never_starts_a_second_ladder(api, team):
    p = team["patient"]
    body = {"id": str(uuid4()), "trigger_reason": "manual", "started_at": now().isoformat()}
    first = api.post(f"{API}/patients/{p}/emergency-events", json=body, headers=auth_header(p))
    again = api.post(f"{API}/patients/{p}/emergency-events", json=body, headers=auth_header(p))
    assert (first.status_code, again.status_code) == (201, 200)
    assert len(esc(api, body["id"], p)["steps"]) == 4


def test_second_trigger_attaches_to_the_active_escalation(api, team):
    p = team["patient"]
    first = open_event(api, p)
    second = open_event(api, p)
    assert second["escalation_status"] is None
    assert "retriggered" in timeline(api, first["id"], p) and timeline(api, second["id"], p) == ["merged_into_active"]
    open_event(api, team["other"])  # another patient is independent


def test_new_escalation_after_the_previous_one_closed(api, team):
    p = team["patient"]
    first = open_event(api, p)
    api.post(f"{API}/emergency-events/{first['id']}/cancel", json={"reason": "false_alarm"}, headers=auth_header(p))
    assert open_event(api, p)["escalation_status"] == "created"


# ---------------------------------------------------------------- worker: send, receipt, ack, timeout
def test_doctor_is_notified_after_the_cancel_grace_then_delivered_then_acknowledged(api, db, team):
    p, doc = team["patient"], team["doctor"]
    e = open_event(api, p)
    assert run(db, 5) == 0  # inside the 30-second grace: nobody notified yet
    assert run(db, 31) >= 1
    step = doctor_step(api, e["id"], p)
    assert step["status"] == "sent" and step["ack_deadline"] and esc(api, e["id"], p)["status"] == "notification_attempted"
    inbox = api.get(f"{API}/me/notifications", headers=auth_header(doc)).json()
    assert [(n["kind"], n["urgent"], n["event_id"]) for n in inbox] == [("escalation", True, e["id"])]
    mine = api.get(f"{API}/doctor/escalations", headers=auth_header(doc)).json()
    assert [(m["event_id"], m["patient_name"], m["step_status"]) for m in mine] == [(e["id"], "Karim", "sent")]
    assert api.post(f"{API}/escalation-steps/{step['id']}/delivered", headers=auth_header(doc)).json()["status"] == "delivered"
    assert esc(api, e["id"], p)["status"] == "delivered"
    ack = api.post(f"{API}/escalation-steps/{step['id']}/acknowledge", headers=auth_header(doc))
    assert ack.status_code == 200 and ack.json()["status"] == "acknowledged"
    assert esc(api, e["id"], p)["status"] == "acknowledged"
    assert api.post(f"{API}/escalation-steps/{step['id']}/acknowledge", headers=auth_header(doc)).status_code == 200
    patient_inbox = api.get(f"{API}/me/notifications", headers=auth_header(p)).json()
    assert [n["kind"] for n in patient_inbox] == ["escalation_update"]


def test_need_help_skips_the_cancel_grace(api, db, team):
    p = team["patient"]
    e = open_event(api, p)
    r = api.post(f"{API}/emergency-events/{e['id']}/patient-response", json={"response": "need_help"}, headers=auth_header(p))
    assert r.status_code == 200 and r.json()["patient_response"] == "need_help"
    run(db, 1)
    assert doctor_step(api, e["id"], p)["status"] == "sent"


def test_no_acknowledgement_escalates_to_the_patient_reminder(api, db, team):
    p = team["patient"]
    e = open_event(api, p)
    run(db, 31)
    run(db, 31 + 301)
    x = esc(api, e["id"], p)
    assert x["status"] == "escalated"
    assert {s["stage"]: s["status"] for s in x["steps"]}["doctor"] == "expired"
    reminder = next(s for s in x["steps"] if s["stage"] == "patient_reminder")
    assert reminder["status"] == "scheduled"
    run(db, 31 + 302)
    assert next(s for s in esc(api, e["id"], p)["steps"] if s["stage"] == "patient_reminder")["status"] == "sent"
    kinds = timeline(api, e["id"], p)
    assert {"step_sent", "step_expired", "escalated", "patient_no_response"} <= set(kinds)
    run(db, 31 + 303)
    assert timeline(api, e["id"], p).count("escalated") == 1  # each stage at most once


def test_late_acknowledgement_after_expiry_is_still_recorded(api, db, team):
    p, doc = team["patient"], team["doctor"]
    e = open_event(api, p)
    run(db, 31)
    run(db, 400)
    step = doctor_step(api, e["id"], p)
    assert step["status"] == "expired"
    assert api.post(f"{API}/escalation-steps/{step['id']}/acknowledge", headers=auth_header(doc)).json()["status"] == "acknowledged"
    assert esc(api, e["id"], p)["status"] == "acknowledged"


def test_facility_without_agreement_is_never_contacted(api, db, conn, team):
    fid = conn.execute(text("insert into public.care_facilities (name, wilaya) values ('CHU Test', 'Alger') returning id")).scalar()
    conn.execute(text("insert into public.doctor_facility_affiliations (doctor_id, facility_id) values (:d, :f)"),
                 {"d": team["doctor"], "f": fid})
    e = open_event(api, team["patient"])
    run(db, 31)
    run(db, 400)
    facility = next(s for s in esc(api, e["id"], team["patient"])["steps"] if s["stage"] == "facility")
    assert (facility["target_label"], facility["status"], facility["skip_reason"]) == ("CHU Test", "skipped", "no_agreement")


def test_urgent_review_reminds_the_doctor_once_and_never_contacts_relatives(api, db, team):
    p = team["patient"]
    alert = reading(api, p, 186, 118)["alert"]
    e = open_event(api, p, trigger_reason="severe_reading", alert_id=alert["id"])
    run(db, 31)
    run(db, 31 + 1801)
    stages = [(s["stage"], s["status"]) for s in esc(api, e["id"], p)["steps"]]
    assert ("doctor", "expired") in stages and ("doctor_reminder", "scheduled") in stages
    assert all(stage in ("doctor", "doctor_reminder") for stage, _ in stages)


class FlakyChannel:
    name = "flaky"

    def __init__(self, failures, permanent=False):
        self.failures, self.permanent, self.calls = failures, permanent, 0

    def send(self, db, step, now):
        self.calls += 1
        if self.calls <= self.failures:
            raise (escalation.PermanentError if self.permanent else escalation.RetryableError)("provider down")
        return "msg-1"


def test_retryable_failures_back_off_then_succeed(api, db, team):
    e = open_event(api, team["patient"])
    ch = FlakyChannel(failures=2)
    t0 = now() + timedelta(seconds=31)
    escalation.run_once(db, t0, {"in_app": ch})
    step = doctor_step(api, e["id"], team["patient"])
    assert (step["status"], step["attempts"]) == ("scheduled", 1)
    escalation.run_once(db, t0 + timedelta(seconds=5), {"in_app": ch})  # before the 10 s backoff
    assert ch.calls == 1
    escalation.run_once(db, t0 + timedelta(seconds=11), {"in_app": ch})
    escalation.run_once(db, t0 + timedelta(seconds=45), {"in_app": ch})
    step = doctor_step(api, e["id"], team["patient"])
    assert (step["status"], step["attempts"], ch.calls) == ("sent", 3, 3)
    assert timeline(api, e["id"], team["patient"]).count("step_retry") == 2


def test_permanent_failure_escalates_immediately(api, db, team):
    e = open_event(api, team["patient"])
    escalation.run_once(db, now() + timedelta(seconds=31), {"in_app": FlakyChannel(1, permanent=True)})
    x = esc(api, e["id"], team["patient"])
    assert x["status"] == "escalated" and any(s["stage"] == "patient_reminder" for s in x["steps"])


def test_in_app_send_is_idempotent_after_a_crash(api, db, team):
    e = open_event(api, team["patient"])
    run(db, 31)
    step = db.get(escalation.EscalationStep, doctor_step(api, e["id"], team["patient"])["id"])
    first = step.provider_message_id
    assert escalation.InAppChannel().send(db, step, now()) == first  # a resend finds the same notification


# ---------------------------------------------------------------- cancel and resolve
def test_cancel_stops_pending_steps_and_updates_doctors_already_shown(api, db, team):
    p, doc = team["patient"], team["doctor"]
    e = open_event(api, p)
    run(db, 31)
    r = api.post(f"{API}/emergency-events/{e['id']}/cancel", json={"reason": "false_alarm"}, headers=auth_header(p))
    assert r.status_code == 200 and r.json()["status"] == "cancelled" and r.json()["cancel_reason"] == "false_alarm"
    assert doctor_step(api, e["id"], p)["status"] == "cancelled"
    assert sorted(n["kind"] for n in api.get(f"{API}/me/notifications", headers=auth_header(doc)).json()) == [
        "escalation", "escalation_update"]  # same transaction in tests: same created_at
    assert api.post(f"{API}/emergency-events/{e['id']}/cancel", json={"reason": "false_alarm"}, headers=auth_header(p)).status_code == 200
    assert run(db, 3600) == 0  # nothing left to send
    assert api.get(f"{API}/doctor/escalations", headers=auth_header(doc)).json() == []
    step = doctor_step(api, e["id"], p)
    assert api.post(f"{API}/escalation-steps/{step['id']}/acknowledge", headers=auth_header(doc)).status_code == 409


def test_cancel_before_the_grace_means_nobody_is_notified(api, db, team):
    p, doc = team["patient"], team["doctor"]
    e = open_event(api, p)
    api.post(f"{API}/emergency-events/{e['id']}/cancel", json={"reason": "false_alarm"}, headers=auth_header(p))
    run(db, 31)
    assert api.get(f"{API}/me/notifications", headers=auth_header(doc)).json() == []


def test_doctor_resolves_with_an_outcome(api, db, team):
    p, doc = team["patient"], team["doctor"]
    e = open_event(api, p)
    missing = api.post(f"{API}/emergency-events/{e['id']}/resolve", json={"outcome": "  "}, headers=auth_header(doc))
    assert missing.status_code == 422
    r = api.post(f"{API}/emergency-events/{e['id']}/resolve", json={"outcome": "Patient seen at the clinic."},
                 headers=auth_header(doc))
    assert r.status_code == 200 and r.json()["status"] == "resolved"
    again = api.post(f"{API}/emergency-events/{e['id']}/cancel", json={"reason": "false_alarm"}, headers=auth_header(p))
    assert again.status_code == 409


# ---------------------------------------------------------------- permissions
def test_permissions(api, db, team):
    p = team["patient"]
    e = open_event(api, p)
    run(db, 31)
    step = doctor_step(api, e["id"], p)
    for who in ("other", "stranger"):
        assert api.get(f"{API}/emergency-events/{e['id']}/escalation", headers=auth_header(team[who])).status_code == 403
        assert api.get(f"{API}/emergency-events/{e['id']}/timeline", headers=auth_header(team[who])).status_code == 403
        assert api.post(f"{API}/emergency-events/{e['id']}/resolve", json={"outcome": "x"},
                        headers=auth_header(team[who])).status_code == 403
    assert api.post(f"{API}/emergency-events/{e['id']}/cancel", json={"reason": "other"},
                    headers=auth_header(team["doctor"])).status_code == 403  # only the patient cancels
    assert api.post(f"{API}/escalation-steps/{step['id']}/acknowledge", headers=auth_header(team["stranger"])).status_code == 404
    assert api.post(f"{API}/escalation-steps/{step['id']}/acknowledge", headers=auth_header(p)).status_code == 403
    assert api.get(f"{API}/doctor/escalations", headers=auth_header(p)).status_code == 403
    assert api.get(f"{API}/doctor/escalations", headers=auth_header(team["stranger"])).json() == []


def test_unassigned_doctor_can_no_longer_acknowledge(api, db, conn, team):
    p, doc = team["patient"], team["doctor"]
    e = open_event(api, p)
    run(db, 31)
    step = doctor_step(api, e["id"], p)
    conn.execute(text("update public.doctor_patient_assignments set status = 'ended', ended_at = now() "
                      "where doctor_id = :d"), {"d": doc})
    assert api.post(f"{API}/escalation-steps/{step['id']}/acknowledge", headers=auth_header(doc)).status_code == 403


def test_notifications_are_private_and_marked_read(api, db, team):
    e = open_event(api, team["patient"])
    run(db, 31)
    n = api.get(f"{API}/me/notifications", headers=auth_header(team["doctor"])).json()[0]
    assert api.post(f"{API}/notifications/{n['id']}/read", headers=auth_header(team["stranger"])).status_code == 404
    read = api.post(f"{API}/notifications/{n['id']}/read", headers=auth_header(team["doctor"])).json()
    assert read["read_at"]
    assert api.get(f"{API}/me/notifications", params={"unread": True}, headers=auth_header(team["doctor"])).json() == []
    assert e["id"] == n["event_id"]


# ---------------------------------------------------------------- non-urgent notifications and timeline
def test_doctor_is_told_about_severe_alerts_but_not_notices(api, team):
    p, doc = team["patient"], team["doctor"]
    reading(api, p, 145, 88)  # notice: no notification
    assert api.get(f"{API}/me/notifications", headers=auth_header(doc)).json() == []
    alert = reading(api, p, 186, 118)["alert"]
    inbox = api.get(f"{API}/me/notifications", headers=auth_header(doc)).json()
    assert [(n["kind"], n["alert_id"], n["urgent"]) for n in inbox] == [("alert_created", alert["id"], False)]
    api.post(f"{API}/alerts/{alert['id']}/transition", json={"to": "reviewed"}, headers=auth_header(doc))
    assert [n["kind"] for n in api.get(f"{API}/me/notifications", headers=auth_header(p)).json()] == ["alert_reviewed"]


def test_timeline_is_append_only(api, conn, team):
    e = open_event(api, team["patient"])
    with pytest.raises(DBAPIError, match="append-only"):
        with conn.begin_nested():
            conn.execute(text("delete from public.escalation_timeline where event_id = :e"), {"e": e["id"]})


def test_location_must_be_fresh(api, team):
    p = team["patient"]
    e = open_event(api, p)
    old = api.patch(f"{API}/emergency-events/{e['id']}", headers=auth_header(p), json={
        "location": {"lat": 36.75, "lon": 3.06}, "location_shared_with_consent": True,
        "location_captured_at": (now() - timedelta(minutes=20)).isoformat()})
    assert old.status_code == 422 and old.json()["error"]["details"][0]["code"] == "stale_location"
    ok = api.patch(f"{API}/emergency-events/{e['id']}", headers=auth_header(p), json={
        "location": {"lat": 36.75, "lon": 3.06}, "location_shared_with_consent": True,
        "location_captured_at": (now() - timedelta(minutes=1)).isoformat(), "location_accuracy_m": 25})
    assert ok.status_code == 200 and ok.json()["location_accuracy_m"] == 25 and ok.json()["location_captured_at"]
    assert api.get(f"{API}/doctor/escalations", headers=auth_header(team["doctor"])).json() == []  # not sent yet


def test_direct_client_cannot_write_escalation_columns(conn, team):
    eid = uuid4()
    conn.execute(text("select set_config('request.jwt.claims', :c, true)"),
                 {"c": '{"sub": "%s", "role": "authenticated"}' % team["patient"]})
    with pytest.raises(DBAPIError):
        with conn.begin_nested():
            conn.execute(text("set local role authenticated"))
            conn.execute(text("insert into public.emergency_events (id, patient_id, trigger_reason, escalation_eligible, "
                              "escalation_status, evidence_provenance) values (:id, :p, 'manual', true, 'acknowledged', "
                              "'patient_reported')"), {"id": eid, "p": team["patient"]})


def test_config_disclaimer_matches_the_escalation_setting(make_api):
    off = make_api(False).get(f"{API}/config/emergency").json()
    on = make_api(True).get(f"{API}/config/emergency").json()
    assert off["escalation_enabled"] is False and "ne prévient pas votre médecin en temps réel" in off["disclaimer_fr"]
    assert on["escalation_enabled"] is True and "notification dans l'application" in on["disclaimer_fr"]
    assert "n'appelle pas les secours" in on["disclaimer_fr"]
