"""Non-urgent in-app notifications (migration M11). Shown in PULSE only: no push, SMS or e-mail yet.

Doctors: a new or raised severe, trend or emergency alert of an assigned patient (notices stay in the alert
list, to avoid noise). Patients: their doctor reviewed or resolved one of their alerts. Alerts come only
from the deterministic rules on readings entered through the API, so simulated data never notifies anyone.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Alert, Assignment, Notification

DOCTOR_LEVELS = ("trend", "severe", "emergency")


def alert_for_doctors(db: Session, alert: Alert, level: str, kind: str) -> None:
    if level not in DOCTOR_LEVELS:
        return
    doctors = db.scalars(select(Assignment.doctor_id).where(Assignment.patient_id == alert.patient_id,
                                                            Assignment.status == "active"))
    for doctor in doctors:
        db.add(Notification(user_id=doctor, patient_id=alert.patient_id, kind=kind, alert_id=alert.id, urgent=False))


def alert_for_patient(db: Session, alert: Alert, kind: str, actor: UUID) -> None:
    if actor != alert.patient_id:
        db.add(Notification(user_id=alert.patient_id, patient_id=alert.patient_id, kind=kind, alert_id=alert.id,
                            urgent=False))
