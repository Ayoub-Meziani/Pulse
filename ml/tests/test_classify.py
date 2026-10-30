"""Weekly classifier checks (review M7). DB test runs on the LOCAL stack only, rolled back."""
import os
from datetime import date

import numpy as np
import pandas as pd
import pytest

from pulse_ml import classify


def readings(weeks: list[tuple[int, int]], patient="P1", start="2026-01-05") -> pd.DataFrame:
    """Two readings a day; week i at systolic/diastolic weeks[i]."""
    rows = [(patient, pd.Timestamp(start) + pd.Timedelta(days=7 * i + d, hours=h), s, dia)
            for i, (s, dia) in enumerate(weeks) for d in range(7) for h in (7, 20)]
    return pd.DataFrame(rows, columns=["patient", "local_dt", "systolic", "diastolic"])


def test_label_is_next_week_with_or_rule_and_features_ignore_it():
    ex = classify.week_examples(readings([(130, 80), (128, 86), (120, 75)]), None, {"P1": (135, 85)})
    assert list(ex.label[:2]) == [1.0, 0.0] and np.isnan(ex.label.iloc[2])   # 86 >= 85 alone makes week 2 "above"
    assert list(ex.week.dt.day_of_week) == [0, 0, 0]                          # Monday-aligned
    changed = classify.week_examples(readings([(130, 80), (170, 110), (120, 75)]), None, {"P1": (135, 85)})
    pd.testing.assert_series_equal(ex.loc[0, classify.BP_FEATURES], changed.loc[0, classify.BP_FEATURES])


def test_classifier_training_is_deterministic():
    rng = np.random.default_rng(3)
    frames = []
    for p in range(40):
        base = rng.uniform(115, 160)
        frames.append(readings([(round(base + rng.normal(0, 6)), round(0.62 * base + rng.normal(0, 4)))
                                for _ in range(6)], patient=f"P{p:02d}"))
    data = pd.concat(frames)
    (_, a), (_, b) = (classify.fit_and_evaluate(data, None, {}) for _ in range(2))
    assert a["test"] == b["test"] and a["algorithm"] == b["algorithm"]


def test_weekly_report_gets_a_classifier_probability():
    psycopg = pytest.importorskip("psycopg")
    from pulse_ml import weekly
    from pulse_ml.predict import LOCAL_DB
    if weekly.load_classifier() is None:
        pytest.skip("wcls-v1 not trained; run `python -m pulse_ml.classify`")
    try:
        conn = psycopg.connect(os.environ.get("PULSE_TEST_DATABASE_URL", LOCAL_DB), autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("local PULSE database not reachable")
    with conn.transaction(force_rollback=True):
        conn.execute("delete from public.weekly_reports")
        out = weekly.run(conn, date.today())
        probs = [r[0] for r in conn.execute("select next_week_above_target_prob from public.weekly_reports"
                                            " where model_versions ->> 'weekly_classifier' = %s",
                                            (classify.MODEL_VERSION,)).fetchall()]
        assert out["with_classifier"] == len(probs) > 0 and all(0 <= float(p) <= 1 for p in probs)
    conn.close()
