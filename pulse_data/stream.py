"""SIMULATED live ring stream for the demo: inserts 'now' samples for the demo ring patients.

    python -m pulse_data.stream [--interval 5] [--minutes 3] [--scenario NAME] [--patient cohort_1] [--speed 5]

Scenarios: spo2_dip / hr_rise (a constant shift), or a live situation from pulse_data.live_sim that unfolds minute
by minute (oxygen_falling, heart_rate_climbing, fever_starting, bad_sleep, sleep_apnea, false_alarm_traps,
normal_night). A live situation starts 15 situation-minutes before its onset; --speed N plays N situation-minutes per
real minute (demo only: the live engine then sees faster slopes than a real night).
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

from . import live_sim
from .ingest import LOCAL_DB
from .simulate import GENERATOR_VERSION, PATIENTS, WEARABLE_KEYS, demo_id, ring_profile, risk_factors

SCENARIOS = {"spo2_dip": ("spo2", -7.0), "hr_rise": ("heart_rate", 40.0)}
LIVE_SITUATIONS = tuple(live_sim.SITUATIONS)
INSERT = ("insert into public.wearable_samples (patient_id, device_id, metric, value, unit, measured_at, source,"
          " external_id) values (%s, %s, %s, %s, %s, now(), 'simulated', %s)")


def _profile(key: str):
    user = next(p for p in PATIENTS if p.key == key)
    codes = risk_factors(user)["codes"]
    return user, ring_profile(random.Random(f"{GENERATOR_VERSION}:{key}:ring"), codes), codes  # same as the seed


def situation_minutes(key: str, situation: str, seed: int = 0) -> tuple[dict, int]:
    """A live situation for this demo patient's own ring profile: {minute: samples} and the start minute."""
    _, rp, codes = _profile(key)
    samples, truth = live_sim.night_for(random.Random(f"stream:{situation}:{seed}"), rp,
                                        tuple(c for c in codes if c in ("copd", "atrial_fibrillation")), situation)
    by_minute: dict[int, list] = {}
    for metric, value, unit, minute in samples:
        by_minute.setdefault(minute, []).append((metric, value, unit))
    return by_minute, max(0, (truth["onset"] or 15) - 15)


def tick_rows(rng: random.Random, scenario: str | None, scenario_key: str, live_samples: list | None = None) -> list[tuple]:
    """One tick for every demo ring. live_samples replace the scenario patient's values (a live situation)."""
    rows = []
    for key in WEARABLE_KEYS:
        user, rp, _ = _profile(key)
        device = demo_id(key + ":ring")
        if live_samples is not None and key == scenario_key:
            rows += [(user.id, device, m, v, u, f"live-{uuid.uuid4().hex[:16]}") for m, v, u in live_samples]
            continue
        hr, spo2 = rng.gauss(rp.hr + 12, 10 if rp.af else 4), min(100.0, rng.gauss(rp.spo2, 0.6))
        if scenario in SCENARIOS and key == scenario_key:
            metric, shift = SCENARIOS[scenario]
            hr, spo2 = (hr + shift, spo2) if metric == "heart_rate" else (hr, spo2 + shift)
        rows += [(user.id, device, "heart_rate", round(hr), "bpm", f"live-{uuid.uuid4().hex[:16]}"),
                 (user.id, device, "spo2", round(spo2, 1), "percent", f"live-{uuid.uuid4().hex[:16]}")]
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--minutes", type=float, default=3.0)
    ap.add_argument("--scenario", choices=sorted(SCENARIOS) + list(LIVE_SITUATIONS))
    ap.add_argument("--patient", default="severe_event", choices=WEARABLE_KEYS,
                    help="who gets the scenario (default Nadia; Fatima has COPD, so her SpO2 limit is 88 %%)")
    ap.add_argument("--speed", type=float, default=1.0, help="live situations: situation-minutes per real minute")
    ap.add_argument("--i-confirmed-cloud", action="store_true")
    a = ap.parse_args()
    url = os.environ.get("DATABASE_URL", LOCAL_DB)
    if urlparse(url).hostname not in ("127.0.0.1", "localhost") and not a.i_confirmed_cloud:
        raise SystemExit("refusing to stream into a non-local database without --i-confirmed-cloud "
                         "(needs backend review + user confirmation)")
    situation = situation_minutes(a.patient, a.scenario) if a.scenario in LIVE_SITUATIONS else None
    rng, sent, began = random.Random(), 0, time.monotonic()
    end, sent_minutes = began + a.minutes * 60, set()
    with psycopg.connect(url, autocommit=True) as conn:
        while time.monotonic() < end:
            live_samples = None
            if situation:
                by_minute, start = situation
                minute = min(live_sim.NIGHT_MINUTES - 1, start + int((time.monotonic() - began) / 60 * a.speed))
                live_samples = [s for s in by_minute[minute] if s[0] in ("heart_rate", "spo2") or minute not in sent_minutes]
                sent_minutes.add(minute)                     # HRV / temperature once per situation-minute
            for row in tick_rows(rng, a.scenario, a.patient, live_samples):
                conn.execute(INSERT, row)
                sent += 1
            time.sleep(a.interval)
    print(json.dumps({"samples_inserted": sent, "scenario": a.scenario, "speed": a.speed, "source": "simulated"}))


if __name__ == "__main__":
    main()
