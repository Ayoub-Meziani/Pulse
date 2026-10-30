"""Doctor list, readings, symptoms, alerts list, summaries and predictions of one patient.

Access (permissions.py): the patient for their own id; an actively assigned doctor for reads.
Writes of readings and symptoms: the patient only.
"""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from ..analysis.types import Evaluation
from ..auth import CurrentUser, current_user
from ..db import require_session
from ..errors import AUTH_RESPONSES, not_implemented
from ..permissions import require_patient_access
from ..schemas import (AlertOut, DailyPoint, EvaluationOut, MeasurementIn, MeasurementOut, MeasurementResult,
                       PatientListItem, PredictionOut, SummaryOut, SymptomReportIn, SymptomResult)
from ..services.measurements import list_readings, record_manual_reading


def evaluation_out(ev: Evaluation) -> EvaluationOut:
    return EvaluationOut(level=ev.level, rule_id=ev.rule_id, reason=ev.reason, next_step=ev.next_step,
                         requires_symptom_check=ev.requires_symptom_check,
                         recheck_after_seconds=ev.recheck_after_seconds, show_emergency=ev.show_emergency)

router = APIRouter(tags=["patients"], responses=AUTH_RESPONSES, dependencies=[Depends(current_user)])


@router.get("/patients", response_model=list[PatientListItem],
            summary="Doctor: assigned patients, most urgent active alert first, then oldest last reading")
def list_patients():
    not_implemented()


@router.post("/patients/{patient_id}/measurements", response_model=MeasurementResult, status_code=201,
             summary="Patient: record a manual reading; returns the rule evaluation in the same response")
def create_measurement(patient_id: UUID, body: MeasurementIn, request: Request,
                       user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    require_patient_access(db, user, patient_id, write=True)
    m, ev = record_manual_reading(db, user, body, request.app.state.clock())
    # alert / trend_alert stay null until alert persistence (integration plan step 5).
    return MeasurementResult(measurement=MeasurementOut.model_validate(m), evaluation=evaluation_out(ev))


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
def summary(patient_id: UUID):
    not_implemented()


@router.get("/patients/{patient_id}/daily", response_model=list[DailyPoint],
            summary="Per local day: morning/evening means of valid readings (deferrable)")
def daily(patient_id: UUID, days: int = Query(30, ge=1, le=90)):
    not_implemented()


@router.post("/patients/{patient_id}/symptom-reports", response_model=SymptomResult, status_code=201,
             summary="Patient: symptom check; any red-flag symptom returns show_emergency=true")
def create_symptom_report(patient_id: UUID, body: SymptomReportIn):
    not_implemented()


@router.get("/patients/{patient_id}/alerts", response_model=list[AlertOut],
            summary="Alerts; active = open or acknowledged")
def list_alerts(patient_id: UUID, status: Literal["active", "all"] = "active"):
    not_implemented()


@router.get("/patients/{patient_id}/predictions/latest", response_model=PredictionOut,
            summary="Doctor only: latest ML estimate (synthetic training data); never used for alerts")
def latest_prediction(patient_id: UUID):
    not_implemented()
