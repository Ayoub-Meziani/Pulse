"""Train + evaluate the ring monitor on SYNTHETIC data (labelled injected episodes).

    cd ml && ..\\.venv\\Scripts\\python -m pulse_ml.ring_train [--contamination 0.01]

IsolationForest is fitted on training patients' personal z-scores (unsupervised: all their nights).
Methods are scored on held-out test patients against ring_episodes.csv. Contamination is a parameter
tuned to an invented episode rate: report it as a synthetic setting [review L3].
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from . import ring
from .train import ARTIFACTS, DATA, SEED, split_patients

RING_DATA = DATA.parent / "wearable_samples.csv"
EPISODES = DATA.parent / "ring_episodes.csv"


def load_nights() -> pd.DataFrame:
    df = pd.read_csv(RING_DATA)
    if not (df.is_synthetic.astype(str).str.lower() == "true").all():
        raise SystemExit("refusing: ring file contains rows not labelled synthetic")
    return ring.night_table(ring.from_csv(df))


def episode_nights(path=EPISODES) -> pd.DataFrame:
    ep = pd.read_csv(path)
    rows = [(r.patient_key, night, r.episode_type, i)
            for i, r in ep.iterrows()
            for night in pd.date_range(r.start_date, r.end_date, freq="D")]
    return pd.DataFrame(rows, columns=["patient", "night", "episode_type", "episode_id"])


def evaluate(flags: list[dict], zdf: pd.DataFrame, episodes: pd.DataFrame, patients: set) -> dict:
    """Per method: episode recall (>= 1 flagged night inside the episode), night precision,
    false flags per patient-week (flagged nights outside episodes)."""
    nights = zdf[zdf.patient.isin(patients)][["patient", "night"]]
    ep = episodes[episodes.patient.isin(patients)]
    ep_nights = set(zip(ep.patient, ep.night))
    weeks = len(nights) / 7
    f = pd.DataFrame(flags) if flags else pd.DataFrame(columns=["patient_id", "kind", "window_start"])
    if len(f):
        f["night"] = pd.to_datetime(f.window_start).dt.tz_localize(None).dt.normalize()
    methods = {"reference_only": ["outside_reference"], "personal_baseline": ["personal_anomaly"],
               "isolation_forest": ["multivariate_anomaly"],
               "personal_or_isolation_forest": ["personal_anomaly", "multivariate_anomaly"]}
    out = {}
    for name, kinds in methods.items():
        sel = f[f.kind.isin(kinds) & f.patient_id.isin(patients)] if len(f) else f
        flagged = set(zip(sel.patient_id, sel.night)) if len(sel) else set()
        hit = {e for (p, n, e) in zip(ep.patient, ep.night, ep.episode_id) if (p, n) in flagged}
        true_flags = len(flagged & ep_nights)
        out[name] = {"episodes": int(ep.episode_id.nunique()), "episodes_detected": len(hit),
                     "episode_recall": round(len(hit) / max(1, ep.episode_id.nunique()), 3),
                     "flagged_nights": len(flagged),
                     "night_precision": round(true_flags / len(flagged), 3) if flagged else None,
                     "false_flags_per_patient_week": round((len(flagged) - true_flags) / weeks, 3) if weeks else None}
    return out


def fit_and_evaluate(nights: pd.DataFrame, episodes: pd.DataFrame, contamination: float = 0.01):
    zdf = ring.personal_z(nights, ring.baselines(nights))
    split = split_patients(nights.patient)
    zcols = [f"z_{m}" for m in ring.METRICS]
    train = zdf[zdf.patient.isin(split["train"])].dropna(subset=zcols)
    forest = IsolationForest(n_estimators=100, max_samples=256, contamination=contamination,
                             random_state=SEED).fit(train[zcols].to_numpy())
    test = zdf[zdf.patient.isin(split["test"])].reset_index(drop=True)
    flags = ring.night_flags(test, iforest=forest)
    meta = {
        "model_version": ring.MODEL_VERSION, "trained_on": "synthetic:pulse-sim-v1 ring (invented BP coupling)",
        "features": zcols, "baseline": f"rolling {ring.BASELINE_DAYS} days before the night, >= "
                                       f"{ring.MIN_BASELINE_NIGHTS} nights, robust z (median / MAD)",
        "z_limit": ring.Z_LIMIT, "contamination": contamination,
        "contamination_note": "synthetic setting: tuned to the simulator's invented episode rate",
        "split": {"method": "patient-level 70/15/15", "seed": SEED, **{k: len(v) for k, v in split.items()}},
        "test_metrics": evaluate(flags, test, episodes, split["test"]),
        "limitations": "Ring data and episodes are simulated. Flags are advisory for the doctor; they never "
                       "create alerts and are not the safety path.",
    }
    return forest, meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--contamination", type=float, default=0.01)
    a = ap.parse_args()
    forest, meta = fit_and_evaluate(load_nights(), episode_nights(), a.contamination)
    meta["trained_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out = ARTIFACTS / ring.MODEL_VERSION
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump(forest, out / "model.joblib")
    (out / "metadata.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(meta["test_metrics"], indent=2))


if __name__ == "__main__":
    main()
