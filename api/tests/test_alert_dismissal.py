"""Q5 (migration M10): dismissal of notice alerts and the read-only alert timeline from audit_log."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from conftest import auth_header
from test_alerts import API, ago, detail, move, people, reading, symptoms  # noqa: F401  (people is a fixture)

pytestmark = pytest.mark.db


def dismiss(api, alert_id, who, reason="remeasured_lower", note=None):
    body = {"to": "dismissed"} | ({"reason": reason} if reason else {}) | ({"note": note} if note is not None else {})
    return api.post(f"{API}/alerts/{alert_id}/transition", json=body, headers=auth_header(who))


def events(api, alert_id, who):
    return api.get(f"{API}/alerts/{alert_id}/events", headers=auth_header(who))


def notice(api, p):
    a = reading(api, p, 145, 88)["alert"]
    assert a["level"] == "notice"
    return a["id"]


# ---------------------------------------------------------------- who and what
@pytest.mark.parametrize("who,status", [("patient", 200), ("doctor", 200), ("other", 403), ("stranger", 403),
                                        ("former", 403)])
def test_patient_or_assigned_doctor_dismisses_a_notice(api, people, who, status):
    alert_id = notice(api, people["patient"])
    r = dismiss(api, alert_id, people[who])
    assert r.status_code == status, r.text
    if status == 200:
        body = r.json()
        assert body["status"] == "dismissed" and body["dismissal_reason"] == "remeasured_lower"
        assert body["dismissed_at"] and body["dismissed_by_role"] == ("patient" if who == "patient" else "doctor")


def test_notice_can_be_dismissed_after_acknowledgement(api, people):
    p = people["patient"]
    alert_id = notice(api, p)
    move(api, alert_id, p, "acknowledged")
    assert dismiss(api, alert_id, p).json()["status"] == "dismissed"


def test_severe_trend_and_emergency_alerts_are_never_dismissable(api, people):
    p, doc = people["patient"], people["doctor"]
    severe = reading(api, p, 186, 118)["alert"]["id"]
    trend = [reading(api, p, 150, 95, measured_at=ago(days=d)) for d in (6, 5, 4)][-1]["trend_alert"]["id"]
    emergency = symptoms(api, p, ["chest_pain"]).json()["alert"]["id"]
    for alert_id in (severe, trend, emergency):
        for who in (p, doc):
            r = dismiss(api, alert_id, who)
            assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_transition", r.text
        assert detail(api, alert_id, p).json()["status"] == "open"


def test_a_notice_raised_to_severe_is_no_longer_dismissable(api, people):
    p = people["patient"]
    alert_id = notice(api, p)
    raised = reading(api, p, 186, 118)["alert"]
    if raised["id"] == alert_id:  # the rules may raise the same episode or open a severe one
        assert dismiss(api, alert_id, p).status_code == 409


def test_reason_is_required_and_other_needs_a_note(api, people):
    p = people["patient"]
    alert_id = notice(api, p)
    missing = dismiss(api, alert_id, p, reason=None)
    assert missing.status_code == 422 and missing.json()["error"]["details"][0]["field"] == "reason"
    other = dismiss(api, alert_id, p, reason="other")
    assert other.status_code == 422 and other.json()["error"]["details"][0]["field"] == "note"
    too_long = dismiss(api, alert_id, p, reason="other", note="x" * 501)
    assert too_long.status_code == 422 and too_long.json()["error"]["details"][0]["code"] == "too_long"
    bad = dismiss(api, alert_id, p, reason="bored")
    assert bad.status_code == 422
    ok = dismiss(api, alert_id, p, reason="other", note="  Cuff was loose.  ")
    assert ok.status_code == 200 and ok.json()["dismissal_note"] == "Cuff was loose."


def test_reason_is_refused_on_other_transitions(api, people):
    alert_id = notice(api, people["patient"])
    r = api.post(f"{API}/alerts/{alert_id}/transition", json={"to": "acknowledged", "reason": "other"},
                 headers=auth_header(people["patient"]))
    assert r.status_code == 422 and r.json()["error"]["details"][0]["code"] == "not_stored"


# ---------------------------------------------------------------- after dismissal
def test_dismissed_notice_is_kept_but_no_longer_active(api, people):
    p, doc = people["patient"], people["doctor"]
    alert_id = notice(api, p)
    dismiss(api, alert_id, p, reason="measurement_error")
    url = f"{API}/patients/{p}/alerts"
    assert api.get(url, headers=auth_header(p)).json() == []
    everything = api.get(url, params={"status": "all"}, headers=auth_header(doc)).json()
    assert [a["id"] for a in everything] == [alert_id] and everything[0]["status"] == "dismissed"
    fresh = reading(api, p, 146, 89)["alert"]  # the next above-target reading opens a new notice
    assert fresh["rule_id"] == "R-TGT-1" and fresh["id"] != alert_id
    assert len(detail(api, alert_id, p).json()["measurements"]) == 1


def test_doctor_can_still_review_a_dismissed_notice_and_patient_cannot_reopen_it(api, people):
    p, doc = people["patient"], people["doctor"]
    alert_id = notice(api, p)
    dismiss(api, alert_id, p)
    assert move(api, alert_id, p, "acknowledged").status_code == 409
    assert dismiss(api, alert_id, doc).status_code == 409
    assert move(api, alert_id, p, "reviewed").status_code == 403
    reviewed = move(api, alert_id, doc, "reviewed").json()
    assert reviewed["status"] == "reviewed" and reviewed["dismissal_reason"] == "remeasured_lower"


def test_database_refuses_a_dismissal_on_a_severe_alert(api, conn, people):
    alert_id = reading(api, people["patient"], 186, 118)["alert"]["id"]
    with pytest.raises(DBAPIError):
        with conn.begin_nested():
            conn.execute(text("update public.alerts set status = 'dismissed', dismissed_at = now(), "
                              "dismissal_reason = 'other', dismissal_note = 'x' where id = :id"), {"id": alert_id})


def test_database_requires_the_dismissal_record(api, conn, people):
    alert_id = notice(api, people["patient"])
    with pytest.raises(DBAPIError):
        with conn.begin_nested():
            conn.execute(text("update public.alerts set status = 'dismissed' where id = :id"), {"id": alert_id})


def test_audit_log_is_append_only(api, conn, people):
    notice(api, people["patient"])
    for stmt in ("update public.audit_log set actor = null", "delete from public.audit_log",
                 "truncate public.audit_log"):
        with pytest.raises(DBAPIError, match="append-only"):
            with conn.begin_nested():
                conn.execute(text(stmt))


# ---------------------------------------------------------------- timeline
def test_timeline_of_a_dismissed_then_reviewed_notice(api, people):
    p, doc = people["patient"], people["doctor"]
    alert_id = notice(api, p)
    reading(api, p, 147, 91)  # attached to the same notice
    move(api, alert_id, p, "acknowledged")
    dismiss(api, alert_id, p, reason="other", note="Remeasured after rest: 128/82.")
    move(api, alert_id, doc, "reviewed")
    r = events(api, alert_id, doc)
    assert r.status_code == 200
    ev = r.json()
    # The test runs in one transaction (one now()), so the attachment ties with the audit rows; audit order holds.
    assert sorted(e["kind"] for e in ev) == ["created", "measurement_attached", "status_changed", "status_changed",
                                             "status_changed"]
    ev = [e for e in ev if e["kind"] != "measurement_attached"]
    assert ev[0] | {"at": None} == {"at": None, "kind": "created", "actor_role": "rule", "from_status": None,
                                    "to_status": "open", "level": "notice", "note": None}
    changes = [(e["actor_role"], e["from_status"], e["to_status"]) for e in ev if e["kind"] == "status_changed"]
    assert changes == [("patient", "open", "acknowledged"), ("patient", "acknowledged", "dismissed"),
                       ("doctor", "dismissed", "reviewed")]
    assert ev[2]["note"] == "Remeasured after rest: 128/82."
    assert [e["at"] for e in ev] == sorted(e["at"] for e in ev)


def test_timeline_shows_a_level_raise(api, people):
    p = people["patient"]
    alert_id = reading(api, p, 186, 118)["alert"]["id"]
    symptoms(api, p, ["chest_pain"])  # raises the open severe episode to emergency
    kinds = [(e["kind"], e["level"]) for e in events(api, alert_id, p).json()]
    assert kinds[0] == ("created", "severe") and ("level_raised", "emergency") in kinds


def test_timeline_never_exposes_user_ids_or_raw_audit_rows(api, people):
    p, doc = people["patient"], people["doctor"]
    alert_id = notice(api, p)
    dismiss(api, alert_id, doc)
    raw = events(api, alert_id, p).text
    assert str(p) not in raw and str(doc) not in raw and "old_data" not in raw and "new_data" not in raw


@pytest.mark.parametrize("who", ["other", "stranger", "former"])
def test_timeline_access_matches_the_alert(api, people, who):
    alert_id = notice(api, people["patient"])
    assert events(api, alert_id, people[who]).status_code == 403
