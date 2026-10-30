from uuid import UUID

from fastapi import APIRouter, Depends

from ..auth import current_user
from ..errors import AUTH_RESPONSES, not_implemented
from ..schemas import AlertDetail, AlertOut, TransitionIn

router = APIRouter(tags=["alerts"], responses=AUTH_RESPONSES, dependencies=[Depends(current_user)])


@router.get("/alerts/{alert_id}", response_model=AlertDetail, summary="Alert with the readings attached to it")
def get_alert(alert_id: UUID):
    not_implemented()


@router.post("/alerts/{alert_id}/transition", response_model=AlertOut,
             summary="open→acknowledged (patient or doctor); →reviewed, reviewed→resolved (doctor). Others: 409")
def transition(alert_id: UUID, body: TransitionIn):
    not_implemented()
