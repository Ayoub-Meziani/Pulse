from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..auth import CurrentUser, current_user
from ..db import require_session
from ..errors import AUTH_RESPONSES
from ..models import Alert
from ..permissions import is_assigned, require_patient_access
from ..schemas import AlertBrief, AlertDetail, AlertEventOut, AlertOut, MeasurementOut, TransitionIn
from ..services import alerts as alert_service

router = APIRouter(tags=["alerts"], responses=AUTH_RESPONSES, dependencies=[Depends(current_user)])


def alert_brief(a: Alert | None) -> AlertBrief | None:
    if a is None:
        return None
    return AlertBrief(id=a.id, level=alert_service.alert_level(a), rule_id=a.rule_code, status=a.status,
                      persistent=a.persistent)


def alert_out(a: Alert) -> AlertOut:
    return AlertOut(id=a.id, patient_id=a.patient_id, level=alert_service.alert_level(a), rule_id=a.rule_code,
                    status=a.status, persistent=a.persistent, reason=a.reason,
                    next_step=a.actions[0] if a.actions else "", measurement_id=a.measurement_id,
                    symptom_report_id=a.symptom_report_id, created_at=a.created_at,
                    acknowledged_at=a.acknowledged_at, reviewed_at=a.reviewed_at, resolved_at=a.resolved_at,
                    resolution_note=a.resolution_note, dismissed_at=a.dismissed_at,
                    dismissed_by_role=alert_service.dismissed_by_role(a), dismissal_reason=a.dismissal_reason,
                    dismissal_note=a.dismissal_note)


@router.get("/alerts/{alert_id}", response_model=AlertDetail, summary="Alert with the readings attached to it")
def get_alert(alert_id: UUID, user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    alert = alert_service.get_alert(db, alert_id)
    require_patient_access(db, user, alert.patient_id)
    readings = [MeasurementOut.model_validate(m) for m in alert_service.episode_measurements(db, alert)]
    return AlertDetail(**alert_out(alert).model_dump(), measurements=readings)


@router.get("/alerts/{alert_id}/events", response_model=list[AlertEventOut],
            summary="Read-only timeline of the alert from the audit log, oldest first (patient or assigned doctor)")
def alert_events(alert_id: UUID, user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    alert = alert_service.get_alert(db, alert_id)
    require_patient_access(db, user, alert.patient_id)
    return [AlertEventOut(**e) for e in alert_service.events(db, alert)]


@router.post("/alerts/{alert_id}/transition", response_model=AlertOut,
             summary="open→acknowledged (patient or doctor); open/acknowledged→dismissed, notice only, reason "
                     "required (patient or doctor); →reviewed, reviewed→resolved (doctor). Others: 409")
def transition(alert_id: UUID, body: TransitionIn, request: Request,
               user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    alert = alert_service.get_alert(db, alert_id)
    require_patient_access(db, user, alert.patient_id)  # 403 for anyone who cannot even read it
    doctor = user.role == "doctor" and is_assigned(db, user.id, alert.patient_id)
    alert_service.transition(db, alert, user, body.to, body.note, request.app.state.clock(), doctor,
                             reason=body.reason)
    db.commit()
    return alert_out(alert)
