"""Ring monitor: writes ADVISORY public.wearable_flags only. Never alerts, never the safety path [review H6].

    cd ml && ..\\.venv\\Scripts\\python -m pulse_ml.monitor --nights [--days 35]
        night windows of actively assigned patients: reference, personal baseline / approved band, IsolationForest
    cd ml && ..\\.venv\\Scripts\\python -m pulse_ml.monitor --follow [--every 5]
        live 10-minute windows, polling new samples by created_at with a 5-minute overlap [review M6]

Uses DATABASE_URL (default: local stack). Prints counts only, never health values.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta, timezone

import joblib
import pandas as pd

from . import ring
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


def poll_once(conn, watermark: datetime) -> tuple[datetime, int]:
    """Live step: samples created since (watermark - 5 min overlap) mark the 10-minute buckets to re-evaluate;
    re-reading with overlap + dedup on insert means a late-committed row is not lost [review M6]."""
    tz = assigned(conn)
    new = conn.execute("select patient_id::text, measured_at, created_at from public.wearable_samples"
                       " where created_at > %s and measured_at > now() - %s and patient_id = any(%s::uuid[])",
                       (watermark - OVERLAP, LIVE_HORIZON, list(tz))).fetchall()
    if not new:
        return watermark, 0
    start = min(m for _, m, _ in new) - timedelta(minutes=2 * ring.LIVE_MINUTES)
    rows = conn.execute("select patient_id::text, metric, value, measured_at from public.wearable_samples"
                        " where patient_id = any(%s::uuid[]) and measured_at >= %s",
                        (sorted({p for p, _, _ in new}), start)).fetchall()
    flags = ring.live_flags(ring.live_buckets(ring.from_db(rows, tz)), active_bands(conn),
                            patient_conditions(conn, {p for p, _, _ in new}))
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
        watermark = datetime.now(timezone.utc) - timedelta(minutes=1)
        print(json.dumps({"mode": "follow", "every_s": a.every}), flush=True)
        while True:
            watermark, n = poll_once(conn, watermark)
            if n:
                print(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "flags_written": n}),
                      flush=True)
            time.sleep(a.every)


if __name__ == "__main__":
    main()
