"""All patient-facing alert wording in one place, for clinician review.

Prototype wording based on public American Heart Association patient guidance
(hypertensive crisis: 180/120 or higher). NOT clinically validated.
Rules (see docs/SAFETY_AND_LIMITATIONS.md):
- never diagnose, never mention starting/stopping/changing medication;
- one clear next step per message;
- severe and emergency messages always point to emergency services if unwell.

French and Arabic versions are still to be added here (keyed by the same ids).
"""

NEXT_STEP = {
    "R-EMG-1": "Call emergency services now. Do not wait to measure again.",
    "R-SEV-1": "Answer the symptom check first. If you have none of the symptoms, rest and "
               "measure again in 60 seconds. If you feel unwell, call emergency services.",
    "R-SEV-2": "Your reading is still very high. Contact your doctor or seek urgent medical "
               "advice today. If symptoms appear, call emergency services.",
    "R-SEV-3": "Your reading is lower now. Your doctor will still see the high reading. "
               "If you feel unwell, call emergency services.",
    "R-TGT-1": "This is above {target_label}. Rest 5 minutes, sitting, and measure again.",
    "R-TRD-1": "Your readings this week are above {target_label}. Your doctor will review them.",
    None: "Reading saved.",
}

# Codes match the database CHECK on symptom_reports.symptoms (supabase/migrations, branch AI).
SYMPTOM_LABELS = {
    "chest_pain": "chest pain",
    "shortness_of_breath": "shortness of breath",
    "back_pain": "back pain",
    "numbness": "numbness",
    "weakness": "weakness",
    "vision_change": "change in vision",
    "difficulty_speaking": "difficulty speaking",
    "severe_headache": "severe headache",
    "confusion": "confusion",
    "dizziness": "dizziness",
    "nausea": "nausea",
    "palpitations": "palpitations",
    "other": "other symptom",
}

NO_RED_FLAG_NEXT_STEP = ("Follow the instructions for your reading. Your doctor will see the symptoms "
                         "you reported. If you feel unwell, call emergency services.")


def target_label(is_default: bool) -> str:
    return "the general target" if is_default else "your target"
