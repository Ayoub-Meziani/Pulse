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
    "DATA-INVALID": "Check the cuff and the numbers, then measure again. If you feel unwell, "
                    "use the Urgence button or call emergency services.",
    # Low pressure (proposed decision D27; wording pending clinician review).
    "R-LOW-1": "Your blood pressure is low. Sit or lie down and measure again later; your doctor will see it. "
               "If you feel dizzy, faint or confused, call emergency services.",
    "R-LOW-2": "Your blood pressure is very low. Answer the symptom check first, then lie down and measure again "
               "in 60 seconds. If you feel faint, confused or unwell, call emergency services.",
    "DATA-INVALID-LOW": "This reading is too low to be a real measurement, or the cuff failed. If you feel faint, "
                        "confused or unwell, call emergency services now. Otherwise check the cuff and measure again.",
    None: "Reading saved.",
    # File imports (proposed decision D26; wording pending clinician review).
    "IMPORT-PAST-SEVERE": "Some imported readings were 180/120 or higher. Measure your blood pressure now. "
                          "If you feel unwell, call emergency services.",
    "IMPORT-PAST-LOW": "Some imported readings were very low. Measure your blood pressure now. If you feel faint, "
                       "confused or unwell, call emergency services.",
    "IMPORT-SIMULATED": "Simulated readings are labelled and never raise an alert.",
    "IMPORT-HISTORY": "Older readings were added to your history; they count in your weekly average.",
    "IMPORT-NOTHING": "Nothing new was added: these readings were already in your history.",
    "IMPORT-REJECTED": "No reading could be added. Check the rejected rows and the file format, then try again.",
    "IMPORT-RING": "Ring data is context for your doctor and never raises an alert.",
}

# Plain words for the database's `invalid` flags (policy pulse-v1), shown with DATA-INVALID.
INVALID_FLAG_TEXT = {
    "systolic_not_above_diastolic": "the top number must be higher than the bottom number",
    "systolic_implausible": "the top number is outside the possible range",
    "diastolic_implausible": "the bottom number is outside the possible range",
    "pulse_implausible": "the pulse is outside the possible range",
    "measured_in_future": "the time of the reading is in the future",
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
