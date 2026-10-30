"""30-day day-by-day test on NEW patients that no model has seen. Every model is frozen; nothing is retrained.

    ..\\.venv\\Scripts\\python -m pulse_data.simulate csv --out data/holdout --patients 100 --days 90 --seed 2026 --prefix H
    cd ml && ..\\.venv\\Scripts\\python -m pulse_ml.backtest

The holdout cohort uses another seed and other patient keys (H0001...), so no patient, day or ring profile overlaps
the training data (S0001...). Days 0-59 are history; days 60-89 are the 30 test days. On every test day D each model
sees only data from before D, through the same feature code as in serving, and is scored against what happened on D:
- mbp-v1.1 / mbp-v2.1: next-morning BP vs the measured morning mean, beside the two simple baselines
- ring-v1.1: every night flagged or not, vs the injected (labelled) episodes; personal baseline from earlier nights
- wcls-v1.1: at the end of each week, P(next week above target) vs what the next week showed
Plus one REAL external test: wrisk-v1 (trained on NHANES 2017-2020) on NHANES 2021-2023 people it never saw
(python -m pulse_ml.real_data fetch nhanes_2021). The other models have no open real data of their kind (daily home BP
of many patients); the ring SpO2 rule's real test (PhysioNet Apnea-ECG) is in artifacts/ring-v1.1/metadata.json.
Writes aggregated results only -> artifacts/backtest-30d/results.json. SYNTHETIC holdout (pulse-sim-v2).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd

from sklearn.metrics import roc_auc_score

from . import classify, mbp_v2, ring, wrisk
from .features import build_examples, daily_table
from .real_data import EXTERNAL, SOURCES, load_nhanes
from .ring_train import episode_nights, evaluate
from .train import ARTIFACTS, ROOT, baselines, load_readings, score, split_patients

HOLDOUT = ROOT / "data" / "holdout"
START = pd.Timestamp("2026-01-01")          # pulse_data.simulate.ML_START
HISTORY_DAYS, TEST_DAYS = 60, 30
TEST_START = START + pd.Timedelta(days=HISTORY_DAYS)
TEST_END = TEST_START + pd.Timedelta(days=TEST_DAYS - 1)
OUT = ARTIFACTS / "backtest-30d" / "results.json"


def _load(version: str) -> dict:
    return joblib.load(ARTIFACTS / version / "model.joblib")


def in_window(days: pd.Series) -> pd.Series:
    return (days >= TEST_START) & (days <= TEST_END)


def mbp_part(readings: pd.DataFrame, nights: pd.DataFrame) -> dict:
    daily = daily_table(readings)
    ex = build_examples(daily)                      # features for day D use days < D only
    ex = ex[in_window(ex.day)].reset_index(drop=True)
    asked = int((in_window(daily.day) & (daily.m_n > 0)).sum())   # test days with a morning reading to predict
    y, pts = ex[["y_sys", "y_dia"]].to_numpy(), ex.patient.to_numpy()
    v1, v2 = _load("mbp-v1.1"), _load(mbp_v2.MODEL_VERSION)
    pred = {"mbp-v1.1": v1["model"].predict(ex[v1["features"]]),
            "mbp-v2.1": v2["model"].predict(mbp_v2.ring_day_features(ex, nights)[v2["features"]]),
            **baselines(ex[v1["features"]])}
    hw = np.asarray(v1["half_width"])
    err = {k: np.abs(p - y) for k, p in pred.items()}
    per_day = []
    for day, idx in ex.groupby("day").groups.items():
        per_day.append({"day": str(day.date()), "n": len(idx),
                        **{f"mae_sys:{k}": round(float(e[idx, 0].mean()), 2) for k, e in err.items()}})
    beats = sum(d["mae_sys:mbp-v1.1"] < d["mae_sys:mean_7_days"] for d in per_day)
    patient = ex.patient.value_counts().index[0]     # an example patient with the most test days
    pe = ex.index[ex.patient == patient]
    return {
        "test_days": TEST_DAYS, "patient_days_to_predict": asked, "patient_days_predicted": len(ex),
        "insufficient_history": asked - len(ex), "patients": int(ex.patient.nunique()),
        "metrics_mmHg": {k: score(p, y, pts) for k, p in pred.items()},
        "within_10_mmHg_systolic": {k: round(float((e[:, 0] <= 10).mean()), 3) for k, e in err.items()},
        "within_5_mmHg_diastolic": {k: round(float((e[:, 1] <= 5).mean()), 3) for k, e in err.items()},
        "interval_coverage_mbp_v1_1": {"nominal": 0.9, "sys": round(float((err["mbp-v1.1"][:, 0] <= hw[0]).mean()), 3),
                                       "dia": round(float((err["mbp-v1.1"][:, 1] <= hw[1]).mean()), 3)},
        "days_mbp_v1_1_beats_7_day_mean_systolic": f"{beats} / {len(per_day)}",
        "per_day": per_day,
        "example_patient": {"patient": patient, "series": [
            {"day": str(ex.day[i].date()), "actual_sys": round(float(y[i, 0]), 1),
             "predicted_sys": round(float(pred["mbp-v1.1"][i, 0]), 1), "mean_7_days_sys": round(float(pred["mean_7_days"][i, 0]), 1)}
            for i in pe]},
    }


def ring_part(nights: pd.DataFrame, conditions: dict) -> dict:
    zdf = ring.personal_z(nights, ring.baselines(nights))     # baseline: the 28 nights strictly before each night
    win = zdf[in_window(zdf.night)].reset_index(drop=True)
    flags = ring.night_flags(win, iforest=_load(ring.MODEL_VERSION), conditions=conditions)
    ep = episode_nights(HOLDOUT / "ring_episodes.csv")
    ep = ep[in_window(pd.to_datetime(ep.night))].assign(night=lambda d: pd.to_datetime(d.night))
    result = evaluate(flags, win, ep, set(win.patient))
    f = pd.DataFrame(flags)
    personal = set(zip(f[f.kind == "personal_anomaly"].patient_id,
                       pd.to_datetime(f[f.kind == "personal_anomaly"].window_start).dt.tz_localize(None).dt.normalize()))
    by_type = {}
    for t, g in ep.groupby("episode_type"):
        found = {e for p, n, e in zip(g.patient, g.night, g.episode_id) if (p, n) in personal}
        by_type[t] = f"{len(found)} / {g.episode_id.nunique()}"
    return {"nights_checked": len(win), "patients": int(win.patient.nunique()), "methods": result,
            "personal_baseline_by_episode_type": by_type}


def wcls_part(readings: pd.DataFrame, nights: pd.DataFrame, targets: dict) -> dict:
    ex = classify.week_examples(readings, nights, targets).dropna(subset=["label"])
    nxt = ex.week + pd.Timedelta(days=7)            # the week being predicted must lie inside the 30 test days
    ex = ex[(nxt >= TEST_START) & (nxt + pd.Timedelta(days=6) <= TEST_END)]
    m = _load(classify.MODEL_VERSION)
    prob = m["model"].predict_proba(ex[m["features"]])[:, 1]
    y, pts, persist = ex.label.to_numpy().astype(int), ex.patient.to_numpy(), ex.above_now.to_numpy()
    changed = persist != y
    return {"weeks_predicted": sorted(str((w + pd.Timedelta(days=7)).date()) for w in ex.week.unique()),
            "predictions": len(ex),
            "model": classify.scores(prob, y, pts), "baseline_status_persists": classify.scores(persist, y, pts),
            "status_changes_only": {"n": int(changed.sum()), "model": classify.scores(prob[changed], y[changed], pts[changed]),
                                    "baseline_status_persists": classify.scores(persist[changed], y[changed], pts[changed])}}


def wrisk_part() -> dict:
    """REAL external test: the frozen wrisk-v1 on NHANES 2021-2023 people (a later survey, never used in training)."""
    if not (EXTERNAL / "nhanes_2021").exists():
        return {"skipped": "run: python -m pulse_ml.real_data fetch nhanes_2021"}
    old, new = wrisk.nhanes_examples(load_nhanes()), wrisk.nhanes_examples(load_nhanes("nhanes_2021"))
    if set(old.person) & set(new.person):
        raise SystemExit("refusing: the 2021-2023 test people overlap the training survey")
    y, w, pts = new.label.to_numpy(), new.weight.to_numpy(), new.person.to_numpy()
    prob = _load(wrisk.MODEL_VERSION)["model"].predict_proba(new[wrisk.FEATURES])[:, 1]
    train = old[old.person.isin(split_patients(old.person)["train"])]   # same training people as wrisk-v1
    agesex = wrisk._fit(wrisk.candidates()["logistic_regression"], train[["age", "female"]], train.label,
                        train.weight).predict_proba(new[["age", "female"]])[:, 1]
    return {"source": f"real:nhanes_2021 ({SOURCES['nhanes_2021']['name']})", "credit": SOURCES["nhanes_2021"]["credit"],
            "terms": SOURCES["nhanes_2021"]["licence"], "people": len(new),
            "uncontrolled_rate_weighted": round(float(np.average(y, weights=w)), 3),
            "model": {**classify.scores(prob, y, pts), "auroc_weighted": round(float(roc_auc_score(y, prob, sample_weight=w)), 3),
                      "calibration_quintiles": wrisk.calibration(prob, y)},
            "baseline_age_sex": {**classify.scores(agesex, y, pts),
                                 "auroc_weighted": round(float(roc_auc_score(y, agesex, sample_weight=w)), 3)}}


def main() -> None:
    if not (HOLDOUT / "readings.csv").exists():
        raise SystemExit("no holdout cohort: run the simulate command in this module's docstring first")
    readings = load_readings(HOLDOUT / "readings.csv")
    if readings.patient.str.startswith("S").any():
        raise SystemExit("refusing: holdout contains training patient keys")
    pts = pd.read_csv(HOLDOUT / "patients.csv", keep_default_na=False)
    targets = {r.patient_key: (int(r.target_systolic), int(r.target_diastolic)) for r in pts.itertuples()}
    conditions = {r.patient_key: tuple(c for c in r.conditions.split(";") if c) for r in pts.itertuples()}
    nights = ring.night_table(ring.from_csv(pd.read_csv(HOLDOUT / "wearable_samples.csv")))
    results = {
        "what": "30-day walk-forward test on an unseen synthetic cohort; models frozen (no retraining)",
        "holdout": {"generator": "pulse-sim-v2", "seed": 2026, "patient_keys": "H0001-H0100 (training: S0001-S0200)",
                    "patients": int(readings.patient.nunique()), "history_days": HISTORY_DAYS,
                    "test_window": [str(TEST_START.date()), str(TEST_END.date())]},
        "mbp": mbp_part(readings, nights),
        "ring": ring_part(nights, conditions),
        "wcls": wcls_part(readings, nights, targets),
        "wrisk_real_external": wrisk_part(),
        "not_testable_on_real_data": {
            "mbp-v1.1 / mbp-v2.1 / wcls-v1.1": "no open real dataset has daily home BP of many patients; the one real "
                                               "series (Mendeley, 1 patient, every 3 days) was used to calibrate the simulator",
            "ring-v1.1": "real SpO2 test already done on all 8 PhysioNet Apnea-ECG nights (artifacts/ring-v1.1/metadata.json)"},
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    brief = {"mbp": {k: results["mbp"][k] for k in ("patient_days_predicted", "insufficient_history",
                                                     "within_10_mmHg_systolic", "interval_coverage_mbp_v1_1",
                                                     "days_mbp_v1_1_beats_7_day_mean_systolic")},
             "mbp_mae": {k: {t: v[t]["mae"] for t in v} for k, v in results["mbp"]["metrics_mmHg"].items()},
             "ring": results["ring"]["methods"], "ring_by_type": results["ring"]["personal_baseline_by_episode_type"],
             "wcls": {k: results["wcls"][k] for k in ("weeks_predicted", "predictions")},
             "wcls_auroc": {"model": results["wcls"]["model"]["auroc"],
                            "persist": results["wcls"]["baseline_status_persists"]["auroc"],
                            "changes_only_model": results["wcls"]["status_changes_only"]["model"].get("auroc")},
             "wrisk_real": {k: v for k, v in results["wrisk_real_external"].items() if k not in ("credit", "terms")}}
    print(json.dumps(brief, indent=2))


if __name__ == "__main__":
    main()
