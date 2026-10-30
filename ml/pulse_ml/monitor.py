"""Ring monitor: writes ADVISORY public.wearable_flags only. Never alerts, never the safety path [review H6].

    cd ml && ..\\.venv\\Scripts\\python -m pulse_ml.monitor --nights [--days 35]
        night windows of actively assigned patients: reference, personal baseline / approved band, IsolationForest
    cd ml && ..\\.venv\\Scripts\\python -m pulse_ml.monitor --follow [--every 5]
        live 10-minute windows, polling new samples by created_at with a 5-minute overlap [review M6], plus the
        live-v1 early warnings (pulse_ml.live: forecast of the next 20 minutes, restless night) for the newest minute

Uses DATABASE_URL (default: local stack). Prints counts only, never health values.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta, timezone

import joblib
import pandas as pd

from . import live, ring
from .predict import PATIENTS, connect
from .train import ARTIFACTS

OVERLAP = timedelta(minutes=5)
LIVE_HORIZON = timedelta(minutes=30)   # live mode only looks at recently measured samples

INSERT = """
    insert into public.wearable_flags (patient_id, metric, kind, window_kind, window_start, window_end, value, score,
      reference_basis, band_id, model_version)
    values (%(patient_id)s, %(metric)s, %(kind)s, %(window_kind)s, %(window_start)s, %(window_end)s, %(value)s,
      %(score)s, %(reference_basis)s, %(band_id)s, %(model_version)s)
    on conflict (patient_id, metric, kind, window_start) do nothing returning id"""  # never overwrites a review


def assigned(conn) -> dict[str, str]:
    return dict(conn.execute(PATIENTS).fetchall())


def patient_conditions(conn, patients) -> dict[str, tuple]:
    rows = conn.execute("select user_id::text, condition_codes from public.patient_profiles"
                        " where user_id = any(%s::uuid[])", (list(patients),)).fetchall()
    return {p: tuple(c or ()) for p, c in rows}


def active_bands(conn) -> dict:
    rows = conn.execute("select patient_id::text, metric, statistic, id::text, low, high from public.patient_bands"
                        " where status = 'active'").fetchall()
    return {(p, m, s): (i, float(lo), float(hi)) for p, m, s, i, lo, hi in rows}


def confirmed_nights(conn, tz_by_patient: dict) -> set[tuple]:
    rows = conn.execute("select patient_id::text, metric, window_start from public.wearable_flags"
                        " where review_status = 'confirmed' and window_kind = 'night'").fetchall()
    return {(p, pd.Timestamp(ws.astimezone(_zone(tz_by_patient.get(p)))).tz_localize(None).normalize(), m)
            for p, m, ws in rows if m in ring.METRICS}


def _zone(tz: str | None):
    from zoneinfo import ZoneInfo
    return ZoneInfo(tz or "Africa/Algiers")


def insert_flags(conn, flags: list[dict]) -> int:
    return sum(1 for f in flags if conn.execute(INSERT, f).fetchone())


def run_nights(conn, forest=None, days: int = 35) -> int:
    tz = assigned(conn)
    if not tz:
        return 0
    rows = conn.execute("select patient_id::text, metric, value, measured_at from public.wearable_samples"
                        " where patient_id = any(%s::uuid[]) and measured_at >= now() - %s * interval '1 day'",
                        (list(tz), days)).fetchall()
    if not rows:
        return 0
    nights = ring.night_table(ring.from_db(rows, tz))
    zdf = ring.personal_z(nights, ring.baselines(nights, confirmed_nights(conn, tz))).reset_index(drop=True)
    return insert_flags(conn, ring.night_flags(zdf, active_bands(conn), iforest=forest, tz_by_patient=tz,
                                               conditions=patient_conditions(conn, tz)))


def load_live():
    path = ARTIFACTS / live.MODEL_VERSION / "model.joblib"
    return joblib.load(path) if path.exists() else None


def live_warnings(conn, patients: set, tz: dict, bundle) -> list[dict]:
    """live-v1 early warnings for the newest minute of each patient (advisory, doctor only). Personal normal = the
    median of the previous nights (14 days); history = the last 6 hours (forecast: last 60 min; sleep: since 00:00)."""
    now = conn.execute("select now()").fetchone()[0]
    rows = conn.execute("select patient_id::text, metric, value, measured_at from public.wearable_samples"
                        " where patient_id = any(%s::uuid[]) and measured_at > %s - interval '14 days'",
                        (sorted(patients), now)).fetchall()
    if not rows:
        return []
    samples = ring.from_db(rows, tz)
    conditions, bands = patient_conditions(conn, patients), active_bands(conn)
    warned = conn.execute("select patient_id::text, metric, max(window_start) from public.wearable_flags"
                          " where kind = 'early_warning' and window_start > %s - interval '30 minutes'"
                          " and patient_id = any(%s::uuid[]) group by 1, 2", (now, sorted(patients))).fetchall()
    out = []
    for patient, s in samples.groupby("patient"):
        zone = _zone(tz.get(patient))
        local_now = pd.Timestamp(now.astimezone(zone)).tz_localize(None)
        recent = s[s.utc > now - timedelta(hours=6)]
        if recent.empty or (pd.Timestamp(now) - recent.utc.max()) > pd.Timedelta(minutes=2):
            continue                                              # nothing measured in the last 2 minutes
        before = s[s.local < local_now.normalize()]
        previous = ring.night_table(before) if len(before) else pd.DataFrame()
        ctx = live.Context(personal={m: float(previous[m].median()) for m in (*live.METRICS, "hrv_rmssd")
                                     if m in previous and previous[m].notna().any()},
                           conditions=conditions.get(patient, ()),
                           bands={m: b for (p, m, st), b in bands.items() if p == patient and st == "live_10min_median"})
        t = live.table(recent.assign(minute=recent.local.dt.floor("min"))[["minute", "metric", "value"]])
        last = {m: pd.Timestamp(w.astimezone(zone)).tz_localize(None) for p, m, w in warned if p == patient}
        out += live.latest_warnings(t.iloc[-live.HISTORY_MINUTES:], ctx, bundle, last, patient, str(zone))
        minute_of_night = local_now.hour * 60 + local_now.minute
        if live.SLEEP_FROM <= minute_of_night < 360 and "heart_rate" in t:
            checkpoint = local_now.normalize() + pd.Timedelta(minutes=minute_of_night // live.SLEEP_EVERY * live.SLEEP_EVERY)
            night = t[(t.index >= local_now.normalize()) & (t.index <= checkpoint)]
            if len(night) >= live.SLEEP_FROM and (p := live.sleep_risk(night, ctx, bundle)) >= live.SLEEP_P:
                start = local_now.normalize().tz_localize(str(zone))
                out.append(dict(patient_id=patient, metric="sleep", kind="early_warning", window_kind="forecast",
                                window_start=start, window_end=start + pd.Timedelta(hours=6), value=None,
                                score=round(p, 3), reference_basis=f"forecast:{live.MODEL_VERSION}:restless_night:"
                                                                   f"P>={live.SLEEP_P}", band_id=None,
                                model_version=live.MODEL_VERSION))
    return out


def poll_once(conn, watermark: datetime, live_bundle=None) -> tuple[datetime, int]:
    """Live step: samples created since (watermark - 5 min overlap) mark the 10-minute buckets to re-evaluate;
    re-reading with overlap + dedup on insert means a late-committed row is not lost [review M6]. With live_bundle,
    the live-v1 early warnings are added for the patients with new samples."""
    tz = assigned(conn)
    new = conn.execute("select patient_id::text, measured_at, created_at from public.wearable_samples"
                       " where created_at > %s and measured_at > now() - %s and patient_id = any(%s::uuid[])",
                       (watermark - OVERLAP, LIVE_HORIZON, list(tz))).fetchall()
    if not new:
        return watermark, 0
    start = min(m for _, m, _ in new) - timedelta(minutes=2 * ring.LIVE_MINUTES)
    patients = {p for p, _, _ in new}
    rows = conn.execute("select patient_id::text, metric, value, measured_at from public.wearable_samples"
                        " where patient_id = any(%s::uuid[]) and measured_at >= %s",
                        (sorted(patients), start)).fetchall()
    flags = ring.live_flags(ring.live_buckets(ring.from_db(rows, tz)), active_bands(conn),
                            patient_conditions(conn, patients))
    if live_bundle is not None:
        flags += live_warnings(conn, patients, tz, live_bundle)
    return max(watermark, max(c for _, _, c in new)), insert_flags(conn, flags)


def load_forest():
    path = ARTIFACTS / ring.MODEL_VERSION / "model.joblib"
    return joblib.load(path) if path.exists() else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--nights", action="store_true")
    mode.add_argument("--follow", action="store_true")
    ap.add_argument("--days", type=int, default=35)
    ap.add_argument("--every", type=float, default=5.0, help="seconds between polls in --follow")
    a = ap.parse_args()
    with connect(autocommit=True) as conn:
        if a.nights:
            print(json.dumps({"mode": "nights", "flags_written": run_nights(conn, load_forest(), a.days)}))
            return
        watermark, bundle = datetime.now(timezone.utc) - timedelta(minutes=1), load_live()
        print(json.dumps({"mode": "follow", "every_s": a.every, "early_warnings": bundle is not None}), flush=True)
        while True:
            watermark, n = poll_once(conn, watermark, bundle)
            if n:
                print(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "flags_written": n}),
                      flush=True)
            time.sleep(a.every)


if __name__ == "__main__":
    main()
