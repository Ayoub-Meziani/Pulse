"""Weekly doctor loop (review L5, M2, M5). DB tests run on the LOCAL stack only, rolled back."""
import json
import os
from datetime import date

import numpy as np
import pandas as pd
import pytest

from pulse_ml import bands, feedback


def nights(values: dict) -> pd.DataFrame:
    n = len(next(iter(values.values())))
    return pd.DataFrame({"night": pd.date_range("2026-01-01", periods=n), **values})


def test_band_proposal_math():
    rng = np.random.default_rng(0)
    df = nights({"heart_rate": 62 + rng.normal(0, 1, 20), "spo2": 95 + rng.normal(0, 0.3, 20),
                 "hrv_rmssd": 35 + rng.normal(0, 3, 20), "skin_temperature": 34 + rng.normal(0, 0.1, 20)})
    low, high = bands.propose(df, "heart_rate")
    assert low < 62 < high and high - low >= 2 * bands.FLOOR["heart_rate"] - 0.02   # bands are rounded to 0.01
    low, high = bands.propose(df, "spo2")
    assert low >= 94 and high <= 100                  # never more permissive than the reference; SpO2 max 100 %
    copd = df.assign(spo2=91 + rng.normal(0, 0.3, 20))
    assert 88 <= bands.propose(copd, "spo2", ("copd",))[0] < 94    # COPD: BTS floor 88 %
    assert bands.propose(df, "hrv_rmssd", ("atrial_fibrillation",)) is None   # HRV not interpretable with AF
    assert bands.propose(df.head(10), "heart_rate") is None   # < 14 nights: no proposal


def test_regression_gate_blocks_lower_recall():
    current = {"test_metrics": {"personal_baseline": {"episode_recall": 0.9}}}
    assert feedback.gate({"test_metrics": {"personal_baseline": {"episode_recall": 0.95}}}, current)[0]
    assert not feedback.gate({"test_metrics": {"personal_baseline": {"episode_recall": 0.8}}}, current)[0]


@pytest.fixture
def conn():
    psycopg = pytest.importorskip("psycopg")
    from pulse_ml.predict import LOCAL_DB
    try:
        c = psycopg.connect(os.environ.get("PULSE_TEST_DATABASE_URL", LOCAL_DB), autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("local PULSE database not reachable")
    if c.execute("select to_regclass('public.weekly_reports')").fetchone()[0] is None:
        pytest.skip("M7 missing; run `supabase db reset --local`")
    with c.transaction(force_rollback=True):
        yield c
    c.close()


def as_doctor(conn, uid):
    conn.execute("set local role authenticated")
    conn.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({"sub": uid, "role": "authenticated"}),))


def test_weekly_reports_and_doctor_band_loop(conn):
    from pulse_data.simulate import DOCTOR, PATIENTS
    from pulse_ml import monitor, weekly
    count = lambda t: conn.execute(f"select count(*) from public.{t}").fetchone()[0]  # noqa: E731
    untouched = ("measurements", "alerts", "ml_predictions", "wearable_flags", "care_plans")
    before = {t: count(t) for t in untouched}
    conn.execute("delete from public.weekly_reports")
    conn.execute("delete from public.patient_bands")

    first = weekly.run(conn, date.today())
    assigned = {u.id for u in PATIENTS if u.assigned}
    reports = conn.execute("select patient_id::text, week_start, status from public.weekly_reports").fetchall()
    assert {p for p, _, _ in reports} == assigned and len(reports) == len(assigned) == first["reports"]
    assert all(ws.isoweekday() == 1 for _, ws, _ in reports)
    assert first["band_proposals"] > 0
    assert conn.execute("select count(*) from public.patient_bands where status <> 'proposed'").fetchone()[0] == 0
    assert {t: count(t) for t in untouched} == before
    home = lambda p: conn.execute("select summary->'bp_home' from public.weekly_reports where patient_id = %s",  # noqa: E731
                                  (p,)).fetchone()[0]
    assert all(home(p)["simulated"] == home(p)["valid_readings"] for p in assigned)   # the seed is all simulated

    karim = next(u.id for u in PATIENTS if u.key == "rising")
    amina = next(u.id for u in PATIENTS if u.key == "controlled")
    conn.execute("insert into public.measurements (patient_id, source, provenance, systolic, diastolic, measured_at)"
                 " values (%s, 'manual', 'measured', 128, 82, now() - interval '1 minute')", (amina,))
    conn.execute("update public.weekly_reports set status = 'reviewed', reviewed_by = %s, reviewed_at = now(),"
                 " doctor_comment = 'seen' where patient_id = %s", (DOCTOR.id, karim))
    second = weekly.run(conn, date.today())   # re-run: no duplicates, reviewed report kept
    assert count("weekly_reports") == len(assigned) and second["band_proposals"] == 0
    assert conn.execute("select status, doctor_comment from public.weekly_reports where patient_id = %s",
                        (karim,)).fetchone() == ("reviewed", "seen")
    assert home(amina)["simulated"] == home(amina)["valid_readings"] - 1          # her own measured reading

    # the doctor rejects one proposal (what POST /bands/{id}/reject does), then the jobs run again
    rejected = conn.execute("update public.patient_bands set status = 'rejected' where id = (select id from"
                            " public.patient_bands where status = 'proposed' and not (patient_id = %s and metric ="
                            " 'heart_rate') limit 1) returning patient_id, metric, statistic", (karim,)).fetchone()
    assert rejected and weekly.run(conn, date.today())["band_proposals"] == 0   # the doctor's reject sticks
    assert conn.execute("select count(*) from public.patient_bands where (patient_id, metric, statistic) ="
                        " (%s, %s, %s) and status = 'proposed'", rejected).fetchone()[0] == 0

    band_id = conn.execute("select id::text from public.patient_bands where patient_id = %s and metric = 'heart_rate'",
                           (karim,)).fetchone()[0]
    as_doctor(conn, DOCTOR.id)
    conn.execute("select private.approve_band(%s, %s, 50, 75)", (band_id, DOCTOR.id))   # doctor edits the band
    conn.execute("reset role")
    assert conn.execute("select status, basis from public.patient_bands where id = %s", (band_id,)).fetchone() \
        == ("active", "doctor")
    monitor.run_nights(conn)   # the monitor now compares Karim's night heart rate with the approved band
    basis = conn.execute("select distinct reference_basis from public.wearable_flags where patient_id = %s"
                         " and metric = 'heart_rate' and kind = 'personal_anomaly'", (karim,)).fetchall()
    assert (f"band:{band_id}",) in basis
    third = weekly.run(conn, date.today())    # jobs re-run after the approval: the active band is not re-proposed
    assert third["band_proposals"] == 0
    assert conn.execute("select count(*) from public.patient_bands where patient_id = %s and metric = 'heart_rate'"
                        " and status = 'proposed'", (karim,)).fetchone()[0] == 0
