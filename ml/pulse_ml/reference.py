"""Medical reference values used for "placement" and outside-reference flags.

Every value carries its source and is PENDING CLINICIAN REVIEW. These are population references;
the patient's own normal (personal baseline / doctor-approved band) is handled in ring.py.
Nothing here decides an emergency: the deterministic backend rules do (review H6).
"""
from __future__ import annotations

PENDING_CLINICIAN_REVIEW = True

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
        "low": 60, "high": 100, "unit": "bpm", "applies_to": "resting (night median / at rest)",
        "source": "Mayo Clinic, 'Heart rate: what's normal?' (adults at rest 60-100 bpm); "
                  "https://www.mayoclinic.org/healthy-lifestyle/fitness/expert-answers/heart-rate/faq-20057979",
        "limits": "Fit people can be normal below 60. Ring heart rate during movement is less reliable.",
    },
    "spo2": {
        "low": 94, "high": 100, "unit": "percent", "applies_to": "at rest",
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
    "status": "proposal, pending clinician review; symptoms keep their own emergency path",
}


def outside_reference(metric: str, value: float) -> bool:
    ref = RING_REFERENCE.get(metric)
    return ref is not None and not (ref["low"] <= value <= ref["high"])
