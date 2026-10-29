"""Plain data types shared by the analysis functions.

The analysis package is pure: no database, no HTTP, no clock. Callers pass
`now` explicitly so every function is deterministic and testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

Level = Literal["none", "notice", "trend", "severe", "emergency"]
AlertAction = Literal["create", "attach", "raise", "none"]
ValidationStatus = Literal["valid", "questionable"]

LEVEL_RANK: dict[str, int] = {"none": 0, "notice": 1, "trend": 2, "severe": 3, "emergency": 4}


@dataclass(frozen=True)
class Target:
    """Blood-pressure target. Default applies until a doctor sets a care plan."""
    systolic: int = 140
    diastolic: int = 90
    is_default: bool = True


@dataclass(frozen=True)
class Reading:
    systolic: int
    diastolic: int
    measured_at: datetime
    pulse: int | None = None
    validation_status: ValidationStatus = "valid"
    id: int | None = None


@dataclass(frozen=True)
class ActiveAlert:
    """An alert that is still active (new / acknowledged / escalated)."""
    id: int
    level: Level
    rule_id: str
    triggered_at: datetime  # measured_at of the reading (or report time) that created it


@dataclass(frozen=True)
class FieldError:
    field: str
    code: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    status: ValidationStatus
    errors: list[FieldError] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Evaluation:
    level: Level
    rule_id: str | None
    reason: str
    next_step: str
    alert_action: AlertAction
    target_alert_id: int | None = None
    requires_symptom_check: bool = False
    recheck_after_seconds: int | None = None
    show_emergency: bool = False
    persistent: bool = False


@dataclass(frozen=True)
class Summary:
    window_days: int
    count_7d: int
    count_questionable_7d: int
    avg_systolic_7d: float | None
    avg_diastolic_7d: float | None
    avg_systolic_30d: float | None
    avg_diastolic_30d: float | None
    max_systolic_7d: int | None
    max_diastolic_7d: int | None
    pct_above_target_7d: float | None
    days_with_reading_7d: int
    trend: Literal["rising", "stable", "falling", "insufficient_data"]
    last_measured_at: datetime | None
    target: Target
