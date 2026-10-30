"""Synthetic PULSE data. Everything produced here is FICTIONAL and labelled as simulated.

    python -m pulse_data.simulate seed     # -> supabase/seed.sql (demo accounts + 30 days of history)
    python -m pulse_data.simulate csv      # -> data/synthetic/*.csv (longitudinal set for the ML phase)
    python -m pulse_data.simulate sample   # -> samples/readings_sample.csv (CSV-import demo)

The "effects" below (missed dose, sodium, activity, sleep) are invented to exercise the
pipeline. They are not clinical knowledge; nothing learned from this data applies to real patients.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

GENERATOR_VERSION = "pulse-sim-v1"
TZ = "Africa/Algiers"
ROOT = Path(__file__).resolve().parent.parent
_NS = uuid.UUID("5b3f8a52-6a2e-4c43-9a59-0c8f1f5d7e10")


def demo_id(name: str) -> str:
    return str(uuid.uuid5(_NS, name))


# ---------------------------------------------------------------- generator core

@dataclass(frozen=True)
class Profile:
    baseline_sys: float
    baseline_dia: float
    trend_per_day: float   # mmHg/day drift
    skip_prob: float       # chance a measurement session is missed
    on_medication: bool
    miss_dose_prob: float


@dataclass(frozen=True)
class Day:
    day: int
    missed_dose: bool | None  # None = no medication
    activity_min: int
    sodium_mg: int            # simulated estimate
    sleep_hours: float
    sleep_quality: int        # 1-5


@dataclass(frozen=True)
class SimReading:
    day: int
    minute: int   # minutes after local midnight
    session: str  # morning | evening
    systolic: int
    diastolic: int
    pulse: int


@dataclass(frozen=True)
class Noise:
    """Day-to-day BP variation. V1 = first generator (demo seed, unchanged). V2 = calibrated on a REAL home-BP
    series (Mendeley pjcv33hpp7: systolic SD ~11.7 and change ~10 mmHg between measurements 3 days apart; V1
    gave 6.7 and 6.5): a slower, larger latent drift plus day-level noise."""
    latent_phi: float = 0.7
    latent_sd: float = 3.0
    day_sd: float = 0.0


NOISE_V1 = Noise()
# Chosen from a small grid: every-3-days systolic SD / change / lag-1 r = 11.8 / 10.0 / 0.41 vs real 11.7 / 10.0 / 0.40
# (diastolic 6.8 / 5.8 / 0.41 vs real 6.4 / 5.1 / 0.37). One real patient: realistic in size, not a population fit.
NOISE_V2 = Noise(latent_phi=0.95, latent_sd=3.6, day_sd=6.0)
ML_GENERATOR_VERSION = "pulse-sim-v2"   # the ML cohort (data/synthetic); the demo seed stays pulse-sim-v1


def simulate_patient(rng: random.Random, p: Profile, days: int, entry_error_prob: float = 0.0,
                     effect_out: list[float] | None = None, noise: Noise = NOISE_V1) -> tuple[list[Day], list[SimReading]]:
    """effect_out, if given, receives each day's latent BP effect (mmHg). It makes no extra random draws,
    so BP output is identical with or without it (guarded by tests/test_simulate_stability.py).
    NOISE_V1 makes no day-noise draw, so the demo seed is unchanged."""
    context: list[Day] = []
    readings: list[SimReading] = []
    latent = 0.0
    prev_missed = False
    for d in range(days):
        missed = (rng.random() < p.miss_dose_prob) if p.on_medication else None
        activity = rng.choice([0, 0, 15, 20, 30, 45, 60])
        sodium = int(min(7000, max(800, rng.gauss(3200, 900))))
        sleep_h = round(min(10.0, max(3.5, rng.gauss(7.0, 1.1))), 1)
        quality = int(min(5, max(1, round((sleep_h - 3.5) / 1.3 + rng.gauss(0, 0.7)))))
        context.append(Day(d, missed, activity, sodium, sleep_h, quality))

        latent = noise.latent_phi * latent + rng.gauss(0, noise.latent_sd)
        day_noise = rng.gauss(0, noise.day_sd) if noise.day_sd else 0.0
        effect = (latent + day_noise + p.trend_per_day * d + (6 if prev_missed else 0)
                  + 1.2 * (sodium - 3200) / 1000 - (2 if activity >= 30 else 0) + (2 if sleep_h < 6 else 0))
        if effect_out is not None:
            effect_out.append(effect)
        for session, base_minute, surge in (("morning", 7 * 60, 4), ("evening", 20 * 60, 0)):
            if rng.random() < p.skip_prob:
                continue
            minute = base_minute + rng.randint(-40, 60)
            for k in range(1 if rng.random() < 0.6 else 2):
                sys_ = round(p.baseline_sys + effect + surge + rng.gauss(0, 5))
                dia = min(round(p.baseline_dia + 0.55 * effect + surge / 2 + rng.gauss(0, 3.5)), sys_ - 15)
                pulse = round(rng.gauss(72, 6) + (3 if session == "morning" else 0))
                if rng.random() < entry_error_prob:
                    sys_, dia = dia, sys_  # simulated data-entry error (swapped values)
                readings.append(SimReading(d, minute + 2 * k, session, sys_, dia, pulse))
        prev_missed = bool(missed)
    return context, readings


# ---------------------------------------------------------------- ring (smart ring / bracelet) samples
# Always drawn from a SEPARATE generator (key + ":ring"), so ring data never changes BP data (review H3).
# Same metrics / units as public.wearable_samples (review H2); no sleep metric (sleep is in lifestyle_logs).

RING_EPISODES = ("hr_rise", "spo2_dip", "hrv_drop")  # injected, labelled anomalies (simulated)

# Demo ring values, chosen from published wearable / clinical figures (docs/data/DATA_SOURCES.md). No real
# ring was used: every value below is SIMULATED.
#   resting HR: mean ~65 bpm across 92,457 wearable users, typical within-person change ~3 bpm (Quer 2020)
#   night SpO2: healthy sleepers dip; mean lowest saturation 90.4 % (Gries & Brooks, Chest 1996)
#   COPD: SpO2 target 88-92 % if at risk of hypercapnic failure (BTS 2017) -> lower personal SpO2
#   obstructive sleep apnea: repeated desaturations of >= 4 % at night (AASM scoring)
#   type 2 diabetes: RMSSD ~0.92 SD lower than controls (PLoS ONE 2018 meta-analysis)
#   atrial fibrillation: irregular pulse on wrist PPG (Apple Heart Study 2019): noisy HR, meaningless RMSSD
RING_HR = (65.0, 7.0)          # between-person mean / SD (SD is an assumption consistent with Quer's 40-109 range)
RING_HRV = (34.0, 9.0)         # between-person RMSSD mean / SD, ms (assumption)
RING_SPO2 = (96.5, 0.8)        # healthy personal night SpO2 (assumption); COPD shifts it down
CHRONIC_RING_CODES = ("copd", "obstructive_sleep_apnea", "atrial_fibrillation", "diabetes")


@dataclass(frozen=True)
class RingProfile:
    hr: float     # personal night resting heart rate, bpm
    hrv: float    # personal night RMSSD, ms
    spo2: float   # personal night SpO2, %
    temp: float   # personal night skin temperature, °C
    osa: bool = False
    af: bool = False


def ring_profile(rng: random.Random, conditions=()) -> RingProfile:
    """Personal ring normal; chronic conditions shift it (no extra random draws, so it stays reproducible)."""
    hr, hrv = rng.gauss(*RING_HR), rng.gauss(*RING_HRV)
    spo2, temp = min(98.5, rng.gauss(*RING_SPO2)), rng.gauss(34.0, 0.4)
    if "diabetes" in conditions:
        hrv -= 0.92 * RING_HRV[1]
    if "copd" in conditions:
        spo2 -= 4.0
    return RingProfile(hr, max(12.0, hrv), spo2, temp, "obstructive_sleep_apnea" in conditions,
                       "atrial_fibrillation" in conditions)


def ring_day_samples(rng: random.Random, rp: RingProfile, effect: float,
                     episode: str | None = None) -> list[tuple[str, float, str, int]]:
    """One local day: (metric, value, unit, minute after local midnight).
    Heart rate every 10 min at night (00:00-06:00) and hourly by day; 6 SpO2 samples per night (healthy nights
    may dip once by 3-5 %, sleep apnea nights 2-4 times by 4-9 %); nightly HRV and skin temperature.
    INVENTED coupling, for pipeline testing only: night heart rate +0.25 bpm and HRV -0.3 ms per mmHg of the
    latent BP effect."""
    night_hr = rp.hr + 0.25 * effect + (15 if episode == "hr_rise" else 0) + (3 if rp.osa else 0)
    hrv = (rp.hrv - 0.3 * effect) * (0.6 if episode == "hrv_drop" else 1.0)
    spo2 = rp.spo2 - (5 if episode == "spo2_dip" else 0)
    hr_sd = 10 if rp.af else 3
    out = [("heart_rate", round(rng.gauss(night_hr, hr_sd)), "bpm", m) for m in range(0, 360, 10)]
    out += [("heart_rate", round(rng.gauss(rp.hr + 12 + 0.25 * effect, 7 + hr_sd)), "bpm", m) for m in range(360, 1440, 60)]
    sat = [rng.gauss(spo2, 0.6) for _ in range(6)]
    dips = rng.randint(2, 4) if rp.osa else (1 if rng.random() < 0.5 else 0)
    for i in rng.sample(range(6), dips):
        sat[i] -= rng.uniform(4, 9) if rp.osa else rng.uniform(3, 5)
    out += [("spo2", round(min(100.0, max(70.0, v)), 1), "percent", m) for v, m in zip(sat, (60, 120, 180, 240, 300, 330))]
    rmssd = rng.gauss(hrv * 2, 25) if rp.af else rng.gauss(hrv, 4)
    out += [("hrv_rmssd", round(min(200.0, max(5.0, rmssd)), 1), "ms", 180),
            ("skin_temperature", round(rng.gauss(rp.temp, 0.25), 2), "celsius", 180)]
    return out


# ---------------------------------------------------------------- demo seed (supabase/seed.sql)

@dataclass(frozen=True)
class DemoUser:
    key: str
    email: str
    name: str
    role: str
    profile: Profile | None = None
    assigned: bool = False

    @property
    def id(self) -> str:
        return demo_id(self.email)


DOCTOR = DemoUser("doctor", "dr.leila.demo@pulse.test", "Dr. Leila H. (demo)", "doctor")
ADMIN = DemoUser("admin", "admin.demo@pulse.test", "PULSE Admin (demo)", "admin")
PATIENTS = (
    DemoUser("controlled", "amina.demo@pulse.test", "Amina B. (demo)", "patient",
             Profile(124, 79, 0.0, 0.10, True, 0.05), assigned=True),
    DemoUser("rising", "karim.demo@pulse.test", "Karim M. (demo)", "patient",
             Profile(134, 85, 0.6, 0.30, True, 0.25), assigned=True),
    DemoUser("severe_event", "nadia.demo@pulse.test", "Nadia S. (demo)", "patient",
             Profile(146, 92, 0.0, 0.15, True, 0.10), assigned=True),
    DemoUser("sparse_unassigned", "yacine.demo@pulse.test", "Yacine T. (demo)", "patient",
             Profile(132, 84, 0.0, 0.75, False, 0.0), assigned=False),
)
# Published figures used to draw the cohort's risk factors. Patients stay fictional; only the shares are real.
# Algerian STEPS 2016-2017, Moussouni et al., BMC Public Health 2022 (PMC9386961), adults 18-69:
STEPS_DZ = {
    "female_share_of_hypertensives": 34.2 / (34.2 + 28.3),     # hypertension 34.2 % women vs 28.3 % men
    "age_bands": {(30, 44): 39.3, (45, 59): 27.7, (60, 69): 11.6},  # sample shares (18-29 left out: low risk)
    "smoking": {"current": 11.1, "former": 11.9, "never": 76.9},
    "diabetes": 0.175, "high_cholesterol": 0.296,  # overall shares; the paper gives no split by sex
    "bmi_bands": {(17.0, 18.4): 3.3, (18.5, 24.9): 36.6, (25.0, 29.9): 35.0, (30.0, 38.0): 24.9},
    "abdominal_obesity": 0.678, "waist_cutoff_cm": {"male": 94, "female": 80},
}
# Not published for Algeria (labelled assumptions in docs): height, salt-habit answers, language, and how
# abdominal obesity depends on BMI. P(abdominal obesity | BMI band) below keeps the overall share at ~67.8 %.
HEIGHT_CM = {"male": (172, 7), "female": (160, 6)}
ABDOMINAL_BY_BMI_BAND = {(17.0, 18.4): 0.0, (18.5, 24.9): 0.36, (25.0, 29.9): 0.85, (30.0, 38.0): 1.0}  # 0.678 overall
NAMES = {"female": ("Fatima", "Khadija", "Houria", "Souad", "Amel", "Nora", "Samira", "Lamia"),
         "male": ("Samir", "Rachid", "Mourad", "Djamel", "Hocine", "Omar", "Farid", "Nabil")}


def _cohort() -> list[tuple[str, str]]:
    """8 (name, sex) pairs; sex drawn from the published share, the name then matches it."""
    rng, used = random.Random(f"{GENERATOR_VERSION}:cohort"), {"female": 0, "male": 0}
    out = []
    for _ in range(8):
        sex = "female" if rng.random() < STEPS_DZ["female_share_of_hypertensives"] else "male"
        out.append((NAMES[sex][used[sex]], sex))
        used[sex] += 1
    return out


COHORT = _cohort()
COHORT_SEX = {f"cohort_{i}": sex for i, (_, sex) in enumerate(COHORT, 1)}


def _cohort_profile(name: str) -> Profile:
    """Monitored, treated hypertensive; BP levels are invented (no published per-patient series)."""
    r = random.Random(f"{GENERATOR_VERSION}:{name}")
    sys_ = r.uniform(128, 162)
    return Profile(sys_, 0.62 * sys_ + r.gauss(0, 4), r.gauss(0, 0.15), r.uniform(0.1, 0.35), True, r.uniform(0, 0.25))


PATIENTS += tuple(DemoUser(f"cohort_{i}", f"{name.lower()}.demo@pulse.test", f"{name} (demo)", "patient",
                           _cohort_profile(name), assigned=True) for i, (name, _) in enumerate(COHORT, 1))
USERS = (DOCTOR, ADMIN) + PATIENTS
SEED_DAYS = 30
MEDS = {"controlled": ("Amlodipine", "5 mg"), "rising": ("Perindopril", "4 mg"), "severe_event": ("Amlodipine", "10 mg")}
COHORT_MEDS = (("Amlodipine", "5 mg"), ("Perindopril", "4 mg"), ("Losartan", "50 mg"), ("Indapamide", "1.5 mg"))
WEARABLE_KEYS = tuple(u.key for u in PATIENTS)  # every demo patient has a simulated ring (no real device)
# Chronic conditions (M8). Demo stories are hand-picked; other cohort patients are drawn from published rates.
DEMO_CHRONIC_BY_NAME = {"Fatima": ["copd"], "Houria": ["atrial_fibrillation"]}
CHRONIC_RATES = {
    "copd": {"male": 0.052, "female": 0.018},   # BREATHE (MENA, adults >= 40): 5.2 % men, 1.8 % women
    "obstructive_sleep_apnea": 0.30,            # assumption: OSA is common with hypertension (83.5 % in resistant HT)
    "atrial_fibrillation": {"65+": 0.03, "<65": 0.005},  # assumption scaled on Apple Heart Study notification rates
}
# Scenario patients get hand-picked factors that fit their story; the cohort is drawn from STEPS_DZ.
SCENARIO_FACTORS = {
    "controlled": dict(sex="female", age=58, smoking="never", codes=["hypertension"], bmi=26.5, waist=86,
                       bread=3, salt="rarely", processed="rarely", lang="ar"),
    "rising": dict(sex="male", age=65, smoking="current",
                   codes=["hypertension", "diabetes", "dyslipidemia", "obstructive_sleep_apnea"],
                   bmi=31.2, waist=104, bread=6, salt="often", processed="sometimes", lang="fr"),
    "severe_event": dict(sex="female", age=69, smoking="never", codes=["hypertension", "chronic_kidney_disease"],
                         bmi=33.0, waist=99, bread=4, salt="sometimes", processed="often", lang="ar"),
    "sparse_unassigned": dict(sex="male", age=47, smoking="former", codes=["hypertension"], bmi=24.0, waist=90,
                              bread=5, salt="sometimes", processed="sometimes", lang="fr"),
}


def _pick(rng: random.Random, weights: dict):
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def risk_factors(u: DemoUser) -> dict:
    """Patient factors + body measurements. Deterministic per demo user."""
    rng = random.Random(f"{GENERATOR_VERSION}:{u.key}:factors")
    if u.key in SCENARIO_FACTORS:
        f = dict(SCENARIO_FACTORS[u.key])
    else:
        sex = COHORT_SEX[u.key]
        lo, hi = _pick(rng, STEPS_DZ["age_bands"])
        band = _pick(rng, STEPS_DZ["bmi_bands"])
        bmi_lo, bmi_hi = band
        bmi = round(rng.uniform(bmi_lo, bmi_hi), 1)
        cut = STEPS_DZ["waist_cutoff_cm"][sex]
        above = cut + rng.randint(1, max(2, round(bmi - 18) + 2))  # waist excess grows with BMI
        f = dict(sex=sex, age=rng.randint(lo, hi), smoking=_pick(rng, STEPS_DZ["smoking"]),
                 codes=["hypertension"] + [c for c, p in (("diabetes", STEPS_DZ["diabetes"]),
                                                          ("dyslipidemia", STEPS_DZ["high_cholesterol"]))
                                           if rng.random() < p],
                 bmi=bmi, waist=above if rng.random() < ABDOMINAL_BY_BMI_BAND[band] else cut - rng.randint(0, 12),
                 bread=rng.randint(2, 7), salt=rng.choice(["never", "rarely", "sometimes", "often", "always"]),
                 processed=rng.choice(["never", "rarely", "sometimes", "often"]), lang=rng.choice(["fr", "ar"]))
    mean, sd = HEIGHT_CM[f["sex"]]
    f["height"] = round(min(195.0, max(145.0, rng.gauss(mean, sd))), 1)
    f["weight"] = round(f["bmi"] * (f["height"] / 100) ** 2, 1)
    if u.key not in SCENARIO_FACTORS:
        f["codes"] = f["codes"] + chronic_codes(u, f["sex"], f["age"])
    return f


def chronic_codes(u: DemoUser, sex: str, age: int) -> list[str]:
    """Separate generator, so adding chronic conditions changes no other factor."""
    name = u.name.split(" ")[0]
    if name in DEMO_CHRONIC_BY_NAME:
        return list(DEMO_CHRONIC_BY_NAME[name])
    rng = random.Random(f"{GENERATOR_VERSION}:{u.key}:chronic")
    rates = {"copd": CHRONIC_RATES["copd"][sex], "obstructive_sleep_apnea": CHRONIC_RATES["obstructive_sleep_apnea"],
             "atrial_fibrillation": CHRONIC_RATES["atrial_fibrillation"]["65+" if age >= 65 else "<65"]}
    return [c for c, p in rates.items() if rng.random() < p]


def sql(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, (list, tuple)):
        return "array[" + ", ".join(sql(x) for x in v) + "]::text[]" if v else "'{}'::text[]"
    return "'" + str(v).replace("'", "''") + "'"


def local_ts(days_ago: int, minute: int, tz: str = TZ) -> str:
    """Timestamp `days_ago` days before today at local `minute`, relative to now() so the demo stays fresh."""
    return (f"((date_trunc('day', now() at time zone '{tz}') - interval '{days_ago} days' "
            f"+ interval '{minute} minutes') at time zone '{tz}')")


def insert(table: str, cols: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return ""
    values = ",\n".join("  (" + ", ".join(r) + ")" for r in rows)
    return f"insert into public.{table} ({', '.join(cols)}) values\n{values};\n\n"


def patient_history(u: DemoUser, effect_out: list[float] | None = None) -> tuple[list[Day], list[SimReading]]:
    rng = random.Random(f"{GENERATOR_VERSION}:{u.key}")
    context, readings = simulate_patient(rng, u.profile, SEED_DAYS, effect_out=effect_out)
    if u.key == "severe_event":  # severe reading 2 days ago, repeated 3 minutes later
        d = SEED_DAYS - 2
        readings += [SimReading(d, 455, "morning", 186, 118, 96), SimReading(d, 458, "morning", 183, 116, 94)]
    if u.key == "sparse_unassigned":  # a double entry and a swapped (invalid) entry
        first = readings[0]
        readings += [SimReading(first.day, first.minute + 1, first.session, first.systolic, first.diastolic, first.pulse),
                     SimReading(first.day + 1, 480, "morning", 78, 124, 70)]
    readings.sort(key=lambda r: (r.day, r.minute))
    return context, readings


WEARABLE_COLS = ["patient_id", "device_id", "metric", "value", "unit", "measured_at", "source", "external_id"]


def ring_device_rows() -> list[list[str]]:
    by_key = {u.key: u.id for u in PATIENTS}
    return [[sql(demo_id(k + ":ring")), sql(by_key[k]), "'simulator'", "'simulated'", "'PULSE'",
             sql(GENERATOR_VERSION), "'Simulated ring (not a real device)'"] for k in WEARABLE_KEYS]


def cloud_ring_demo_parts(rows_per_part: int = 5000) -> list[str]:
    """The same refresh in several smaller DO blocks (API request size). Part 1 deletes the old simulated demo-ring
    samples, sets conditions and devices; every part inserts with ON CONFLICT DO NOTHING, so running all parts
    again, in order, is always safe."""
    rings = ", ".join(sql(demo_id(k + ":ring")) for k in WEARABLE_KEYS)
    rows = wearable_rows()
    head = [f"delete from public.wearable_samples where source = 'simulated' and device_id in ({rings});\n",
            *(f"update public.patient_profiles set condition_codes = {sql(risk_factors(u)['codes'])} "
              f"where user_id = {sql(u.id)};\n" for u in PATIENTS),
            insert("devices", ["id", "patient_id", "device_type", "bp_capability", "manufacturer", "model", "label"],
                   ring_device_rows()).replace(";\n\n", "\non conflict (id) do nothing;\n\n")]
    parts = []
    for i in range(0, len(rows), rows_per_part):
        body = insert("wearable_samples", WEARABLE_COLS, rows[i:i + rows_per_part]).replace(
            ";\n\n", "\non conflict (device_id, external_id) where external_id is not null do nothing;\n\n")
        parts.append(f"-- part {len(parts) + 1}: FICTIONAL demo ring data (simulated)\ndo $ring_demo$ begin\n"
                     + ("".join(head) if not parts else "") + body + "end $ring_demo$;\n")
    return parts


def cloud_ring_demo_sql() -> str:
    """Refresh the ring demo in a database that ALREADY holds the demo seed (the cloud project), in one
    transaction: chronic conditions of the demo patients (needs M8), a simulated ring for every demo patient,
    and 28 fresh days of samples. Deletes ONLY simulated samples of the demo rings; nothing else."""
    rings = ", ".join(sql(demo_id(k + ":ring")) for k in WEARABLE_KEYS)
    # One DO block = one command (what `supabase db query` accepts) and one atomic transaction.
    out = ["-- GENERATED by `python -m pulse_data.simulate ring-demo-sql`. FICTIONAL demo ring data (simulated).\n",
           "do $ring_demo$ begin\n",
           f"delete from public.wearable_samples where source = 'simulated' and device_id in ({rings});\n"]
    out += [f"update public.patient_profiles set condition_codes = {sql(risk_factors(u)['codes'])} "
            f"where user_id = {sql(u.id)};\n" for u in PATIENTS]
    out.append(insert("devices", ["id", "patient_id", "device_type", "bp_capability", "manufacturer", "model", "label"],
                      ring_device_rows()).replace(";\n\n", "\non conflict (id) do nothing;\n\n"))
    out.append(insert("wearable_samples", WEARABLE_COLS, wearable_rows()))
    out.append("end $ring_demo$;\n")
    return "".join(out)


SEED_RING_DAYS = 28                        # enough nights for a personal baseline (review H1)
SEED_RING_EPISODES = {"rising": ("hr_rise", (3, 2))}  # Karim: night heart rate up 3 and 2 days ago (simulated)


def wearable_rows(days: int = SEED_RING_DAYS) -> list[list[str]]:
    """Simulated ring samples for the demo ring patients, coupled to each patient's simulated BP history."""
    rows = []
    for k in WEARABLE_KEYS:
        u = next(p for p in PATIENTS if p.key == k)
        effects: list[float] = []
        patient_history(u, effects)
        rng = random.Random(f"{GENERATOR_VERSION}:{k}:ring")
        rp = ring_profile(rng, risk_factors(u)["codes"])
        episode, episode_days = SEED_RING_EPISODES.get(k, (None, ()))
        device, n = demo_id(k + ":ring"), 0
        for ago in range(days, 0, -1):
            samples = ring_day_samples(rng, rp, effects[SEED_DAYS - ago], episode if ago in episode_days else None)
            for metric, value, unit, minute in samples:
                n += 1
                rows.append([sql(u.id), sql(device), sql(metric), sql(value), sql(unit), local_ts(ago, minute),
                             "'simulated'", sql(f"sim-ring-{k}-{n:04d}")])
    return rows


def build_seed_sql(password: str) -> str:
    ids_by_key = {u.key: u.id for u in PATIENTS}
    out = [
        "-- GENERATED by `python -m pulse_data.simulate seed`; do not edit by hand, do not commit.\n"
        "-- FICTIONAL DEMO DATA. Every row is labelled simulated.\n"
        f"-- Demo accounts use the password from PULSE_DEMO_PASSWORD. Generator: {GENERATOR_VERSION}.\n\n"
    ]
    out.append(
        "insert into auth.users (instance_id, id, aud, role, email, encrypted_password, email_confirmed_at,\n"
        "  raw_app_meta_data, raw_user_meta_data, created_at, updated_at,\n"
        "  confirmation_token, recovery_token, email_change_token_new, email_change) values\n"
        + ",\n".join(
            f"  ('00000000-0000-0000-0000-000000000000', {sql(u.id)}, 'authenticated', 'authenticated', {sql(u.email)},\n"
            f"   extensions.crypt({sql(password)}, extensions.gen_salt('bf')), now(),\n"
            f"   '{{\"provider\":\"email\",\"providers\":[\"email\"]}}', {sql(json.dumps({'display_name': u.name}))},\n"
            f"   now() - interval '{SEED_DAYS + 5} days', now(), '', '', '', '')"
            for u in USERS)
        + ";\n\n")
    out.append(
        "insert into auth.identities (provider_id, user_id, identity_data, provider, last_sign_in_at, created_at, updated_at) values\n"
        + ",\n".join(
            f"  ({sql(u.id)}, {sql(u.id)}, {sql(json.dumps({'sub': u.id, 'email': u.email, 'email_verified': True}))}, "
            f"'email', now(), now(), now())" for u in USERS)
        + ";\n\n")
    out.append(f"update public.profiles set role = 'doctor' where id = {sql(DOCTOR.id)};\n")
    out.append(f"update public.profiles set role = 'admin' where id = {sql(ADMIN.id)};\n\n")

    factors = {u.key: risk_factors(u) for u in PATIENTS}
    year = date.today().year
    out.append(insert("patient_profiles",
                      ["user_id", "relevant_conditions", "condition_codes", "sex", "birth_year", "smoking_status",
                       "bread_portions_per_day", "adds_salt_at_table", "salty_processed_food", "allergies",
                       "regular_doctor_id", "regular_clinic", "consent_location", "data_consent_at"],
                      [[sql(u.id), sql(f["codes"]), sql(f["codes"]), sql(f["sex"]), sql(year - f["age"]),
                        sql(f["smoking"]), sql(f["bread"]), sql(f["salt"]), sql(f["processed"]),
                        sql("none reported" if u.assigned else None), sql(DOCTOR.id if u.assigned else None),
                        sql("Clinique Demo (fictional)" if u.assigned else None), sql(u.key == "severe_event"),
                        f"now() - interval '{SEED_DAYS} days'"]
                       for u in PATIENTS for f in [factors[u.key]]]))
    out.extend(f"update public.profiles set preferred_language = {sql(factors[u.key]['lang'])} where id = {sql(u.id)};\n"
               for u in PATIENTS)
    out.append("\n")
    out.append(insert("body_measurements", ["patient_id", "measured_at", "weight_kg", "height_cm", "waist_cm", "source"],
                      [row for u in PATIENTS for f in [factors[u.key]] for row in (
                          [sql(u.id), local_ts(SEED_DAYS - 2, 9 * 60), sql(f["weight"]), sql(f["height"]),
                           sql(float(f["waist"])), "'simulated'"],
                          [sql(u.id), local_ts(3, 7 * 60 + 30), sql(round(f["weight"] - 0.4, 1)), "null", "null",
                           "'simulated'"])]))
    out.append(insert("doctor_patient_assignments", ["doctor_id", "patient_id"],
                      [[sql(DOCTOR.id), sql(u.id)] for u in PATIENTS if u.assigned]))
    out.append(insert("devices", ["id", "patient_id", "device_type", "bp_capability", "manufacturer", "model", "label"],
                      [[sql(demo_id(u.key + ":device")), sql(u.id), "'simulator'", "'simulated'", "'PULSE'",
                        sql(GENERATOR_VERSION), "'Simulated cuff (not a real device)'"] for u in PATIENTS]
                      + ring_device_rows()))
    out.append(insert("wearable_samples", WEARABLE_COLS, wearable_rows()))

    measurements, lifestyle, adherence, meds, plans, contacts = [], [], [], [], [], []
    for u in PATIENTS:
        context, readings = patient_history(u)
        device = demo_id(u.key + ":device")
        for n, r in enumerate(readings, 1):
            measurements.append([sql(u.id), sql(device), "'simulated'", "'simulated'", "'unknown'",
                                 sql(r.systolic), sql(r.diastolic), sql(r.pulse),
                                 local_ts(SEED_DAYS - r.day, r.minute), sql(TZ), "'sitting'", "'left'",
                                 sql(f"sim-{u.key}-{n:04d}")])
        if not u.assigned:
            continue
        med_id = demo_id(u.key + ":med")
        name, dose = MEDS.get(u.key) or COHORT_MEDS[len(meds) % len(COHORT_MEDS)]
        meds.append([sql(med_id), sql(u.id), sql(name), sql(dose), "'once daily, morning'", "'clinician'",
                     sql(DOCTOR.id), f"current_date - {SEED_DAYS + 60}"])
        plans.append([sql(u.id), sql(DOCTOR.id), f"current_date - {SEED_DAYS}", f"current_date + 30", "135", "85", "2",
                      "'Two seated readings each morning and evening, one minute apart.'",
                      "'General guidance only: regular walking; limit very salty meals.'",
                      "'Review home readings at the next visit.'",
                      "'Continue home monitoring as agreed at the last visit (fictional demo plan).'"])
        contacts.append([sql(u.id), sql(f"Contact of {u.name}"), "'family'", sql(f"+213 555 00 00 0{len(contacts) + 1}")])
        for c in context[-14:]:
            ago = SEED_DAYS - c.day
            if c.activity_min:
                lifestyle.append([sql(u.id), "'activity'", local_ts(ago, 18 * 60), local_ts(ago, 18 * 60 + c.activity_min),
                                  "'simulated'", "'walking'", sql("moderate" if c.activity_min >= 30 else "light"),
                                  "null", "null", "null", "null"])
            lifestyle.append([sql(u.id), "'sleep'", local_ts(ago + 1, 23 * 60), local_ts(ago + 1, 23 * 60 + round(c.sleep_hours * 60)),
                              "'simulated'", "null", "null", "null", "null", "null", sql(c.sleep_quality)])
            if c.day % 3 == 0:
                lifestyle.append([sql(u.id), "'meal'", local_ts(ago, 19 * 60 + 30), "null", "'simulated'", "null", "null",
                                  "'dinner'", sql(c.sodium_mg), "'estimated'", "null"])
            if c.missed_dose is not None:
                adherence.append([sql(u.id), sql(med_id), sql("missed" if c.missed_dose else "taken"),
                                  local_ts(ago, 8 * 60), "null" if c.missed_dose else local_ts(ago, 8 * 60 + 10),
                                  "'simulated'", local_ts(ago, 21 * 60)])
    # Two make-up fasting days for Amina: fast from dawn to sunset (iftar), local time.
    lifestyle += [[sql(ids_by_key["controlled"]), "'fasting'", local_ts(ago, 5 * 60 + 40), local_ts(ago, 18 * 60 + 10),
                   "'simulated'", "null", "null", "null", "null", "null", "null"] for ago in (9, 16)]

    out.append(insert("measurements",
                      ["patient_id", "device_id", "source", "provenance", "method", "systolic", "diastolic", "pulse",
                       "measured_at", "measured_tz", "body_position", "arm", "external_id"], measurements))
    out.append(insert("medications", ["id", "patient_id", "name", "dose_text", "schedule_text", "source",
                                      "prescribed_by", "started_on"], meds))
    out.append(insert("medication_adherence_events", ["patient_id", "medication_id", "status", "scheduled_for",
                                                      "taken_at", "source", "reported_at"], adherence))
    out.append(insert("lifestyle_logs", ["patient_id", "category", "started_at", "ended_at", "source", "activity_type",
                                         "intensity", "meal_type", "sodium_mg", "sodium_basis", "sleep_quality"],
                      lifestyle))
    out.append(insert("care_plans", ["patient_id", "clinician_id", "effective_from", "review_date", "target_systolic",
                                     "target_diastolic", "monitoring_readings_per_day", "monitoring_instructions",
                                     "lifestyle_recommendations", "follow_up_instructions", "clinician_guidance"], plans))
    out.append(insert("trusted_contacts", ["patient_id", "name", "relationship", "phone"], contacts))

    ids = ids_by_key
    severe, rising, controlled = ids["severe_event"], ids["rising"], ids["controlled"]
    out.append(insert("symptom_reports", ["patient_id", "symptoms", "onset_at", "reported_at", "source", "notes"], [
        [sql(severe), sql(["chest_pain", "severe_headache"]), local_ts(2, 450), local_ts(2, 460), "'simulated'",
         "'Fictional demo report linked to the severe reading.'"],
        [sql(rising), sql(["dizziness"]), local_ts(10, 1200), local_ts(10, 1210), "'simulated'", "null"],
    ]))
    out.append(insert("journal_entries", ["patient_id", "category", "entry_text", "created_at"], [
        [sql(controlled), "'question'", "'Is it fine to measure right after my morning walk?'", local_ts(6, 600)],
        [sql(rising), "'food'", "'Several salty meals at a family event this week; readings felt higher.'", local_ts(4, 1260)],
        [sql(severe), "'symptoms'", "'Felt chest tightness and a strong headache during the high reading.'", local_ts(2, 540)],
    ]))
    out.append(insert("doctor_notes", ["doctor_id", "patient_id", "note", "advice", "follow_up_at", "created_at"], [
        [sql(DOCTOR.id), sql(controlled), "'Home readings stable around target (fictional note).'",
         "'Keep measuring twice daily.'", "now() + interval '30 days'", local_ts(7, 660)],
    ]))
    return "".join(out)


# ---------------------------------------------------------------- longitudinal synthetic dataset (ML phase)

ML_START = date(2026, 1, 1)


def _ml_cohort(patients: int, days: int, seed: int, noise: Noise = NOISE_V2):
    """The synthetic ML cohort, patient by patient: (key, on_medication, context, readings, daily BP effects).
    One shared generator for BP; day-to-day variation from `noise` (pulse-sim-v2: calibrated on real home BP)."""
    rng = random.Random(seed)
    for i in range(1, patients + 1):
        sys_ = rng.uniform(110, 165)
        on_med = rng.random() < 0.6
        p = Profile(sys_, 0.62 * sys_ + rng.gauss(0, 4), rng.gauss(0, 0.12), rng.uniform(0.05, 0.45),
                    on_med, rng.uniform(0, 0.3) if on_med else 0.0)
        effects: list[float] = []
        context, readings = simulate_patient(rng, p, days, entry_error_prob=0.003, effect_out=effects, noise=noise)
        yield f"S{i:04d}", on_med, context, readings, effects


def write_ml_csv(out_dir: Path, patients: int = 200, days: int = 90, seed: int = 7) -> None:
    tz = ZoneInfo(TZ)
    start = ML_START
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "readings.csv", "w", newline="") as fr, open(out_dir / "daily_context.csv", "w", newline="") as fc:
        rw, cw = csv.writer(fr), csv.writer(fc)
        rw.writerow(["patient_key", "measured_at", "local_date", "session", "systolic", "diastolic", "pulse",
                     "is_synthetic", "generator_version"])
        cw.writerow(["patient_key", "local_date", "on_medication", "missed_dose", "activity_minutes",
                     "sodium_mg_estimated", "sleep_hours", "sleep_quality", "is_synthetic"])
        for key, on_med, context, readings, _ in _ml_cohort(patients, days, seed):
            for r in readings:
                local = datetime.combine(start + timedelta(days=r.day), datetime.min.time(), tz) + timedelta(minutes=r.minute)
                rw.writerow([key, local.isoformat(), local.date().isoformat(), r.session, r.systolic, r.diastolic,
                             r.pulse, "true", ML_GENERATOR_VERSION])
            for c in context:
                cw.writerow([key, (start + timedelta(days=c.day)).isoformat(), on_med,
                             "" if c.missed_dose is None else c.missed_dose, c.activity_min, c.sodium_mg,
                             c.sleep_hours, c.sleep_quality, "true"])


def write_ring_csv(out_dir: Path, patients: int = 200, days: int = 90, seed: int = 7) -> None:
    """Ring data for the same cohort:
    - wearable_samples.csv: same columns as public.wearable_samples (+ is_synthetic)
    - ring_episodes.csv: injected, labelled anomaly episodes (to score the ring monitor)
    - patients.csv: per-patient synthetic home-BP target (classifier label, review M7)
    Ring draws use a separate generator per patient, so BP files are unchanged."""
    tz = ZoneInfo(TZ)
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "wearable_samples.csv", "w", newline="") as fs, \
            open(out_dir / "ring_episodes.csv", "w", newline="") as fe, \
            open(out_dir / "patients.csv", "w", newline="") as fp:
        ws, we, wp = csv.writer(fs), csv.writer(fe), csv.writer(fp)
        ws.writerow(["patient_key", "device_key", "metric", "value", "unit", "measured_at", "source", "external_id",
                     "is_synthetic", "generator_version"])
        we.writerow(["patient_key", "episode_type", "start_date", "end_date", "is_synthetic"])
        wp.writerow(["patient_key", "target_systolic", "target_diastolic", "conditions", "is_synthetic"])
        for key, _, _, _, effects in _ml_cohort(patients, days, seed):
            rr = random.Random(f"{GENERATOR_VERSION}:{key}:ring")
            # No age / sex in this cohort: overall rates (STEPS diabetes 17.5 %, BREATHE COPD 3.6 %, assumptions).
            conditions = [c for c, p in (("diabetes", 0.175), ("copd", 0.036), ("obstructive_sleep_apnea", 0.30),
                                         ("atrial_fibrillation", 0.02)) if rr.random() < p]
            rp = ring_profile(rr, conditions)
            wp.writerow([key, *rr.choice(((135, 85), (135, 85), (130, 80))), ";".join(conditions), "true"])
            episode, episode_days = None, range(0)
            if rr.random() < 0.3:
                episode, first = rr.choice(RING_EPISODES), rr.randint(35, days - 4)
                episode_days = range(first, first + rr.randint(1, 3))
                we.writerow([key, episode, (ML_START + timedelta(days=first)).isoformat(),
                             (ML_START + timedelta(days=episode_days[-1])).isoformat(), "true"])
            n = 0
            for d in range(days):
                if rr.random() < 0.1:  # ring not worn that day
                    continue
                day0 = datetime.combine(ML_START + timedelta(days=d), datetime.min.time(), tz)
                for metric, value, unit, minute in ring_day_samples(rr, rp, effects[d],
                                                                    episode if d in episode_days else None):
                    n += 1
                    ws.writerow([key, f"{key}-ring", metric, value, unit, (day0 + timedelta(minutes=minute)).isoformat(),
                                 "simulated", f"sim-{key}-{n:06d}", "true", ML_GENERATOR_VERSION])


def write_sample_csv(path: Path) -> None:
    """Cuff-export style CSV (naive local times) with a few rows that must be rejected."""
    rng = random.Random(f"{GENERATOR_VERSION}:sample")
    _, readings = simulate_patient(rng, Profile(138, 87, 0.2, 0.2, False, 0.0), 14)
    first = date(2026, 10, 14)
    rows = [[(datetime.combine(first + timedelta(days=r.day), datetime.min.time()) + timedelta(minutes=r.minute))
             .strftime("%Y-%m-%d %H:%M"), r.systolic, r.diastolic, r.pulse, "mmHg", "sitting", "left", ""] for r in readings]
    rows[3][4] = "kPa"            # unsupported unit -> rejected
    rows[5][2] = ""               # missing diastolic -> rejected
    rows[7][0] = "yesterday 8am"  # unparseable timestamp -> rejected
    rows[9][7] = "after coffee"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["# SYNTHETIC SAMPLE generated by pulse_data.simulate; not a real patient"])
        w.writerow(["measured_at", "systolic", "diastolic", "pulse", "unit", "position", "arm", "note"])
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed").add_argument("--out", type=Path, default=ROOT / "supabase" / "seed.sql")
    c = sub.add_parser("csv")
    c.add_argument("--out", type=Path, default=ROOT / "data" / "synthetic")
    c.add_argument("--patients", type=int, default=200)
    c.add_argument("--days", type=int, default=90)
    c.add_argument("--seed", type=int, default=7)
    sub.add_parser("sample").add_argument("--out", type=Path, default=ROOT / "samples" / "readings_sample.csv")
    sub.add_parser("ring-demo-sql").add_argument("--out", type=Path, default=ROOT / "data" / "cloud_ring_demo.sql")
    a = ap.parse_args()
    if a.cmd == "seed":
        password = os.environ.get("PULSE_DEMO_PASSWORD")
        if not password:
            sys.exit("set PULSE_DEMO_PASSWORD (demo accounts' password; never commit it)")
        a.out.write_text(build_seed_sql(password), encoding="utf-8")
    elif a.cmd == "csv":
        write_ml_csv(a.out, a.patients, a.days, a.seed)
        write_ring_csv(a.out, a.patients, a.days, a.seed)
    elif a.cmd == "ring-demo-sql":
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(cloud_ring_demo_sql(), encoding="utf-8")
        for i, part in enumerate(cloud_ring_demo_parts(), 1):   # smaller files for the cloud API
            (a.out.parent / f"{a.out.stem}_part{i}.sql").write_text(part, encoding="utf-8")
    else:
        write_sample_csv(a.out)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
