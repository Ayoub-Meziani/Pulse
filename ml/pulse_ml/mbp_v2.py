"""mbp-v2.1 EXPERIMENT: mbp-v1.1 features + ring night features, same examples and same patient split.

    cd ml && ..\\.venv\\Scripts\\python -m pulse_ml.mbp_v2

Reported side by side with v1. mbp-v1.1 stays the served model unless v2 wins on validation AND the backend
agrees (contract §4: BP history only for the MVP). Ring nights strictly before the target day. Any gain is
on synthetic data whose ring <-> BP coupling was invented, so it is a gain by construction.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.multioutput import MultiOutputRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .features import FEATURES, build_examples, daily_table
from .ring_train import load_nights
from .train import ARTIFACTS, SEED, load_readings, score, split_patients

MODEL_VERSION = "mbp-v2.1"
RING_FEATURES = ["hr_last_night", "hrv_last_night", "spo2_last_night", "temp_last_night",
                 "hr_7_nights", "hrv_7_nights", "ring_nights_7"]


def ring_day_features(ex: pd.DataFrame, nights: pd.DataFrame) -> pd.DataFrame:
    """For each example (patient, day D): ring nights strictly before D (last night and 7-night means)."""
    by_patient = {p: n.set_index("night").sort_index() for p, n in nights.groupby("patient")}
    rows = []
    for patient, day in zip(ex.patient, ex.day):
        n = by_patient.get(patient)
        w = n.loc[day - pd.Timedelta(days=7): day - pd.Timedelta(days=1)] if n is not None else None
        if w is None or w.empty:
            rows.append({c: np.nan for c in RING_FEATURES[:-1]} | {"ring_nights_7": 0})
            continue
        last = w.iloc[-1]
        rows.append({"hr_last_night": last.heart_rate, "hrv_last_night": last.hrv_rmssd, "spo2_last_night": last.spo2,
                     "temp_last_night": last.skin_temperature, "hr_7_nights": w.heart_rate.mean(),
                     "hrv_7_nights": w.hrv_rmssd.mean(), "ring_nights_7": len(w)})
    return pd.concat([ex.reset_index(drop=True), pd.DataFrame(rows)], axis=1)


def candidates() -> dict:
    return {"ridge": make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=1.0)),
            "hist_gradient_boosting": MultiOutputRegressor(
                HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, random_state=SEED))}


def fit_and_evaluate(readings: pd.DataFrame, nights: pd.DataFrame):
    ex = ring_day_features(build_examples(daily_table(readings)), nights)
    split = split_patients(ex.patient)
    part = {k: ex[ex.patient.isin(v)] for k, v in split.items()}
    y = {k: v[["y_sys", "y_dia"]].to_numpy() for k, v in part.items()}
    results, models = {}, {}
    for version, cols in {"v1_features": FEATURES, "v2_features": FEATURES + RING_FEATURES}.items():
        val = {}
        for name, model in candidates().items():
            model.fit(part["train"][cols], y["train"])
            val[name] = round(float(np.abs(model.predict(part["val"][cols]) - y["val"]).mean()), 3)
            models[(version, name)] = model
        best = min(val, key=val.get)
        pred = models[(version, best)].predict(part["test"][cols])
        results[version] = {"validation_mae_mean_of_sys_dia": val, "chosen": best,
                            "test_metrics_mmHg": score(pred, y["test"], part["test"].patient.to_numpy())}
    v2_best = results["v2_features"]["chosen"]
    meta = {
        "model_version": MODEL_VERSION, "status": "experiment, not served", "trained_on": "synthetic:pulse-sim-v2",
        "ring_features": RING_FEATURES, "split": {"method": "patient-level 70/15/15", "seed": SEED,
                                                  **{f"{k}_examples": len(v) for k, v in part.items()}},
        "comparison": results,
        "v2_wins_on_validation": min(results["v2_features"]["validation_mae_mean_of_sys_dia"].values())
                                 < min(results["v1_features"]["validation_mae_mean_of_sys_dia"].values()),
        "serving_decision": "mbp-v1.1 stays served unless v2 wins on validation AND the backend agrees",
        "limitations": "Ring <-> BP coupling in the simulator is invented: any v2 gain is by construction.",
    }
    return {"model": models[("v2_features", v2_best)], "features": FEATURES + RING_FEATURES}, meta


def main() -> None:
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    bundle, meta = fit_and_evaluate(load_readings(), load_nights())
    meta["trained_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out = ARTIFACTS / MODEL_VERSION
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, out / "model.joblib")
    (out / "metadata.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: meta[k] for k in ("comparison", "v2_wins_on_validation")}, indent=2))


if __name__ == "__main__":
    main()
