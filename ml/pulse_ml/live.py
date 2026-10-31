"""Live ring engine (live-v1): checks every new minute and warns the DOCTOR before a limit is crossed. ADVISORY.

One path for the minute-by-minute test (live_test.py) and the live monitor (monitor.py --follow):
    table        one row per minute, the median of each metric (HRV / temperature carried for up to 5 minutes)
    forecast     the value at +10 and +20 minutes (gradient boosting on the last 30 minutes, shown to the doctor)
    candidates   per minute and metric: still inside its limit, and P(limit crossed within 20 minutes) >= the
                 metric's threshold (gradient-boosting classifier; thresholds chosen on held-out TRAINING nights)
    early warning  a candidate 2 minutes in a row, at most once per metric every 30 minutes
    sleep        from 01:00, every 30 minutes: P(this night ends restless); warn once when >= 0.7
A linear forecast alone learned "it comes back to normal" (most blips do) and never warned; the classifier learns
how a real decline differs from a passing dip, wake-up or loose ring.
Limits: SpO2 94 % (COPD 88 %), resting HR 100 bpm (or the doctor's live band), skin temperature personal normal
+ 1.0 C. Every feature at minute t uses minutes <= t only (rolling windows look back), so scoring a whole night at
once equals replaying it minute by minute (checked in tests and in live_test.py).
Never an alert and never the safety path. R-RING-1 is not implemented and stays disabled (B26): nothing happens when
a ring limit is crossed (no alert, no patient guidance); the backend's BP and symptom rules decide anything urgent.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import reference

MODEL_VERSION = "live-v1"
METRICS = ("heart_rate", "spo2", "skin_temperature")
HORIZONS = (10, 20)
HISTORY_MINUTES = 60
QUIET_MINUTES = 30
FEVER_RISE = 1.0            # C above the personal night normal (assumption, matches pulse_data.live_sim)
AWAKE_HR = 10               # bpm above the personal sleeping heart rate = an awake minute
SLEEP_FROM, SLEEP_EVERY, SLEEP_P = 60, 30, 0.7
FEATURES = ["d15", "d30", "slope10", "slope25", "sd15", "dev"]
WARN_FEATURES = FEATURES + ["margin"]      # margin: distance to the limit, positive while still inside
WARN_WITHIN = 20
SLEEP_FEATURES = ["awake_share", "bouts", "hr_excess", "hrv_ratio", "elapsed"]


@dataclass
class Context:
    personal: dict                                   # metric -> median of the previous nights
    conditions: tuple = ()
    bands: dict = field(default_factory=dict)        # metric -> (band_id, low, high), live_10min_median bands


def table(minute_values: pd.DataFrame) -> pd.DataFrame:
    """minute_values: columns minute (int or Timestamp), metric, value -> full minute grid, one column per metric."""
    t = minute_values.pivot_table(index="minute", columns="metric", values="value", aggfunc="median")
    full = (pd.date_range(t.index.min(), t.index.max(), freq="min") if isinstance(t.index, pd.DatetimeIndex)
            else range(int(t.index.min()), int(t.index.max()) + 1))
    t = t.reindex(full)
    for m in ("hrv_rmssd", "skin_temperature"):
        if m in t:
            t[m] = t[m].ffill(limit=5)
    return t


def feature_frame(s: pd.Series, personal: float | None) -> pd.DataFrame:
    s3 = s.rolling(3, min_periods=2).median()                 # a single loose-ring reading cannot move it
    med5 = s.rolling(5, min_periods=3).median()
    f = pd.DataFrame({"last": s3,
                      "d15": s3 - s.rolling(15, min_periods=8).median(),
                      "d30": s3 - s.rolling(30, min_periods=15).median(),
                      "slope10": (med5 - med5.shift(10)) / 10, "slope25": (med5 - med5.shift(25)) / 25,
                      "sd15": s.rolling(15, min_periods=8).std(),
                      "dev": s3 - (personal if personal is not None else s.rolling(60, min_periods=15).median())})
    return f


def limit_for(metric: str, ctx: Context) -> tuple[str, float, str, str | None] | None:
    """(side, value, basis, band_id) or None when the metric cannot be judged for this patient."""
    if not reference.interpretable(metric, ctx.conditions):
        return None
    if metric == "skin_temperature":
        p = ctx.personal.get(metric)
        return None if p is None else ("high", p + FEVER_RISE, f"personal+{FEVER_RISE}C", None)
    ref = reference.reference_for(metric, ctx.conditions)
    side = "low" if metric == "spo2" else "high"
    band = ctx.bands.get(metric)
    if band:
        return side, band[1] if side == "low" else band[2], f"band:{band[0]}", band[0]
    return side, ref["low"] if side == "low" else ref["high"], f"reference:{metric}<{ref['low']}" if side == "low" \
        else f"reference:{metric}>{ref['high']}", None


def warn_frame(t: pd.DataFrame, metric: str, ctx: Context) -> pd.DataFrame | None:
    """Features + margin for the warning classifier. None when the metric is not judged for this patient."""
    lim = limit_for(metric, ctx)
    if lim is None or metric not in t:
        return None
    f = feature_frame(t[metric], ctx.personal.get(metric))
    f["margin"] = f["last"] - lim[1] if lim[0] == "low" else lim[1] - f["last"]
    return f


def candidates(t: pd.DataFrame, metric: str, ctx: Context, bundle: dict) -> pd.DataFrame | None:
    """Per minute: candidate (bool), P(crossing within 20 min) and the +20-minute forecast."""
    f = warn_frame(t, metric, ctx)
    if f is None:
        return None
    ok = (f[WARN_FEATURES + ["last"]].notna().all(axis=1) & (f["margin"] > 0)).to_numpy()
    out = pd.DataFrame({"candidate": False, "p": np.nan, "forecast": np.nan}, index=t.index)
    if ok.any():
        p = bundle["warn"][metric].predict_proba(f.loc[ok, WARN_FEATURES])[:, 1]
        out.loc[ok, "p"] = p
        out.loc[ok, "candidate"] = p >= bundle["threshold"][metric]
        out.loc[ok, "forecast"] = f.loc[ok, "last"].to_numpy() + bundle["forecast"][(metric, WARN_WITHIN)].predict(
            f.loc[ok, FEATURES])
    return out


def _warning(patient, metric, ctx, minute, p, value, tz) -> dict:
    _, limit, basis, band_id = limit_for(metric, ctx)
    start = pd.Timestamp(minute).tz_localize(tz) if tz else minute
    return dict(patient_id=patient, metric=metric, kind="early_warning", window_kind="forecast", window_start=start,
                window_end=start + pd.Timedelta(minutes=WARN_WITHIN) if tz else int(minute) + WARN_WITHIN,
                value=round(float(value), 2), score=round(float(p), 3),
                reference_basis=f"forecast:{MODEL_VERSION}:{basis}:limit={limit:g}:P(cross<{WARN_WITHIN}min)",
                band_id=band_id, model_version=MODEL_VERSION)


def night_warnings(t: pd.DataFrame, ctx: Context, bundle: dict, patient=None, tz=None) -> list[dict]:
    """Every early warning a live run would have produced over this table (2 minutes in a row, 30 minutes quiet)."""
    out = []
    for metric in METRICS:
        c = candidates(t, metric, ctx, bundle)
        if c is None:
            continue
        cand, last = c.candidate.to_numpy(), -10 ** 9
        for i in range(1, len(c)):
            if cand[i] and cand[i - 1] and i - last >= QUIET_MINUTES:
                out.append(_warning(patient, metric, ctx, c.index[i], c.p.iat[i], c.forecast.iat[i], tz))
                last = i
    return out


def latest_warnings(t: pd.DataFrame, ctx: Context, bundle: dict, last_warned: dict, patient=None, tz=None) -> list[dict]:
    """Live step: warnings for the newest minute of t only. last_warned[metric] = minute of the last warning."""
    out = []
    for metric in METRICS:
        c = candidates(t, metric, ctx, bundle)
        if c is None or len(c) < 2 or not (c.candidate.iat[-1] and c.candidate.iat[-2]):
            continue
        now, prev = c.index[-1], last_warned.get(metric)
        quiet = pd.Timedelta(minutes=QUIET_MINUTES) if isinstance(now, pd.Timestamp) else QUIET_MINUTES
        if prev is None or now - prev >= quiet:
            out.append(_warning(patient, metric, ctx, now, c.p.iat[-1], c.forecast.iat[-1], tz))
    return out


def sleep_features(t: pd.DataFrame, ctx: Context) -> dict:
    """From midnight to now: awake minutes and bouts (HR >= personal + 10 for 3+ minutes), HR and HRV vs normal."""
    hr = t["heart_rate"].dropna()
    p_hr = ctx.personal.get("heart_rate") or float(hr.median())
    awake = hr.rolling(3, min_periods=2).median() > p_hr + AWAKE_HR
    runs = awake.groupby((awake != awake.shift()).cumsum()).agg(["first", "size"])
    p_hrv = ctx.personal.get("hrv_rmssd")
    hrv_ok = "hrv_rmssd" in t and p_hrv and reference.interpretable("hrv_rmssd", ctx.conditions)
    return {"awake_share": float(awake.mean()), "bouts": int((runs["first"] & (runs["size"] >= 3)).sum()),
            "hr_excess": float(hr.median() - p_hr),
            "hrv_ratio": float(t["hrv_rmssd"].median() / p_hrv) if hrv_ok else 1.0,
            "elapsed": len(t) / 360}


def sleep_risk(t: pd.DataFrame, ctx: Context, bundle: dict) -> float:
    return float(bundle["sleep"].predict_proba(pd.DataFrame([sleep_features(t, ctx)])[SLEEP_FEATURES])[0, 1])
