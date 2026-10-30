"""Weekly report for each patient's doctor + proposed personal ring bands.

    cd ml && ..\\.venv\\Scripts\\python -m pulse_ml.weekly [--week YYYY-MM-DD]

For patients actively assigned AT JOB TIME [review L5]; week = patient-local Monday to Sunday (default: the
last complete week). Writes public.weekly_reports (upsert; a report the doctor already reviewed is never
overwritten) and public.patient_bands with status 'proposed' only. "Sent" means available to the backend for
the doctor app; no email or SMS. Prints counts only.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import psycopg
from psycopg.types.json import Jsonb

from . import bands, reference, ring
from .predict import LOCAL_DB, PATIENTS

DEFAULT_TARGET = (140, 90)  # contract default when there is no active care plan
MIN_WEEK_READINGS = 3

UPSERT = """
    insert into public.weekly_reports as w (patient_id, week_start, home_bp_category, control_status,
      next_week_above_target_prob, model_versions, summary)
    values (%(patient_id)s, %(week_start)s, %(home_bp_category)s, %(control_status)s, %(prob)s,
      %(model_versions)s, %(summary)s)
    on conflict (patient_id, week_start) do update set home_bp_category = excluded.home_bp_category,
      control_status = excluded.control_status, next_week_above_target_prob = excluded.next_week_above_target_prob,
      model_versions = excluded.model_versions, summary = excluded.summary
    where w.status = 'ready'"""
PROPOSE = """
    insert into public.patient_bands (patient_id, metric, statistic, low, high, basis, status, proposed_model_version)
    select %s, %s, %s, %s, %s, 'model_proposal', 'proposed', %s
    where not exists (select 1 from public.patient_bands where patient_id = %s and metric = %s and statistic = %s
                      and status = 'proposed')"""   # one open proposal per metric at a time


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def week_window(week_start: date, tz: str) -> tuple[datetime, datetime]:
    start = datetime.combine(week_start, time(0), ZoneInfo(tz))
    return start, start + timedelta(days=7)


def bp_part(conn, patient: str, start: datetime, end: datetime) -> tuple[dict, str | None, str]:
    s, d, n = conn.execute("select avg(systolic), avg(diastolic), count(*) from public.measurements where patient_id = %s"
                           " and validation_status = 'valid' and measured_at >= %s and measured_at < %s",
                           (patient, start, end)).fetchone()
    plan = conn.execute("select target_systolic, target_diastolic from public.care_plans where patient_id = %s"
                        " and status = 'active' and target_systolic is not null", (patient,)).fetchone()
    target, source = (plan, "care_plan") if plan else (DEFAULT_TARGET, "default")
    part = {"valid_readings": n, "target": list(target), "target_source": source}
    if n < MIN_WEEK_READINGS:
        return part, None, "insufficient_data"
    s, d = float(s), float(d)
    part.update(mean_systolic=round(s, 1), mean_diastolic=round(d, 1))
    status = "above_target" if s >= target[0] or d >= target[1] else "at_or_below_target"
    return part, reference.home_bp_category(s, d), status


def ring_part(conn, patient: str, tz: str, start: datetime, end: datetime) -> tuple[dict, list[dict]]:
    rows = conn.execute("select patient_id::text, metric, value, measured_at from public.wearable_samples"
                        " where patient_id = %s and measured_at >= %s - interval '28 days' and measured_at < %s",
                        (patient, start, end)).fetchall()
    flags = conn.execute("select kind, review_status, count(*) from public.wearable_flags where patient_id = %s"
                         " and window_start >= %s and window_start < %s group by 1, 2", (patient, start, end)).fetchall()
    part = {"flags": [{"kind": k, "review_status": r, "count": c} for k, r, c in flags]}
    if not rows:
        return part, []
    nights = ring.night_table(ring.from_db(rows, {patient: tz}))
    week = nights[nights.night >= start.replace(tzinfo=None)]
    part["nights_this_week"] = int(len(week))
    for m in ring.METRICS:
        if len(week) and week[m].notna().any():
            part[f"{m}_{ring.NIGHT_STAT[m]}"] = round(float(week[m].median()), 2)
    return part, bands.propose_for_patient(nights)


def run(conn, week: date | None = None) -> dict:
    out = {"reports": 0, "band_proposals": 0}
    for patient, tz in conn.execute(PATIENTS).fetchall():
        week_start = monday(week) if week else monday(datetime.now(ZoneInfo(tz)).date()) - timedelta(days=7)
        start, end = week_window(week_start, tz)
        bp, category, control = bp_part(conn, patient, start, end)
        ring_summary, proposals = ring_part(conn, patient, tz, start, end)
        mbp = conn.execute("select model_version, target_date, predicted_systolic, predicted_diastolic"
                           " from public.ml_predictions where patient_id = %s and status = 'ok'"
                           " order by target_date desc, created_at desc limit 1", (patient,)).fetchone()
        summary = {"bp_home": bp, "ring": ring_summary, "reference": "home-BP category: ACC/AHA 2017 Table 11 "
                   "(home column); pending clinician review"}
        if mbp:
            summary["mbp_estimate"] = {"target_date": mbp[1].isoformat(), "systolic": float(mbp[2]),
                                       "diastolic": float(mbp[3])}
        conn.execute(UPSERT, dict(patient_id=patient, week_start=week_start, home_bp_category=category,
                                  control_status=control, prob=None, summary=Jsonb(summary),
                                  model_versions=Jsonb({"mbp": mbp[0] if mbp else None, "ring": ring.MODEL_VERSION,
                                                        "weekly_classifier": None})))
        out["reports"] += 1
        for p in proposals:
            cur = conn.execute(PROPOSE, (patient, p["metric"], p["statistic"], p["low"], p["high"], ring.MODEL_VERSION,
                                         patient, p["metric"], p["statistic"]))
            out["band_proposals"] += cur.rowcount
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", type=date.fromisoformat, help="any day of the week to report (default: last full week)")
    a = ap.parse_args()
    with psycopg.connect(os.environ.get("DATABASE_URL", LOCAL_DB), autocommit=True) as conn:
        print(json.dumps(run(conn, a.week)))


if __name__ == "__main__":
    main()
