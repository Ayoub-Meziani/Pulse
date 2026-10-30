"""ML pipeline checks (contract §4 tests). DB test runs on the LOCAL stack only, rolled back."""
import os

import numpy as np
import pandas as pd
import pytest

from pulse_ml.features import FEATURES, daily_table, window_features
from pulse_ml.train import fit_and_evaluate, split_patients


def fixture_readings(patients=20, days=21, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for p in range(patients):
        base = rng.uniform(115, 160)
        for d in range(days):
            for hour in (7, 20):
                s = base + 0.3 * d + rng.normal(0, 5) + (4 if hour == 7 else 0)
                rows.append((f"P{p:02d}", pd.Timestamp("2026-01-01") + pd.Timedelta(days=d, hours=hour),
                             round(s), round(0.62 * s + rng.normal(0, 3))))
    return pd.DataFrame(rows, columns=["patient", "local_dt", "systolic", "diastolic"])


def one_patient_days(readings):
    return daily_table(readings[readings.patient == "P00"]).set_index("day").sort_index()


def test_home_bp_category_uses_home_thresholds():
    from pulse_ml.reference import home_bp_category, outside_reference
    assert home_bp_category(118, 76) == "normal"
    assert home_bp_category(124, 78) == "elevated"
    assert home_bp_category(118, 81) == "stage_1_range"   # diastolic alone raises the category
    assert home_bp_category(134, 84) == "stage_1_range"   # office 140/90 corresponds to home 135/85
    assert home_bp_category(135, 70) == "stage_2_range"
    assert outside_reference("spo2", 91) and not outside_reference("spo2", 96)
    assert not outside_reference("hrv_rmssd", 3)          # no population reference: personal only


def test_split_has_no_patient_overlap():
    s = split_patients([f"S{i}" for i in range(200)])
    assert not (s["train"] & s["val"] or s["train"] & s["test"] or s["val"] & s["test"])
    assert sum(map(len, s.values())) == 200


def test_features_use_only_earlier_days():
    r = fixture_readings(patients=1)
    target = pd.Timestamp("2026-01-15")
    before, _ = window_features(one_patient_days(r), target)
    leak = pd.DataFrame({"patient": "P00", "local_dt": [target + pd.Timedelta(hours=7), target + pd.Timedelta(days=1, hours=7)],
                         "systolic": [250, 250], "diastolic": [140, 140]})
    after, _ = window_features(one_patient_days(pd.concat([r, leak])), target)
    assert before == after and list(before) == FEATURES


def test_short_history_is_insufficient():
    r = fixture_readings(patients=1, days=3)  # 6 readings but only 3 days
    assert window_features(one_patient_days(r), pd.Timestamp("2026-01-04")) == (None, 6)


def test_training_is_deterministic():
    r = fixture_readings()
    (_, a), (_, b) = fit_and_evaluate(r), fit_and_evaluate(r)
    assert a["test_metrics_mmHg"] == b["test_metrics_mmHg"] and a["algorithm"] == b["algorithm"]


def test_prediction_job_writes_only_predictions_for_assigned_patients():
    psycopg = pytest.importorskip("psycopg")
    from pulse_ml.predict import LOCAL_DB, run
    try:
        conn = psycopg.connect(os.environ.get("PULSE_TEST_DATABASE_URL", LOCAL_DB), autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("local PULSE database not reachable")
    if conn.execute("select to_regclass('public.ml_predictions')").fetchone()[0] is None:
        pytest.skip("ml_predictions missing; run `supabase db reset` (local)")
    bundle, _ = fit_and_evaluate(fixture_readings())
    others = ("measurements", "alerts", "alert_measurements", "symptom_reports", "audit_log")
    count = lambda t: conn.execute(f"select count(*) from public.{t}").fetchone()[0]  # noqa: E731
    with conn.transaction(force_rollback=True):
        conn.execute("delete from public.ml_predictions")
        before = {t: count(t) for t in others}
        rows = run(conn, bundle)
        run(conn, bundle)  # re-run upserts, no duplicates
        written = {r[0] for r in conn.execute("select patient_id::text from public.ml_predictions").fetchall()}
        assigned = {r[0] for r in conn.execute("select patient_id::text from public.doctor_patient_assignments"
                                               " where status = 'active'").fetchall()}
        assert written == assigned == {r["patient_id"] for r in rows}
        assert count("ml_predictions") == len(assigned)
        assert {t: count(t) for t in others} == before
        assert all(r["status"] == "insufficient_history" or r["predicted_systolic"] > r["predicted_diastolic"] for r in rows)
    conn.close()
