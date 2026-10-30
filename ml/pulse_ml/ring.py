"""Ring features, personal baselines and ADVISORY flags.

ONE path from raw samples to windows, used by training (CSV) and serving (DB) [review H2]:
    from_csv / from_db -> night_table / live_buckets -> baselines -> night_flags / live_flags
Flags never create alerts and are not the safety path [review H6]; the backend evaluates R-RING-1 itself.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import reference

METRICS = ("heart_rate", "hrv_rmssd", "spo2", "skin_temperature")
EPISODE_METRIC = {"hr_rise": "heart_rate", "spo2_dip": "spo2", "hrv_drop": "hrv_rmssd"}
NIGHT_HOURS = (0, 6)                 # local 00:00-06:00
LIVE_MINUTES = 10
BASELINE_DAYS, MIN_BASELINE_NIGHTS = 28, 14
Z_LIMIT = 3.5
MIN_LIVE_SAMPLES = 2
# The night statistic compared with references and personal bands, per metric [review M8]. SpO2 uses the night
# MEDIAN: healthy sleepers normally dip (mean lowest saturation 90.4 %, Gries & Brooks 1996), so the night minimum
# would flag healthy people against the 94 % reference.
NIGHT_STAT = {"heart_rate": "night_median", "hrv_rmssd": "night_median", "spo2": "night_median",
              "skin_temperature": "night_median"}
MODEL_VERSION = "ring-v1"


# ---------------------------------------------------------------- one sample frame for CSV and DB

def _frame(patient, metric, value, utc: pd.Series, tz: pd.Series) -> pd.DataFrame:
    local = pd.Series(pd.NaT, index=utc.index, dtype="datetime64[ns]")
    for zone in tz.unique():
        m = tz == zone
        local[m] = utc[m].dt.tz_convert(zone).dt.tz_localize(None)
    return pd.DataFrame({"patient": patient.astype(str), "metric": metric, "value": value.astype(float),
                         "utc": utc, "local": local})


def from_csv(df: pd.DataFrame, tz: str = "Africa/Algiers") -> pd.DataFrame:
    """data/synthetic/wearable_samples.csv rows -> sample frame."""
    utc = pd.to_datetime(df.measured_at, utc=True)
    return _frame(df.patient_key, df.metric, df.value, utc, pd.Series(tz, index=df.index))


def from_db(rows: list[tuple], tz_by_patient: dict[str, str]) -> pd.DataFrame:
    """rows (patient_id, metric, value, measured_at) from public.wearable_samples -> sample frame."""
    df = pd.DataFrame(rows, columns=["patient", "metric", "value", "measured_at"])
    df["patient"] = df.patient.astype(str)
    utc = pd.to_datetime(df.measured_at, utc=True)
    return _frame(df.patient, df.metric, pd.to_numeric(df.value), utc,
                  df.patient.map(lambda p: tz_by_patient.get(p, "Africa/Algiers")))


# ---------------------------------------------------------------- night windows (baselines, weekly, multivariate)

def night_table(samples: pd.DataFrame) -> pd.DataFrame:
    """One row per patient-night: the NIGHT_STAT of each metric (night medians; several SpO2 samples per night),
    plus sample counts."""
    s = samples[(samples.local.dt.hour >= NIGHT_HOURS[0]) & (samples.local.dt.hour < NIGHT_HOURS[1])]
    s = s.assign(night=s.local.dt.normalize())
    g = s.groupby(["patient", "night", "metric"]).value
    stats = g.agg(["median", "min", "count"]).unstack("metric")
    out = pd.DataFrame(index=stats.index)
    for m in METRICS:
        col = ("min" if NIGHT_STAT[m] == "night_min" else "median", m)
        out[m] = stats[col] if col in stats.columns else np.nan
        out[f"n_{m}"] = stats[("count", m)] if ("count", m) in stats.columns else 0
    return out.reset_index()


def baselines(nights: pd.DataFrame, exclude: set[tuple] = frozenset()) -> pd.DataFrame:
    """Personal baseline per patient-night from the 28 days STRICTLY BEFORE that night, skipping windows a
    doctor confirmed as anomalies (exclude = {(patient, night, metric)}) [review L4]. Needs 14 nights."""
    parts = []
    for patient, p in nights.groupby("patient"):
        p = p.set_index("night").sort_index()
        values = p[list(METRICS)].copy()
        for (pt, night, metric) in exclude:
            if pt == patient and night in values.index:
                values.loc[night, metric] = np.nan
        roll = values.rolling(f"{BASELINE_DAYS}D", closed="left", min_periods=MIN_BASELINE_NIGHTS)
        mad = roll.apply(lambda x: np.median(np.abs(x - np.median(x))), raw=True)
        b = pd.concat([roll.median().add_suffix("_med"), mad.add_suffix("_mad"), roll.count().add_suffix("_n")], axis=1)
        parts.append(b.assign(patient=patient).reset_index())
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def robust_z(value: float, med: float, mad: float) -> float:
    return (value - med) / (1.4826 * mad + 1e-6)


def personal_z(nights: pd.DataFrame, base: pd.DataFrame) -> pd.DataFrame:
    """Night values as robust z-scores against the personal baseline (NaN while in cold start)."""
    df = nights.merge(base, on=["patient", "night"], how="left")
    for m in METRICS:
        ok = df[f"{m}_n"] >= MIN_BASELINE_NIGHTS
        df[f"z_{m}"] = np.where(ok, robust_z(df[m], df[f"{m}_med"], df[f"{m}_mad"]), np.nan)
    return df


def _flag(patient, metric, kind, window_kind, start: pd.Timestamp, end: pd.Timestamp, value, score, basis,
          band_id=None) -> dict:
    return dict(patient_id=patient, metric=metric, kind=kind, window_kind=window_kind, window_start=start,
                window_end=end, value=None if value is None or pd.isna(value) else round(float(value), 2),
                score=None if score is None or pd.isna(score) else round(float(score), 3),
                reference_basis=basis, band_id=band_id, model_version=MODEL_VERSION)


def night_flags(zdf: pd.DataFrame, bands: dict | None = None, k: float = Z_LIMIT,
                iforest=None, tz_by_patient: dict | None = None, conditions: dict | None = None) -> list[dict]:
    """Advisory flags for night windows. A doctor-approved band (bands[(patient, metric, statistic)] =
    (id, low, high)) always overrides the learned baseline. conditions[patient] = chronic condition codes:
    they move references (COPD) or make a metric not interpretable (AF: HRV, and so the multivariate score)."""
    bands, tz_by_patient, conditions = bands or {}, tz_by_patient or {}, conditions or {}
    flags = []
    zcols = [f"z_{m}" for m in METRICS]
    scores = None
    if iforest is not None:
        all_ok = zdf.patient.map(lambda p: all(reference.interpretable(m, conditions.get(p, ())) for m in METRICS))
        complete = zdf[zcols].notna().all(axis=1) & all_ok
        scores = pd.Series(np.nan, index=zdf.index)
        if complete.any():
            scores[complete] = -iforest.score_samples(zdf.loc[complete, zcols].to_numpy())
    for i, row in zdf.iterrows():
        start = pd.Timestamp(row.night).tz_localize(tz_by_patient.get(row.patient, "Africa/Algiers"))
        end = start + pd.Timedelta(hours=NIGHT_HOURS[1])
        conds = conditions.get(row.patient, ())
        for m in METRICS:
            v = row[m]
            if pd.isna(v) or not reference.interpretable(m, conds):
                continue
            if reference.outside_reference(m, v, conds):
                flags.append(_flag(row.patient, m, "outside_reference", "night", start, end, v, None, f"reference:{m}"))
            band = bands.get((row.patient, m, NIGHT_STAT[m]))
            if band is not None:
                if not band[1] <= v <= band[2]:
                    flags.append(_flag(row.patient, m, "personal_anomaly", "night", start, end, v, None,
                                       f"band:{band[0]}", band[0]))
            elif not pd.isna(row[f"z_{m}"]) and abs(row[f"z_{m}"]) > k:
                flags.append(_flag(row.patient, m, "personal_anomaly", "night", start, end, v, row[f"z_{m}"],
                                   f"baseline:robust_z>{k}:{BASELINE_DAYS}d"))
        if scores is not None and not pd.isna(scores[i]) and scores[i] > -iforest.offset_:  # score_samples < offset_
            flags.append(_flag(row.patient, "multivariate", "multivariate_anomaly", "night", start, end, None,
                               scores[i], "isolation_forest:personal_z"))
    return flags


# ---------------------------------------------------------------- live 10-minute windows (--follow)

def live_buckets(samples: pd.DataFrame) -> pd.DataFrame:
    s = samples.assign(bucket=samples.utc.dt.floor(f"{LIVE_MINUTES}min"))
    return s.groupby(["patient", "metric", "bucket"]).value.agg(["median", "count"]).reset_index()


def live_flags(buckets: pd.DataFrame, bands: dict | None = None, conditions: dict | None = None) -> list[dict]:
    """outside_reference: bucket median outside the (condition-aware) reference with >= 2 samples.
    personal_anomaly: outside an active live band in 2 consecutive buckets (sustained)."""
    bands, conditions = bands or {}, conditions or {}
    flags = []
    ok = buckets[buckets["count"] >= MIN_LIVE_SAMPLES].sort_values("bucket")
    for (patient, metric), g in ok.groupby(["patient", "metric"]):
        conds = conditions.get(patient, ())
        if not reference.interpretable(metric, conds):
            continue
        band = bands.get((patient, metric, "live_10min_median"))
        prev_out = None
        for _, r in g.iterrows():
            end = r.bucket + pd.Timedelta(minutes=LIVE_MINUTES)
            if reference.outside_reference(metric, r["median"], conds):
                flags.append(_flag(patient, metric, "outside_reference", "live_10min", r.bucket, end, r["median"],
                                   None, f"reference:{metric}"))
            out = band is not None and not band[1] <= r["median"] <= band[2]
            if out and prev_out == r.bucket - pd.Timedelta(minutes=LIVE_MINUTES):
                flags.append(_flag(patient, metric, "personal_anomaly", "live_10min", r.bucket, end, r["median"],
                                   None, f"band:{band[0]}", band[0]))
            prev_out = r.bucket if out else None
    return flags
