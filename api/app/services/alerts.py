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
from ..models import Alert, AlertMeasurement, AuditLog, Measurement, SymptomReport

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
    elif ev.alert_action == "raise":
        current = vocab.ALERT_CLASS_TO_LEVEL[alert.alert_class]
        if vocab.LEVEL_RANK[ev.level] > vocab.LEVEL_RANK[current]:  # severity never goes down
            alert.alert_class = vocab.LEVEL_TO_ALERT_CLASS[ev.level]
            alert.reason, alert.actions = ev.reason, [ev.next_step]
            if alert.symptom_report_id is None:
                alert.symptom_report_id = symptom_report_id
    else:
        raise ValueError(f"Unknown alert_action {ev.alert_action}")
    db.flush()
    return alert


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
# (from status -> allowed targets) ; who may do it is checked in transition().
ALLOWED = {"open": {"acknowledged", "reviewed", "dismissed"}, "acknowledged": {"reviewed", "dismissed"},
           "dismissed": {"reviewed"}, "reviewed": {"resolved"}}
DISMISSABLE_LEVELS = ("notice",)  # Q5 (Ayoub): severe, trend and emergency alerts are never dismissed
DISMISSAL_NOTE_MAX = 500


def transition(db: Session, alert: Alert, user: CurrentUser, to: str, note: str | None, now: datetime,
               is_assigned_doctor: bool, reason: str | None = None) -> Alert:
    if to not in ALLOWED.get(alert.status, set()) or (to == "dismissed"
                                                     and alert_level(alert) not in DISMISSABLE_LEVELS):
        raise ApiError(409, "invalid_transition", f"An alert that is {alert.status} cannot become {to}.",
                       {"from": alert.status, "to": to, "level": alert_level(alert)})
    if to in ("acknowledged", "dismissed"):
        if not (user.id == alert.patient_id or is_assigned_doctor):
            raise ApiError(403, "forbidden", f"Only the patient or the assigned doctor can {to[:-1]}.")
    elif not is_assigned_doctor:
        raise ApiError(403, "forbidden", "Only the assigned doctor can review or resolve.")
    if to == "dismissed":
        return _dismiss(db, alert, user, reason, note, now)
    if reason is not None:
        raise ApiError(422, "validation_failed", "A reason is only recorded when dismissing a notice.",
                       [{"field": "reason", "code": "not_stored", "message": "Send the reason with to='dismissed'."}])
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



def _dismiss(db: Session, alert: Alert, user: CurrentUser, reason: str | None, note: str | None,
             now: datetime) -> Alert:
    note = note.strip() if note and note.strip() else None
    errors = []
    if reason is None:
        errors.append({"field": "reason", "code": "required", "message": "Choose why this notice is dismissed."})
    elif reason == "other" and note is None:
        errors.append({"field": "note", "code": "required", "message": "Explain the reason."})
    if note is not None and len(note) > DISMISSAL_NOTE_MAX:
        errors.append({"field": "note", "code": "too_long", "message": f"At most {DISMISSAL_NOTE_MAX} characters."})
    if errors:
        raise ApiError(422, "validation_failed", "The dismissal is incomplete.", errors)
    alert.status = "dismissed"
    alert.dismissed_at, alert.dismissed_by = now, user.id
    alert.dismissal_reason, alert.dismissal_note = reason, note
    db.flush()
    return alert


def dismissed_by_role(alert: Alert) -> str | None:
    if alert.dismissed_by is None:
        return None
    return "patient" if alert.dismissed_by == alert.patient_id else "doctor"


# ---------------------------------------------------------------- timeline (read-only, from audit_log)
def events(db: Session, alert: Alert) -> list[dict]:
    """Creation, level raises, status changes (audit_log) and attached readings (alert_measurements), oldest first.

    Only roles are returned, never user ids or raw audit rows. The rule engine creates and raises alerts while
    serving the patient's request, so those rows are attributed to 'rule' whatever the recorded actor.
    """
    rows = db.execute(select(AuditLog.id, AuditLog.action, AuditLog.actor, AuditLog.changed_at,
                             AuditLog.old_data, AuditLog.new_data)
                      .where(AuditLog.table_name == "alerts", AuditLog.row_id == alert.id)
                      .order_by(AuditLog.changed_at, AuditLog.id)).all()

    def role(actor):
        return "patient" if actor == alert.patient_id else "doctor"

    out = []  # (time, tie-break, event); the tie-break keeps audit order and puts a raise before its status change
    for audit_id, action, actor, at, old, new in rows:
        if action == "INSERT":
            out.append((at, (0, audit_id, 0), dict(kind="created", actor_role="rule", to_status=new["status"],
                                                   level=vocab.ALERT_CLASS_TO_LEVEL.get(new["alert_class"]))))
        elif action == "UPDATE":
            if old["alert_class"] != new["alert_class"]:
                out.append((at, (0, audit_id, 0), dict(kind="level_raised", actor_role="rule",
                                                       level=vocab.ALERT_CLASS_TO_LEVEL.get(new["alert_class"]))))
            if old["status"] != new["status"]:
                note = {"dismissed": new.get("dismissal_note"), "resolved": new.get("resolution_note")}.get(new["status"])
                out.append((at, (0, audit_id, 1), dict(kind="status_changed", actor_role=role(actor),
                                                       from_status=old["status"], to_status=new["status"], note=note)))
    attached = db.scalars(select(AlertMeasurement.attached_at).where(AlertMeasurement.alert_id == alert.id))
    out += [(at, (1, 0, 0), dict(kind="measurement_attached", actor_role="rule")) for at in attached]
    return [dict(at=at, **event) for at, _, event in sorted(out, key=lambda e: (e[0], e[1]))]
