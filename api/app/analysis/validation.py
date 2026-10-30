"""Measurement validation (rules V1-V4). Pure function.

Impossible values are rejected. Plausible-but-odd values are kept and flagged
`questionable` so nothing is silently rewritten or dropped.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from .types import FieldError, ValidationResult

SYSTOLIC_RANGE = (50, 300)
DIASTOLIC_RANGE = (30, 200)
PULSE_RANGE = (25, 250)
MAX_FUTURE = timedelta(minutes=5)
PULSE_PRESSURE_RANGE = (20, 120)


def _range_error(field: str, value: int, lo: int, hi: int) -> FieldError:
    return FieldError(field, "out_of_range", f"{field} must be between {lo} and {hi} (got {value}).")


def validate_measurement(systolic: int, diastolic: int, pulse: int | None,
                         measured_at: datetime, now: datetime) -> ValidationResult:
    errors: list[FieldError] = []
    # V1: physiologically possible ranges
    if not SYSTOLIC_RANGE[0] <= systolic <= SYSTOLIC_RANGE[1]:
        errors.append(_range_error("systolic", systolic, *SYSTOLIC_RANGE))
    if not DIASTOLIC_RANGE[0] <= diastolic <= DIASTOLIC_RANGE[1]:
        errors.append(_range_error("diastolic", diastolic, *DIASTOLIC_RANGE))
    if pulse is not None and not PULSE_RANGE[0] <= pulse <= PULSE_RANGE[1]:
        errors.append(_range_error("pulse", pulse, *PULSE_RANGE))
    # V2: systolic must exceed diastolic
    if systolic <= diastolic:
        errors.append(FieldError("systolic", "not_above_diastolic",
                                 "Systolic must be greater than diastolic."))
    # V3: not in the future
    if measured_at - now > MAX_FUTURE:
        errors.append(FieldError("measured_at", "in_future",
                                 "measured_at is more than 5 minutes in the future."))
    if errors:
        return ValidationResult(ok=False, status="questionable", errors=errors)

    # V4: unusual pulse pressure -> keep, but flag
    notes: list[str] = []
    pp = systolic - diastolic
    if not PULSE_PRESSURE_RANGE[0] <= pp <= PULSE_PRESSURE_RANGE[1]:
        notes.append(f"Unusual pulse pressure ({pp} mmHg). Please measure again to confirm.")
        return ValidationResult(ok=True, status="questionable", notes=notes)
    return ValidationResult(ok=True, status="valid")
