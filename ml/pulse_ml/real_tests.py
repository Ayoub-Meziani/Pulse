"""Tests of PULSE logic on REAL data (no retraining).

    cd ml && ..\\.venv\\Scripts\\python -m pulse_ml.real_tests [mendeley|apnea|all]

mendeley  real:mendeley_hbpm, 1 patient, 1 measurement every 3 days. mbp-v1 cannot be applied (it needs >= 6
          readings on >= 4 days in 7), so this is a REALISM check: how much does real home BP move between
          measurements 3 days apart, compared with our simulator? Results -> artifacts/mbp-v1/metadata.json
apnea     real:apnea_ecg, 8 overnight SpO2 recordings (apnea / borderline / control). Our ring SpO2 rules
          (night median vs 94 %, dips of >= 4 %) at ring cadence, plus ODI-4 from the full signal.
          Results -> artifacts/ring-v1/metadata.json
Results are labelled real:<source> and carry n; the data never leaves data/external/.
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from . import reference
from .real_data import APNEA_RECORDS, SOURCES, load_apnea_spo2, load_mendeley
from .train import ARTIFACTS, DATA

RING_MINUTES = (60, 120, 180, 240, 300, 330)   # the simulated ring's night SpO2 times
GROUPS = {"a": "apnea", "b": "borderline", "c": "control"}


def series_stats(x: np.ndarray) -> dict:
    """How predictable is the next measurement: persistence and mean-of-last-3 errors, spread, lag-1 correlation."""
    x = np.asarray(x, float)
    last3 = pd.Series(x).rolling(3).mean().shift(1).to_numpy()
    return {"n": int(len(x)), "mean": round(float(x.mean()), 1), "sd": round(float(x.std(ddof=1)), 1),
            "persistence_mae": round(float(np.nanmean(np.abs(x[1:] - x[:-1]))), 2),
            "mean_last3_mae": round(float(np.nanmean(np.abs(x - last3))), 2),
            "lag1_correlation": round(float(np.corrcoef(x[1:], x[:-1])[0, 1]), 3)}


def synthetic_every_3_days(min_days: int = 20) -> dict:
    """Same statistics on the synthetic cohort (treated patients), sampled like the real series: one daily
    mean every 3 days. Median across patients."""
    r = pd.read_csv(DATA)
    ctx = pd.read_csv(DATA.parent / "daily_context.csv")
    treated = set(ctx[ctx.on_medication.astype(str) == "True"].patient_key)
    r = r[r.patient_key.isin(treated) & (r.systolic > r.diastolic)]
    daily = r.groupby(["patient_key", "local_date"]).systolic.mean().reset_index()
    per = []
    for _, g in daily.groupby("patient_key"):
        g = g.sort_values("local_date").iloc[::3]
        if len(g) >= min_days:
            per.append(series_stats(g.systolic.to_numpy()))
    keys = ("sd", "persistence_mae", "mean_last3_mae", "lag1_correlation")
    return {"patients": len(per), **{k: round(float(np.median([p[k] for p in per])), 3) for k in keys}}


def mendeley_test() -> dict:
    m = load_mendeley()
    real = {k: series_stats(m[k].to_numpy()) for k in ("systolic", "diastolic", "pulse")}
    synth = synthetic_every_3_days()
    return {
        "source": "real:mendeley_hbpm", "credit": SOURCES["mendeley_hbpm"]["credit"],
        "licence": SOURCES["mendeley_hbpm"]["licence"],
        "patient": "1 treated 67-year-old man (dataset description), Microlife BP 3AG1, mean of 3 trials, "
                   "1 measurement every 3 days over 384 days",
        "mbp_v1_applicable": False,
        "why_not": "mbp-v1 needs >= 6 valid readings on >= 4 days in the 7 days before the target day and a "
                   "morning reading; this series has 1 measurement every 3 days and no clock times",
        "real_systolic": real["systolic"], "real_diastolic": real["diastolic"], "real_pulse": real["pulse"],
        "synthetic_systolic_same_sampling_median_patient": synth,
    }


def odi4(spo2: np.ndarray, hz: float = 1.0) -> float:
    """Desaturation events per hour: >= 4 % below the highest value of the previous 120 s, lasting >= 10 s."""
    s = pd.Series(spo2)
    base = s.rolling(int(120 * hz), min_periods=int(30 * hz)).max().shift(1)
    desat = (s <= base - 4).astype(int)
    runs = (desat.diff() == 1).cumsum().where(desat == 1)
    events = int((runs.value_counts() >= 10 * hz).sum()) if runs.notna().any() else 0
    hours = s.notna().sum() / hz / 3600
    return round(events / hours, 1) if hours > 0 else float("nan")


def night_summary(spo2_1hz: np.ndarray) -> dict:
    s = spo2_1hz[~np.isnan(spo2_1hz)]
    picks = [spo2_1hz[m * 60] for m in RING_MINUTES if m * 60 < len(spo2_1hz) and not np.isnan(spo2_1hz[m * 60])]
    med6 = float(np.median(picks)) if picks else float("nan")
    return {"hours": round(len(s) / 3600, 1), "median": round(float(np.median(s)), 1),
            "p5": round(float(np.percentile(s, 5)), 1), "minimum": round(float(s.min()), 1),
            "pct_time_below_90": round(float((s < 90).mean() * 100), 1), "odi4_per_hour": odi4(spo2_1hz),
            "ring6_median": round(med6, 1), "ring6_samples": len(picks),
            "ring6_dips_4pct": int(sum(p <= med6 - 4 for p in picks)),
            "ring_rule_outside_reference": bool(reference.outside_reference("spo2", med6)) if picks else None}


def apnea_test() -> dict:
    rows = {}
    for rec in APNEA_RECORDS:
        sig, fs = load_apnea_spo2(rec)
        sig = np.where((sig >= 50) & (sig <= 100), sig, np.nan)       # 0 / out-of-range = artifact
        per_sec = pd.Series(sig).groupby(np.arange(len(sig)) // int(fs)).median().to_numpy()
        rows[rec] = {"group": GROUPS[rec[0]], **night_summary(per_sec)}
    df = pd.DataFrame(rows).T
    by_group = {}
    for g, part in df.groupby("group"):
        by_group[g] = {"recordings": int(len(part)),
                       **{k: round(float(pd.to_numeric(part[k]).mean()), 2)
                          for k in ("median", "minimum", "pct_time_below_90", "odi4_per_hour", "ring6_median",
                                    "ring6_dips_4pct")},
                       "ring_rule_flagged": int(part.ring_rule_outside_reference.sum())}
    return {"source": "real:apnea_ecg", "credit": SOURCES["apnea_ecg"]["credit"],
            "licence": SOURCES["apnea_ecg"]["licence"], "recordings": rows, "by_group": by_group,
            "simulator_assumption": "sleep apnea: 2-4 of 6 night samples dip 4-9 %; healthy: 0-1 dip of 3-5 %"}


def _attach(model: str, key: str, result: dict) -> None:
    path = ARTIFACTS / model / "metadata.json"
    meta = json.loads(path.read_text(encoding="utf-8"))
    meta.setdefault("real_tests", {})[key] = result
    path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("which", choices=["mendeley", "apnea", "all"])
    a = ap.parse_args()
    if a.which in ("mendeley", "all"):
        res = mendeley_test()
        _attach("mbp-v1", "mendeley_hbpm", res)
        print(json.dumps({k: res[k] for k in ("real_systolic", "real_diastolic",
                                               "synthetic_systolic_same_sampling_median_patient")}, indent=2))
    if a.which in ("apnea", "all"):
        res = apnea_test()
        _attach("ring-v1", "apnea_ecg", res)
        print(json.dumps(res["by_group"], indent=2))


if __name__ == "__main__":
    main()
