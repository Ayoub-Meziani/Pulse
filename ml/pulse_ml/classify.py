"""Weekly classifier: P(next week's home BP mean >= target), for the doctor's weekly report.

    cd ml && ..\\.venv\\Scripts\\python -m pulse_ml.classify

Label [review M7]: next Monday-Sunday week's mean of valid home readings >= the patient's target, with the
rule systolic OR diastolic (synthetic per-patient targets from patients.csv; fallback = home threshold
135/85). Baseline: "this week's status persists". Metrics overall AND on weeks where the status changes,
because on a persistent series the baseline is strong. The same week_examples() builds training rows and
the serving row used by weekly.py. SYNTHETIC data only; ring features use an invented coupling.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, brier_score_loss, confusion_matrix, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import reference, ring
from .ring_train import load_nights
from .train import ARTIFACTS, DATA, SEED, load_readings, split_patients

MODEL_VERSION = "wcls-v1.1"
FALLBACK_TARGET = (135, 85)          # ESH / ACC-AHA home threshold, see reference.py
MIN_WEEK_READINGS = 3
BP_FEATURES = ["mean_sys", "mean_dia", "n", "m_sys", "e_sys", "slope_sys", "sd_sys", "last3_sys",
               "gap_sys", "gap_dia", "above_now"]
RING_FEATURES = ["ring_nights", "hr_night", "hrv_night", "spo2_night", "temp_night"]


def week_examples(readings: pd.DataFrame, nights: pd.DataFrame | None, targets: dict) -> pd.DataFrame:
    """One row per patient-week (Monday-aligned, local time) with >= 3 valid readings. Features use that
    week only; label columns describe the NEXT week (NaN when it is missing)."""
    r = readings.assign(day=readings.local_dt.dt.normalize())
    r["week"] = r.day - pd.to_timedelta(r.day.dt.day_of_week, unit="D")
    rows = []
    for (patient, week), w in r.groupby(["patient", "week"]):
        if len(w) < MIN_WEEK_READINGS:
            continue
        ts, td = targets.get(patient, FALLBACK_TARGET)
        daily = w.groupby("day").systolic.mean()
        x = (daily.index - week).days.to_numpy(float)
        morning = w[w.local_dt.dt.hour < 12]
        evening = w[w.local_dt.dt.hour >= 12]
        mean_s, mean_d = w.systolic.mean(), w.diastolic.mean()
        rows.append({
            "patient": patient, "week": week, "target_sys": ts, "target_dia": td,
            "mean_sys": mean_s, "mean_dia": mean_d, "n": len(w),
            "m_sys": morning.systolic.mean() if len(morning) else mean_s,
            "e_sys": evening.systolic.mean() if len(evening) else mean_s,
            "slope_sys": np.polyfit(x, daily.to_numpy(), 1)[0] if len(daily) > 1 else 0.0,
            "sd_sys": float(daily.std(ddof=0)),
            "last3_sys": w[w.day >= week + pd.Timedelta(days=4)].systolic.mean() if (w.day >= week + pd.Timedelta(days=4)).any() else mean_s,
            "gap_sys": mean_s - ts, "gap_dia": mean_d - td,
            "above_now": float(mean_s >= ts or mean_d >= td),
        })
    ex = pd.DataFrame(rows)
    if ex.empty:
        return ex
    if nights is not None and len(nights):
        n = nights.assign(week=nights.night - pd.to_timedelta(nights.night.dt.day_of_week, unit="D"))
        agg = n.groupby(["patient", "week"]).agg(ring_nights=("night", "size"), hr_night=("heart_rate", "mean"),
                                                 hrv_night=("hrv_rmssd", "mean"), spo2_night=("spo2", "mean"),
                                                 temp_night=("skin_temperature", "mean")).reset_index()
        ex = ex.merge(agg, on=["patient", "week"], how="left")
    for c in RING_FEATURES:
        if c not in ex:
            ex[c] = np.nan
    nxt = ex[["patient", "week", "mean_sys", "mean_dia", "target_sys", "target_dia"]].copy()
    nxt["week"] = nxt.week - pd.Timedelta(days=7)
    nxt["label"] = ((nxt.mean_sys >= nxt.target_sys) | (nxt.mean_dia >= nxt.target_dia)).astype(float)
    return ex.merge(nxt[["patient", "week", "label"]], on=["patient", "week"], how="left")


def candidates() -> dict:
    return {
        "logistic_regression": make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                                             LogisticRegression(max_iter=1000)),
        "hist_gradient_boosting": HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, random_state=SEED),
    }


def scores(prob: np.ndarray, y: np.ndarray, patients: np.ndarray, n_boot: int = 1000) -> dict:
    """AUROC, balanced accuracy (threshold 0.5), Brier, confusion matrix; 95% CIs resampling patients."""
    pred = (prob >= 0.5).astype(int)
    out = {"n": int(len(y)), "positives": int(y.sum()), "brier": round(float(brier_score_loss(y, prob)), 4),
           "balanced_accuracy": round(float(balanced_accuracy_score(y, pred)), 3),
           "confusion_matrix [[tn, fp], [fn, tp]]": confusion_matrix(y, pred, labels=[0, 1]).tolist()}
    if len(np.unique(y)) < 2:
        out["auroc"] = None
        return out
    out["auroc"] = round(float(roc_auc_score(y, prob)), 3)
    ids = np.unique(patients)
    rng = np.random.default_rng(SEED)
    boot_auc, boot_ba = [], []
    groups = {p: np.flatnonzero(patients == p) for p in ids}
    for _ in range(n_boot):
        idx = np.concatenate([groups[p] for p in rng.choice(ids, len(ids))])
        if len(np.unique(y[idx])) == 2:
            boot_auc.append(roc_auc_score(y[idx], prob[idx]))
            boot_ba.append(balanced_accuracy_score(y[idx], pred[idx]))
    out["auroc_ci95"] = [round(float(v), 3) for v in np.percentile(boot_auc, [2.5, 97.5])]
    out["balanced_accuracy_ci95"] = [round(float(v), 3) for v in np.percentile(boot_ba, [2.5, 97.5])]
    return out


def fit_and_evaluate(readings: pd.DataFrame, nights: pd.DataFrame | None, targets: dict):
    ex = week_examples(readings, nights, targets).dropna(subset=["label"])
    split = split_patients(ex.patient)
    part = {k: ex[ex.patient.isin(v)] for k, v in split.items()}
    feature_sets = {"bp_only": BP_FEATURES}
    if part["train"][RING_FEATURES].notna().any().all():   # ring variant only when ring data exists
        feature_sets["bp_and_ring"] = BP_FEATURES + RING_FEATURES
    val, fitted = {}, {}
    for fs_name, cols in feature_sets.items():
        for name, model in candidates().items():
            key = f"{name}:{fs_name}"
            fitted[key] = (model.fit(part["train"][cols], part["train"].label), cols)
            val[key] = round(float(roc_auc_score(part["val"].label, model.predict_proba(part["val"][cols])[:, 1])), 4)
    best = max(val, key=val.get)
    model, cols = fitted[best]
    test = part["test"]
    y, pts = test.label.to_numpy().astype(int), test.patient.to_numpy()
    changed = (test.above_now != test.label).to_numpy()
    prob = model.predict_proba(test[cols])[:, 1]
    persist = test.above_now.to_numpy()
    meta = {
        "model_version": MODEL_VERSION, "algorithm": best, "features": cols, "trained_on": "synthetic:pulse-sim-v2",
        "label": "next week's mean of valid home readings >= target (systolic OR diastolic); targets from "
                 f"patients.csv, fallback {FALLBACK_TARGET}",
        "split": {"method": "patient-level 70/15/15", "seed": SEED, **{f"{k}_weeks": len(v) for k, v in part.items()}},
        "validation_auroc": val,
        "test": {"model": scores(prob, y, pts), "baseline_status_persists": scores(persist.astype(float), y, pts)},
        "test_status_changes_only": {"model": scores(prob[changed], y[changed], pts[changed]),
                                     "baseline_status_persists": scores(persist[changed].astype(float), y[changed],
                                                                        pts[changed])},
        "limitations": "Synthetic data; ring features carry an invented coupling. Shown to the doctor as a "
                       "probability with its limits; never an alert, never a treatment suggestion.",
    }
    return {"model": model, "features": cols}, meta


def load_targets() -> dict:
    t = pd.read_csv(DATA.parent / "patients.csv")
    return {r.patient_key: (int(r.target_systolic), int(r.target_diastolic)) for r in t.itertuples()}


def main() -> None:
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    bundle, meta = fit_and_evaluate(load_readings(), load_nights(), load_targets())
    meta["trained_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out = ARTIFACTS / MODEL_VERSION
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, out / "model.joblib")
    (out / "metadata.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: meta[k] for k in ("algorithm", "validation_auroc", "test", "test_status_changes_only")},
                     indent=2))


if __name__ == "__main__":
    main()
