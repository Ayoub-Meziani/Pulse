"""The single place where patient-data access is decided.

Patients: only their own data. Doctors: only assigned patients, read-only for
patient-owned data. Every patient-scoped route must call require_patient_access.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .errors import ApiError
from .models import DoctorPatientAssignment, User


def is_assigned(db: Session, doctor_id: int, patient_id: int) -> bool:
    return db.scalar(select(DoctorPatientAssignment).where(
        DoctorPatientAssignment.doctor_id == doctor_id,
        DoctorPatientAssignment.patient_id == patient_id)) is not None


def require_patient_access(db: Session, user: User, patient_id: int, write: bool = False) -> User:
    """Return the patient User or raise 403/404. `write` = patient-only actions."""
    allowed = (user.role == "patient" and user.id == patient_id) or \
              (user.role == "doctor" and not write and is_assigned(db, user.id, patient_id))
    if not allowed:
        # Same answer whether or not the patient exists, to avoid leaking ids.
        raise ApiError(403, "forbidden", "You do not have access to this patient.")
    patient = db.get(User, patient_id)
    if patient is None or patient.role != "patient":
        raise ApiError(404, "not_found", "Patient not found.")
    return patient


def require_role(user: User, role: str) -> None:
    if user.role != role:
        raise ApiError(403, "forbidden", f"Only a {role} can do this.")
