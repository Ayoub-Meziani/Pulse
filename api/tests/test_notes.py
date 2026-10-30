"""Step 8: private doctor notes. Assigned doctors read and write; the patient sees advice only; nothing leaks."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text

from conftest import assign, auth_header, new_user

pytestmark = pytest.mark.db
API = "/api/v1"
SECRET = "PRIVATE-CLINICAL-NOTE-7f3a suspected white-coat effect"


@pytest.fixture
def team(conn):
    patient, other = new_user(conn, "patient", "Patient One"), new_user(conn, "patient")
    doctor, colleague = new_user(conn, "doctor", "Dr Assigned"), new_user(conn, "doctor", "Dr Colleague")
    stranger, former, admin = new_user(conn, "doctor"), new_user(conn, "doctor"), new_user(conn, "admin")
    assign(conn, doctor, patient)
    assign(conn, colleague, patient)
    assign(conn, former, patient, status="ended")
    assign(conn, stranger, other)
    return dict(patient=patient, other=other, doctor=doctor, colleague=colleague, stranger=stranger,
                former=former, admin=admin)


def write(api, team, body=None, who="doctor"):
    return api.post(f"{API}/patients/{team['patient']}/notes", json=body or {"note": SECRET},
                    headers=auth_header(team[who]))


def read(api, team, who):
    return api.get(f"{API}/patients/{team['patient']}/notes", headers=auth_header(team[who]))


def test_assigned_doctor_writes_and_reads_full_note(api, team):
    follow = (datetime.now(timezone.utc) + timedelta(days=14)).replace(microsecond=0)
    r = write(api, team, {"note": SECRET, "advice": "Measure twice each morning.", "follow_up_at": follow.isoformat()})
    assert r.status_code == 201
    n = r.json()
    assert (n["note"], n["advice"], n["doctor_id"], n["doctor_name"]) == (
        SECRET, "Measure twice each morning.", str(team["doctor"]), "Dr Assigned")
    assert datetime.fromisoformat(n["follow_up_at"]) == follow and n["created_at"]
    listed = read(api, team, "doctor").json()
    assert [x["id"] for x in listed] == [n["id"]] and listed[0]["note"] == SECRET
    assert read(api, team, "colleague").json()[0]["note"] == SECRET  # the care team shares clinical notes


def test_patient_sees_advice_only_and_never_the_note(api, team):
    write(api, team, {"note": SECRET, "advice": "Reduce salt."})
    write(api, team, {"note": SECRET + " second", "follow_up_at": datetime.now(timezone.utc).isoformat()})
    write(api, team, {"note": SECRET + " private only"})  # nothing for the patient: not listed at all
    r = read(api, team, "patient")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2 and all(n["note"] is None for n in body)
    assert {n["advice"] for n in body} == {"Reduce salt.", None}
    assert SECRET not in r.text and "PRIVATE" not in r.text


@pytest.mark.parametrize("who", ["stranger", "former", "admin", "other"])
def test_others_cannot_read_notes_and_errors_do_not_leak(api, team, who):
    write(api, team, {"note": SECRET, "advice": "Reduce salt."})
    r = read(api, team, who)
    assert r.status_code == 403 and SECRET not in r.text and "salt" not in r.text


@pytest.mark.parametrize("who", ["patient", "stranger", "former", "admin", "other"])
def test_only_assigned_doctors_write_notes(api, conn, team, who):
    assert write(api, team, who=who).status_code == 403
    assert conn.execute(text("select count(*) from public.doctor_notes where patient_id = :p"),
                        {"p": team["patient"]}).scalar_one() == 0


def test_note_author_is_the_caller_and_creation_is_audited(api, conn, team):
    r = write(api, team, {"note": SECRET, "doctor_id": str(team["colleague"])})  # a doctor_id in the body is ignored
    nid = r.json()["id"]
    assert r.json()["doctor_id"] == str(team["doctor"])
    rows = conn.execute(text("select action, actor from public.audit_log where table_name = 'doctor_notes' "
                             "and row_id = :id"), {"id": nid}).all()
    assert [tuple(x) for x in rows] == [("INSERT", team["doctor"])]


def test_note_modifications_are_audited_with_old_and_new_values(conn, team):
    # The API has no edit endpoint (contract v1); the database still audits any change and touches updated_at.
    nid = conn.execute(text("insert into public.doctor_notes (doctor_id, patient_id, note) values (:d, :p, 'v1') "
                            "returning id"), {"d": team["doctor"], "p": team["patient"]}).scalar_one()
    conn.execute(text("update public.doctor_notes set note = 'v2' where id = :id"), {"id": nid})
    rows = conn.execute(text("select action, old_data->>'note', new_data->>'note' from public.audit_log "
                             "where table_name = 'doctor_notes' and row_id = :id order by id"), {"id": nid}).all()
    assert [tuple(x) for x in rows] == [("INSERT", None, "v1"), ("UPDATE", "v1", "v2")]


def test_invalid_note_errors_do_not_echo_the_text(api, team):
    r = write(api, team, {"note": SECRET + "x" * 8000})
    assert r.status_code == 422 and SECRET not in r.text
    assert write(api, team, {"note": ""}).status_code == 422


def test_notes_never_leak_into_other_responses(api, team):
    p = team["patient"]
    write(api, team, {"note": SECRET, "advice": "ADVICE-ONLY-FOR-NOTES-ENDPOINT"})
    api.post(f"{API}/patients/{p}/measurements", json={"systolic": 185, "diastolic": 100}, headers=auth_header(p))
    e = api.post(f"{API}/patients/{p}/emergency-events",
                 json={"id": str(uuid4()), "trigger_reason": "manual",
                       "started_at": datetime.now(timezone.utc).isoformat()}, headers=auth_header(p)).json()
    paths = [f"/patients/{p}/emergency-card", f"/patients/{p}/alerts?status=all", f"/patients/{p}/summary",
             f"/patients/{p}/profile", f"/patients/{p}/measurements", f"/patients/{p}/emergency-events",
             f"/emergency-events/{e['id']}/report", f"/patients/{p}/care-plan", "/me"]
    for who in ("patient", "doctor"):
        for path in paths:
            r = api.get(API + path, headers=auth_header(team[who]))
            assert r.status_code in (200, 404), (who, path, r.status_code)
            assert SECRET not in r.text and "ADVICE-ONLY" not in r.text, (who, path)
    doctor_list = api.get(f"{API}/patients", headers=auth_header(team["doctor"]))
    assert doctor_list.status_code == 200 and SECRET not in doctor_list.text
    pred = api.get(f"{API}/patients/{p}/predictions/latest", headers=auth_header(team["doctor"]))
    assert SECRET not in pred.text
