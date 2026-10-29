"""Patient-scoped endpoints. Every route calls require_patient_access first."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import AwareDatetime
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import analysis
from ..analysis.types import LEVEL_RANK
from ..auth import current_user, get_db
from ..models import ACTIVE_ALERT_STATES, Alert, DoctorPatientAssignment, Measurement, User
from ..permissions import require_patient_access, require_role
from ..schemas import (AlertBrief, AlertOut, EvaluationOut, MeasurementIn, MeasurementOut,
                       MeasurementResult, PatientListItem, SummaryOut, SymptomReportIn,
                       SymptomReportOut, SymptomResult, TargetOut)
from ..services.measurements import current_target, ingest_measurement, readings_since, report_symptoms

router = APIRouter(tags=["patients"])


def _now(request: Request) -> datetime:
    return request.app.state.clock()


def _eval_out(ev) -> EvaluationOut:
    return EvaluationOut(level=ev.level, rule_id=ev.rule_id, reason=ev.reason, next_step=ev.next_step,
                         requires_symptom_check=ev.requires_symptom_check,
                         recheck_after_seconds=ev.recheck_after_seconds, show_emergency=ev.show_emergency)


def _brief(a: Alert | None) -> AlertBrief | None:
    return AlertBrief.model_validate(a) if a else None


def _summary_out(db: Session, patient_id: int, now: datetime) -> SummaryOut:
    target = current_target(db, patient_id, now)
    s = analysis.compute_summary(readings_since(db, patient_id, now - timedelta(days=30)), target, now)
    data = s.__dict__ | {"target": TargetOut(**target.__dict__)}
    return SummaryOut(**data)


@router.get("/patients", response_model=list[PatientListItem])
def list_patients(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Doctor only: assigned patients, most urgent first, then oldest last reading."""
    require_role(user, "doctor")
    now = _now(request)
    patients = db.scalars(select(User).join(DoctorPatientAssignment, DoctorPatientAssignment.patient_id == User.id)
                          .where(DoctorPatientAssignment.doctor_id == user.id))
    items = []
    for p in patients:
        actives = list(db.scalars(select(Alert).where(Alert.patient_id == p.id,
                                                      Alert.state.in_(ACTIVE_ALERT_STATES))))
        latest = db.scalar(select(Measurement).where(Measurement.patient_id == p.id)
                           .order_by(Measurement.measured_at.desc()).limit(1))
        summary = _summary_out(db, p.id, now)
        highest = max((a.level for a in actives), key=LEVEL_RANK.get, default=None)
        items.append(PatientListItem(
            id=p.id, full_name=p.full_name, highest_active_alert=highest, active_alert_count=len(actives),
            latest_measurement=MeasurementOut.model_validate(latest) if latest else None,
            last_measured_at=latest.measured_at if latest else None,
            avg_systolic_7d=summary.avg_systolic_7d, avg_diastolic_7d=summary.avg_diastolic_7d))
    items.sort(key=lambda i: (-LEVEL_RANK.get(i.highest_active_alert or "none"),
                              i.last_measured_at.timestamp() if i.last_measured_at else 0.0))
    return items


@router.post("/patients/{patient_id}/measurements", response_model=MeasurementResult, status_code=201)
def create_measurement(patient_id: int, body: MeasurementIn, request: Request,
                       user: User = Depends(current_user), db: Session = Depends(get_db)):
    patient = require_patient_access(db, user, patient_id, write=True)
    m, ev, alert, trend_alert = ingest_measurement(db, patient, body, user, _now(request))
    return MeasurementResult(measurement=MeasurementOut.model_validate(m), evaluation=_eval_out(ev),
                             alert=_brief(alert), trend_alert=_brief(trend_alert))


@router.get("/patients/{patient_id}/measurements", response_model=list[MeasurementOut])
def list_measurements(patient_id: int, user: User = Depends(current_user), db: Session = Depends(get_db),
                      from_: AwareDatetime | None = Query(None, alias="from"), to: AwareDatetime | None = None,
                      limit: int = Query(200, ge=1, le=1000)):
    require_patient_access(db, user, patient_id)
    q = select(Measurement).where(Measurement.patient_id == patient_id)
    if from_:
        q = q.where(Measurement.measured_at >= from_)
    if to:
        q = q.where(Measurement.measured_at <= to)
    return list(db.scalars(q.order_by(Measurement.measured_at.desc()).limit(limit)))


@router.get("/patients/{patient_id}/summary", response_model=SummaryOut)
def summary(patient_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_patient_access(db, user, patient_id)
    return _summary_out(db, patient_id, _now(request))


@router.post("/patients/{patient_id}/symptom-reports", response_model=SymptomResult, status_code=201)
def create_symptom_report(patient_id: int, body: SymptomReportIn, request: Request,
                          user: User = Depends(current_user), db: Session = Depends(get_db)):
    patient = require_patient_access(db, user, patient_id, write=True)
    report, ev, alert = report_symptoms(db, patient, body, _now(request))
    return SymptomResult(report=SymptomReportOut.model_validate(report), evaluation=_eval_out(ev),
                         alert=_brief(alert))


@router.get("/patients/{patient_id}/alerts", response_model=list[AlertOut])
def list_alerts(patient_id: int, state: Literal["active", "all"] = "active",
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_patient_access(db, user, patient_id)
    q = select(Alert).where(Alert.patient_id == patient_id)
    if state == "active":
        q = q.where(Alert.state.in_(ACTIVE_ALERT_STATES))
    return list(db.scalars(q.order_by(Alert.created_at.desc())))
