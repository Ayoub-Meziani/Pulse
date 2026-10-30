"""Patient profile (emergency-card fields), trusted contacts and care plan."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from ..auth import CurrentUser, current_user
from ..db import require_session
from ..errors import AUTH_RESPONSES
from ..permissions import require_assigned_doctor, require_patient_access
from ..schemas import (CarePlanIn, CarePlanOut, ProfileIn, ProfileOut, TrustedContactIn,
                       TrustedContactOut, TrustedContactPatch)
from ..services import patient_data as svc

router = APIRouter(tags=["profile"], responses=AUTH_RESPONSES, dependencies=[Depends(current_user)])
Db = Depends(require_session)
User = Depends(current_user)


def _now(request: Request):
    return request.app.state.clock()


@router.get("/patients/{patient_id}/profile", response_model=ProfileOut)
def get_profile(patient_id: UUID, request: Request, user: CurrentUser = User, db: Session = Db):
    require_patient_access(db, user, patient_id)
    return svc.get_profile(db, patient_id, svc.local_today(db, patient_id, _now(request)))


@router.put("/patients/{patient_id}/profile", response_model=ProfileOut, summary="Patient only")
def put_profile(patient_id: UUID, body: ProfileIn, request: Request, user: CurrentUser = User, db: Session = Db):
    require_patient_access(db, user, patient_id, write=True)
    return svc.put_profile(db, user, body, svc.local_today(db, patient_id, _now(request)))


@router.get("/patients/{patient_id}/trusted-contacts", response_model=list[TrustedContactOut])
def list_contacts(patient_id: UUID, user: CurrentUser = User, db: Session = Db):
    require_patient_access(db, user, patient_id)
    return svc.list_contacts(db, patient_id)


@router.post("/patients/{patient_id}/trusted-contacts", response_model=TrustedContactOut, status_code=201,
             summary="Patient only; consented_at is set by the server")
def create_contact(patient_id: UUID, body: TrustedContactIn, request: Request, user: CurrentUser = User,
                   db: Session = Db):
    require_patient_access(db, user, patient_id, write=True)
    return svc.add_contact(db, user, body, _now(request))


@router.patch("/trusted-contacts/{contact_id}", response_model=TrustedContactOut,
              summary="Patient only; a new phone number needs a new contact with consent (422)")
def patch_contact(contact_id: UUID, body: TrustedContactPatch, user: CurrentUser = User, db: Session = Db):
    return svc.patch_contact(db, user, contact_id, body)


@router.delete("/trusted-contacts/{contact_id}", status_code=204, summary="Patient only")
def delete_contact(contact_id: UUID, user: CurrentUser = User, db: Session = Db):
    svc.delete_contact(db, user, contact_id)
    return Response(status_code=204)


@router.get("/patients/{patient_id}/care-plan", response_model=CarePlanOut,
            summary="Active care plan, or the default target 140/90 (is_default=true)")
def get_care_plan(patient_id: UUID, user: CurrentUser = User, db: Session = Db):
    require_patient_access(db, user, patient_id)
    return svc.get_care_plan(db, patient_id)


@router.put("/patients/{patient_id}/care-plan", response_model=CarePlanOut,
            summary="Assigned doctor: new active plan, previous one superseded (deferrable)")
def put_care_plan(patient_id: UUID, body: CarePlanIn, request: Request, user: CurrentUser = User, db: Session = Db):
    require_assigned_doctor(db, user, patient_id)
    return svc.put_care_plan(db, user, patient_id, body, svc.local_today(db, patient_id, _now(request)))
