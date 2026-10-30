"""Symptom check: store the answer (including "none of these"), run R-EMG-1, persist the alert.

Any of the 7 red-flag symptoms means emergency whatever the reading (show_emergency=true), raising
the most recent active severe alert from the last hour or creating one. Evaluated in the same
request; no ML.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .. import vocab
from ..analysis import evaluate_symptoms
from ..analysis.types import Evaluation
from ..auth import CurrentUser
from ..errors import ApiError
from ..models import Alert, Measurement, SymptomReport
from ..schemas import SymptomReportIn
from .alerts import active_alerts, apply_evaluation


def record_symptoms(db: Session, patient: CurrentUser, data: SymptomReportIn,
                    now: datetime) -> tuple[SymptomReport, Evaluation, Alert | None]:
    if data.measurement_id is not None:
        # symptom_reports has no measurement_id column yet (requested as migration M7), so the link is
        # validated but not stored; it is never accepted for another patient's reading.
        m = db.get(Measurement, data.measurement_id)
        if m is None or m.patient_id != patient.id:
            raise ApiError(422, "invalid_reference", "measurement_id is not one of your readings.",
                           [{"field": "measurement_id", "code": "invalid_reference",
                             "message": "Use the id returned when you recorded the reading."}])
    if data.onset_at is not None and data.onset_at > now + timedelta(minutes=5):  # DB allows 5 min skew
        raise ApiError(422, "validation_failed", "Symptom onset cannot be in the future.",
                       [{"field": "onset_at", "code": "in_future", "message": "Use the time the symptoms started."}])
    report = SymptomReport(patient_id=patient.id, symptoms=list(dict.fromkeys(data.symptoms)),
                           onset_at=data.onset_at, reported_at=now, source=vocab.PATIENT_SYMPTOM_SOURCE,
                           notes=data.notes)
    db.add(report)
    db.flush()
    evaluation = evaluate_symptoms(report.symptoms, active_alerts(db, patient.id), now)
    alert = apply_evaluation(db, patient.id, evaluation, symptom_report_id=report.id)
    db.commit()
    return report, evaluation, alert
