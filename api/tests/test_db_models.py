"""The ORM mappings and vocabularies match the migrated schema (catches drift from supabase/migrations)."""
import pytest
from sqlalchemy import inspect, select, text

from app import models, vocab
from app.analysis.rules import KNOWN_SYMPTOMS
from app.db import Base

from conftest import new_user

pytestmark = pytest.mark.db

MAPPED = [m for m in Base.registry.mappers]


def _check(conn, constraint: str) -> str:
    return conn.execute(text("select pg_get_constraintdef(oid) from pg_constraint where conname = :n"),
                        {"n": constraint}).scalar_one()


@pytest.mark.parametrize("mapper", MAPPED, ids=lambda m: m.class_.__name__)
def test_every_mapped_column_exists(conn, mapper):
    table = mapper.local_table
    cols = {c["name"] for c in inspect(conn).get_columns(table.name, schema=table.schema or "public")}
    assert {c.name for c in table.columns} <= cols
    conn.execute(select(mapper.class_).limit(1)).all()  # the SELECT the API will issue works


def test_all_api_tables_are_mapped():
    names = {m.local_table.name for m in MAPPED}
    assert {"profiles", "patient_profiles", "doctor_patient_assignments", "care_plans", "measurements",
            "symptom_reports", "alerts", "alert_measurements", "trusted_contacts", "emergency_events",
            "doctor_notes", "journal_entries", "ml_predictions", "users", "devices", "wearable_samples"} <= names


def test_alert_classes_exist_in_database(conn):
    definition = _check(conn, "alerts_alert_class_check")
    for alert_class in vocab.LEVEL_TO_ALERT_CLASS.values():
        assert f"'{alert_class}'" in definition


def test_symptom_codes_match_database(conn):
    definition = _check(conn, "symptom_reports_symptoms_check")
    assert {code for code in KNOWN_SYMPTOMS if f"'{code}'" in definition} == KNOWN_SYMPTOMS


def test_manual_reading_vocabulary_is_accepted(conn, db):
    patient = new_user(conn)
    m = models.Measurement(patient_id=patient, source=vocab.MANUAL_SOURCE, provenance=vocab.MANUAL_PROVENANCE,
                           method=vocab.MANUAL_METHOD, systolic=128, diastolic=82,
                           measured_at=conn.execute(text("select now() - interval '1 hour'")).scalar_one())
    db.add(m)
    db.flush()
    assert (m.validation_status, m.validation_policy_version) == ("valid", "pulse-v1")  # set by the trigger


def test_signup_trigger_creates_patient_profile(conn, db):
    uid = new_user(conn, role="doctor", name="Dr Test")
    p = db.get(models.Profile, uid)
    assert (p.role, p.display_name, p.timezone) == ("doctor", "Dr Test", "Africa/Algiers")
