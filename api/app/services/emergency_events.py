"""Emergency events: the record that the emergency screen was used, and what the patient tapped.

An event is an incident record, nothing more. Actions are what the patient's phone reports was
tapped or opened (an attempt); PULSE has no call, SMS or dispatch integration, so no action ever
means that a call connected, a message was sent or delivered, or help is on the way
(confirmed is always false). Events never create, change or close alerts, and no model or
wearable sample is read here.

Only the patient writes their own events. The patient and an actively assigned doctor read them.
Location is stored only with consent given in the same request (contract: 422 consent_required).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import CurrentUser
from ..errors import ApiError
from ..models import Alert, EmergencyEvent, SymptomReport
from ..schemas import (EmergencyActionOut, EmergencyActionsIn, EmergencyEventIn, EmergencyEventOut,
                       EmergencyEventPatch, Location)

CLOCK_SKEW = timedelta(minutes=5)   # same tolerance as readings and symptom onsets
LOCATION_MAX_AGE = timedelta(minutes=15)  # an older position is not shown to anyone as "where the patient is"
MAX_ACTIONS = 500                   # per event; a real incident has a few dozen at most
REPORT_WINDOW = timedelta(hours=24)


def _invalid(field: str, code: str, message: str, status: int = 422, error: str = "validation_failed") -> ApiError:
    return ApiError(status, error, message, [{"field": field, "code": code, "message": message}])


def event_out(e: EmergencyEvent) -> EmergencyEventOut:
    actions = [EmergencyActionOut(client_action_id=a["client_action_id"], action=a["action"], at=a["at"],
                                  detail=a.get("detail")) for a in e.actions_attempted or []]
    location = Location(lat=e.location_lat, lon=e.location_lon) if e.location_lat is not None else None
    return EmergencyEventOut(id=e.id, patient_id=e.patient_id, trigger_reason=e.trigger_reason, alert_id=e.alert_id,
                             symptoms_snapshot=e.symptoms_snapshot, started_at=e.started_at, ended_at=e.ended_at,
                             actions=actions, reported_outcome=e.reported_outcome, location=location,
                             location_captured_at=e.location_captured_at if location else None,
                             location_accuracy_m=e.location_accuracy_m if location else None,
                             severity=e.severity, evidence_provenance=e.evidence_provenance,
                             escalation_status=e.escalation_status)


def get_event(db: Session, event_id: UUID, lock: bool = False) -> EmergencyEvent:
    q = select(EmergencyEvent).where(EmergencyEvent.id == event_id)
    # populate_existing: after waiting for the lock, read the row as committed, not the cached copy
    event = db.scalar(q.with_for_update().execution_options(populate_existing=True) if lock else q)
    if event is None:
        raise ApiError(404, "not_found", "Emergency event not found.")
    return event


def create_event(db: Session, patient: CurrentUser, data: EmergencyEventIn,
                 now: datetime) -> tuple[EmergencyEvent, bool]:
    """Returns (event, created). Repeating a client id returns the stored event unchanged."""
    existing = db.get(EmergencyEvent, data.id)
    if existing is not None:
        return _same_patient(existing, patient), False
    if data.started_at > now + CLOCK_SKEW:
        raise _invalid("started_at", "in_future", "Use the time the emergency screen was opened.")
    if data.alert_id is not None:
        alert = db.get(Alert, data.alert_id)
        if alert is None or alert.patient_id != patient.id:
            raise _invalid("alert_id", "invalid_reference", "alert_id is not one of your alerts.",
                           error="invalid_reference")
    event = EmergencyEvent(id=data.id, patient_id=patient.id, trigger_reason=data.trigger_reason,
                           alert_id=data.alert_id, symptoms_snapshot=list(dict.fromkeys(data.symptoms_snapshot)),
                           started_at=data.started_at, actions_attempted=[])
    db.add(event)
    try:
        db.commit()
    except IntegrityError:  # the same client id arrived twice at once: return the stored one
        db.rollback()
        stored = db.get(EmergencyEvent, data.id)
        if stored is None:
            raise
        return _same_patient(stored, patient), False
    return event, True


def _same_patient(event: EmergencyEvent, patient: CurrentUser) -> EmergencyEvent:
    # A client id that belongs to another patient's event: never return that event.
    if event.patient_id != patient.id:
        raise ApiError(409, "conflict", "This event id is already used. Generate a new id.")
    return event


def list_events(db: Session, patient_id: UUID) -> list[EmergencyEvent]:
    return list(db.scalars(select(EmergencyEvent).where(EmergencyEvent.patient_id == patient_id)
                           .order_by(EmergencyEvent.started_at.desc(), EmergencyEvent.id)))


def add_actions(db: Session, event: EmergencyEvent, data: EmergencyActionsIn, now: datetime) -> EmergencyEvent:
    stored = list(event.actions_attempted or [])
    known = {a["client_action_id"] for a in stored}
    for i, a in enumerate(data.actions):
        if a.at > now + CLOCK_SKEW:
            raise _invalid(f"actions.{i}.at", "in_future", "Use the time the action happened.")
        key = str(a.client_action_id)
        if key in known:
            continue
        known.add(key)
        stored.append({"client_action_id": key, "action": a.action, "at": a.at.astimezone(timezone.utc).isoformat(),
                       "detail": a.detail, "confirmed": False})
    if len(stored) > MAX_ACTIONS:
        raise _invalid("actions", "too_many_actions", f"An event keeps at most {MAX_ACTIONS} actions.")
    stored.sort(key=lambda a: a["at"])
    event.actions_attempted = stored  # a new list, so the JSONB column is written
    db.commit()
    return event


def patch_event(db: Session, event: EmergencyEvent, data: EmergencyEventPatch, now: datetime) -> EmergencyEvent:
    sent = data.model_fields_set
    if "location" in sent and data.location is not None:
        if data.location_shared_with_consent is not True:
            raise _invalid("location", "consent_required",
                           "Location is stored only with location_shared_with_consent=true in the same request.",
                           error="consent_required")
        captured = data.location_captured_at or now
        if captured > now + CLOCK_SKEW:
            raise _invalid("location_captured_at", "in_future", "Use the time the phone measured the position.")
        if captured < now - LOCATION_MAX_AGE:
            raise _invalid("location_captured_at", "stale_location",
                           "This position is older than 15 minutes. Share the current position.")
        event.location_lat, event.location_lon = data.location.lat, data.location.lon
        event.location_captured_at, event.location_accuracy_m = captured, data.location_accuracy_m
    elif "location" in sent:  # explicit null removes a stored location
        event.location_lat = event.location_lon = None
        event.location_captured_at = event.location_accuracy_m = None
    if "location_shared_with_consent" in sent and data.location_shared_with_consent is not None:
        event.location_shared_with_consent = data.location_shared_with_consent
        if not data.location_shared_with_consent:  # consent withdrawn: the location goes with it
            event.location_lat = event.location_lon = None
            event.location_captured_at = event.location_accuracy_m = None
    if "reported_outcome" in sent:
        event.reported_outcome = data.reported_outcome
    if "ended_at" in sent and data.ended_at is not None:
        if data.ended_at < event.started_at:
            raise _invalid("ended_at", "before_start", "ended_at cannot be before started_at.")
        if data.ended_at > now + CLOCK_SKEW:
            raise _invalid("ended_at", "in_future", "Use the time the emergency screen was closed.")
        event.ended_at = data.ended_at
    db.commit()
    return event


def report_context(db: Session, event: EmergencyEvent) -> tuple[Alert | None, list[SymptomReport]]:
    """The linked alert and the symptom reports of the same patient within ±24 h. Filtering on the
    event's patient again means a stray reference can never pull in another patient's data."""
    alert = None
    if event.alert_id is not None:
        alert = db.scalar(select(Alert).where(Alert.id == event.alert_id, Alert.patient_id == event.patient_id))
    start, end = event.started_at - REPORT_WINDOW, event.started_at + REPORT_WINDOW
    reports = list(db.scalars(select(SymptomReport)
                              .where(SymptomReport.patient_id == event.patient_id,
                                     SymptomReport.reported_at >= start, SymptomReport.reported_at <= end)
                              .order_by(SymptomReport.reported_at.desc())))
    return alert, reports
