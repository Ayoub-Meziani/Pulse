"""Doctor list, readings, symptoms, alerts list, summaries and predictions of one patient.

Access (permissions.py): the patient for their own id; an actively assigned doctor for reads.
Writes of readings and symptoms: the patient only.
"""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from ..analysis.types import Evaluation
from ..auth import CurrentUser, current_user
from ..db import require_session
from ..errors import AUTH_RESPONSES, not_implemented
from ..permissions import require_assigned_doctor, require_patient_access, require_role
from ..services import patient_data, predictions
from ..schemas import (AlertOut, DailyPoint, EvaluationOut, MeasurementIn, MeasurementOut, MeasurementResult,
                       PatientListItem, PredictionOut, SummaryOut, SymptomReportIn, SymptomReportOut,
                       SymptomResult)
from ..services import alerts as alert_service
from ..services.measurements import list_readings, record_manual_reading
from ..services.symptoms import list_reports, record_symptoms
from .alerts import alert_brief, alert_out


def evaluation_out(ev: Evaluation) -> EvaluationOut:
    return EvaluationOut(level=ev.level, rule_id=ev.rule_id, reason=ev.reason, next_step=ev.next_step,
                         requires_symptom_check=ev.requires_symptom_check,
                         recheck_after_seconds=ev.recheck_after_seconds, show_emergency=ev.show_emergency)

router = APIRouter(tags=["patients"], responses=AUTH_RESPONSES, dependencies=[Depends(current_user)])


@router.get("/patients", response_model=list[PatientListItem],
            summary="Doctor: assigned patients, most urgent active alert first, then oldest last reading")
def list_patients(request: Request, user: CurrentUser = Depends(current_user),
                  db: Session = Depends(require_session)):
    require_role(user, "doctor")
    return patient_data.doctor_patient_list(db, user, request.app.state.clock())


@router.post("/patients/{patient_id}/measurements", response_model=MeasurementResult, status_code=201,
             summary="Patient: record a manual reading; returns the rule evaluation in the same response",
             responses={200: {"model": MeasurementResult,
                              "description": "A reading with this client-generated id already exists; it is returned "
                                             "and no alert is changed (safe retry)."},
                        201: {"description": "Reading stored and evaluated."}})
def create_measurement(patient_id: UUID, body: MeasurementIn, request: Request, response: Response,
                       user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    require_patient_access(db, user, patient_id, write=True)
    m, ev, alert, trend_alert, created = record_manual_reading(db, user, body, request.app.state.clock())
    if not created:
        response.status_code = 200
    return MeasurementResult(measurement=MeasurementOut.model_validate(m), evaluation=evaluation_out(ev),
                             alert=alert_brief(alert), trend_alert=alert_brief(trend_alert))


@router.get("/patients/{patient_id}/measurements", response_model=list[MeasurementOut],
            summary="Readings, newest first; invalid readings only with include_invalid=true")
def list_measurements(patient_id: UUID,
                      from_: AwareDatetime | None = Query(None, alias="from"),
                      to: AwareDatetime | None = None,
                      limit: int = Query(200, ge=1, le=1000),
                      include_invalid: bool = False,
                      user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    require_patient_access(db, user, patient_id)
    return [MeasurementOut.model_validate(m)
            for m in list_readings(db, patient_id, from_, to, limit, include_invalid)]


@router.get("/patients/{patient_id}/summary", response_model=SummaryOut,
            summary="7/30-day statistics on valid readings, trend direction and target")
def summary(patient_id: UUID, request: Request, user: CurrentUser = Depends(current_user),
            db: Session = Depends(require_session)):
    require_patient_access(db, user, patient_id)
    return patient_data.summary(db, patient_id, request.app.state.clock())


@router.get("/patients/{patient_id}/daily", response_model=list[DailyPoint],
            summary="Per local day: morning/evening means of valid readings (deferrable)")
def daily(patient_id: UUID, days: int = Query(30, ge=1, le=90)):
    not_implemented()


@router.post("/patients/{patient_id}/symptom-reports", response_model=SymptomResult, status_code=201,
             summary="Patient: symptom check; any red-flag symptom returns show_emergency=true")
def create_symptom_report(patient_id: UUID, body: SymptomReportIn, request: Request,
                          user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    require_patient_access(db, user, patient_id, write=True)
    report, ev, alert = record_symptoms(db, user, body, request.app.state.clock())
    return SymptomResult(report=symptom_report_out(report), evaluation=evaluation_out(ev), alert=alert_brief(alert))


def symptom_report_out(report) -> SymptomReportOut:
    # measurement_id stays null: the link to a reading is not stored until a migration adds it (B24).
    return SymptomReportOut(id=report.id, patient_id=report.patient_id, symptoms=report.symptoms,
                            measurement_id=None, onset_at=report.onset_at, reported_at=report.reported_at,
                            source=report.source)


@router.get("/patients/{patient_id}/symptom-reports", response_model=list[SymptomReportOut],
            summary="Symptom reports, newest first (patient or assigned doctor); measurement_id is always null (B24)")
def list_symptom_reports(patient_id: UUID,
                         from_: AwareDatetime | None = Query(None, alias="from"),
                         to: AwareDatetime | None = None,
                         limit: int = Query(100, ge=1, le=500),
                         user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    require_patient_access(db, user, patient_id)
    return [symptom_report_out(r) for r in list_reports(db, patient_id, from_, to, limit)]


@router.get("/patients/{patient_id}/alerts", response_model=list[AlertOut],
            summary="Alerts; active = open or acknowledged")
def list_alerts(patient_id: UUID, status: Literal["active", "all"] = "active",
                user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    require_patient_access(db, user, patient_id)
    return [alert_out(a) for a in alert_service.list_alerts(db, patient_id, active_only=status == "active")]


@router.get("/patients/{patient_id}/predictions/latest", response_model=PredictionOut,
            summary="Doctor only: latest experimental ML estimate (synthetic training data); never used for alerts")
def latest_prediction(patient_id: UUID, request: Request, user: CurrentUser = Depends(current_user),
                      db: Session = Depends(require_session)):
    require_assigned_doctor(db, user, patient_id)  # patients, unassigned doctors and admin: 403
    today = patient_data.local_today(db, patient_id, request.app.state.clock())
    return predictions.latest_prediction(db, patient_id, request.app.state.settings.ml_model_version, today)
