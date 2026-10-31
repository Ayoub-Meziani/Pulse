"""Persist rule evaluations as alerts (create / attach / raise) and run alert status transitions.

Only the deterministic rules (app.analysis) create or change alerts. Every insert/update on
public.alerts is copied to public.audit_log by the database trigger, with the caller recorded via
request.jwt.claims; that log is the escalation history. Severity never goes down.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import vocab
from ..analysis.types import ActiveAlert, Evaluation
from ..auth import CurrentUser
from ..errors import ApiError
from ..models import Alert, AlertMeasurement, Measurement, SymptomReport

OUR_CLASSES = tuple(vocab.ALERT_CLASS_TO_LEVEL)  # alerts of other classes are not produced by the rules


def active_alerts(db: Session, patient_id: UUID) -> list[ActiveAlert]:
    """Open/acknowledged rule alerts, each with the time of the event that triggered it."""
    triggered = func.coalesce(Measurement.measured_at, SymptomReport.reported_at, Alert.created_at)
    rows = db.execute(
        select(Alert.id, Alert.alert_class, Alert.rule_code, triggered)
        .outerjoin(Measurement, Measurement.id == Alert.measurement_id)
        .outerjoin(SymptomReport, SymptomReport.id == Alert.symptom_report_id)
        .where(Alert.patient_id == patient_id, Alert.status.in_(vocab.ACTIVE_ALERT_STATUSES),
               Alert.alert_class.in_(OUR_CLASSES))).all()
    return [ActiveAlert(id=r[0], level=vocab.ALERT_CLASS_TO_LEVEL[r[1]], rule_id=r[2], triggered_at=r[3])
            for r in rows]


def apply_evaluation(db: Session, patient_id: UUID, ev: Evaluation, *, measurement_id: UUID | None = None,
                     symptom_report_id: UUID | None = None) -> Alert | None:
    """Create / attach / raise according to the evaluation. Caller commits."""
    if ev.alert_action == "none":
        return None
    if ev.alert_action == "create":
        alert = Alert(patient_id=patient_id, measurement_id=measurement_id, symptom_report_id=symptom_report_id,
                      alert_class=vocab.LEVEL_TO_ALERT_CLASS[ev.level], trigger_source=vocab.ALERT_TRIGGER_SOURCE,
                      rule_code=ev.rule_id, rule_version=vocab.RULE_VERSION, reason=ev.reason,
                      actions=[ev.next_step], persistent=ev.persistent)
        db.add(alert)
        db.flush()
        return alert

    alert = db.get(Alert, ev.target_alert_id)
    if alert is None or alert.patient_id != patient_id:
        raise RuntimeError("Evaluation targets an alert that does not belong to this patient.")
    if ev.alert_action == "attach":
        if measurement_id is not None:
            db.add(AlertMeasurement(alert_id=alert.id, measurement_id=measurement_id, patient_id=patient_id))
        if ev.persistent:
            alert.persistent = True
            _reopen_if_confirmed(alert, ev.level)  # still very high on the recheck: a new bad reading rings again
    elif ev.alert_action == "raise":
        current = vocab.ALERT_CLASS_TO_LEVEL[alert.alert_class]
        if vocab.LEVEL_RANK[ev.level] > vocab.LEVEL_RANK[current]:  # severity never goes down
            alert.alert_class = vocab.LEVEL_TO_ALERT_CLASS[ev.level]
            alert.reason, alert.actions = ev.reason, [ev.next_step]
            _reopen_if_confirmed(alert, ev.level)  # the patient confirmed the lower level, never this one
            if alert.symptom_report_id is None:
                alert.symptom_report_id = symptom_report_id
    else:
        raise ValueError(f"Unknown alert_action {ev.alert_action}")
    db.flush()
    return alert


def _reopen_if_confirmed(alert: Alert, level: str) -> None:
    """A new severe or emergency reason on an alert the patient already confirmed: open again, so it rings until the
    patient confirms it with the password (D28; proposed D29)."""
    if alert.status == "acknowledged" and level in CONFIRMED_LEVELS:
        alert.status, alert.acknowledged_at, alert.acknowledged_by = "open", None, None


def alert_level(alert: Alert) -> str:
    return vocab.ALERT_CLASS_TO_LEVEL[alert.alert_class]


def list_alerts(db: Session, patient_id: UUID, active_only: bool) -> list[Alert]:
    q = select(Alert).where(Alert.patient_id == patient_id, Alert.alert_class.in_(OUR_CLASSES))
    if active_only:
        q = q.where(Alert.status.in_(vocab.ACTIVE_ALERT_STATUSES))
    return list(db.scalars(q.order_by(Alert.created_at.desc())))


def get_alert(db: Session, alert_id: UUID) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None or alert.alert_class not in OUR_CLASSES:
        raise ApiError(404, "not_found", "Alert not found.")
    return alert


def episode_measurements(db: Session, alert: Alert) -> list[Measurement]:
    """The triggering reading plus every reading attached to the episode, oldest first."""
    attached = select(AlertMeasurement.measurement_id).where(AlertMeasurement.alert_id == alert.id)
    q = select(Measurement).where(Measurement.patient_id == alert.patient_id,
                                  (Measurement.id == alert.measurement_id) | Measurement.id.in_(attached))
    return list(db.scalars(q.order_by(Measurement.measured_at, Measurement.created_at)))


# ---------------------------------------------------------------- transitions
CONFIRMED_LEVELS = ("severe", "emergency")  # a patient acknowledges these only after re-entering the password


# (from status -> allowed targets) ; who may do it is checked in transition().
ALLOWED = {"open": {"acknowledged", "reviewed"}, "acknowledged": {"reviewed"}, "reviewed": {"resolved"}}


def transition(db: Session, alert: Alert, user: CurrentUser, to: str, note: str | None, now: datetime,
               is_assigned_doctor: bool, password_confirmed: bool = False) -> Alert:
    if to not in ALLOWED.get(alert.status, set()):
        raise ApiError(409, "invalid_transition", f"An alert that is {alert.status} cannot become {to}.",
                       {"from": alert.status, "to": to})
    if to == "acknowledged":
        if not (user.id == alert.patient_id or is_assigned_doctor):
            raise ApiError(403, "forbidden", "Only the patient or the assigned doctor can acknowledge.")
        if (user.id == alert.patient_id and alert_level(alert) in CONFIRMED_LEVELS and not password_confirmed):
            raise ApiError(403, "password_confirmation_required",
                           "Confirm a severe or emergency alert with your password "
                           "(POST /alerts/{id}/patient-confirmation).")
    elif not is_assigned_doctor:
        raise ApiError(403, "forbidden", "Only the assigned doctor can review or resolve.")
    if note is not None and to != "resolved":
        raise ApiError(422, "validation_failed", "A note is only recorded when resolving an alert.",
                       [{"field": "note", "code": "not_stored", "message": "Send the note with the resolve step."}])
    if to == "resolved" and alert_level(alert) in ("severe", "emergency") and not (note and note.strip()):
        raise ApiError(422, "validation_failed", "A note is required to resolve a severe or emergency alert.",
                       [{"field": "note", "code": "required", "message": "Describe the follow-up."}])
    alert.status = to
    if to == "acknowledged":
        alert.acknowledged_at, alert.acknowledged_by = now, user.id
    elif to == "reviewed":
        alert.reviewed_at, alert.reviewed_by = now, user.id
    else:
        alert.resolved_at, alert.resolved_by, alert.resolution_note = now, user.id, note.strip() if note else None
    db.flush()
    return alert



def doctor_alerts(db: Session, doctor_id) -> list[tuple[Alert, str, Measurement | None]]:
    """Severe and emergency alerts of actively assigned patients that the doctor has not resolved yet
    (open, acknowledged by the patient, or reviewed), most severe then newest first."""
    from ..models import Assignment, Profile
    rows = db.execute(
        select(Alert, Profile.display_name, Measurement)
        .join(Assignment, (Assignment.patient_id == Alert.patient_id) & (Assignment.doctor_id == doctor_id)
              & (Assignment.status == "active"))
        .join(Profile, Profile.id == Alert.patient_id)
        .outerjoin(Measurement, Measurement.id == Alert.measurement_id)
        .where(Alert.alert_class.in_([vocab.LEVEL_TO_ALERT_CLASS[lv] for lv in CONFIRMED_LEVELS]),
               Alert.status.in_(("open", "acknowledged", "reviewed")))).all()
    return sorted(rows, key=lambda r: (-vocab.LEVEL_RANK[alert_level(r[0])], -r[0].created_at.timestamp()))
