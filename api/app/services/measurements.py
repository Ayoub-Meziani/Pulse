"""Manual blood-pressure readings: store, read back the database's validation, evaluate the rules.

The database trigger (policy pulse-v1) is the only authority on validation_status; the API never
computes or sends it. Rule evaluation is the deterministic analysis package, in the same request.
No ML is involved here.

Step 4 of the integration plan: alerts are not persisted yet (step 5), so the rules see no active
alerts. A repeat severe reading is therefore evaluated as R-SEV-1 again (symptom check + recheck),
which is the more cautious answer, and `alert`/`trend_alert` stay null.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import vocab
from ..analysis import evaluate_measurement, texts
from ..analysis.types import Evaluation, Reading, Target
from ..auth import CurrentUser
from ..errors import ApiError
from ..models import CarePlan, Measurement
from ..schemas import MeasurementIn

UPPER_LIMIT_FLAGS = {"systolic_implausible": 300, "diastolic_implausible": 200}  # pulse-v1 upper bounds


def current_target(db: Session, patient_id: UUID) -> Target:
    plan = db.scalar(select(CarePlan).where(CarePlan.patient_id == patient_id, CarePlan.status == "active"))
    if plan and plan.target_systolic and plan.target_diastolic:
        return Target(plan.target_systolic, plan.target_diastolic, is_default=False)
    return Target(*vocab.DEFAULT_TARGET, is_default=True)


def _check_timezone(tz: str | None) -> None:
    if tz is None:
        return
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise ApiError(422, "validation_failed", "Reading rejected.",
                       [{"field": "measured_tz", "code": "invalid_timezone",
                         "message": "Use an IANA time zone such as Africa/Algiers."}]) from None


def invalid_evaluation(m: Measurement) -> Evaluation:
    flags = [f for f in m.quality_flags if f in texts.INVALID_FLAG_TEXT]
    reason = "This reading cannot be used: " + "; ".join(texts.INVALID_FLAG_TEXT[f] for f in flags) + "."
    above_limit = (m.systolic > UPPER_LIMIT_FLAGS["systolic_implausible"]
                   or m.diastolic > UPPER_LIMIT_FLAGS["diastolic_implausible"])
    # A typo must never hide a possible crisis: values above the plausible range ask for the symptom check.
    return Evaluation(level="none", rule_id="DATA-INVALID", reason=reason,
                      next_step=texts.NEXT_STEP["DATA-INVALID"], alert_action="none",
                      requires_symptom_check=above_limit)


def record_manual_reading(db: Session, patient: CurrentUser, data: MeasurementIn,
                          now: datetime) -> tuple[Measurement, Evaluation]:
    _check_timezone(data.measured_tz)
    m = Measurement(patient_id=patient.id, source=vocab.MANUAL_SOURCE, provenance=vocab.MANUAL_PROVENANCE,
                    method=vocab.MANUAL_METHOD, systolic=data.systolic, diastolic=data.diastolic,
                    pulse=data.pulse, measured_at=data.measured_at or now,
                    measured_tz=data.measured_tz or patient.timezone, body_position=data.body_position,
                    arm=data.arm, rested_5_min=data.rested_5_min, context=data.context, created_by=patient.id)
    db.add(m)
    db.flush()  # the pulse-v1 trigger sets validation_status / quality_flags; read back via RETURNING
    if m.validation_status == "invalid":
        evaluation = invalid_evaluation(m)
    else:  # valid and needs_review readings both go through the safety rules
        reading = Reading(m.systolic, m.diastolic, m.measured_at, m.pulse, m.validation_status)
        evaluation = evaluate_measurement(reading, current_target(db, patient.id), active_alerts=[])
    db.commit()
    return m, evaluation


def list_readings(db: Session, patient_id: UUID, start: datetime | None, end: datetime | None,
                  limit: int, include_invalid: bool) -> list[Measurement]:
    q = select(Measurement).where(Measurement.patient_id == patient_id)
    if not include_invalid:
        q = q.where(Measurement.validation_status != "invalid")
    if start:
        q = q.where(Measurement.measured_at >= start)
    if end:
        q = q.where(Measurement.measured_at <= end)
    return list(db.scalars(q.order_by(Measurement.measured_at.desc(), Measurement.created_at.desc()).limit(limit)))
