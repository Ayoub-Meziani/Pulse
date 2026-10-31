"""Emergency escalation (migration M11): status, timeline, patient answer, cancel/resolve, doctor receipts and
acknowledgements, and the in-app notification inbox.

Statuses are honest: 'sent' is not 'read', 'acknowledged' means a person pressed the button, and
emergency services are never notified by PULSE (no official channel exists).
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import CurrentUser, current_user
from ..db import require_session
from ..errors import AUTH_RESPONSES, ApiError
from ..models import EmergencyEvent, EscalationStep, Notification
from ..permissions import is_assigned, require_patient_access, require_role
from ..schemas import (DoctorEscalationOut, EscalationCancelIn, EscalationOut, EscalationResolveIn,
                       EscalationStepOut, EscalationTimelineOut, NotificationOut, PatientResponseIn)
from ..services import emergency_events as events, escalation

router = APIRouter(tags=["escalation"], responses=AUTH_RESPONSES, dependencies=[Depends(current_user)])


def step_out(s: EscalationStep, labels: dict) -> EscalationStepOut:
    return EscalationStepOut(id=s.id, stage=s.stage, target_kind=s.target_kind,
                             target_label=labels.get(s.target_id) if s.target_id else None, channel=s.channel,
                             status=s.status, skip_reason=s.skip_reason, sequence=s.sequence, due_at=s.due_at,
                             sent_at=s.sent_at, delivered_at=s.delivered_at, acknowledged_at=s.acknowledged_at,
                             ack_deadline=s.ack_deadline, attempts=s.attempts)


def escalation_out(db: Session, event: EmergencyEvent, enabled: bool) -> EscalationOut:
    steps = escalation.steps_of(db, event.id)
    labels = escalation.target_labels(db, steps)
    return EscalationOut(
        event_id=event.id, enabled=enabled, eligible=event.escalation_eligible, severity=event.severity,
        evidence_provenance=event.evidence_provenance, status=event.escalation_status, policy=event.escalation_policy,
        patient_response=event.patient_response, patient_responded_at=event.patient_responded_at,
        cancelled_at=event.cancelled_at, cancel_reason=event.cancel_reason, resolved_at=event.resolved_at,
        resolution_outcome=event.resolution_outcome, steps=[step_out(s, labels) for s in steps])


def _readable(db: Session, user: CurrentUser, event_id: UUID) -> EmergencyEvent:
    event = events.get_event(db, event_id)
    require_patient_access(db, user, event.patient_id)
    return event


def _own(db: Session, user: CurrentUser, event_id: UUID) -> EmergencyEvent:
    event = events.get_event(db, event_id)
    require_patient_access(db, user, event.patient_id, write=True)  # only the patient
    return events.get_event(db, event_id, lock=True)


def _enabled(request: Request) -> bool:
    return request.app.state.settings.escalation_enabled


@router.get("/emergency-events/{event_id}/escalation", response_model=EscalationOut,
            summary="Who PULSE tried to reach and what actually happened (patient or assigned doctor)")
def get_escalation(event_id: UUID, request: Request, user: CurrentUser = Depends(current_user),
                   db: Session = Depends(require_session)):
    return escalation_out(db, _readable(db, user, event_id), _enabled(request))


@router.get("/emergency-events/{event_id}/timeline", response_model=list[EscalationTimelineOut],
            summary="Append-only escalation timeline, oldest first (patient or assigned doctor)")
def get_timeline(event_id: UUID, user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    _readable(db, user, event_id)
    return [EscalationTimelineOut(at=t.at, kind=t.kind, actor_kind=t.actor_kind, step_id=t.step_id, details=t.details)
            for t in escalation.timeline_of(db, event_id)]


@router.post("/emergency-events/{event_id}/patient-response", response_model=EscalationOut,
             summary="Patient answers the alarm: ok, or need_help (notifies without waiting for the cancel delay)")
def patient_response(event_id: UUID, body: PatientResponseIn, request: Request,
                     user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    event = _own(db, user, event_id)
    escalation.patient_response(db, event, body.response, request.app.state.clock())
    return escalation_out(db, event, _enabled(request))


@router.post("/emergency-events/{event_id}/cancel", response_model=EscalationOut,
             summary="Patient: false alarm. Pending steps stop; doctors already shown it get an update")
def cancel(event_id: UUID, body: EscalationCancelIn, request: Request,
           user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    event = _own(db, user, event_id)
    escalation.cancel(db, event, user, body.reason, request.app.state.clock())
    return escalation_out(db, event, _enabled(request))


@router.post("/emergency-events/{event_id}/resolve", response_model=EscalationOut,
             summary="Patient or assigned doctor: close the escalation with how it ended")
def resolve(event_id: UUID, body: EscalationResolveIn, request: Request,
            user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    event = _readable(db, user, event_id)
    if user.id != event.patient_id and not (user.role == "doctor" and is_assigned(db, user.id, event.patient_id)):
        raise ApiError(403, "forbidden", "Only the patient or the assigned doctor can resolve.")
    event = events.get_event(db, event_id, lock=True)
    escalation.resolve(db, event, user, body.outcome, request.app.state.clock())
    return escalation_out(db, event, _enabled(request))


@router.get("/doctor/escalations", response_model=list[DoctorEscalationOut],
            summary="Doctor: active escalations of assigned patients that were sent to me, newest first")
def doctor_escalations(user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    require_role(user, "doctor")
    return [DoctorEscalationOut(event_id=e.id, patient_id=e.patient_id, patient_name=name, severity=e.severity,
                                status=e.escalation_status, trigger_reason=e.trigger_reason, started_at=e.started_at,
                                step_id=s.id, step_status=s.status, ack_deadline=s.ack_deadline,
                                location_shared=e.location_lat is not None)
            for e, s, name in escalation.doctor_active(db, user.id)]


@router.post("/escalation-steps/{step_id}/delivered", response_model=EscalationStepOut,
             summary="Target doctor's app: the escalation was displayed (delivery receipt). Repeat-safe")
def step_delivered(step_id: UUID, request: Request, user: CurrentUser = Depends(current_user),
                   db: Session = Depends(require_session)):
    require_role(user, "doctor")
    s = escalation.mark_delivered(db, step_id, user, request.app.state.clock())
    return step_out(s, escalation.target_labels(db, [s]))


@router.post("/escalation-steps/{step_id}/acknowledge", response_model=EscalationStepOut,
             summary="Target doctor: 'J'ai vu / je m'en occupe'. Seen, not a promise that help has arrived")
def step_acknowledge(step_id: UUID, request: Request, user: CurrentUser = Depends(current_user),
                     db: Session = Depends(require_session)):
    require_role(user, "doctor")
    s = escalation.acknowledge(db, step_id, user, request.app.state.clock())
    return step_out(s, escalation.target_labels(db, [s]))


@router.get("/me/notifications", response_model=list[NotificationOut], summary="My in-app notifications, newest first")
def my_notifications(unread: bool = False, limit: int = Query(50, ge=1, le=200),
                     user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    q = select(Notification).where(Notification.user_id == user.id)
    if unread:
        q = q.where(Notification.read_at.is_(None))
    return [NotificationOut.model_validate(n, from_attributes=True)
            for n in db.scalars(q.order_by(Notification.created_at.desc()).limit(limit))]


@router.post("/notifications/{notification_id}/read", response_model=NotificationOut,
             summary="Mark one of my notifications as read. Repeat-safe")
def read_notification(notification_id: UUID, request: Request, user: CurrentUser = Depends(current_user),
                      db: Session = Depends(require_session)):
    n = db.get(Notification, notification_id)
    if n is None or n.user_id != user.id:
        raise ApiError(404, "not_found", "Notification not found.")
    if n.read_at is None:
        n.read_at = request.app.state.clock()
        db.commit()
    return NotificationOut.model_validate(n, from_attributes=True)
