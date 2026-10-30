"""Database tests against the LOCAL PULSE Supabase stack only (never a shared database).

Each test runs in a transaction that is rolled back. Apply migrations + seed first:
    npx supabase@2.122.0 db reset
"""
import json
import os
import subprocess
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

import pytest

psycopg = pytest.importorskip("psycopg")

from pulse_data import simulate as sim  # noqa: E402
from pulse_data.ingest import LOCAL_DB, DuplicateFileError, Reading, import_readings  # noqa: E402

DB = os.environ.get("PULSE_TEST_DATABASE_URL", LOCAL_DB)
IDS = {u.key: u.id for u in sim.PATIENTS}
AMINA, KARIM, NADIA, YACINE = (IDS[k] for k in ("controlled", "rising", "severe_event", "sparse_unassigned"))
ASSIGNED = {u.id for u in sim.PATIENTS if u.assigned}  # Amina, Karim, Nadia + 8 cohort patients
Denied = psycopg.errors.InsufficientPrivilege


@pytest.fixture(scope="session")
def _conn():
    try:
        conn = psycopg.connect(DB, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError as e:
        pytest.skip(f"local PULSE database not reachable ({e.__class__.__name__}); run `supabase start`")
    if conn.execute("select to_regprocedure('private.validate_measurement()')").fetchone()[0] is None:
        pytest.skip("connected database does not have the PULSE schema; run `supabase db reset`")
    yield conn
    conn.close()


@pytest.fixture
def db(_conn):
    with _conn.transaction(force_rollback=True):
        yield _conn


def as_user(db, uid, role="authenticated"):
    db.execute(f"set local role {role}")
    db.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({"sub": uid, "role": role}),))


def new_user(db, role="patient"):
    uid = str(uuid.uuid4())
    db.execute("insert into auth.users (id, email) values (%s, %s)", (uid, f"{uid}@pulse.test"))
    db.execute("update public.profiles set role = %s where id = %s", (role, uid))
    return uid


def reading(db, patient, systolic, diastolic, pulse=None, at=None, **cols):
    cols = {"patient_id": patient, "source": "manual", "provenance": "measured", "systolic": systolic,
            "diastolic": diastolic, "pulse": pulse,
            "measured_at": at or datetime.now(timezone.utc) - timedelta(hours=1)} | cols
    return db.execute(f"insert into public.measurements ({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))})"
                      " returning validation_status, quality_flags", list(cols.values())).fetchone()


def fails(db, exc, query, params=()):
    with pytest.raises(exc):
        with db.transaction():
            db.execute(query, params)


# ---------------------------------------------------------------- seed

def test_seed_loaded(db):
    counts = dict(db.execute("select patient_id::text, count(*) from public.measurements group by 1").fetchall())
    assert set(counts) == set(IDS.values()) and all(n >= 10 for n in counts.values())
    assert db.execute("select count(*) from public.measurements where provenance <> 'simulated'").fetchone()[0] == 0
    flags = db.execute("select array_agg(distinct f) from public.measurements, unnest(quality_flags) f"
                       " where patient_id = %s", (YACINE,)).fetchone()[0]
    assert {"possible_duplicate", "systolic_not_above_diastolic"} <= set(flags)
    assert db.execute("select count(*) from public.doctor_patient_assignments where status = 'active'").fetchone()[0] == len(ASSIGNED)
    complete = db.execute("select count(*) from public.patient_profiles where sex is not null and birth_year is not null"
                          " and smoking_status is not null and 'hypertension' = any(condition_codes)").fetchone()[0]
    assert complete == len(IDS)
    for table in ("body_measurements", "wearable_samples"):
        assert db.execute(f"select count(*) from public.{table} where source = 'simulated'").fetchone()[0] > 0, table


# ---------------------------------------------------------------- validation policy (trigger)

@pytest.mark.parametrize("values, cols, status, flag", [
    ((128, 82, 70), {}, "valid", None),
    ((186, 118, 96), {}, "valid", None),  # severe is an alert matter, not a data-quality one
    ((82, 128, 70), {}, "invalid", "systolic_not_above_diastolic"),
    ((320, 100, 70), {}, "invalid", "systolic_implausible"),
    ((120, 80, 300), {}, "invalid", "pulse_implausible"),
    ((255, 140, 90), {}, "needs_review", "unusual_value_recheck"),
    ((128, 82, None), {"provenance": "estimated", "method": "wearable_estimate"}, "needs_review", "estimated_not_cuff"),
    ((128, 82, None), {"quality_flags": ["body_movement"]}, "needs_review", "body_movement"),
    ((128, 82, None), {"validation_status": "valid", "measured_at": datetime.now(timezone.utc) + timedelta(hours=2)},
     "invalid", "measured_in_future"),
])
def test_validation_policy(db, values, cols, status, flag):
    got_status, flags = reading(db, new_user(db), *values, **cols)
    assert got_status == status
    assert (flag in flags) if flag else flags == []


def test_possible_duplicate_is_flagged_not_dropped(db):
    p, at = new_user(db), datetime.now(timezone.utc) - timedelta(hours=3)
    assert reading(db, p, 140, 90, 70, at=at)[0] == "valid"
    assert reading(db, p, 140, 90, 70, at=at + timedelta(minutes=1)) == ("needs_review", ["possible_duplicate"])


def test_labelling_constraints(db):
    p = new_user(db)
    fails(db, psycopg.errors.CheckViolation, "insert into public.measurements (patient_id, source, provenance, systolic,"
          " diastolic, measured_at) values (%s, 'simulated', 'measured', 120, 80, now())", (p,))
    fails(db, psycopg.errors.CheckViolation, "insert into public.measurements (patient_id, source, method, systolic,"
          " diastolic, measured_at) values (%s, 'manual', 'wearable_estimate', 120, 80, now())", (p,))
    fails(db, psycopg.errors.CheckViolation, "insert into public.measurements (patient_id, source, unit, systolic,"
          " diastolic, measured_at) values (%s, 'manual', 'kPa', 16, 11, now())", (p,))


# ---------------------------------------------------------------- ingestion batches

def test_import_dedups_device_readings_and_refuses_same_file(db):
    p = new_user(db)
    device = db.execute("insert into public.devices (patient_id, device_type, bp_capability) values (%s, 'bp_cuff',"
                        " 'measured') returning id", (p,)).fetchone()[0]
    t = datetime.now(timezone.utc) - timedelta(days=1)
    rs = [Reading(t, 130, 85, 70, external_id="a", row=2), Reading(t + timedelta(hours=1), 135, 88, external_id="b", row=3),
          Reading(t, 130, 85, 70, external_id="a", row=4), Reading(t, 1500, 85, row=5)]
    s = import_readings(db, p, rs, source="device_sync", provenance="measured", method="cuff_oscillometric",
                        device_id=device, sha256="0" * 64)
    assert (s["rows_inserted"], s["rows_duplicate"], s["rows_rejected"]) == (2, 1, 1)
    assert s["rejections"][0]["row"] == 5 and s["rejections"][0]["reasons"][0].startswith("refused_by_database")
    batch = db.execute("select rows_inserted, rows_duplicate, rows_rejected from public.ingestion_batches where id = %s",
                       (s["batch_id"],)).fetchone()
    assert batch == (2, 1, 1)
    with pytest.raises(DuplicateFileError):
        import_readings(db, p, rs[:1], source="device_sync", provenance="measured", device_id=device, sha256="0" * 64)


def test_reading_cannot_use_another_patients_device(db):
    device = db.execute("select id from public.devices where patient_id = %s", (KARIM,)).fetchone()[0]
    fails(db, psycopg.errors.ForeignKeyViolation, "insert into public.measurements (patient_id, device_id, source,"
          " systolic, diastolic, measured_at) values (%s, %s, 'manual', 120, 80, now())", (AMINA, device))


# ---------------------------------------------------------------- other integrity rules

def test_one_active_care_plan_and_roles(db):
    fails(db, psycopg.errors.UniqueViolation, "insert into public.care_plans (patient_id, clinician_id, effective_from,"
          " clinician_guidance) values (%s, %s, current_date, 'x')", (AMINA, sim.DOCTOR.id))
    fails(db, psycopg.errors.CheckViolation, "insert into public.care_plans (patient_id, clinician_id, effective_from,"
          " clinician_guidance, status) values (%s, %s, current_date, 'x', 'draft')", (AMINA, KARIM))
    fails(db, psycopg.errors.CheckViolation, "insert into public.doctor_patient_assignments (doctor_id, patient_id)"
          " values (%s, %s)", (KARIM, AMINA))


@pytest.mark.parametrize("cols", [
    "category, started_at, steps) values (%s, 'meal', now(), 100",
    "category, started_at, sodium_mg) values (%s, 'meal', now(), 900",
    "category, started_at) values (%s, 'sleep', now() - interval '8 hours'",
    "category, started_at, ended_at) values (%s, 'activity', now(), now() - interval '1 hour'",
])
def test_lifestyle_constraints(db, cols):
    fails(db, psycopg.errors.CheckViolation, f"insert into public.lifestyle_logs (patient_id, {cols})", (AMINA,))


def test_alert_once_per_event_and_audited(db):
    m = db.execute("select id from public.measurements where patient_id = %s limit 1", (NADIA,)).fetchone()[0]
    q = ("insert into public.alerts (patient_id, measurement_id, alert_class, rule_code, reason)"
         " values (%s, %s, 'data_quality_review', %s, 'test') returning id")
    alert = db.execute(q, (NADIA, m, "DATA_INVALID")).fetchone()[0]
    fails(db, psycopg.errors.UniqueViolation, q, (NADIA, m, "DATA_INVALID"))
    fails(db, psycopg.errors.ForeignKeyViolation, q, (AMINA, m, "OTHER"))  # measurement belongs to another patient
    assert db.execute("select action from public.audit_log where table_name = 'alerts' and row_id = %s",
                      (alert,)).fetchall() == [("INSERT",)]


# ---------------------------------------------------------------- row-level security

def visible_patients(db, table="measurements"):
    return {str(r[0]) for r in db.execute(f"select distinct patient_id from public.{table}").fetchall()}


def test_patient_sees_only_own_records(db):
    as_user(db, AMINA)
    for table in ("measurements", "lifestyle_logs", "care_plans", "medications", "journal_entries"):
        assert visible_patients(db, table) == {AMINA}, table


def test_doctor_sees_only_assigned_patients(db):
    as_user(db, sim.DOCTOR.id)
    assert visible_patients(db) == ASSIGNED
    assert YACINE not in {str(r[0]) for r in db.execute("select id from public.profiles").fetchall()}


def test_unassigned_doctor_and_anon_see_nothing(db):
    other_doctor = new_user(db, "doctor")
    as_user(db, other_doctor)
    assert visible_patients(db) == set()
    db.execute("reset role")
    as_user(db, None, role="anon")
    fails(db, Denied, "select 1 from public.measurements")


def test_admin_reads_all(db):
    as_user(db, sim.ADMIN.id)
    assert visible_patients(db) == set(IDS.values())


def test_patient_manual_entry_allowed(db):
    as_user(db, AMINA)
    assert reading(db, AMINA, 128, 82, 70, body_position="sitting")[0] == "valid"


@pytest.mark.parametrize("query, params", [
    ("update public.profiles set role = 'doctor' where id = %s", (AMINA,)),
    ("insert into public.measurements (patient_id, source, systolic, diastolic, measured_at)"
     " values (%s, 'manual', 120, 80, now())", (KARIM,)),
    ("insert into public.measurements (patient_id, source, provenance, systolic, diastolic, measured_at)"
     " values (%s, 'simulated', 'simulated', 120, 80, now())", (AMINA,)),
    ("insert into public.measurements (patient_id, source, systolic, diastolic, measured_at)"
     " values (%s, 'csv_import', 120, 80, now())", (AMINA,)),
    ("update public.measurements set systolic = 110 where patient_id = %s", (AMINA,)),
    ("delete from public.measurements where patient_id = %s", (AMINA,)),
    ("insert into public.alerts (patient_id, alert_class, rule_code, reason) values (%s, 'routine', 'X', 'x')", (AMINA,)),
    ("insert into public.doctor_patient_assignments (doctor_id, patient_id) values (%s, %s)", (sim.DOCTOR.id, AMINA)),
])
def test_patient_forbidden_writes(db, query, params):
    as_user(db, AMINA)
    fails(db, Denied, query, params)


def test_patient_cannot_mark_journal_reviewed(db):
    as_user(db, AMINA)
    cur = db.execute("update public.journal_entries set doctor_review_status = 'reviewed', reviewed_at = now()")
    assert cur.rowcount == 0


def test_doctor_writes_limited_to_assigned(db):
    as_user(db, sim.DOCTOR.id)
    db.execute("insert into public.doctor_notes (doctor_id, patient_id, note) values (%s, %s, 'ok')", (sim.DOCTOR.id, KARIM))
    fails(db, Denied, "insert into public.doctor_notes (doctor_id, patient_id, note) values (%s, %s, 'no')",
          (sim.DOCTOR.id, YACINE))
    fails(db, Denied, "insert into public.measurements (patient_id, source, systolic, diastolic, measured_at)"
          " values (%s, 'manual', 120, 80, now())", (KARIM,))


# ---------------------------------------------------------------- M3 backend alignment, M4 ml_predictions

def test_empty_symptom_answer_is_stored(db):
    q = "insert into public.symptom_reports (patient_id, symptoms) values (%s, %s)"
    db.execute(q, (AMINA, []))
    fails(db, psycopg.errors.CheckViolation, q, (AMINA, ["not_a_symptom"]))


def test_alert_episode_attaches_same_patient_readings_only(db):
    alert = db.execute("insert into public.alerts (patient_id, alert_class, rule_code, reason, persistent)"
                       " values (%s, 'above_target_trend', 'R-TREND', 'test', true) returning id", (KARIM,)).fetchone()[0]
    own, other = (db.execute("select id from public.measurements where patient_id = %s limit 1", (p,)).fetchone()[0]
                  for p in (KARIM, AMINA))
    q = "insert into public.alert_measurements (alert_id, measurement_id, patient_id) values (%s, %s, %s)"
    db.execute(q, (alert, own, KARIM))
    fails(db, psycopg.errors.ForeignKeyViolation, q, (alert, other, KARIM))
    as_user(db, KARIM)
    assert db.execute("select count(*) from public.alert_measurements").fetchone()[0] == 1
    fails(db, Denied, q, (alert, own, KARIM))


def test_doctor_notes_hidden_from_patient(db):
    assert db.execute("select count(*) from public.doctor_notes").fetchone()[0] > 0
    patient = db.execute("select patient_id::text from public.doctor_notes limit 1").fetchone()[0]
    as_user(db, patient)
    assert db.execute("select count(*) from public.doctor_notes").fetchone()[0] == 0
    db.execute("reset role")
    as_user(db, sim.DOCTOR.id)
    assert db.execute("select count(*) from public.doctor_notes").fetchone()[0] > 0


def test_ml_predictions_doctor_only(db):
    q = ("insert into public.ml_predictions (patient_id, target_date, target, status, predicted_systolic,"
         " predicted_diastolic, model_version, trained_on, features_until, n_readings_used)"
         " values (%s, current_date, 'morning_mean_bp', %s, %s, %s, 'test', 'synthetic:pulse-sim-v1', now(), 10)")
    for p in (AMINA, YACINE):
        db.execute(q, (p, "ok", 131.5, 84.0))
    fails(db, psycopg.errors.CheckViolation, q, (KARIM, "ok", None, None))
    as_user(db, AMINA)
    assert visible_patients(db, "ml_predictions") == set()
    fails(db, Denied, q, (AMINA, "ok", 120, 80))
    db.execute("reset role")
    as_user(db, sim.DOCTOR.id)
    assert visible_patients(db, "ml_predictions") == {AMINA}


def test_patient_sets_own_birth_year(db):
    as_user(db, AMINA)
    assert db.execute("update public.patient_profiles set birth_year = 1968 where user_id = %s", (AMINA,)).rowcount == 1
    fails(db, psycopg.errors.CheckViolation, "update public.patient_profiles set birth_year = 1850 where user_id = %s", (AMINA,))
    assert db.execute("update public.patient_profiles set birth_year = 1970 where user_id = %s", (KARIM,)).rowcount == 0


def test_algerian_factor_fields(db):
    fails(db, psycopg.errors.CheckViolation, "update public.patient_profiles set condition_codes = '{asthma}' where user_id = %s", (AMINA,))
    fails(db, psycopg.errors.CheckViolation, "update public.patient_profiles set adds_salt_at_table = 'daily' where user_id = %s", (AMINA,))
    db.execute("insert into public.lifestyle_logs (patient_id, category, started_at, ended_at)"
               " values (%s, 'fasting', now() - interval '13 hours', now() - interval '30 minutes')", (AMINA,))
    as_user(db, AMINA)
    assert db.execute("update public.profiles set preferred_language = 'ar' where id = %s", (AMINA,)).rowcount == 1
    db.execute("insert into public.body_measurements (patient_id, measured_at, weight_kg, source)"
               " values (%s, now(), 71.5, 'patient_reported')", (AMINA,))
    fails(db, Denied, "insert into public.body_measurements (patient_id, measured_at, weight_kg, source)"
          " values (%s, now(), 71.5, 'clinician')", (AMINA,))
    fails(db, Denied, "insert into public.body_measurements (patient_id, measured_at, weight_kg, source)"
          " values (%s, now(), 80, 'patient_reported')", (KARIM,))


def test_wearable_samples(db):
    ring = db.execute("select device_id from public.wearable_samples where patient_id = %s limit 1", (KARIM,)).fetchone()[0]
    q = ("insert into public.wearable_samples (patient_id, device_id, metric, value, unit, measured_at, source)"
         " values (%s, %s, %s, %s, %s, now(), 'device_sync')")
    fails(db, psycopg.errors.CheckViolation, q, (KARIM, ring, "spo2", 97, "bpm"))           # wrong unit
    fails(db, psycopg.errors.CheckViolation, q, (KARIM, ring, "heart_rate", 400, "bpm"))    # implausible
    fails(db, psycopg.errors.ForeignKeyViolation, q, (AMINA, ring, "heart_rate", 70, "bpm"))  # another patient's ring
    as_user(db, KARIM)
    assert visible_patients(db, "wearable_samples") == {KARIM}
    fails(db, Denied, q, (KARIM, ring, "heart_rate", 70, "bpm"))  # written by the backend only
    db.execute("reset role")
    as_user(db, AMINA)
    assert visible_patients(db, "wearable_samples") == set()


# ---------------------------------------------------------------- M7 ml_monitoring (review M1-M4, M8)

def band(db, patient, status="proposed", low=55, high=75):
    active = status == "active"
    return db.execute("insert into public.patient_bands (patient_id, metric, statistic, low, high, basis, status,"
                      " approved_by, approved_at, effective_from) values (%s, 'heart_rate', 'night_median', %s, %s,"
                      " 'model_proposal', %s, %s, case when %s then now() end, case when %s then current_date end)"
                      " returning id", (patient, low, high, status, sim.DOCTOR.id if active else None, active, active)
                      ).fetchone()[0]


def test_m7_tables_are_doctor_only(db):
    for table in ("wearable_flags", "weekly_reports", "patient_bands"):  # local job runs may have left rows
        db.execute(f"delete from public.{table}")
    band(db, KARIM)
    db.execute("insert into public.weekly_reports (patient_id, week_start, control_status)"
               " values (%s, date_trunc('week', now())::date, 'above_target')", (KARIM,))
    as_user(db, KARIM)
    for table in ("patient_bands", "wearable_flags", "weekly_reports"):
        assert visible_patients(db, table) == set(), table
    db.execute("reset role")
    as_user(db, sim.DOCTOR.id)
    assert visible_patients(db, "patient_bands") == visible_patients(db, "weekly_reports") == {KARIM}
    db.execute("reset role")
    as_user(db, None, role="anon")
    for table in ("patient_bands", "wearable_flags", "weekly_reports"):
        fails(db, Denied, f"select 1 from public.{table}")


def test_approve_band_supersedes_and_is_audited(db):
    old = band(db, KARIM, status="active")
    new = band(db, KARIM, low=58, high=78)
    other_doctor = new_user(db, "doctor")
    as_user(db, other_doctor)
    fails(db, psycopg.errors.CheckViolation, "select private.approve_band(%s, %s)", (new, other_doctor))  # cannot see it
    db.execute("reset role")
    fails(db, Denied, "select private.approve_band(%s, %s)", (new, other_doctor))  # not assigned (privileged path)
    as_user(db, sim.DOCTOR.id)
    fails(db, Denied, "select private.approve_band(%s, %s)", (new, other_doctor))  # approver must be the caller
    db.execute("select private.approve_band(%s, %s, %s, %s)", (new, sim.DOCTOR.id, 57, 78))
    db.execute("reset role")
    rows = {r[0]: r[1:] for r in db.execute("select id, status, basis, supersedes_id, low from public.patient_bands"
                                            " where patient_id = %s", (KARIM,)).fetchall()}
    assert rows[old][0] == "superseded"
    assert rows[new] == ("active", "doctor", old, 57)
    assert db.execute("select count(*) from public.audit_log where table_name = 'patient_bands' and row_id = %s",
                      (new,)).fetchone()[0] >= 2


def test_flag_and_report_review_by_assigned_doctor(db):
    flag = db.execute("insert into public.wearable_flags (patient_id, metric, kind, window_kind, window_start, window_end,"
                      " value, reference_basis, model_version) values (%s, 'spo2', 'outside_reference', 'live_10min',"
                      " now() - interval '10 minutes', now(), 91, 'reference:spo2', 'test') returning id",
                      (KARIM,)).fetchone()[0]
    fails(db, psycopg.errors.CheckViolation, "insert into public.wearable_flags (patient_id, metric, kind, window_kind,"
          " window_start, window_end, reference_basis, model_version) values (%s, 'heart_rate', 'multivariate_anomaly',"
          " 'night', now() - interval '6 hours', now(), 'x', 'test')", (KARIM,))
    fails(db, psycopg.errors.CheckViolation, "insert into public.weekly_reports (patient_id, week_start, control_status)"
          " values (%s, date_trunc('week', now())::date + 2, 'above_target')", (KARIM,))  # not a Monday
    report = db.execute("insert into public.weekly_reports (patient_id, week_start, control_status) values"
                        " (%s, date_trunc('week', now())::date, 'above_target') returning id", (KARIM,)).fetchone()[0]
    other_doctor = new_user(db, "doctor")
    as_user(db, KARIM)
    assert db.execute("update public.wearable_flags set review_status = 'dismissed' where id = %s", (flag,)).rowcount == 0
    db.execute("reset role")
    as_user(db, sim.DOCTOR.id)
    fails(db, Denied, "update public.wearable_flags set review_status = 'confirmed', reviewed_by = %s, reviewed_at = now()"
          " where id = %s", (other_doctor, flag))  # reviewer must be the caller
    assert db.execute("update public.wearable_flags set review_status = 'confirmed', reviewed_by = %s, reviewed_at = now(),"
                      " review_note = 'checked with patient' where id = %s", (sim.DOCTOR.id, flag)).rowcount == 1
    assert db.execute("update public.weekly_reports set status = 'reviewed', reviewed_by = %s, reviewed_at = now(),"
                      " doctor_comment = 'ok' where id = %s", (sim.DOCTOR.id, report)).rowcount == 1
    fails(db, Denied, "update public.weekly_reports set summary = '{}' where id = %s", (report,))  # job-only column


def test_new_tables_have_no_anon_access(db):
    as_user(db, None, role="anon")
    for table in ("alert_measurements", "ml_predictions", "body_measurements", "wearable_samples"):
        fails(db, Denied, f"select 1 from public.{table}")


# ---------------------------------------------------------------- live API (GoTrue + PostgREST)

def _api():
    url, key = os.environ.get("PULSE_API_URL", "http://127.0.0.1:55321"), os.environ.get("PULSE_ANON_KEY")
    if not key:
        try:
            out = subprocess.run("npx -y supabase@2.122.0 status -o env", shell=True, capture_output=True,
                                 text=True, timeout=60).stdout
        except (OSError, subprocess.TimeoutExpired):
            out = ""
        env = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
        key = (env.get("ANON_KEY") or env.get("PUBLISHABLE_KEY") or "").strip('"')
    if not key:
        pytest.skip("local Supabase API key unavailable (set PULSE_ANON_KEY)")
    return url, key


def _call(url, key, path, token=None, body=None):
    req = urllib.request.Request(url + path, data=json.dumps(body).encode() if body else None,
                                 headers={"apikey": key, "Content-Type": "application/json",
                                          "Authorization": f"Bearer {token or key}"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


@pytest.mark.parametrize("user, expected", [(sim.PATIENTS[0], {AMINA}), (sim.DOCTOR, ASSIGNED)])
def test_live_api_enforces_access(_conn, user, expected):
    url, key = _api()
    password = os.environ.get("PULSE_DEMO_PASSWORD") or pytest.skip("set PULSE_DEMO_PASSWORD (same as used for the seed)")
    token = _call(url, key, "/auth/v1/token?grant_type=password", body={"email": user.email,
                                                                        "password": password})["access_token"]
    rows = _call(url, key, "/rest/v1/measurements?select=patient_id", token=token)
    assert {r["patient_id"] for r in rows} == expected
    with pytest.raises(urllib.error.HTTPError) as anon:  # anon key alone is refused
        _call(url, key, "/rest/v1/measurements?select=id")
    assert anon.value.code in (401, 403)
