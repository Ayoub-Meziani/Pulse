"""SIMULATED live ring stream for the demo: inserts 'now' samples for the demo ring patients.

    python -m pulse_data.stream [--interval 5] [--minutes 3] [--scenario NAME] [--patient cohort_1] [--speed 5]
    python -m pulse_data.stream --patient-email patient.b@demo.pulse.test --scenario oxygen_falling --speed 5 --minutes 20

Scenarios: spo2_dip / hr_rise (a constant shift), or a live situation from pulse_data.live_sim that unfolds minute
by minute (oxygen_falling, heart_rate_climbing, fever_starting, bad_sleep, sleep_apnea, false_alarm_traps,
normal_night). A live situation starts 15 situation-minutes before its onset (at least 30 minutes into the night);
--speed N plays N situation-minutes per real minute (demo only: the live engine then sees faster slopes than a real
night). The accelerated on-stage demo uses oxygen_falling only (speed 3-5); other situations warn reliably only at
speed 1. Give it enough --minutes: the default 3 at speed 5 ends just before the onset; with --minutes 20 the
early warning comes ~7-10 real minutes in. That holds for a personal night SpO2 of about 96-98 % without COPD (Karim:
yes); nearer 94 % or at 98.5 % the median crosses the limit with no early warning, and with COPD no early warning
comes within 20 minutes (offline replay with live-v1).
--patient-email streams to that patient's existing simulated ring in whichever local database DATABASE_URL points to
(e.g. the local dev stack behind the website), and to no other ring. Ring profile: the median of the patient's
previous nights in that database (00:00-06:00 local, last 14 days; the default profile below 3 nights); COPD / atrial
fibrillation from patient_profiles.condition_codes, so the situation's limit is the engine's (COPD: SpO2 88 %).
A live situation first inserts the 30 situation-minutes before its start, one per minute ending now (the live engine
needs ~27 minutes of history before it can warn), then plays at --speed.
Every row is source = 'simulated' with a fresh external_id. Local stack by default; a non-local DATABASE_URL is
always refused (no unlock, D26).
Prints counts only.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import time
import uuid
from dataclasses import replace

import psycopg

from . import live_sim
from .ingest import LOCAL_DB, resolve_patient, ring_device
from .localdb import require_local
from .simulate import GENERATOR_VERSION, PATIENTS, WEARABLE_KEYS, demo_id, ring_profile, risk_factors

SCENARIOS = {"spo2_dip": ("spo2", -7.0), "hr_rise": ("heart_rate", 40.0)}
LIVE_SITUATIONS = tuple(live_sim.SITUATIONS)
LIVE_CONDITIONS = ("copd", "atrial_fibrillation")    # the codes that move a live_sim limit or the heart rate noise
WARM_UP = 30                                         # situation-minutes inserted before the start, one per minute
INSERT = ("insert into public.wearable_samples (patient_id, device_id, metric, value, unit, measured_at, source,"
          " external_id) values (%s, %s, %s, %s, %s, now(), 'simulated', %s)")
INSERT_AGO = INSERT.replace("now()", "now() - make_interval(mins => %s)")
PREVIOUS_NIGHTS = """
    with n as (select s.metric, (s.measured_at at time zone p.timezone)::date as night,
                      percentile_cont(0.5) within group (order by s.value) as v
               from public.wearable_samples s join public.profiles p on p.id = s.patient_id
               where s.patient_id = %s and s.measured_at > now() - interval '14 days'
                 and s.measured_at < (date_trunc('day', now() at time zone p.timezone) at time zone p.timezone)
                 and extract(hour from s.measured_at at time zone p.timezone) < 6
               group by 1, 2)
    select metric, percentile_cont(0.5) within group (order by v), count(*) from n group by 1"""
PROFILE_FIELDS = {"heart_rate": "hr", "hrv_rmssd": "hrv", "spo2": "spo2", "skin_temperature": "temp"}
MIN_NIGHTS = 3


def _profile(key: str):
    user = next(p for p in PATIENTS if p.key == key)
    codes = risk_factors(user)["codes"]
    return user, ring_profile(random.Random(f"{GENERATOR_VERSION}:{key}:ring"), codes), codes  # same as the seed


def patient_profile(conn, patient_id: str, email: str) -> tuple:
    """(ring profile, condition codes): the median of the patient's previous nights, as the live engine computes its
    personal normal; the default profile for a metric with fewer than MIN_NIGHTS nights."""
    found = conn.execute("select condition_codes from public.patient_profiles where user_id = %s", (patient_id,)).fetchone()
    codes = tuple(found[0] or ()) if found else ()
    rp = ring_profile(random.Random(f"{GENERATOR_VERSION}:stream:{email}"), codes)
    medians = {PROFILE_FIELDS[m]: float(v) for m, v, n in conn.execute(PREVIOUS_NIGHTS, (patient_id,)).fetchall()
               if m in PROFILE_FIELDS and n >= MIN_NIGHTS}
    return replace(rp, **medians), codes


def situation_minutes(rp, conditions, situation: str, seed: int = 0) -> tuple[dict, int]:
    """A live situation for this ring profile: {minute: samples} and the start minute."""
    samples, truth = live_sim.night_for(random.Random(f"stream:{situation}:{seed}"), rp,
                                        tuple(c for c in conditions if c in LIVE_CONDITIONS), situation)
    by_minute: dict[int, list] = {}
    for metric, value, unit, minute in samples:
        by_minute.setdefault(minute, []).append((metric, value, unit))
    return by_minute, max(WARM_UP, (truth["onset"] or 15) - 15)


def warm_up(by_minute: dict, start: int) -> list[tuple[int, list]]:
    """(minutes before now, samples) for the WARM_UP situation-minutes before the start, oldest first."""
    return [(start - m, by_minute[m]) for m in range(max(0, start - WARM_UP), start)]


def situation_minute(start: int, elapsed_s: float, speed: float) -> int:
    return min(live_sim.NIGHT_MINUTES - 1, start + int(elapsed_s / 60 * speed))


def tick_samples(by_minute: dict, minute: int, sent_minutes: set) -> list:
    """Heart rate + SpO2 every tick; HRV / temperature once per situation-minute."""
    out = [s for s in by_minute[minute] if s[0] in ("heart_rate", "spo2") or minute not in sent_minutes]
    sent_minutes.add(minute)
    return out


def tick_rows(rng: random.Random, scenario: str | None, scenario_key: str, live_samples: list | None = None) -> list[tuple]:
    """One tick for every demo ring. live_samples replace the scenario patient's values (a live situation)."""
    rows = []
    for key in WEARABLE_KEYS:
        user, rp, _ = _profile(key)
        device = demo_id(key + ":ring")
        if live_samples is not None and key == scenario_key:
            rows += [(user.id, device, m, v, u, f"live-{uuid.uuid4().hex[:16]}") for m, v, u in live_samples]
            continue
        rows += ring_rows(rng, rp, user.id, device, scenario if key == scenario_key else None)
    return rows


def ring_rows(rng: random.Random, rp, patient_id: str, device: str, scenario: str | None) -> list[tuple]:
    """One awake-time heart rate + SpO2 pair around the personal normal, shifted by a constant scenario."""
    hr, spo2 = rng.gauss(rp.hr + 12, 10 if rp.af else 4), min(100.0, rng.gauss(rp.spo2, 0.6))
    if scenario in SCENARIOS:
        metric, shift = SCENARIOS[scenario]
        hr, spo2 = (hr + shift, spo2) if metric == "heart_rate" else (hr, spo2 + shift)
    return [(patient_id, device, "heart_rate", round(hr), "bpm", f"live-{uuid.uuid4().hex[:16]}"),
            (patient_id, device, "spo2", round(spo2, 1), "percent", f"live-{uuid.uuid4().hex[:16]}")]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--minutes", type=float, default=3.0)
    ap.add_argument("--scenario", choices=sorted(SCENARIOS) + list(LIVE_SITUATIONS))
    ap.add_argument("--patient", default="severe_event", choices=WEARABLE_KEYS,
                    help="who gets the scenario (default Nadia; Fatima has COPD, so her SpO2 limit is 88 %%)")
    ap.add_argument("--speed", type=float, default=1.0, help="live situations: situation-minutes per real minute")
    ap.add_argument("--patient-email", help="stream to this patient's existing simulated ring instead of the seed rings")
    a = ap.parse_args()
    url = os.environ.get("DATABASE_URL", LOCAL_DB)
    require_local(url)
    live = a.scenario in LIVE_SITUATIONS
    situation = situation_minutes(*_profile(a.patient)[1:], a.scenario) if live and not a.patient_email else None
    rng, sent, sent_minutes = random.Random(), 0, set()
    with psycopg.connect(url, autocommit=True) as conn:
        target = None
        if a.patient_email:
            pid = resolve_patient(conn, a.patient_email)
            rp, codes = patient_profile(conn, pid, a.patient_email)
            target = (pid, ring_device(conn, pid, simulated=True, create=False), rp)
            if live:
                situation = situation_minutes(rp, codes, a.scenario)
                for ago, samples in warm_up(*situation):
                    for m, v, u in samples:
                        conn.execute(INSERT_AGO, (pid, target[1], m, v, u, ago, f"live-{uuid.uuid4().hex[:16]}"))
                        sent += 1
        began = time.monotonic()
        while time.monotonic() < began + a.minutes * 60:
            live_samples = None
            if situation:
                by_minute, start = situation
                live_samples = tick_samples(by_minute, situation_minute(start, time.monotonic() - began, a.speed),
                                            sent_minutes)
            if target:
                pid, device, rp = target
                rows = (ring_rows(rng, rp, pid, device, a.scenario) if live_samples is None else
                        [(pid, device, m, v, u, f"live-{uuid.uuid4().hex[:16]}") for m, v, u in live_samples])
            else:
                rows = tick_rows(rng, a.scenario, a.patient, live_samples)
            for row in rows:
                conn.execute(INSERT, row)
                sent += 1
            time.sleep(a.interval)
    print(json.dumps({"samples_inserted": sent, "scenario": a.scenario, "speed": a.speed, "source": "simulated"}))


if __name__ == "__main__":
    main()
