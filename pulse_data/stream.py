"""SIMULATED live ring stream for the demo: inserts 'now' samples for the demo ring patients.

    python -m pulse_data.stream [--interval 5] [--minutes 3] [--scenario spo2_dip|hr_rise] [--patient cohort_1]

Every row is source = 'simulated' with a fresh external_id. Local stack by default; a non-local
DATABASE_URL is refused unless --i-confirmed-cloud is given (backend review + user confirmation, review M9).
Prints counts only.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import time
import uuid
from urllib.parse import urlparse

import psycopg

from .ingest import LOCAL_DB
from .simulate import GENERATOR_VERSION, PATIENTS, WEARABLE_KEYS, demo_id, ring_profile, risk_factors

SCENARIOS = {"spo2_dip": ("spo2", -7.0), "hr_rise": ("heart_rate", 40.0)}
INSERT = ("insert into public.wearable_samples (patient_id, device_id, metric, value, unit, measured_at, source,"
          " external_id) values (%s, %s, %s, %s, %s, now(), 'simulated', %s)")


def tick_rows(rng: random.Random, scenario: str | None, scenario_key: str) -> list[tuple]:
    rows = []
    for key in WEARABLE_KEYS:
        user = next(p for p in PATIENTS if p.key == key)
        rp = ring_profile(random.Random(f"{GENERATOR_VERSION}:{key}:ring"),
                          risk_factors(user)["codes"])  # same personal values (and chronic conditions) as the seed
        hr, spo2 = rng.gauss(rp.hr + 12, 10 if rp.af else 4), min(100.0, rng.gauss(rp.spo2, 0.6))
        if scenario and key == scenario_key:
            metric, shift = SCENARIOS[scenario]
            hr, spo2 = (hr + shift, spo2) if metric == "heart_rate" else (hr, spo2 + shift)
        device = demo_id(key + ":ring")
        rows += [(user.id, device, "heart_rate", round(hr), "bpm", f"live-{uuid.uuid4().hex[:16]}"),
                 (user.id, device, "spo2", round(spo2, 1), "percent", f"live-{uuid.uuid4().hex[:16]}")]
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--minutes", type=float, default=3.0)
    ap.add_argument("--scenario", choices=sorted(SCENARIOS))
    ap.add_argument("--patient", default="severe_event", choices=WEARABLE_KEYS,
                    help="who gets the scenario (default Nadia; Fatima has COPD, so her SpO2 limit is 88 %%)")
    ap.add_argument("--i-confirmed-cloud", action="store_true")
    a = ap.parse_args()
    url = os.environ.get("DATABASE_URL", LOCAL_DB)
    if urlparse(url).hostname not in ("127.0.0.1", "localhost") and not a.i_confirmed_cloud:
        raise SystemExit("refusing to stream into a non-local database without --i-confirmed-cloud "
                         "(needs backend review + user confirmation)")
    rng, sent, end = random.Random(), 0, time.monotonic() + a.minutes * 60
    with psycopg.connect(url, autocommit=True) as conn:
        while time.monotonic() < end:
            for row in tick_rows(rng, a.scenario, a.patient):
                conn.execute(INSERT, row)
                sent += 1
            time.sleep(a.interval)
    print(json.dumps({"samples_inserted": sent, "scenario": a.scenario, "source": "simulated"}))


if __name__ == "__main__":
    main()
