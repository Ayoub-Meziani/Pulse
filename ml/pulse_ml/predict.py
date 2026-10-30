"""Batch job: next-day morning BP estimates -> public.ml_predictions (contract §4).

    cd ml && ..\\.venv\\Scripts\\python -m pulse_ml.predict --all [--date YYYY-MM-DD] [--dry-run]

Reads `valid` measurements of actively assigned patients only and writes ml_predictions only
(upsert on patient_id, target_date, model_version, so re-runs are safe). Uses DATABASE_URL
(default: local stack). Prints counts, never health values.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, time, timedelta
from time import sleep
from zoneinfo import ZoneInfo

import joblib
import pandas as pd
import psycopg
from psycopg import sql

from .features import daily_table, window_features
from .train import ARTIFACTS, MODEL_VERSION, TRAINED_ON

LOCAL_DB = "postgresql://postgres:postgres@127.0.0.1:55322/postgres"


def connect(**kw) -> psycopg.Connection:
    """DATABASE_URL (default: local stack). PULSE_DB_ROLE, if set, is assumed right after login: the Supabase CLI's
    temporary login (scripts/run_cloud_jobs.ps1) must act as postgres, and the pooler drops startup options."""
    role = os.environ.get("PULSE_DB_ROLE")
    for attempt in range(6 if role else 1):
        try:
            conn = psycopg.connect(os.environ.get("DATABASE_URL", LOCAL_DB), **kw)
            break
        except psycopg.OperationalError:
            if attempt == (5 if role else 0):
                raise
            sleep(5)   # the pooler can take a few seconds to accept a freshly issued CLI login
    if role:
        conn.execute(sql.SQL("set role {}").format(sql.Identifier(role)))
        conn.commit()
    return conn

PATIENTS = """
    select distinct p.id::text, p.timezone from public.profiles p
    join public.doctor_patient_assignments a on a.patient_id = p.id and a.status = 'active'
    where p.role = 'patient' order by 1"""
READINGS = """
    select measured_at, measured_tz, systolic, diastolic from public.measurements
    where patient_id = %s and validation_status = 'valid' and measured_at >= %s and measured_at < %s"""
UPSERT = """
    insert into public.ml_predictions (patient_id, target_date, target, status, predicted_systolic,
      predicted_diastolic, interval_systolic_low, interval_systolic_high, interval_diastolic_low,
      interval_diastolic_high, model_version, trained_on, features_until, n_readings_used)
    values (%(patient_id)s, %(target_date)s, 'morning_mean_bp', %(status)s, %(predicted_systolic)s,
      %(predicted_diastolic)s, %(interval_systolic_low)s, %(interval_systolic_high)s,
      %(interval_diastolic_low)s, %(interval_diastolic_high)s, %(model_version)s, %(trained_on)s,
      %(features_until)s, %(n_readings_used)s)
    on conflict (patient_id, target_date, model_version) do update set
      status = excluded.status, predicted_systolic = excluded.predicted_systolic,
      predicted_diastolic = excluded.predicted_diastolic, interval_systolic_low = excluded.interval_systolic_low,
      interval_systolic_high = excluded.interval_systolic_high, interval_diastolic_low = excluded.interval_diastolic_low,
      interval_diastolic_high = excluded.interval_diastolic_high, trained_on = excluded.trained_on,
      features_until = excluded.features_until, n_readings_used = excluded.n_readings_used, created_at = now()"""


def load_bundle(version: str = MODEL_VERSION) -> dict:
    path = ARTIFACTS / version / "model.joblib"
    if not path.exists():
        raise SystemExit(f"no model at {path}; run `python -m pulse_ml.train` first")
    return joblib.load(path)


def predict_patient(conn, bundle: dict, patient_id: str, tz: str, target: date, version: str) -> dict:
    zone = ZoneInfo(tz)
    until = datetime.combine(target, time(0), zone)   # features strictly before the target day
    rows = conn.execute(READINGS, (patient_id, until - timedelta(days=8), until)).fetchall()
    readings = pd.DataFrame({
        "patient": patient_id,
        "local_dt": [m.astimezone(ZoneInfo(mtz or tz)).replace(tzinfo=None) for m, mtz, _, _ in rows],
        "systolic": [r[2] for r in rows], "diastolic": [r[3] for r in rows]})
    f, n = None, 0
    if len(readings):
        f, n = window_features(daily_table(readings).set_index("day").sort_index(), pd.Timestamp(target))
    row = dict(patient_id=patient_id, target_date=target, status="insufficient_history", predicted_systolic=None,
               predicted_diastolic=None, interval_systolic_low=None, interval_systolic_high=None,
               interval_diastolic_low=None, interval_diastolic_high=None, model_version=version,
               trained_on=TRAINED_ON, features_until=until, n_readings_used=n)
    if f is not None:
        (s, d), (hs, hd) = bundle["model"].predict(pd.DataFrame([f])[bundle["features"]])[0], bundle["half_width"]
        row.update(status="ok", predicted_systolic=round(float(s), 1), predicted_diastolic=round(float(d), 1),
                   interval_systolic_low=round(float(s - hs), 1), interval_systolic_high=round(float(s + hs), 1),
                   interval_diastolic_low=round(float(d - hd), 1), interval_diastolic_high=round(float(d + hd), 1))
    return row


def run(conn, bundle: dict, target: date | None = None, dry_run: bool = False,
        version: str = MODEL_VERSION) -> list[dict]:
    out = []
    for patient_id, tz in conn.execute(PATIENTS).fetchall():
        day = target or datetime.now(ZoneInfo(tz)).date() + timedelta(days=1)
        row = predict_patient(conn, bundle, patient_id, tz, day, version)
        if not dry_run:
            conn.execute(UPSERT, row)
        out.append(row)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", required=True, help="all actively assigned patients")
    ap.add_argument("--date", type=date.fromisoformat, help="target day (default: tomorrow, patient-local)")
    ap.add_argument("--dry-run", action="store_true", help="compute, do not write")
    ap.add_argument("--model-version", default=MODEL_VERSION)
    a = ap.parse_args()
    with connect() as conn:
        rows = run(conn, load_bundle(a.model_version), a.date, a.dry_run, a.model_version)
    counts = pd.Series([r["status"] for r in rows], dtype=str).value_counts().to_dict()
    print(json.dumps({"model_version": a.model_version, "patients": len(rows), "by_status": counts,
                      "written": not a.dry_run}))


if __name__ == "__main__":
    main()
