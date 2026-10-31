"""Manual blood-pressure readings: store, read back the database's validation, evaluate the rules.

The database trigger (policy pulse-v1) is the only authority on validation_status; the API never
computes or sends it. Rule evaluation is the deterministic analysis package, in the same request.
No ML is involved here.

Alerts are persisted in the same transaction (services/alerts.py). A reading the database flags as
`possible_duplicate` (e.g. a network retry) still gets the rules' guidance but does not change any
alert, so a retry is never counted as a recheck.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import vocab
from ..analysis import evaluate_measurement, evaluate_trend, texts
from ..analysis.rules import TREND_WINDOW
from ..analysis.types import Evaluation, Reading, Target
from ..auth import CurrentUser
from ..errors import ApiError
from ..models import Alert, AlertMeasurement, CarePlan, Measurement
from ..schemas import MeasurementIn
from .alerts import active_alerts, apply_evaluation

UPPER_LIMIT_FLAGS = {"systolic_implausible": 300, "diastolic_implausible": 200}  # pulse-v1 upper bounds
LOWER_LIMIT_FLAGS = {"systolic_implausible": 50, "diastolic_implausible": 25}   # pulse-v1 lower bounds


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
    below_limit = (m.systolic < LOWER_LIMIT_FLAGS["systolic_implausible"]
                   or m.diastolic < LOWER_LIMIT_FLAGS["diastolic_implausible"])
    # A typo must never hide a possible crisis: values outside the plausible range, too high or too low (a failed
    # cuff, or a person who is faint), ask for the symptom check. Not a usable reading, so no alert.
    return Evaluation(level="none", rule_id="DATA-INVALID", reason=reason,
                      next_step=texts.NEXT_STEP["DATA-INVALID-LOW" if below_limit else "DATA-INVALID"],
                      alert_action="none", requires_symptom_check=above_limit or below_limit)


def to_reading(m: Measurement) -> Reading:
    return Reading(m.systolic, m.diastolic, m.measured_at, m.pulse, m.validation_status, m.id)


def recent_readings(db: Session, patient_id: UUID, now: datetime) -> list[Reading]:
    """Input of the clinical trend rule (R-TRD-1). Simulated readings are excluded: generated data must never
    decide a clinical alert. They stay in the history (labelled by provenance) and the descriptive summary."""
    q = select(Measurement).where(Measurement.patient_id == patient_id,
                                  Measurement.provenance != vocab.SIMULATED_PROVENANCE,
                                  Measurement.measured_at >= now - TREND_WINDOW,
                                  Measurement.measured_at <= now + timedelta(minutes=5))
    return [to_reading(m) for m in db.scalars(q)]


def record_manual_reading(db: Session, patient: CurrentUser, data: MeasurementIn,
                          now: datetime) -> tuple[Measurement, Evaluation, Alert | None, Alert | None, bool]:
    """Returns (reading, evaluation, alert, trend_alert, created). A repeated client id replays the stored one."""
    _check_timezone(data.measured_tz)
    if data.id is not None and (stored := db.get(Measurement, data.id)) is not None:
        return (*replay_reading(db, stored, patient, data), False)
    m = Measurement(patient_id=patient.id, source=vocab.MANUAL_SOURCE, provenance=vocab.MANUAL_PROVENANCE,
                    method=vocab.MANUAL_METHOD, systolic=data.systolic, diastolic=data.diastolic,
                    pulse=data.pulse, measured_at=data.measured_at or now,
                    measured_tz=data.measured_tz or patient.timezone, body_position=data.body_position,
                    arm=data.arm, rested_5_min=data.rested_5_min, context=data.context, created_by=patient.id)
    if data.id is not None:
        m.id = data.id
    db.add(m)
    try:
        # The pulse-v1 trigger sets validation_status / quality_flags; read back via RETURNING. A concurrent
        # request with the same id waits here on the primary key until the first one commits.
        db.flush()
    except IntegrityError:
        db.rollback()
        stored = db.get(Measurement, data.id) if data.id is not None else None
        if stored is None:
            raise
        return (*replay_reading(db, stored, patient, data), False)
    alert = trend_alert = None
    if m.validation_status == "invalid":
        evaluation = invalid_evaluation(m)
    else:  # valid and needs_review readings both go through the safety rules
        target = current_target(db, patient.id)
        evaluation = evaluate_measurement(to_reading(m), target, active_alerts(db, patient.id))
        if "possible_duplicate" not in m.quality_flags:
            alert = apply_evaluation(db, patient.id, evaluation, measurement_id=m.id)
            trend = evaluate_trend(recent_readings(db, patient.id, now), target, active_alerts(db, patient.id), now)
            if trend is not None:
                trend_alert = apply_evaluation(db, patient.id, trend, measurement_id=m.id)
    db.commit()
    return m, evaluation, alert, trend_alert, True


def _same_reading(m: Measurement, data: MeasurementIn) -> bool:
    return ((m.systolic, m.diastolic, m.pulse) == (data.systolic, data.diastolic, data.pulse)
            and (data.measured_at is None or m.measured_at == data.measured_at))


def replay_reading(db: Session, m: Measurement, patient: CurrentUser,
                   data: MeasurementIn) -> tuple[Measurement, Evaluation, Alert | None, Alert | None]:
    """The stored reading for a repeated client id. Alerts are never changed by a retry.

    The evaluation is recomputed for the stored reading with the alerts it created itself set aside, so it
    matches the first answer while nothing else changed in between."""
    if m.patient_id != patient.id or m.source != vocab.MANUAL_SOURCE or not _same_reading(m, data):
        # Never reveal another patient's reading, nor what the first request contained.
        raise ApiError(409, "conflict", "This reading id is already used. Generate a new id.")
    attached = select(AlertMeasurement.alert_id).where(AlertMeasurement.measurement_id == m.id)
    linked = list(db.scalars(select(Alert).where(Alert.patient_id == patient.id,
                                                 (Alert.measurement_id == m.id) | Alert.id.in_(attached))
                             .order_by(Alert.created_at)))
    if m.validation_status == "invalid":
        evaluation = invalid_evaluation(m)
    else:
        own = {a.id for a in linked if a.measurement_id == m.id}
        others = [a for a in active_alerts(db, patient.id) if a.id not in own]
        evaluation = evaluate_measurement(to_reading(m), current_target(db, patient.id), others)
    alert = next((a for a in linked if a.alert_class != vocab.LEVEL_TO_ALERT_CLASS["trend"]), None)
    trend_alert = next((a for a in linked if a.alert_class == vocab.LEVEL_TO_ALERT_CLASS["trend"]), None)
    return m, evaluation, alert, trend_alert


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
