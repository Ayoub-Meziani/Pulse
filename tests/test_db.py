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
ASSIGNED = {AMINA, KARIM, NADIA}
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
    assert db.execute("select count(*) from public.doctor_patient_assignments where status = 'active'").fetchone()[0] == 3


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
