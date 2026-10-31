"""Emergency escalation (migration M11, docs/EMERGENCY_ESCALATION_DESIGN.md).

An escalation extends an emergency event: who PULSE tries to reach, through which channel, and what
actually happened. It never replaces the patient's own call to 14, which the emergency screen shows first.

Honesty rules enforced here:
- 'sent' means the notification was handed to a channel; 'delivered' only comes from a receipt (for the
  in-app channel: the target's app reported that it displayed it); 'acknowledged' only from a person.
- Trusted contacts, facilities and emergency services have no automated channel yet. Their steps are
  recorded as 'skipped' with the reason, so nobody is told they were notified.
- Only deterministic evidence starts an escalation: the patient's own Emergency button, a red-flag symptom
  report (R-EMG-1), or a severe reading entered by the patient or a device. Simulated, imported or mixed
  readings, ML estimates and wearable flags never do (database CHECK emergency_eligible_evidence too).
- Real escalation stays off (PULSE_ESCALATION_ENABLED) until the triggers, delays and wording are
  clinically approved. When off, the event records why nothing was escalated.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import vocab
from ..analysis.rules import RED_FLAG_SYMPTOMS
from ..auth import CurrentUser
from ..errors import ApiError
from ..models import (Alert, AlertMeasurement, Assignment, CareFacility, DoctorFacilityAffiliation, EmergencyEvent,
                      EscalationStep, EscalationTimeline, Measurement, Notification, Profile, SymptomReport,
                      TrustedContact)

TERMINAL = ("resolved", "cancelled")
OPEN_STEP = ("scheduled", "sending", "sent", "delivered")
SYMPTOM_WINDOW = timedelta(minutes=30)
STALE_AFTER = timedelta(minutes=30)  # an episode synced later than this is recorded, never escalated as live
ESCALATING_SOURCES = ("manual", "device")  # evidence provenance values that may escalate


@dataclass(frozen=True)
class Policy:
    """Delays are placeholders until clinical review (design §3). The version is stored on every episode."""
    name: str = "emergency-v1"
    cancel_grace_s: int = 30          # the patient can cancel a false alarm before anyone is notified
    patient_alarm_s: int = 60         # no answer to the alarm -> recorded as unresponsive
    doctor_ack_s: int = 300           # emergency: doctor acknowledgement window
    urgent_doctor_ack_s: int = 1800   # urgent review (severe reading, no red flag)
    patient_reminder_ack_s: int = 300
    retry_backoff_s: tuple[int, ...] = (10, 30, 90)
    max_attempts: int = 3


POLICY = Policy()


def _invalid(field: str, code: str, message: str, status: int = 422, error: str = "validation_failed") -> ApiError:
    return ApiError(status, error, message, [{"field": field, "code": code, "message": message}])


def note(db: Session, event: EmergencyEvent, kind: str, actor_kind: str = "system", actor_id: UUID | None = None,
         step: EscalationStep | None = None, **details) -> None:
    db.add(EscalationTimeline(event_id=event.id, patient_id=event.patient_id, step_id=step.id if step else None,
                              kind=kind, actor_kind=actor_kind, actor_id=actor_id, details=details))


# ---------------------------------------------------------------- eligibility (deterministic evidence only)
def _kind(source: str, provenance: str) -> str:
    if source == "simulated" or provenance == "simulated":
        return "simulated"
    if provenance == "estimated":
        return "estimated"
    if source == "csv_import":
        return "imported"
    return {"manual": "manual", "device_sync": "device"}.get(source, "mixed")


def _reading_provenance(db: Session, alert: Alert) -> str:
    """One label for every reading behind the alert episode. Any non-measured reading disqualifies it."""
    attached = select(AlertMeasurement.measurement_id).where(AlertMeasurement.alert_id == alert.id)
    kinds = {_kind(s, p) for s, p in db.execute(select(Measurement.source, Measurement.provenance).where(
        Measurement.patient_id == alert.patient_id,
        (Measurement.id == alert.measurement_id) | Measurement.id.in_(attached)))}
    if not kinds:
        return "none"
    if kinds <= set(ESCALATING_SOURCES):
        return "manual" if kinds == {"manual"} else "device"
    return kinds.pop() if len(kinds) == 1 else "mixed"


def evaluate(db: Session, event: EmergencyEvent) -> tuple[str | None, str]:
    """(severity or None, evidence provenance)."""
    if event.trigger_reason == "manual":
        return "emergency", "patient_reported"  # the patient's own decision is always enough
    alert = None
    if event.alert_id is not None:
        alert = db.scalar(select(Alert).where(Alert.id == event.alert_id, Alert.patient_id == event.patient_id))
    level = vocab.ALERT_CLASS_TO_LEVEL.get(alert.alert_class) if alert else None
    if event.trigger_reason == "symptom":
        if level == "emergency" and alert.symptom_report_id is not None:
            return "emergency", "patient_reported"
        recent = db.scalars(select(SymptomReport.symptoms).where(
            SymptomReport.patient_id == event.patient_id,
            SymptomReport.reported_at >= event.started_at - SYMPTOM_WINDOW)).all()
        if any(set(s) & RED_FLAG_SYMPTOMS for s in recent):
            return "emergency", "patient_reported"
        return None, "none"
    # severe_reading
    if alert is None or level not in ("severe", "emergency"):
        return None, "none"
    provenance = _reading_provenance(db, alert)
    if provenance not in ESCALATING_SOURCES:
        return None, provenance
    return ("emergency" if level == "emergency" else "urgent"), provenance


# ---------------------------------------------------------------- start
def _doctors(db: Session, patient_id: UUID) -> list[UUID]:
    return list(db.scalars(select(Assignment.doctor_id).where(Assignment.patient_id == patient_id,
                                                              Assignment.status == "active")
                           .order_by(Assignment.id)))


def _step(event: EmergencyEvent, stage: str, target_kind: str, target_id: UUID | None, channel: str, due: datetime,
          *, sequence: int = 1, ack_s: int | None = None, skip: str | None = None) -> EscalationStep:
    key = f"{event.id}:{stage}:{target_id or target_kind}:{channel}:{sequence}"
    return EscalationStep(event_id=event.id, patient_id=event.patient_id, stage=stage, target_kind=target_kind,
                          target_id=target_id, channel=channel, sequence=sequence, due_at=due,
                          ack_window_seconds=ack_s, max_attempts=POLICY.max_attempts, idempotency_key=key,
                          status="skipped" if skip else "scheduled", skip_reason=skip)


def start(db: Session, event: EmergencyEvent, enabled: bool, now: datetime) -> EmergencyEvent:
    """Called once, right after the event is created. Commits."""
    severity, provenance = evaluate(db, event)
    event.severity, event.evidence_provenance = severity, provenance
    if severity is None:
        note(db, event, "not_eligible", provenance=provenance)
        db.commit()
        return event
    if now - event.started_at > STALE_AFTER:  # queued offline: notifying now would describe the past as live
        note(db, event, "not_eligible", reason="too_old", severity=severity)
        db.commit()
        return event
    if not enabled:
        note(db, event, "escalation_disabled", severity=severity)
        db.commit()
        return event
    active = db.scalar(select(EmergencyEvent).where(
        EmergencyEvent.patient_id == event.patient_id, EmergencyEvent.id != event.id,
        EmergencyEvent.escalation_eligible.is_(True), EmergencyEvent.escalation_status.not_in(TERMINAL)))
    if active is not None:
        return _merge(db, event, active)
    event.escalation_eligible, event.escalation_status, event.escalation_policy = True, "created", POLICY.name
    try:
        db.flush()  # the partial unique index decides a race between two new episodes
    except IntegrityError:
        db.rollback()
        event = db.get(EmergencyEvent, event.id)
        active = db.scalar(select(EmergencyEvent).where(
            EmergencyEvent.patient_id == event.patient_id, EmergencyEvent.escalation_eligible.is_(True),
            EmergencyEvent.escalation_status.not_in(TERMINAL)))
        event.severity, event.evidence_provenance = severity, provenance
        return _merge(db, event, active)
    note(db, event, "escalation_started", severity=severity, policy=POLICY.name)
    grace = now + timedelta(seconds=POLICY.cancel_grace_s)
    doctors = _doctors(db, event.patient_id)
    ack = POLICY.doctor_ack_s if severity == "emergency" else POLICY.urgent_doctor_ack_s
    for doctor in doctors:
        db.add(_step(event, "doctor", "doctor", doctor, "in_app", grace, ack_s=ack))
    if not doctors:
        note(db, event, "no_assigned_doctor")
    if severity == "emergency":
        contacts = db.scalars(select(TrustedContact).where(TrustedContact.patient_id == event.patient_id,
                                                           TrustedContact.active.is_(True))
                              .order_by(TrustedContact.priority, TrustedContact.name)).all()
        for c in contacts:  # no SMS or voice provider yet: recorded honestly, the patient calls them
            db.add(_step(event, "contact", "contact", c.id, "none", now, skip="no_channel"))
        db.add(_step(event, "emergency_services", "emergency_services", None, "none", now,
                     skip="no_official_channel"))
    db.commit()
    return event


def _merge(db: Session, event: EmergencyEvent, active: EmergencyEvent) -> EmergencyEvent:
    """A second trigger while an escalation is active: recorded on both, no second ladder."""
    note(db, event, "merged_into_active", active_event_id=str(active.id))
    note(db, active, "retriggered", event_id=str(event.id), trigger_reason=event.trigger_reason)
    if event.severity == "emergency" and active.severity == "urgent":
        note(db, active, "severity_raise_requested", note="A new emergency trigger arrived during an urgent review.")
    db.commit()
    return event


# ---------------------------------------------------------------- derived status
def refresh_status(db: Session, event: EmergencyEvent) -> None:
    if not event.escalation_eligible or event.escalation_status in TERMINAL:
        return
    statuses = set(db.scalars(select(EscalationStep.status).where(EscalationStep.event_id == event.id)))
    new = ("acknowledged" if "acknowledged" in statuses else
           "escalated" if statuses & {"expired", "failed"} else
           "delivered" if "delivered" in statuses else
           "notification_attempted" if "sent" in statuses else "created")
    if new != event.escalation_status:
        note(db, event, "status_changed", from_status=event.escalation_status, to_status=new)
        event.escalation_status = new


# ---------------------------------------------------------------- patient and doctor actions (API)
def _require_active(event: EmergencyEvent) -> None:
    if not event.escalation_eligible:
        raise ApiError(409, "no_escalation", "This event has no escalation.")
    if event.escalation_status in TERMINAL:
        raise ApiError(409, "invalid_transition", f"The escalation is already {event.escalation_status}.",
                       {"from": event.escalation_status})


def patient_response(db: Session, event: EmergencyEvent, response: str, now: datetime) -> EmergencyEvent:
    _require_active(event)
    if event.patient_response == response:
        return event  # repeat: unchanged
    event.patient_response, event.patient_responded_at = response, now
    note(db, event, "patient_response", "patient", event.patient_id, response=response)
    if response == "need_help":  # skip the cancel grace: notify now
        for s in db.scalars(select(EscalationStep).where(EscalationStep.event_id == event.id,
                                                         EscalationStep.status == "scheduled",
                                                         EscalationStep.due_at > now)):
            s.due_at = now
    db.commit()
    return event


def _close_steps(db: Session, event: EmergencyEvent) -> None:
    for s in db.scalars(select(EscalationStep).where(EscalationStep.event_id == event.id,
                                                     EscalationStep.status.in_(OPEN_STEP + ("expired",)))):
        s.status = "cancelled"


def cancel(db: Session, event: EmergencyEvent, user: CurrentUser, reason: str, now: datetime) -> EmergencyEvent:
    if event.escalation_status == "cancelled":
        return event
    _require_active(event)
    _close_steps(db, event)
    event.escalation_status, event.cancelled_at, event.cancel_reason = "cancelled", now, reason
    note(db, event, "cancelled", "patient", user.id, reason=reason)
    _notify_targets(db, event, now)
    db.commit()
    return event


def resolve(db: Session, event: EmergencyEvent, user: CurrentUser, outcome: str, now: datetime) -> EmergencyEvent:
    if event.escalation_status == "resolved":
        return event
    _require_active(event)
    outcome = outcome.strip()
    if not outcome:
        raise _invalid("outcome", "required", "Describe how the episode ended.")
    _close_steps(db, event)
    event.escalation_status, event.resolved_at, event.resolution_outcome = "resolved", now, outcome
    actor = "patient" if user.id == event.patient_id else "doctor"
    note(db, event, "resolved", actor, user.id, outcome=outcome)
    _notify_targets(db, event, now)
    db.commit()
    return event


def _notify_targets(db: Session, event: EmergencyEvent, now: datetime) -> None:
    """Doctors who were shown the escalation get an update (in-app), so nobody acts on a closed episode."""
    shown = db.scalars(select(EscalationStep.target_id).where(
        EscalationStep.event_id == event.id, EscalationStep.target_kind == "doctor",
        EscalationStep.sent_at.is_not(None)).distinct())
    for doctor in shown:
        db.add(Notification(user_id=doctor, patient_id=event.patient_id, kind="escalation_update",
                            event_id=event.id, urgent=False))


def _own_doctor_step(db: Session, step_id: UUID, user: CurrentUser) -> tuple[EscalationStep, EmergencyEvent]:
    step = db.get(EscalationStep, step_id, with_for_update=True)
    if step is None or step.target_kind != "doctor" or step.target_id != user.id:
        raise ApiError(404, "not_found", "Escalation step not found.")
    if not db.scalar(select(func.count()).select_from(Assignment).where(
            Assignment.doctor_id == user.id, Assignment.patient_id == step.patient_id, Assignment.status == "active")):
        raise ApiError(403, "forbidden", "You are no longer assigned to this patient.")
    return step, db.get(EmergencyEvent, step.event_id)


def mark_delivered(db: Session, step_id: UUID, user: CurrentUser, now: datetime) -> EscalationStep:
    step, event = _own_doctor_step(db, step_id, user)
    if step.status == "sent":
        step.status, step.delivered_at = "delivered", now
        note(db, event, "step_delivered", "doctor", user.id, step)
        refresh_status(db, event)
    db.commit()
    return step


def acknowledge(db: Session, step_id: UUID, user: CurrentUser, now: datetime) -> EscalationStep:
    step, event = _own_doctor_step(db, step_id, user)
    if step.status == "acknowledged":
        return step
    if step.status not in ("sent", "delivered", "expired") or event.escalation_status in TERMINAL:
        raise ApiError(409, "invalid_transition", f"This step is {step.status}.",
                       {"from": step.status, "escalation_status": event.escalation_status})
    step.status, step.acknowledged_at, step.acknowledged_by = "acknowledged", now, user.id
    step.delivered_at = step.delivered_at or now
    note(db, event, "step_acknowledged", "doctor", user.id, step)
    db.add(Notification(user_id=event.patient_id, patient_id=event.patient_id, kind="escalation_update",
                        event_id=event.id, urgent=False))
    refresh_status(db, event)
    db.commit()
    return step


# ---------------------------------------------------------------- worker (one pass; app/escalation_worker.py loops)
class RetryableError(Exception):
    pass


class PermanentError(Exception):
    pass


class InAppChannel:
    """The target sees it in PULSE (doctor banner / patient screen). 'sent' = the row exists."""
    name = "in_app"

    def send(self, db: Session, step: EscalationStep, now: datetime) -> str:
        user = step.target_id if step.target_kind in ("doctor", "patient") else None
        if user is None:
            raise PermanentError("in_app needs a user target")
        existing = db.scalar(select(Notification.id).where(Notification.step_id == step.id))
        if existing is not None:  # a retry after a crash between send and record
            return str(existing)
        n = Notification(user_id=user, patient_id=step.patient_id, kind="escalation", event_id=step.event_id,
                         step_id=step.id, urgent=True)
        db.add(n)
        db.flush()
        return str(n.id)


CHANNELS = {"in_app": InAppChannel()}


def run_once(db: Session, now: datetime, channels: dict | None = None, batch: int = 50) -> int:
    """Send due steps, expire unacknowledged ones, record unanswered alarms. Returns the number of changes.
    Safe to run in several workers at once (FOR UPDATE SKIP LOCKED)."""
    channels = CHANNELS if channels is None else channels
    changed, touched = 0, set()
    due = db.scalars(select(EscalationStep).where(EscalationStep.status == "scheduled", EscalationStep.due_at <= now)
                     .order_by(EscalationStep.due_at).limit(batch).with_for_update(skip_locked=True)).all()
    for step in due:
        event = db.get(EmergencyEvent, step.event_id)
        touched.add(event.id)
        changed += 1
        if event.escalation_status in TERMINAL:
            step.status = "cancelled"
            continue
        _send(db, event, step, channels, now)
    expired = db.scalars(select(EscalationStep).where(EscalationStep.status.in_(("sent", "delivered")),
                                                      EscalationStep.ack_deadline <= now)
                         .limit(batch).with_for_update(skip_locked=True)).all()
    for step in expired:
        event = db.get(EmergencyEvent, step.event_id)
        touched.add(event.id)
        changed += 1
        step.status = "expired"
        note(db, event, "step_expired", step=step)
        _after_failure(db, event, step, now)
    changed += _unanswered_alarms(db, now, touched)
    for event_id in touched:
        refresh_status(db, db.get(EmergencyEvent, event_id))
    db.commit()
    return changed


def _send(db: Session, event: EmergencyEvent, step: EscalationStep, channels: dict, now: datetime) -> None:
    channel = channels.get(step.channel)
    step.attempts += 1
    try:
        if channel is None:
            raise PermanentError(f"no channel {step.channel!r}")
        step.provider_message_id = channel.send(db, step, now)
    except RetryableError as exc:
        step.last_error = str(exc)[:500]
        if step.attempts < step.max_attempts:
            backoff = POLICY.retry_backoff_s[min(step.attempts, len(POLICY.retry_backoff_s)) - 1]
            step.due_at = now + timedelta(seconds=backoff)
            note(db, event, "step_retry", step=step, attempt=step.attempts, error=step.last_error)
            return
        step.status = "failed"
        note(db, event, "step_failed", step=step, error=step.last_error)
        _after_failure(db, event, step, now)
        return
    except PermanentError as exc:
        step.status, step.last_error = "failed", str(exc)[:500]
        note(db, event, "step_failed", step=step, error=step.last_error)
        _after_failure(db, event, step, now)
        return
    step.status, step.sent_at, step.provider = "sent", now, getattr(channel, "name", step.channel)
    if step.ack_window_seconds:
        step.ack_deadline = now + timedelta(seconds=step.ack_window_seconds)
    note(db, event, "step_sent", step=step, channel=step.channel)


def _after_failure(db: Session, event: EmergencyEvent, step: EscalationStep, now: datetime) -> None:
    """Next stage of the ladder once nobody acknowledged (design §3). Each stage is created at most once."""
    if event.escalation_status in TERMINAL:
        return
    if step.stage == "doctor":
        others = db.scalar(select(func.count()).select_from(EscalationStep).where(
            EscalationStep.event_id == event.id, EscalationStep.stage == "doctor",
            EscalationStep.status.in_(OPEN_STEP + ("acknowledged",))))
        if others:
            return  # another doctor may still answer
        if event.severity == "urgent":
            for doctor in _doctors(db, event.patient_id):
                _add_once(db, _step(event, "doctor_reminder", "doctor", doctor, "in_app", now, sequence=2,
                                    ack_s=POLICY.urgent_doctor_ack_s))
            return
        for facility in _facilities(db, event.patient_id):
            skip = "no_channel" if facility.agreement_status == "active" else "no_agreement"
            _add_once(db, _step(event, "facility", "facility", facility.id, "none", now, skip=skip))
        _add_once(db, _step(event, "patient_reminder", "patient", event.patient_id, "in_app", now,
                            ack_s=POLICY.patient_reminder_ack_s))
        note(db, event, "escalated", reason="no doctor acknowledged", next="patient_reminder")


def _add_once(db: Session, step: EscalationStep) -> None:
    if db.scalar(select(EscalationStep.id).where(EscalationStep.idempotency_key == step.idempotency_key)) is None:
        db.add(step)
        db.flush()


def _facilities(db: Session, patient_id: UUID) -> list[CareFacility]:
    doctors = select(Assignment.doctor_id).where(Assignment.patient_id == patient_id, Assignment.status == "active")
    return list(db.scalars(select(CareFacility).join(
        DoctorFacilityAffiliation, DoctorFacilityAffiliation.facility_id == CareFacility.id).where(
        DoctorFacilityAffiliation.doctor_id.in_(doctors), DoctorFacilityAffiliation.active.is_(True),
        CareFacility.active.is_(True)).distinct()))


def _unanswered_alarms(db: Session, now: datetime, touched: set) -> int:
    limit = now - timedelta(seconds=POLICY.patient_alarm_s)
    recorded = select(EscalationTimeline.event_id).where(EscalationTimeline.kind == "patient_no_response")
    events = db.scalars(select(EmergencyEvent).where(
        EmergencyEvent.escalation_eligible.is_(True), EmergencyEvent.escalation_status.not_in(TERMINAL),
        EmergencyEvent.severity == "emergency", EmergencyEvent.patient_response.is_(None),
        EmergencyEvent.started_at <= limit, EmergencyEvent.id.not_in(recorded))).all()
    for e in events:
        note(db, e, "patient_no_response", seconds=POLICY.patient_alarm_s)
        touched.add(e.id)
    return len(events)


# ---------------------------------------------------------------- reads
def steps_of(db: Session, event_id: UUID) -> list[EscalationStep]:
    return list(db.scalars(select(EscalationStep).where(EscalationStep.event_id == event_id)
                           .order_by(EscalationStep.created_at, EscalationStep.stage, EscalationStep.sequence)))


def timeline_of(db: Session, event_id: UUID) -> list[EscalationTimeline]:
    return list(db.scalars(select(EscalationTimeline).where(EscalationTimeline.event_id == event_id)
                           .order_by(EscalationTimeline.at, EscalationTimeline.id)))


def target_labels(db: Session, steps: list[EscalationStep]) -> dict[UUID, str]:
    """First names only (doctor display name, contact name); never phone numbers."""
    ids = {s.target_id for s in steps if s.target_id}
    labels = {p.id: p.display_name for p in db.scalars(select(Profile).where(Profile.id.in_(ids)))} if ids else {}
    if ids:
        labels |= {c.id: c.name for c in db.scalars(select(TrustedContact).where(TrustedContact.id.in_(ids)))}
        labels |= {f.id: f.name for f in db.scalars(select(CareFacility).where(CareFacility.id.in_(ids)))}
    return labels


def doctor_active(db: Session, doctor_id: UUID) -> list[tuple[EmergencyEvent, EscalationStep, str]]:
    """Active escalations where this doctor has a step, newest first, with the patient's display name."""
    rows = db.execute(
        select(EmergencyEvent, EscalationStep, Profile.display_name)
        .join(EscalationStep, EscalationStep.event_id == EmergencyEvent.id)
        .join(Profile, Profile.id == EmergencyEvent.patient_id)
        .join(Assignment, (Assignment.patient_id == EmergencyEvent.patient_id) & (Assignment.doctor_id == doctor_id)
              & (Assignment.status == "active"))
        .where(EscalationStep.target_kind == "doctor", EscalationStep.target_id == doctor_id,
               EscalationStep.sent_at.is_not(None), EmergencyEvent.escalation_status.not_in(TERMINAL))
        .order_by(EmergencyEvent.started_at.desc(), EscalationStep.sequence.desc())).all()
    seen, out = set(), []
    for event, step, name in rows:  # latest step per event
        if event.id not in seen:
            seen.add(event.id)
            out.append((event, step, name))
    return out
