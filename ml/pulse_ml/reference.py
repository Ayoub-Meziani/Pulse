"""Medical reference values used for "placement" and outside-reference flags.

Every value carries its source; all were reviewed by the team's medical mentor on 30 Oct 2026 (CLINICIAN_REVIEW).
These are population references;
the patient's own normal (personal baseline / doctor-approved band) is handled in ring.py.
Nothing here decides an emergency: the deterministic backend rules do (review H6).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

CLINICIAN_REVIEW = "reviewed by the team's medical mentor, 30 Oct 2026 (prototype use)"

# Home BP categories [review H4]: the HOME (HBPM) column of ACC/AHA 2017 Table 11, which maps office
# 120/80, 130/80, 140/90, 160/100 to home 120/80, 130/80, 135/85, 145/90. Applied to a mean of home
# readings only, never to office readings; labelled "home-BP category".
HOME_BP_SOURCE = ("2017 ACC/AHA high blood pressure guideline, Table 11 (corresponding clinic / HBPM values); "
                  "https://www.acc.org/~/media/Non-Clinical/Files-PDFs-Excel-MS-Word-etc/Guidelines/2017/Guidelines_Made_Simple_2017_HBP.pdf")
HOME_BP_CATEGORIES = (  # (category, systolic lower bound, diastolic lower bound); first match from the top wins
    ("stage_2_range", 135, 85),   # home equivalent of office 140/90
    ("stage_1_range", 130, 80),   # home equivalent of office 130/80
    ("elevated", 120, None),      # home 120-129 with diastolic < 80
    ("normal", 0, 0),
)
HOME_MARKEDLY_HIGH = (145, 90)    # home equivalent of office 160/100 (informational, not a category)


def home_bp_category(mean_systolic: float, mean_diastolic: float) -> str:
    """Category of a MEAN of home readings (e.g. 7 days). OR rule: either value can raise the category."""
    for name, s, d in HOME_BP_CATEGORIES:
        if mean_systolic >= s or (d is not None and mean_diastolic >= d):
            return name
    return "normal"


# Ring metrics. Only heart rate and SpO2 have population references; HRV and skin temperature are personal only.
RING_REFERENCE = {
    "heart_rate": {
        "low": 60, "high": 100, "flag_sides": ("high",), "unit": "bpm", "applies_to": "resting (night median / at rest)",
        "source": "Mayo Clinic, 'Heart rate: what's normal?' (adults at rest 60-100 bpm); "
                  "https://www.mayoclinic.org/healthy-lifestyle/fitness/expert-answers/heart-rate/faq-20057979",
        "limits": "Fit people can be normal below 60. Ring heart rate during movement is less reliable.",
    },
    "spo2": {
        "low": 94, "high": 100, "flag_sides": ("low",), "unit": "percent", "applies_to": "at rest",
        "source": "BTS guideline for oxygen use in adults (O'Driscoll et al., Thorax 2017;72 Suppl 1): "
                  "target 94-98% for most acutely ill adults, 88-92% if at risk of hypercapnic failure; "
                  "https://www.brit-thoracic.org.uk/quality-improvement/guidelines/emergency-oxygen",
        "limits": "Consumer ring SpO2 is less accurate than a clinical oximeter. FDA safety communication "
                  "(19 Feb 2021): pulse oximeters can overestimate SpO2 in people with darker skin pigmentation, "
                  "and are affected by poor circulation, skin temperature, tobacco use and nail polish. "
                  "Some stable adults over 70 read 92-94%. COPD patients may have a doctor-set lower target.",
    },
    "hrv_rmssd": None,
    "skin_temperature": None,
}

# Proposed backend rule R-RING-1 [review H6]: evaluated by the BACKEND directly on wearable_samples,
# not by any ML job. Delivered here as a spec and constants only.
R_RING_1 = {
    "metric": "spo2", "window_minutes": 10, "statistic": "median", "below": RING_REFERENCE["spo2"]["low"],
    "min_samples": 2,
    "action": "prompt a cuff reading, a symptom check and re-seating the ring; never an emergency by itself",
    "status": f"{CLINICIAN_REVIEW}; for the backend to implement; symptoms keep their own emergency path",
}


# Chronic conditions (patient_profiles.condition_codes, M8) that change what "normal" means for a ring value.
CONDITION_ADJUSTMENTS = {
    "copd": {"spo2": {
        "low": 88,
        "source": "BTS 2017 oxygen guideline: target 88-92 % for patients at risk of hypercapnic respiratory failure "
                  "(e.g. COPD); https://www.brit-thoracic.org.uk/quality-improvement/guidelines/emergency-oxygen",
        "limits": "Not every COPD patient has this risk: the doctor confirms by approving the patient's SpO2 band."}},
}
# Atrial fibrillation: beat-to-beat intervals are irregular, so a ring's HRV (RMSSD) says nothing about stress or
# recovery, and wrist / finger PPG may report an irregular pulse instead (Apple Heart Study, 2019).
NOT_INTERPRETABLE = {"atrial_fibrillation": ("hrv_rmssd",)}


NHANES_BANDS_FILE = Path(__file__).resolve().parent / "reference_nhanes.json"   # real:nhanes (real_bands.py)


@lru_cache(maxsize=1)
def nhanes_bands() -> dict | None:
    return json.loads(NHANES_BANDS_FILE.read_text(encoding="utf-8")) if NHANES_BANDS_FILE.exists() else None


def pulse_vs_population(sex: str | None, age: int | None, mean_cuff_pulse: float | None) -> dict | None:
    """Where a patient's mean SEATED cuff pulse sits among US adults of the same sex and age (NHANES, weighted).
    Context for the doctor, not a threshold. Never applied to ring night heart rate (different measurement)."""
    ref = nhanes_bands()
    if ref is None or sex not in ("female", "male") or age is None or mean_cuff_pulse is None:
        return None
    groups = ref["bands"]["pulse"].get(sex, {})
    key = next((k for k in groups if (k.endswith("+") and age >= int(k[:-1]))
                or ("-" in k and int(k.split("-")[0]) <= age <= int(k.split("-")[1]))), None)
    if key is None:
        return None
    g = groups[key]
    qs = ref["percentiles"]
    values = [g[f"p{q:g}"] for q in qs]
    pct = float(np.interp(mean_cuff_pulse, values, qs, left=0.0, right=100.0))
    return {"mean_cuff_pulse": round(float(mean_cuff_pulse), 1), "percentile": round(pct, 1), "age_band": key,
            "band_p2_5_p97_5": [g["p2.5"], g["p97.5"]], "source": "real:nhanes 2017-2020 (US adults, weighted)",
            "note": "seated cuff pulse vs US adults of the same sex and age band; context, not a threshold"}


def reference_for(metric: str, conditions=()) -> dict | None:
    ref = RING_REFERENCE.get(metric)
    if ref is None:
        return None
    for c in conditions:
        if metric in CONDITION_ADJUSTMENTS.get(c, {}):
            ref = {**ref, **CONDITION_ADJUSTMENTS[c][metric]}
    return ref


def interpretable(metric: str, conditions=()) -> bool:
    return not any(metric in NOT_INTERPRETABLE.get(c, ()) for c in conditions)


def outside_reference(metric: str, value: float, conditions=()) -> bool:
    """Only the clinically meaningful side is flagged: heart rate too high (a low resting rate is often
    normal in fit people), SpO2 too low. Chronic conditions can move the limit (COPD) or remove it (AF / HRV)."""
    ref = reference_for(metric, conditions)
    if ref is None or not interpretable(metric, conditions):
        return False
    return ("low" in ref["flag_sides"] and value < ref["low"]) or ("high" in ref["flag_sides"] and value > ref["high"])
