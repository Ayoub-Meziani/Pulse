"""Patient journal: GET/POST /patients/{id}/journal and POST /journal/{id}/review (conception §14.1, §14.2)."""
import uuid

import pytest
from sqlalchemy import text

from conftest import assign, auth_header, new_user

pytestmark = pytest.mark.db
API = "/api/v1"


@pytest.fixture
def team(conn):
    patient, other, doctor, stranger, former, admin = (new_user(conn, r) for r in
                                                       ("patient", "patient", "doctor", "doctor", "doctor", "admin"))
    assign(conn, doctor, patient)
    assign(conn, former, patient, status="ended")
    return dict(patient=patient, other=other, doctor=doctor, stranger=stranger, former=former, admin=admin)


def write(api, team, category="food", text_="Couscous au déjeuner, peu salé.", who="patient"):
    return api.post(f"{API}/patients/{team['patient']}/journal", headers=auth_header(team[who]),
                    json={"category": category, "entry_text": text_})


def test_patient_records_food_and_activity_and_reads_them_back(api, conn, team):
    food = write(api, team, "food").json()
    # Both inserts share now() inside the test transaction; date the first one earlier, as real requests would be.
    conn.execute(text("update public.journal_entries set created_at = now() - interval '1 hour' where id = :id"), {"id": food["id"]})
    r = write(api, team, "activity", "Marche 30 minutes après le dîner.")
    assert r.status_code == 201
    e = r.json()
    assert (e["category"], e["doctor_review_status"], e["reviewed_at"]) == ("activity", "not_reviewed", None)
    entries = api.get(f"{API}/patients/{team['patient']}/journal", headers=auth_header(team["patient"])).json()
    assert [x["category"] for x in entries] == ["activity", "food"]          # newest first
    only_food = api.get(f"{API}/patients/{team['patient']}/journal", params={"category": "food"},
                        headers=auth_header(team["patient"])).json()
    assert [x["category"] for x in only_food] == ["food"]


@pytest.mark.parametrize("category", ["symptoms", "food", "activity", "medication", "question", "other"])
def test_every_contract_category_is_accepted(api, team, category):
    assert write(api, team, category).status_code == 201


def test_unknown_category_and_empty_text_are_rejected(api, team):
    assert write(api, team, "sport").status_code == 422
    assert write(api, team, "food", "").status_code == 422
    r = write(api, team, "food", "   ")
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_failed"


@pytest.mark.parametrize("who", ["doctor", "other", "stranger", "admin"])
def test_only_the_patient_writes(api, team, who):
    assert write(api, team, who=who).status_code == 403


@pytest.mark.parametrize("who,status", [("patient", 200), ("doctor", 200), ("other", 403), ("stranger", 403),
                                        ("former", 403), ("admin", 403)])
def test_read_access(api, team, who, status):
    write(api, team)
    assert api.get(f"{API}/patients/{team['patient']}/journal", headers=auth_header(team[who])).status_code == status


def test_assigned_doctor_marks_reviewed_once(api, conn, team):
    entry = write(api, team, "question", "Puis-je faire du vélo ?").json()
    r = api.post(f"{API}/journal/{entry['id']}/review", headers=auth_header(team["doctor"]))
    assert r.status_code == 200 and r.json()["doctor_review_status"] == "reviewed" and r.json()["reviewed_at"]
    again = api.post(f"{API}/journal/{entry['id']}/review", headers=auth_header(team["doctor"]))
    assert again.json()["reviewed_at"] == r.json()["reviewed_at"]
    by = conn.execute(text("select reviewed_by from public.journal_entries where id = :id"), {"id": entry["id"]}).scalar()
    assert by == team["doctor"]
    patient_view = api.get(f"{API}/patients/{team['patient']}/journal", headers=auth_header(team["patient"])).json()
    assert patient_view[0]["doctor_review_status"] == "reviewed"


@pytest.mark.parametrize("who", ["patient", "other", "stranger", "former", "admin"])
def test_only_an_assigned_doctor_reviews(api, team, who):
    entry = write(api, team).json()
    assert api.post(f"{API}/journal/{entry['id']}/review", headers=auth_header(team[who])).status_code == 403


def test_reviewing_an_unknown_entry_is_404(api, team):
    assert api.post(f"{API}/journal/{uuid.uuid4()}/review", headers=auth_header(team["doctor"])).status_code == 404


def test_journal_entries_never_create_alerts(api, conn, team):
    write(api, team, "symptoms", "Douleur dans la poitrine ce matin.")  # free text is never interpreted
    n = conn.execute(text("select count(*) from public.alerts where patient_id = :p"), {"p": team["patient"]}).scalar()
    assert n == 0


def test_other_patients_entries_never_leak(api, team):
    api.post(f"{API}/patients/{team['other']}/journal", headers=auth_header(team["other"]),
             json={"category": "food", "entry_text": "autre patient"})
    assert api.get(f"{API}/patients/{team['patient']}/journal", headers=auth_header(team["patient"])).json() == []
