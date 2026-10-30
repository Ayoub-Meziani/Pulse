"""SIMULATED live ring situations, minute by minute (there is no real ring yet; every value is synthetic).

    python -m pulse_data.live_sim --out data/live/train --nights 700 --seed 11
    python -m pulse_data.live_sim --out data/live/test --nights 700 --seed 2027     (unseen nights)

A night is 00:00-06:00 local (360 minutes): heart rate and SpO2 every minute, HRV and skin temperature every
5 minutes, with the metrics / units / ranges of public.wearable_samples. The personal normal comes from
simulate.ring_profile() (COPD: lower SpO2; atrial fibrillation: noisy heart rate). Before each night the same person
has one ordinary night: its medians are the "previous nights" a live monitor would know (no hidden truth used).
Situations and their ground truth (onset minute, the minute a limit is really crossed, restless night or not):
    normal_night, bad_sleep, sleep_apnea, oxygen_falling, heart_rate_climbing, fever_starting, false_alarm_traps
Levels follow the published values in simulate.py; slopes, bout counts and artefacts are ASSUMPTIONS for testing.
Writes samples.csv and nights.csv into a git-ignored folder.
"""
from __future__ import annotations

import argparse
import csv
import math
import random
import statistics
from dataclasses import replace
from pathlib import Path

from .simulate import RingProfile, ring_profile

NIGHT_MINUTES = 360
SITUATIONS = {"normal_night": 0.20, "bad_sleep": 0.20, "sleep_apnea": 0.10, "oxygen_falling": 0.15,
              "heart_rate_climbing": 0.15, "fever_starting": 0.10, "false_alarm_traps": 0.10}
FEVER_RISE = 1.0     # skin temperature above the personal normal that counts as "fever reached" (assumption)


def limits(conditions, prev: dict) -> dict:
    """The line each situation is judged against: the same references the engine uses (COPD: SpO2 88 %)."""
    return {"spo2": 88.0 if "copd" in conditions else 94.0, "heart_rate": 100.0,
            "skin_temperature": round(prev["skin_temperature"] + FEVER_RISE, 2)}


def _bouts(rng, hr, hrv, count, length, up, late_share=0.0):
    for _ in range(count):
        start = rng.randint(120, NIGHT_MINUTES - 25) if rng.random() < late_share else rng.randint(5, NIGHT_MINUTES - 25)
        rise = rng.uniform(*up)
        for m in range(start, min(NIGHT_MINUTES, start + rng.randint(*length))):
            hr[m] += rise
            hrv[m] *= 0.7


def true_night(rng: random.Random, rp: RingProfile, situation: str, lim: dict) -> tuple[dict, dict]:
    """Underlying (true) per-minute values + ground truth. Measurement noise is added in measure()."""
    n = NIGHT_MINUTES
    hr = [rp.hr + 2.0 - 3.0 * math.sin(math.pi * m / n) for m in range(n)]       # a little lower mid-night
    spo2, hrv, temp = [rp.spo2] * n, [rp.hrv] * n, [rp.temp + 0.3 * math.sin(math.pi * m / n) for m in range(n)]
    truth = {"situation": situation, "restless": 0, "metric": "", "onset": None, "crossing": None, "events": 0}
    if situation in ("normal_night", "false_alarm_traps", "oxygen_falling", "heart_rate_climbing", "fever_starting"):
        _bouts(rng, hr, hrv, rng.randint(0, 2), (2, 8), (6, 12))                 # ordinary short wake-ups
        if rng.random() < 0.5:                                                   # healthy sleepers dip once
            m = rng.randint(10, n - 3)
            for k in (m, m + 1):
                spo2[k] -= rng.uniform(3, 5)
    if situation == "bad_sleep":
        _bouts(rng, hr, hrv, rng.randint(3, 7), (5, 20), (10, 20), late_share=0.7)
        hrv = [v * 0.85 for v in hrv]
        truth["restless"] = 1
    elif situation == "sleep_apnea":
        m = rng.randint(5, 12)
        while m < n - 2:
            depth = rng.uniform(4, 9)
            spo2[m] -= depth
            spo2[m + 1] -= depth / 2
            hr[m] += 3
            truth["events"] += 1
            m += rng.randint(2, 7)
    elif situation in ("oxygen_falling", "heart_rate_climbing", "fever_starting"):
        onset = rng.randint(30, 180) if situation == "fever_starting" else rng.randint(60, 220)
        truth["onset"] = onset
        for m in range(onset, n):
            t = m - onset
            if situation == "oxygen_falling":
                drop = min(t * rng.uniform(0.05, 0.10), rp.spo2 - (lim["spo2"] - rng.uniform(2, 4)))
                spo2[m] = rp.spo2 - drop
                hr[m] += drop                                                    # low oxygen raises heart rate
            elif situation == "heart_rate_climbing":
                hr[m] += min(t * rng.uniform(0.4, 0.8), rng.uniform(108, 125) - rp.hr)
                hrv[m] *= 0.75
            else:
                rise = min(t * rng.uniform(0.008, 0.015), rng.uniform(1.2, 2.0))
                temp[m] += rise
                hr[m] += 10 * rise                                               # ~10 bpm per degree
        metric = {"oxygen_falling": "spo2", "heart_rate_climbing": "heart_rate"}.get(situation, "skin_temperature")
        series = {"spo2": spo2, "heart_rate": hr, "skin_temperature": temp}[metric]
        crossed = [m for m in range(onset, n) if (series[m] < lim[metric] if metric == "spo2" else series[m] > lim[metric])]
        truth.update(metric=metric, crossing=crossed[0] if crossed else None)
    return {"heart_rate": hr, "spo2": spo2, "hrv_rmssd": hrv, "skin_temperature": temp}, truth


def measure(rng: random.Random, rp: RingProfile, true: dict, traps: bool = False) -> list[tuple[str, float, str, int]]:
    """Ring readings: (metric, value, unit, minute). traps = loose-ring SpO2 readings + a short bathroom HR spike."""
    artefacts = set(rng.sample(range(NIGHT_MINUTES), rng.randint(3, 6))) if traps else set()
    hr = list(true["heart_rate"])
    if traps:
        m = rng.randint(30, NIGHT_MINUTES - 5)
        for k in range(m, m + 3):
            hr[k] = rng.uniform(98, 108)
    out = []
    for m in range(NIGHT_MINUTES):
        out.append(("heart_rate", round(min(220, max(35, rng.gauss(hr[m], 8 if rp.af else 2)))), "bpm", m))
        s = rng.uniform(70, 85) if m in artefacts else rng.gauss(true["spo2"][m], 0.4)
        out.append(("spo2", round(min(100.0, max(50.0, s)), 1), "percent", m))
        if m % 5 == 0:
            r = rng.gauss(true["hrv_rmssd"][m] * (2 if rp.af else 1), 25 if rp.af else 3)
            out.append(("hrv_rmssd", round(min(300.0, max(5.0, r)), 1), "ms", m))
            out.append(("skin_temperature", round(rng.gauss(true["skin_temperature"][m], 0.05), 2), "celsius", m))
    return out


def night(rng: random.Random, situation: str, conditions: tuple = ()) -> tuple[list, dict]:
    """One person, one situation: (samples, truth incl. the previous-night medians and the limits)."""
    conditions = tuple(conditions)
    if not conditions:
        conditions = tuple(c for c, p in (("copd", 0.3 if situation == "oxygen_falling" else 0.08),
                                          ("atrial_fibrillation", 0.06)) if rng.random() < p)
        if situation == "sleep_apnea":
            conditions += ("obstructive_sleep_apnea",)
    return night_for(rng, ring_profile(rng, conditions), conditions, situation)


def night_for(rng: random.Random, rp: RingProfile, conditions: tuple, situation: str) -> tuple[list, dict]:
    """The same for a known person (e.g. a demo patient's own ring profile, used by stream.py)."""
    rp = replace(rp, hr=min(max(rp.hr, 42.0), 100.0))   # individual resting HR 40-109 bpm (Quer et al. 2020)
    prev_true, _ = true_night(rng, rp, "normal_night", {"spo2": 94.0, "heart_rate": 100.0, "skin_temperature": 99.0})
    prev_samples = measure(rng, rp, prev_true)
    prev = {k: round(statistics.median(v for m, v, _, _ in prev_samples if m == k), 2)
            for k in ("heart_rate", "spo2", "hrv_rmssd", "skin_temperature")}
    lim = limits(conditions, prev)
    true, truth = true_night(rng, rp, situation, lim)
    samples = measure(rng, rp, true, traps=situation == "false_alarm_traps")
    truth.update(conditions=";".join(conditions), **{f"prev_{k}": v for k, v in prev.items()},
                 **{f"limit_{k}": v for k, v in lim.items()})
    return samples, truth


def write(out: Path, nights: int, seed: int) -> None:
    rng = random.Random(f"live-sim:{seed}")
    out.mkdir(parents=True, exist_ok=True)
    names, weights = list(SITUATIONS), list(SITUATIONS.values())
    with open(out / "samples.csv", "w", newline="") as fs, open(out / "nights.csv", "w", newline="") as fn:
        ws, wn = csv.writer(fs), None
        ws.writerow(["night_id", "minute", "metric", "value", "unit", "is_synthetic"])
        for i in range(nights):
            samples, truth = night(rng, rng.choices(names, weights)[0])
            nid = f"L{seed}-{i:04d}"
            for metric, value, unit, minute in samples:
                ws.writerow([nid, minute, metric, value, unit, "true"])
            row = {"night_id": nid, **truth, "is_synthetic": "true"}
            if wn is None:
                wn = csv.DictWriter(fn, fieldnames=list(row))
                wn.writeheader()
            wn.writerow(row)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--nights", type=int, default=700)
    ap.add_argument("--seed", type=int, required=True)
    a = ap.parse_args()
    write(a.out, a.nights, a.seed)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
