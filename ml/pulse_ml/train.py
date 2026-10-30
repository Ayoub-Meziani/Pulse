"""Offline training + evaluation for the next-day morning BP estimate (contract §4).

    cd ml && ..\\.venv\\Scripts\\python -m pulse_ml.train     # needs data/synthetic/readings.csv
                                                             # (python -m pulse_data.simulate csv)

Patient-level 70/15/15 split (no patient in two sets), features only from earlier days,
scaler fitted on training patients only. Two candidates are compared on validation patients;
the chosen one is scored once on test patients against two baselines.
Results describe SYNTHETIC data (generator pulse-sim-v2) only.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.multioutput import MultiOutputRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .features import FEATURES, build_examples, daily_table, pulse_v1_valid

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "synthetic" / "readings.csv"
ARTIFACTS = ROOT / "ml" / "artifacts"
MODEL_VERSION = "mbp-v1.1"   # v1 features/method, retrained on pulse-sim-v2
TRAINED_ON = "synthetic:pulse-sim-v2"
TZ = "Africa/Algiers"
SEED = 7
INTERVAL_COVERAGE = 0.90
TARGETS = ("sys", "dia")


def load_readings(path: Path = DATA) -> pd.DataFrame:
    df = pd.read_csv(path)
    if not (df.is_synthetic.astype(str).str.lower() == "true").all():
        raise SystemExit("refusing: training file contains rows not labelled synthetic")
    df = df[pulse_v1_valid(df)]
    local = pd.to_datetime(df.measured_at, utc=True).dt.tz_convert(TZ).dt.tz_localize(None)
    return pd.DataFrame({"patient": df.patient_key, "local_dt": local,
                         "systolic": df.systolic, "diastolic": df.diastolic})


def split_patients(patients, seed: int = SEED) -> dict[str, set]:
    p = np.array(sorted(set(patients)))
    np.random.default_rng(seed).shuffle(p)
    a, b = int(0.70 * len(p)), int(0.85 * len(p))
    return {"train": set(p[:a]), "val": set(p[a:b]), "test": set(p[b:])}


def candidates() -> dict:
    return {
        "ridge": make_pipeline(StandardScaler(), Ridge(alpha=1.0)),
        "hist_gradient_boosting": MultiOutputRegressor(
            HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, random_state=SEED)),
    }


def baselines(X: pd.DataFrame) -> dict[str, np.ndarray]:
    return {"persistence_last_morning": X[["last_m_sys", "last_m_dia"]].to_numpy(),
            "mean_7_days": X[["mean7_sys", "mean7_dia"]].to_numpy()}


def score(pred: np.ndarray, y: np.ndarray, patients: np.ndarray, n_boot: int = 1000) -> dict:
    """MAE / RMSE (mmHg) per target with 95% bootstrap CIs, resampling patients."""
    ids, inv = np.unique(patients, return_inverse=True)
    counts = np.bincount(inv)
    idx = np.random.default_rng(SEED).integers(0, len(ids), size=(n_boot, len(ids)))
    out = {}
    for j, t in enumerate(TARGETS):
        err = pred[:, j] - y[:, j]
        abs_s, sq_s = np.bincount(inv, np.abs(err)), np.bincount(inv, err ** 2)
        n_b = counts[idx].sum(1)
        mae_b, rmse_b = abs_s[idx].sum(1) / n_b, np.sqrt(sq_s[idx].sum(1) / n_b)
        out[t] = {"mae": round(float(np.abs(err).mean()), 2),
                  "mae_ci95": [round(float(v), 2) for v in np.percentile(mae_b, [2.5, 97.5])],
                  "rmse": round(float(np.sqrt((err ** 2).mean())), 2),
                  "rmse_ci95": [round(float(v), 2) for v in np.percentile(rmse_b, [2.5, 97.5])]}
    return out


def fit_and_evaluate(readings: pd.DataFrame) -> tuple[object, dict]:
    ex = build_examples(daily_table(readings))
    split = split_patients(ex.patient)
    part = {k: ex[ex.patient.isin(v)] for k, v in split.items()}
    X = {k: v[FEATURES] for k, v in part.items()}
    y = {k: v[["y_sys", "y_dia"]].to_numpy() for k, v in part.items()}

    val_mae, fitted = {}, {}
    for name, model in candidates().items():
        fitted[name] = model.fit(X["train"], y["train"])
        val_mae[name] = round(float(np.abs(model.predict(X["val"]) - y["val"]).mean()), 3)
    best = min(val_mae, key=val_mae.get)
    model = fitted[best]
    # Split-conformal interval: half-width = 90th percentile of |error| on validation patients.
    half_width = np.quantile(np.abs(model.predict(X["val"]) - y["val"]), INTERVAL_COVERAGE, axis=0)

    test_pred = model.predict(X["test"])
    pts = part["test"].patient.to_numpy()
    covered = (np.abs(test_pred - y["test"]) <= half_width).mean(axis=0)
    metrics = {name: score(p, y["test"], pts) for name, p in baselines(X["test"]).items()}
    metrics[f"model:{best}"] = score(test_pred, y["test"], pts)
    meta = {
        "model_version": MODEL_VERSION, "algorithm": best, "target": "morning_mean_bp",
        "trained_on": TRAINED_ON, "features": FEATURES,
        "eligibility": "≥6 valid readings on ≥4 local days in the 7 days before the target day, ≥1 morning reading",
        "split": {"method": "patient-level 70/15/15", "seed": SEED,
                  **{f"{k}_patients": len(v) for k, v in split.items()},
                  **{f"{k}_examples": len(v) for k, v in part.items()}},
        "validation_mae_mean_of_sys_dia": val_mae,
        "test_metrics_mmHg": metrics,
        "interval": {"method": "split-conformal on validation patients", "nominal_coverage": INTERVAL_COVERAGE,
                     "half_width_sys": round(float(half_width[0]), 1), "half_width_dia": round(float(half_width[1]), 1),
                     "test_coverage_sys": round(float(covered[0]), 3), "test_coverage_dia": round(float(covered[1]), 3)},
        "limitations": "Model estimate trained on synthetic data only. Not a measurement, not clinically validated, "
                       "not used for alerts, never a basis for medication decisions.",
    }
    return {"model": model, "features": FEATURES, "half_width": half_width.tolist()}, meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=DATA)
    a = ap.parse_args()
    bundle, meta = fit_and_evaluate(load_readings(a.data))
    meta["trained_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    meta["data"] = {"file": a.data.name, "generator_version": "pulse-sim-v2", "generator_seed": SEED}
    out = ARTIFACTS / MODEL_VERSION
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, out / "model.joblib")
    (out / "metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"algorithm": meta["algorithm"], "validation": meta["validation_mae_mean_of_sys_dia"],
                      "test": meta["test_metrics_mmHg"], "interval": meta["interval"]}, indent=2))


if __name__ == "__main__":
    main()
