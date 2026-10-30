"""Features for the next-day morning blood-pressure estimate (PULSE_INTEGRATION_CONTRACTS.md §4).

Shared by training and the prediction job, so both see exactly the same inputs.
Every feature for target day D comes from readings on local days strictly before D.
Input readings must already be valid (DB `validation_status = 'valid'`, or `pulse_v1_valid` offline).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

WINDOW_DAYS = 7
MIN_READINGS, MIN_DAYS, MIN_MORNING = 6, 4, 1   # eligibility in the 7 days before D
MORNING_BEFORE_HOUR = 12                        # "morning" = local time before 12:00

FEATURES = [
    "last_m_sys", "last_m_dia", "mean7_sys", "mean7_dia", "mean3_sys", "mean3_dia",
    "m7_sys", "m7_dia", "slope7_sys", "slope7_dia", "sd7_sys", "gap7_sys", "n7", "days7",
    *(f"dow_{k}" for k in range(7)),
]


def pulse_v1_valid(df: pd.DataFrame) -> pd.Series:
    """Offline files only: True where DB policy pulse-v1 would say 'valid' (value rules; the
    2-minute duplicate rule needs the DB). Keep in step with private.validate_measurement()."""
    s, d, p = df.systolic, df.diastolic, df.get("pulse", pd.Series(np.nan, index=df.index))
    return (s > d) & s.between(70, 250) & d.between(40, 150) & (p.isna() | p.between(25, 250))


def daily_table(readings: pd.DataFrame) -> pd.DataFrame:
    """readings: patient, local_dt (naive local time), systolic, diastolic -> one row per patient-day."""
    r = readings.assign(day=readings.local_dt.dt.normalize(),
                        morning=readings.local_dt.dt.hour < MORNING_BEFORE_HOUR)

    def agg(part: pd.DataFrame, prefix: str) -> pd.DataFrame:
        g = part.groupby(["patient", "day"])
        return g.agg(**{f"{prefix}sys": ("systolic", "mean"), f"{prefix}dia": ("diastolic", "mean"),
                        f"{prefix}n": ("systolic", "size")})

    out = agg(r, "").join(agg(r[r.morning], "m_")).join(agg(r[~r.morning], "e_"))
    return out.fillna({"m_n": 0, "e_n": 0}).reset_index()


def window_features(days: pd.DataFrame, target: pd.Timestamp) -> tuple[dict | None, int]:
    """days: one patient's daily_table indexed by day. Returns (features or None if not eligible,
    number of valid readings in the 7-day window)."""
    w = days.loc[target - pd.Timedelta(days=WINDOW_DAYS): target - pd.Timedelta(days=1)]
    n = int(w.n.sum())
    if n < MIN_READINGS or len(w) < MIN_DAYS or w.m_n.sum() < MIN_MORNING:
        return None, n
    wm, we = w[w.m_n > 0], w[w.e_n > 0]
    last3 = w[w.index >= target - pd.Timedelta(days=3)]
    if last3.empty:
        last3 = w
    x = (w.index - target).days.to_numpy(float)
    m7_sys = np.average(wm.m_sys, weights=wm.m_n)
    f = {
        "last_m_sys": wm.m_sys.iloc[-1], "last_m_dia": wm.m_dia.iloc[-1],
        "mean7_sys": np.average(w.sys, weights=w.n), "mean7_dia": np.average(w.dia, weights=w.n),
        "mean3_sys": np.average(last3.sys, weights=last3.n), "mean3_dia": np.average(last3.dia, weights=last3.n),
        "m7_sys": m7_sys, "m7_dia": np.average(wm.m_dia, weights=wm.m_n),
        "slope7_sys": np.polyfit(x, w.sys, 1)[0], "slope7_dia": np.polyfit(x, w.dia, 1)[0],
        "sd7_sys": float(w.sys.std(ddof=0)),
        "gap7_sys": m7_sys - np.average(we.e_sys, weights=we.e_n) if len(we) else 0.0,
        "n7": n, "days7": len(w),
        **{f"dow_{k}": float(target.day_of_week == k) for k in range(7)},
    }
    return {k: float(v) for k, v in f.items()}, n


def build_examples(daily: pd.DataFrame) -> pd.DataFrame:
    """Training rows: every patient-day with a morning reading and an eligible history.
    Target = that day's morning mean systolic / diastolic."""
    rows = []
    for patient, days in daily.groupby("patient"):
        days = days.set_index("day").sort_index()
        for day, target in days[days.m_n > 0].iterrows():
            f, _ = window_features(days, day)
            if f is not None:
                rows.append({"patient": patient, "day": day, **f, "y_sys": target.m_sys, "y_dia": target.m_dia})
    return pd.DataFrame(rows)
