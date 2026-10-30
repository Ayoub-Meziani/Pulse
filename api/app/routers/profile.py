"""Patient profile (emergency-card fields), trusted contacts and care plan."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from ..auth import require_token
from ..errors import AUTH_RESPONSES, not_implemented
from ..schemas import (CarePlanIn, CarePlanOut, ProfileIn, ProfileOut, TrustedContactIn,
                       TrustedContactOut, TrustedContactPatch)

router = APIRouter(tags=["profile"], responses=AUTH_RESPONSES, dependencies=[Depends(require_token)])


@router.get("/patients/{patient_id}/profile", response_model=ProfileOut)
def get_profile(patient_id: UUID):
    not_implemented()


@router.put("/patients/{patient_id}/profile", response_model=ProfileOut, summary="Patient only")
def put_profile(patient_id: UUID, body: ProfileIn):
    not_implemented()


@router.get("/patients/{patient_id}/trusted-contacts", response_model=list[TrustedContactOut])
def list_contacts(patient_id: UUID):
    not_implemented()


@router.post("/patients/{patient_id}/trusted-contacts", response_model=TrustedContactOut, status_code=201,
             summary="Patient only; consented_at is set by the server")
def create_contact(patient_id: UUID, body: TrustedContactIn):
    not_implemented()


@router.patch("/trusted-contacts/{contact_id}", response_model=TrustedContactOut, summary="Patient only")
def patch_contact(contact_id: UUID, body: TrustedContactPatch):
    not_implemented()


@router.delete("/trusted-contacts/{contact_id}", status_code=204, summary="Patient only")
def delete_contact(contact_id: UUID):
    not_implemented()


@router.get("/patients/{patient_id}/care-plan", response_model=CarePlanOut,
            summary="Active care plan, or the default target 140/90 (is_default=true)")
def get_care_plan(patient_id: UUID):
    not_implemented()


@router.put("/patients/{patient_id}/care-plan", response_model=CarePlanOut,
            summary="Assigned doctor: new active plan, previous one superseded (deferrable)")
def put_care_plan(patient_id: UUID, body: CarePlanIn):
    not_implemented()
