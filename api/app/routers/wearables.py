"""Devices and wearable samples (read only). Optional data: never used by rules, alerts or emergency guidance.

Access (permissions.py): the patient for their own id; an actively assigned doctor. Admin: 403.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from ..auth import CurrentUser, current_user
from ..db import require_session
from ..errors import AUTH_RESPONSES
from ..permissions import require_patient_access
from ..schemas import DeviceOut, WearableMetric, WearableSampleOut
from ..services import wearables

router = APIRouter(tags=["wearables"], responses=AUTH_RESPONSES, dependencies=[Depends(current_user)])


@router.get("/patients/{patient_id}/devices", response_model=list[DeviceOut],
            summary="Registered devices (oldest first); simulator devices are flagged is_simulated")
def list_devices(patient_id: UUID, user: CurrentUser = Depends(current_user),
                 db: Session = Depends(require_session)):
    require_patient_access(db, user, patient_id)
    return wearables.list_devices(db, patient_id)


@router.get("/patients/{patient_id}/wearable-samples", response_model=list[WearableSampleOut],
            summary="Wearable samples, newest first; optional, advisory, never used for alerts or guidance")
def list_wearable_samples(patient_id: UUID,
                          metric: WearableMetric | None = None,
                          device_id: UUID | None = None,
                          from_: AwareDatetime | None = Query(None, alias="from"),
                          to: AwareDatetime | None = None,
                          limit: int = Query(500, ge=1, le=5000),
                          user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    require_patient_access(db, user, patient_id)
    return wearables.list_samples(db, patient_id, metric, device_id, from_, to, limit)
