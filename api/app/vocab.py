"""Single mapping between API vocabulary and database vocabulary (architecture §7)."""
from __future__ import annotations

from .analysis.rules import RED_FLAG_SYMPTOMS  # noqa: F401  (re-exported: one source for red flags)

LEVEL_TO_ALERT_CLASS = {
    "notice": "above_target",
    "trend": "above_target_trend",
    "severe": "severely_high",
    "emergency": "possible_emergency",
}
ALERT_CLASS_TO_LEVEL = {v: k for k, v in LEVEL_TO_ALERT_CLASS.items()}
LEVEL_RANK = {"none": 0, "notice": 1, "trend": 2, "severe": 3, "emergency": 4}

ACTIVE_ALERT_STATUSES = ("open", "acknowledged")
ALERT_TRIGGER_SOURCE = "rule_engine"
RULE_VERSION = "pulse-rules-1"

# Manual readings posted by patients through the API.
MANUAL_SOURCE, MANUAL_PROVENANCE, MANUAL_METHOD = "manual", "measured", "unknown"
PATIENT_SYMPTOM_SOURCE = "patient_reported"

DEFAULT_TARGET = (140, 90)  # used when no active care plan sets a target
