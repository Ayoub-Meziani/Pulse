"""The single place where patient/doctor access is decided (architecture A4).

Patient: only their own id. Doctor: only patients with an *active* assignment, read-only on
patient-owned data; doctor-owned resources (care plan, notes, reviews) need
require_assigned_doctor. Admin: no patient data through the API in the MVP.
The same 403 is returned whether or not the patient exists, so ids cannot be probed.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import CurrentUser
from .errors import ApiError
from .models import Assignment


def _forbidden() -> ApiError:
    return ApiError(403, "forbidden", "You do not have access to this patient.")


def is_assigned(db: Session, doctor_id: UUID, patient_id: UUID) -> bool:
    return db.scalar(select(Assignment.id).where(Assignment.doctor_id == doctor_id,
                                                 Assignment.patient_id == patient_id,
                                                 Assignment.status == "active").limit(1)) is not None


def require_patient_access(db: Session, user: CurrentUser, patient_id: UUID, write: bool = False) -> None:
    if user.role == "patient" and user.id == patient_id:
        return
    if user.role == "doctor" and not write and is_assigned(db, user.id, patient_id):
        return
    raise _forbidden()


def require_assigned_doctor(db: Session, user: CurrentUser, patient_id: UUID) -> None:
    if user.role == "doctor" and is_assigned(db, user.id, patient_id):
        return
    raise _forbidden()


def require_role(user: CurrentUser, *roles: str) -> None:
    if user.role not in roles:
        raise ApiError(403, "forbidden", "Your role cannot use this endpoint.")
