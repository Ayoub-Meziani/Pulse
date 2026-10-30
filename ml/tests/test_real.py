"""Real-data pipeline checks WITHOUT network or downloaded files (small fixtures with the real column names)."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pulse_ml import real_bands, real_data, real_tests, wrisk


def test_raw_real_data_is_git_ignored():
    ignore = (Path(__file__).resolve().parents[2] / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "/data/" in ignore       # data/external/ (raw NHANES, Mendeley, PhysioNet files) never committed


def test_weighted_percentiles():
    assert real_bands.weighted_percentiles([1, 2, 3, 4], [1, 1, 1, 1], (50,)) == [2.5]
    assert real_bands.weighted_percentiles([10, 20], [3, 1], (50,))[0] < 15   # heavier weight pulls the median


def nhanes_fixture() -> pd.DataFrame:
    """Already-loaded NHANES rows (load_nhanes output columns)."""
    return pd.DataFrame({
        "seqn": [1, 2, 3, 4], "age": [55, 62, 40, 17], "weight": [1000.0, 2000.0, 1500.0, 900.0],
        "female": [1.0, 0.0, 1.0, 0.0], "bmi": [31.0, 25.0, np.nan, 22.0], "waist": [102.0, 95.0, 88.0, 80.0],
        "sys1": [150, 128, 135, 120], "sys2": [146, 126, 131, 118], "sys3": [np.nan, 124, 0, 119],
        "dia1": [92, 78, 88, 70], "dia2": [90, 80, 92, 72], "dia3": [np.nan, 79, 0, 71],
        "pulse1": [70, 66, 80, 75], "pulse2": [72, 64, np.nan, 77], "pulse3": [np.nan, 65, np.nan, 76],
        "bp_med_now": [1.0, 1.0, 1.0, 1.0], "smoking": ["current", "never", "former", None],
        "diabetes_told": [1.0, 0.0, np.nan, 0.0], "high_chol_told": [1.0, 0.0, 0.0, 0.0],
        "kidney_told": [0.0, 0.0, 0.0, 0.0], "copd_told": [0.0, 1.0, 0.0, 0.0], "chf_told": [0.0, 0.0, 0.0, 0.0],
        "stroke_told": [0.0, 0.0, 1.0, 0.0]})


def test_valid_mean_needs_two_valid_readings():
    df = nhanes_fixture()
    sys_ = real_data.valid_mean(df, "sys", 50, 300)
    assert sys_.tolist()[:2] == [148.0, 126.0] and sys_[2] == 133.0   # the 0 reading is ignored
    assert np.isnan(real_data.valid_mean(df, "pulse", 25, 250)[2])    # only 1 valid pulse -> no mean


def test_wrisk_examples_label_and_population():
    ex = wrisk.nhanes_examples(nhanes_fixture()).set_index("person")
    assert "4" not in ex.index                                     # under 18 excluded
    assert ex.loc["1", "label"] == 1 and ex.loc["2", "label"] == 0  # 148/91 uncontrolled, 126/79 controlled
    assert ex.loc["3", "label"] == 1                                # 133/90: diastolic alone -> uncontrolled (OR rule)
    assert ex.loc["1", "smoking_current"] == 1 and ex.loc["3", "smoking_former"] == 1


def test_pulse_patient_maps_to_the_same_features():
    f = wrisk.pulse_patient_features(66, "male", 31.2, 104, "current", ["hypertension", "diabetes", "copd"])
    assert list(f) == wrisk.FEATURES or set(f) == set(wrisk.FEATURES)
    assert f["female"] == 0 and f["diabetes"] == 1 and f["copd"] == 1 and f["stroke"] == 0
    assert np.isnan(wrisk.pulse_patient_features(None, None, None, None, None, [])["age"])


def test_mendeley_frame_and_series_stats():
    m = real_data.mendeley_frame(pd.Series([140, 150, 145]), pd.Series([80, 85, 82]), pd.Series([70, 72, 71]))
    assert m.day.tolist() == [0, 3, 6]                          # 1 measurement every 3 days
    s = real_tests.series_stats(np.array([140, 150, 145, 155.0]))
    assert s["persistence_mae"] == round((10 + 5 + 10) / 3, 2)
    with pytest.raises(ValueError):
        real_data.mendeley_frame(pd.Series([1, 2]), pd.Series([1]), pd.Series([1, 2]))


def test_pulse_placement_uses_the_right_band(monkeypatch):
    from pulse_ml import reference
    fake = {"percentiles": [2.5, 50, 97.5], "bands": {"pulse": {"male": {"60-69": {"p2.5": 50.0, "p50": 65.0,
                                                                                    "p97.5": 93.0},
                                                                          "80+": {"p2.5": 48.0, "p50": 64.0,
                                                                                  "p97.5": 95.0}}}}}
    monkeypatch.setattr(reference, "nhanes_bands", lambda: fake)
    p = reference.pulse_vs_population("male", 65, 65.0)
    assert p["age_band"] == "60-69" and p["percentile"] == 50.0
    assert reference.pulse_vs_population("male", 85, 64.0)["age_band"] == "80+"
    assert reference.pulse_vs_population("female", 65, 65.0) is None      # no band for that group in the fixture
    assert reference.pulse_vs_population("male", 65, None) is None


def test_weekly_report_places_cuff_pulse_with_real_bands():
    psycopg = pytest.importorskip("psycopg")
    import os
    from datetime import date
    from pulse_ml import reference, weekly
    from pulse_ml.predict import LOCAL_DB
    if reference.nhanes_bands() is None:
        pytest.skip("reference_nhanes.json missing; run `python -m pulse_ml.real_bands`")
    try:
        conn = psycopg.connect(os.environ.get("PULSE_TEST_DATABASE_URL", LOCAL_DB), autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("local PULSE database not reachable")
    with conn.transaction(force_rollback=True):
        conn.execute("delete from public.weekly_reports")
        weekly.run(conn, date.today())
        rows = conn.execute("select summary -> 'pulse_vs_population' from public.weekly_reports").fetchall()
        placed = [r[0] for r in rows if r[0]]
        assert placed and all(0 <= p["percentile"] <= 100 and p["source"].startswith("real:nhanes") for p in placed)
    conn.close()


def test_odi4_counts_real_desaturations():
    night = np.full(3600, 96.0)                                 # 1 hour at 1 Hz
    for start in (600, 1500, 2400):                             # 3 dips of 6 %, 30 s each
        night[start:start + 30] = 90.0
    night[3000:3005] = 90.0                                     # a 5-second blip is not an event
    assert real_tests.odi4(night) == 3.0
    summary = real_tests.night_summary(np.concatenate([night] * 6))
    assert summary["median"] == 96.0 and summary["ring_rule_outside_reference"] is False
