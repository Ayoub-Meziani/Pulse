"""Ingestion: validate -> de-duplicate -> persist -> deterministic rules -> alerts.

ML forecasting is intentionally NOT part of this path: urgent guidance must
never wait for, or depend on, a model.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import analysis
from ..analysis.types import Reading, Target
from ..errors import ApiError
from ..models import CarePlan, Measurement, SymptomReport, User
from ..schemas import MeasurementIn, SymptomReportIn
from .alerts import active_alerts, apply_evaluation, as_active


def current_target(db: Session, patient_id: int, now: datetime) -> Target:
    plan = db.scalar(select(CarePlan).where(CarePlan.patient_id == patient_id, CarePlan.effective_from <= now)
                     .order_by(CarePlan.effective_from.desc()).limit(1))
    return Target(plan.target_systolic, plan.target_diastolic, is_default=False) if plan else Target()


def to_reading(m: Measurement) -> Reading:
    return Reading(m.systolic, m.diastolic, m.measured_at, m.pulse, m.validation_status, m.id)


def readings_since(db: Session, patient_id: int, since: datetime) -> list[Reading]:
    rows = db.scalars(select(Measurement).where(Measurement.patient_id == patient_id,
                                                Measurement.measured_at > since))
    return [to_reading(m) for m in rows]


def ingest_measurement(db: Session, patient: User, data: MeasurementIn, actor: User, now: datetime):
    measured_at = data.measured_at or now
    v = analysis.validate_measurement(data.systolic, data.diastolic, data.pulse, measured_at, now)
    if not v.ok:
        raise ApiError(422, "validation_failed", "Measurement rejected.",
                       [{"field": e.field, "code": e.code, "message": e.message} for e in v.errors])

    if data.external_id:
        dup = db.scalar(select(Measurement).where(
            Measurement.patient_id == patient.id, Measurement.source == data.source,
            Measurement.external_id == data.external_id))
        if dup:
            raise ApiError(409, "duplicate_measurement", "This reading was already recorded.",
                           {"existing_id": dup.id})

    m = Measurement(patient_id=patient.id, systolic=data.systolic, diastolic=data.diastolic,
                    pulse=data.pulse, measured_at=measured_at, received_at=now, source=data.source,
                    source_ref=data.source_ref, external_id=data.external_id,
                    context=data.context.model_dump(exclude_none=True) if data.context else None,
                    validation_status=v.status, validation_notes=v.notes or None, created_by=actor.id)
    db.add(m)
    db.flush()

    target = current_target(db, patient.id, now)
    actives = as_active(active_alerts(db, patient.id))
    ev = analysis.evaluate_measurement(to_reading(m), target, actives)
    alert = apply_evaluation(db, patient.id, ev, triggered_at=measured_at, measurement_id=m.id)

    db.flush()
    trend_alert = None
    trend_ev = analysis.evaluate_trend(readings_since(db, patient.id, now - timedelta(days=7)), target,
                                       as_active(active_alerts(db, patient.id)), now)
    if trend_ev is not None:
        trend_alert = apply_evaluation(db, patient.id, trend_ev, triggered_at=measured_at, measurement_id=m.id)

    db.commit()
    return m, ev, alert, trend_alert


def report_symptoms(db: Session, patient: User, data: SymptomReportIn, now: datetime):
    if data.measurement_id is not None:
        m = db.get(Measurement, data.measurement_id)
        if m is None or m.patient_id != patient.id:
            raise ApiError(422, "validation_failed", "measurement_id does not belong to this patient.")
    report = SymptomReport(patient_id=patient.id, symptoms=list(data.symptoms), notes=data.notes,
                           measurement_id=data.measurement_id, reported_at=now)
    db.add(report)
    db.flush()
    ev = analysis.evaluate_symptoms(list(data.symptoms), as_active(active_alerts(db, patient.id)), now)
    alert = apply_evaluation(db, patient.id, ev, triggered_at=now, symptom_report_id=report.id,
                             actor_user_id=patient.id, actor_role="patient")
    db.commit()
    return report, ev, alert
