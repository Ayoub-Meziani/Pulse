from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..auth import CurrentUser, current_user
from ..db import require_session
from ..errors import AUTH_RESPONSES, ApiError
from ..models import Alert
from ..gotrue import AuthUnavailable, InvalidGrant
from ..permissions import is_assigned, require_patient_access, require_role
from ..schemas import (AlertBrief, AlertDetail, AlertOut, AlertReading, DoctorAlertOut, MeasurementOut,
                       PatientConfirmationIn, TransitionIn)
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
                    resolution_note=a.resolution_note)


@router.get("/alerts/{alert_id}", response_model=AlertDetail, summary="Alert with the readings attached to it")
def get_alert(alert_id: UUID, user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    alert = alert_service.get_alert(db, alert_id)
    require_patient_access(db, user, alert.patient_id)
    readings = [MeasurementOut.model_validate(m) for m in alert_service.episode_measurements(db, alert)]
    return AlertDetail(**alert_out(alert).model_dump(), measurements=readings)


@router.post("/alerts/{alert_id}/transition", response_model=AlertOut,
             summary="open→acknowledged (patient or doctor); →reviewed, reviewed→resolved (doctor). Others: 409")
def transition(alert_id: UUID, body: TransitionIn, request: Request,
               user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    alert = alert_service.get_alert(db, alert_id)
    require_patient_access(db, user, alert.patient_id)  # 403 for anyone who cannot even read it
    doctor = user.role == "doctor" and is_assigned(db, user.id, alert.patient_id)
    alert_service.transition(db, alert, user, body.to, body.note, request.app.state.clock(), doctor)
    db.commit()
    return alert_out(alert)


@router.post("/alerts/{alert_id}/patient-confirmation", response_model=AlertOut,
             summary="Patient: re-enter the password to acknowledge an open alert (seen; not a medical resolution)")
def patient_confirmation(alert_id: UUID, body: PatientConfirmationIn, request: Request,
                         user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    alert = alert_service.get_alert(db, alert_id)
    if user.role != "patient" or alert.patient_id != user.id:
        raise ApiError(403, "forbidden", "Only the patient can confirm their own alert.")
    if alert.status != "open":
        if alert.status == "acknowledged" and alert.acknowledged_by == user.id:
            return alert_out(alert)  # repeat: unchanged
        raise ApiError(409, "invalid_transition", f"An alert that is {alert.status} cannot be confirmed.",
                       {"from": alert.status, "to": "acknowledged"})
    gotrue = request.app.state.gotrue
    if gotrue is None:
        raise ApiError(503, "auth_unavailable", "Authentication is not configured.")
    try:
        session = gotrue.password(user.email.strip().lower(), body.password)
    except InvalidGrant:
        raise ApiError(403, "reauthentication_failed", "The password is incorrect.") from None
    except AuthUnavailable:
        raise ApiError(503, "auth_unavailable", "Authentication service is unavailable. Try again.") from None
    if session.get("user", {}).get("id") != str(user.id):
        raise ApiError(403, "reauthentication_failed", "The password is incorrect.")
    gotrue.revoke(session["access_token"])  # the check needed no new session
    alert_service.transition(db, alert, user, "acknowledged", None, request.app.state.clock(), False,
                             password_confirmed=True)
    db.commit()
    return alert_out(alert)


@router.get("/doctor/alerts", response_model=list[DoctorAlertOut],
            summary="Doctor: severe and emergency alerts of assigned patients not resolved yet, most severe first")
def doctor_alerts(user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    require_role(user, "doctor")
    out = []
    for alert, name, m in alert_service.doctor_alerts(db, user.id):
        reading = (AlertReading(systolic=m.systolic, diastolic=m.diastolic, measured_at=m.measured_at, source=m.source,
                                provenance=m.provenance) if m is not None else None)
        out.append(DoctorAlertOut(**alert_out(alert).model_dump(), patient_name=name, reading=reading))
    return out
