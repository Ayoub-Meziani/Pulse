"""Step 6: doctor patient list, summary, profile, trusted contacts, care plan, emergency card.

Covers permissions (own patient / active assignment), privacy (no doctor notes, no M6 fields, no
wearable data where they do not belong), trusted-contact consent, and simulated-data labelling.
"""
import json
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from conftest import assign, auth_header, new_user

pytestmark = pytest.mark.db
API = "/api/v1"
PRIVATE_NOTE = "PRIVATE-CLINICAL-NOTE-do-not-show"
M6_KEYS = {"sex", "smoking_status", "condition_codes", "bread_portions_per_day", "adds_salt_at_table",
           "salty_processed_food", "preferred_language"}


def ago(**kw):
    return (datetime.now(timezone.utc) - timedelta(**kw)).isoformat()


def post_reading(api, patient, s, d, **body):
    r = api.post(f"{API}/patients/{patient}/measurements", json={"systolic": s, "diastolic": d} | body,
                 headers=auth_header(patient))
    assert r.status_code == 201, r.text
    return r.json()


def simulated_reading(conn, patient, s, d, at):
    conn.execute(text("insert into public.measurements (patient_id, source, provenance, systolic, diastolic, measured_at) "
                      "values (:p, 'simulated', 'simulated', :s, :d, :at)"), {"p": patient, "s": s, "d": d, "at": at})


def get(api, path, who):
    return api.get(f"{API}{path}", headers=auth_header(who))


PROFILE = {"full_name": "Nadia M.", "timezone": "Africa/Algiers", "birth_year": 1968,
           "relevant_conditions": ["hypertension", "type 2 diabetes"], "allergies": "penicillin",
           "medication_context": "amlodipine 5 mg (as written by the patient)", "regular_clinic": "Polyclinique Bab El Oued",
           "consent_location": True}
CONTACT = {"name": "Samira M.", "relationship": "sister", "phone": "+213 555 11 22 33", "contact_consented": True}


@pytest.fixture
def team(conn):
    patient = new_user(conn, "patient", "Nadia M.")
    other = new_user(conn, "patient", "Other P.")
    doctor = new_user(conn, "doctor", "Dr. Amina S.")
    stranger, former = new_user(conn, "doctor"), new_user(conn, "doctor")
    admin = new_user(conn, "admin")
    assign(conn, doctor, patient)
    assign(conn, former, patient, status="ended")
    return dict(patient=patient, other=other, doctor=doctor, stranger=stranger, former=former, admin=admin)


# ---------------------------------------------------------------- doctor patient list
def test_doctor_list_shows_only_actively_assigned_patients_most_urgent_first(api, conn, team):
    doc = team["doctor"]
    calm, quiet = new_user(conn, "patient", "Calm"), new_user(conn, "patient", "Quiet")
    unassigned = new_user(conn, "patient", "Not mine")
    for p in (calm, quiet):
        assign(conn, doc, p)
    post_reading(api, calm, 120, 78, measured_at=ago(hours=1))
    post_reading(api, team["patient"], 186, 118)                      # severe -> most urgent
    post_reading(api, unassigned, 190, 120)
    r = get(api, "/patients", doc)
    assert r.status_code == 200
    names = [p["full_name"] for p in r.json()]
    assert names == ["Nadia M.", "Quiet", "Calm"]                    # severe first; then no reading before oldest
    first = r.json()[0]
    assert (first["highest_active_alert"], first["active_alert_count"]) == ("severe", 1)
    assert first["latest_measurement"]["systolic"] == 186 and first["latest_measurement"]["source"] == "manual"


def test_doctor_list_age_latest_valid_reading_and_simulated_label(api, conn, team):
    p, doc = team["patient"], team["doctor"]
    assert api.put(f"{API}/patients/{p}/profile", json=PROFILE, headers=auth_header(p)).status_code == 200
    simulated_reading(conn, p, 132, 84, datetime.now(timezone.utc) - timedelta(hours=3))
    post_reading(api, p, 120, 130)                                     # invalid: must not become "latest"
    item = get(api, "/patients", doc).json()[0]
    assert item["age"] == date.today().year - 1968
    latest = item["latest_measurement"]
    assert (latest["systolic"], latest["source"], latest["provenance"]) == (132, "simulated", "simulated")


@pytest.mark.parametrize("who", ["patient", "admin"])
def test_doctor_list_is_doctor_only(api, team, who):
    assert get(api, "/patients", team[who]).status_code == 403


def test_ended_assignment_disappears_from_doctor_list(api, team):
    assert get(api, "/patients", team["former"]).json() == []


# ---------------------------------------------------------------- summary
def test_summary_counts_and_averages_valid_readings_only(api, team):
    p = team["patient"]
    for days, (s, d) in enumerate([(150, 95), (148, 92), (152, 96)], start=1):
        post_reading(api, p, s, d, measured_at=ago(days=days))
    post_reading(api, p, 262, 120, measured_at=ago(hours=5))          # needs_review (unusual) -> counted apart
    post_reading(api, p, 120, 130, measured_at=ago(hours=4))          # invalid -> counted apart
    s = get(api, f"/patients/{p}/summary", p).json()
    assert (s["count_7d"], s["count_needs_review_7d"], s["count_invalid_7d"]) == (3, 1, 1)
    assert s["avg_systolic_7d"] == 150.0 and s["max_systolic_7d"] == 152
    assert s["timezone"] == "Africa/Algiers" and s["target"] == {"systolic": 140, "diastolic": 90, "is_default": True}
    assert s["pct_above_target_7d"] == 100.0 and s["trend"] == "insufficient_data"


@pytest.mark.parametrize("who,status", [("patient", 200), ("doctor", 200), ("other", 403), ("stranger", 403),
                                        ("former", 403), ("admin", 403)])
def test_summary_permissions(api, team, who, status):
    assert get(api, f"/patients/{team['patient']}/summary", team[who]).status_code == status


def test_wearable_samples_never_count_as_blood_pressure(api, conn, team):
    p = team["patient"]
    device = conn.execute(text("insert into public.devices (patient_id, device_type, bp_capability, label) "
                               "values (:p, 'wearable', 'none', 'ring') returning id"), {"p": p}).scalar_one()
    conn.execute(text("insert into public.wearable_samples (patient_id, device_id, metric, value, unit, measured_at, source) "
                      "values (:p, :d, 'heart_rate', 140, 'bpm', now(), 'simulated')"), {"p": p, "d": device})
    assert get(api, f"/patients/{p}/measurements", p).json() == []
    assert get(api, f"/patients/{p}/summary", p).json()["count_7d"] == 0
    assert get(api, f"/patients/{p}/alerts", p).json() == []


# ---------------------------------------------------------------- profile
def test_profile_defaults_then_full_replacement(api, team):
    p = team["patient"]
    before = get(api, f"/patients/{p}/profile", p).json()
    assert before["relevant_conditions"] == [] and before["consent_location"] is False and before["birth_year"] is None
    r = api.put(f"{API}/patients/{p}/profile", json=PROFILE, headers=auth_header(p))
    assert r.status_code == 200
    after = r.json()
    assert after["allergies"] == "penicillin" and after["birth_year"] == 1968 and after["consent_location"] is True
    assert get(api, f"/patients/{p}/profile", team["doctor"]).json() == after


def test_profile_never_exposes_or_erases_m6_fields(api, conn, team):
    p = team["patient"]
    api.put(f"{API}/patients/{p}/profile", json=PROFILE, headers=auth_header(p))
    conn.execute(text("update public.patient_profiles set sex = 'female', smoking_status = 'never' where user_id = :p"),
                 {"p": p})
    body = get(api, f"/patients/{p}/profile", p).json()
    assert not (M6_KEYS & set(body))
    api.put(f"{API}/patients/{p}/profile", json=PROFILE | {"allergies": None}, headers=auth_header(p))
    kept = conn.execute(text("select sex, smoking_status from public.patient_profiles where user_id = :p"), {"p": p}).one()
    assert tuple(kept) == ("female", "never")                          # data the API does not manage stays intact


@pytest.mark.parametrize("change,field", [({"birth_year": date.today().year + 1}, "birth_year"),
                                          ({"timezone": "Mars/Olympus"}, "timezone")])
def test_profile_validation(api, team, change, field):
    r = api.put(f"{API}/patients/{team['patient']}/profile", json=PROFILE | change, headers=auth_header(team["patient"]))
    assert r.status_code == 422 and r.json()["error"]["details"][0]["field"] == field


@pytest.mark.parametrize("who", ["doctor", "other", "stranger", "admin"])
def test_only_the_patient_edits_their_profile(api, team, who):
    r = api.put(f"{API}/patients/{team['patient']}/profile", json=PROFILE, headers=auth_header(team[who]))
    assert r.status_code == 403


# ---------------------------------------------------------------- trusted contacts
def test_contact_needs_explicit_consent_and_records_when(api, conn, team):
    p = team["patient"]
    url = f"{API}/patients/{p}/trusted-contacts"
    for bad in ({k: v for k, v in CONTACT.items() if k != "contact_consented"}, CONTACT | {"contact_consented": False}):
        assert api.post(url, json=bad, headers=auth_header(p)).status_code == 422
    r = api.post(url, json=CONTACT, headers=auth_header(p))
    assert r.status_code == 201 and r.json()["consented_at"]
    assert conn.execute(text("select count(*) from public.trusted_contacts where patient_id = :p"), {"p": p}).scalar_one() == 1


def test_changing_a_contacts_phone_requires_new_consent(api, team):
    p = team["patient"]
    c = api.post(f"{API}/patients/{p}/trusted-contacts", json=CONTACT, headers=auth_header(p)).json()
    r = api.patch(f"{API}/trusted-contacts/{c['id']}", json={"phone": "+213 555 99 99 99"}, headers=auth_header(p))
    assert r.status_code == 422 and r.json()["error"]["code"] == "consent_required"
    ok = api.patch(f"{API}/trusted-contacts/{c['id']}", json={"relationship": "sister (lives nearby)"}, headers=auth_header(p))
    assert ok.status_code == 200 and ok.json()["phone"] == CONTACT["phone"]


@pytest.mark.parametrize("who", ["other", "doctor", "stranger"])
def test_someone_elses_contact_is_not_found(api, team, who):
    p = team["patient"]
    c = api.post(f"{API}/patients/{p}/trusted-contacts", json=CONTACT, headers=auth_header(p)).json()
    assert api.patch(f"{API}/trusted-contacts/{c['id']}", json={"active": False}, headers=auth_header(team[who])).status_code == 404
    assert api.delete(f"{API}/trusted-contacts/{c['id']}", headers=auth_header(team[who])).status_code == 404


@pytest.mark.parametrize("who,read,write", [("doctor", 200, 403), ("other", 403, 403), ("former", 403, 403)])
def test_contact_list_permissions(api, team, who, read, write):
    url = f"{API}/patients/{team['patient']}/trusted-contacts"
    assert api.get(url, headers=auth_header(team[who])).status_code == read
    assert api.post(url, json=CONTACT, headers=auth_header(team[who])).status_code == write


def test_patient_removes_a_contact(api, conn, team):
    p = team["patient"]
    c = api.post(f"{API}/patients/{p}/trusted-contacts", json=CONTACT, headers=auth_header(p)).json()
    assert api.delete(f"{API}/trusted-contacts/{c['id']}", headers=auth_header(p)).status_code == 204
    assert get(api, f"/patients/{p}/trusted-contacts", p).json() == []


# ---------------------------------------------------------------- care plan
def test_care_plan_default_then_doctor_sets_new_target_used_by_the_rules(api, conn, team):
    p, doc = team["patient"], team["doctor"]
    default = get(api, f"/patients/{p}/care-plan", p).json()
    assert (default["id"], default["target_systolic"], default["is_default"]) == (None, 140, True)
    body = {"target_systolic": 130, "target_diastolic": 80, "clinician_guidance": "Measure morning and evening."}
    first = api.put(f"{API}/patients/{p}/care-plan", json=body, headers=auth_header(doc)).json()
    second = api.put(f"{API}/patients/{p}/care-plan", json=body | {"target_systolic": 135}, headers=auth_header(doc)).json()
    assert second["target_systolic"] == 135 and second["is_default"] is False
    rows = conn.execute(text("select id, status, supersedes_id from public.care_plans where patient_id = :p "
                             "order by created_at"), {"p": p}).all()
    assert [r.status for r in rows] == ["superseded", "active"] and rows[1].supersedes_id == rows[0].id
    assert str(rows[0].id) == first["id"]
    ev = post_reading(api, p, 136, 78)["evaluation"]
    assert ev["level"] == "notice" and "your target (135/80)" in ev["reason"]


@pytest.mark.parametrize("who", ["patient", "stranger", "former", "admin"])
def test_only_the_assigned_doctor_sets_the_care_plan(api, team, who):
    body = {"target_systolic": 130, "target_diastolic": 80, "clinician_guidance": "x"}
    assert api.put(f"{API}/patients/{team['patient']}/care-plan", json=body, headers=auth_header(team[who])).status_code == 403


@pytest.mark.parametrize("change", [{"target_systolic": 100, "target_diastolic": 100},
                                    {"review_date": (date.today() - timedelta(days=3)).isoformat()}])
def test_care_plan_validation(api, team, change):
    body = {"target_systolic": 130, "target_diastolic": 80, "clinician_guidance": "x"} | change
    r = api.put(f"{API}/patients/{team['patient']}/care-plan", json=body, headers=auth_header(team["doctor"]))
    assert r.status_code == 422


# ---------------------------------------------------------------- emergency card
def test_emergency_card_has_the_minimum_and_nothing_private(api, conn, team):
    p, doc = team["patient"], team["doctor"]
    api.put(f"{API}/patients/{p}/profile", json=PROFILE, headers=auth_header(p))
    conn.execute(text("update public.patient_profiles set regular_doctor_id = :d, sex = 'female' where user_id = :p"),
                 {"d": doc, "p": p})
    conn.execute(text("insert into public.doctor_notes (doctor_id, patient_id, note, advice) values (:d, :p, :n, 'Rest')"),
                 {"d": doc, "p": p, "n": PRIVATE_NOTE})
    later = CONTACT | {"name": "Later Contact", "phone": "+213 555 44 44 44"}
    api.post(f"{API}/patients/{p}/trusted-contacts", json=CONTACT, headers=auth_header(p))
    api.post(f"{API}/patients/{p}/trusted-contacts", json=later, headers=auth_header(p))
    simulated_reading(conn, p, 134, 86, datetime.now(timezone.utc) - timedelta(hours=1))
    r = get(api, f"/patients/{p}/emergency-card", p)
    assert r.status_code == 200
    card = r.json()
    assert card["full_name"] == "Nadia M." and card["age"] == date.today().year - 1968
    assert card["allergies"] == "penicillin" and card["regular_doctor_name"] == "Dr. Amina S."
    assert card["primary_contact"] == {"name": "Samira M.", "relationship": "sister", "phone": "+213 555 11 22 33"}
    assert card["last_reading"]["source"] == "simulated" and card["last_reading"]["provenance"] == "simulated"
    raw = json.dumps(card)
    assert PRIVATE_NOTE not in raw and "Rest" not in raw and not (M6_KEYS & set(card))
    assert set(card) == {"full_name", "age", "relevant_conditions", "allergies", "medication_context",
                         "primary_contact", "regular_doctor_name", "regular_clinic", "last_reading", "generated_at"}


def test_inactive_contact_is_never_the_emergency_contact(api, team):
    p = team["patient"]
    c = api.post(f"{API}/patients/{p}/trusted-contacts", json=CONTACT, headers=auth_header(p)).json()
    api.patch(f"{API}/trusted-contacts/{c['id']}", json={"active": False}, headers=auth_header(p))
    assert get(api, f"/patients/{p}/emergency-card", p).json()["primary_contact"] is None


@pytest.mark.parametrize("who,status", [("patient", 200), ("doctor", 200), ("other", 403), ("stranger", 403),
                                        ("former", 403), ("admin", 403)])
def test_emergency_card_permissions(api, team, who, status):
    assert get(api, f"/patients/{team['patient']}/emergency-card", team[who]).status_code == status


def test_unknown_patient_gets_403_not_404(api, team):
    assert get(api, f"/patients/{uuid.uuid4()}/emergency-card", team["doctor"]).status_code == 403


def test_partial_profile_put_is_refused_and_erases_nothing(api, team):
    p = team["patient"]
    api.put(f"{API}/patients/{p}/profile", json=PROFILE, headers=auth_header(p))
    r = api.put(f"{API}/patients/{p}/profile", json={"full_name": "Only a name"}, headers=auth_header(p))
    assert r.status_code == 422
    assert get(api, f"/patients/{p}/profile", p).json()["allergies"] == "penicillin"
