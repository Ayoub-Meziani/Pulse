"""Apply an analysis Evaluation to persisted alerts, with an audit event for every change."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..analysis.types import LEVEL_RANK, ActiveAlert, Evaluation
from ..models import ACTIVE_ALERT_STATES, Alert, AlertEvent


def active_alerts(db: Session, patient_id: int) -> list[Alert]:
    return list(db.scalars(select(Alert).where(
        Alert.patient_id == patient_id, Alert.state.in_(ACTIVE_ALERT_STATES))))


def as_active(alerts: list[Alert]) -> list[ActiveAlert]:
    return [ActiveAlert(a.id, a.level, a.rule_id, a.triggered_at) for a in alerts]


def apply_evaluation(db: Session, patient_id: int, ev: Evaluation, triggered_at: datetime,
                     measurement_id: int | None = None, symptom_report_id: int | None = None,
                     actor_user_id: int | None = None, actor_role: str = "system") -> Alert | None:
    """Create / attach / raise according to the evaluation. Caller commits."""
    if ev.alert_action == "none":
        return None

    if ev.alert_action == "create":
        alert = Alert(patient_id=patient_id, level=ev.level, rule_id=ev.rule_id,
                      reason_text=ev.reason, next_step_text=ev.next_step,
                      measurement_id=measurement_id, symptom_report_id=symptom_report_id,
                      state="new", persistent=ev.persistent, triggered_at=triggered_at)
        db.add(alert)
        db.flush()
        db.add(AlertEvent(alert_id=alert.id, type="state_change", from_state=None, to_state="new",
                          actor_user_id=actor_user_id, actor_role=actor_role,
                          note=f"{ev.rule_id}: {ev.reason}", measurement_id=measurement_id))
        return alert

    alert = db.get(Alert, ev.target_alert_id)
    if alert is None or alert.patient_id != patient_id:
        raise RuntimeError("Evaluation targets an alert that does not belong to this patient.")

    if ev.alert_action == "attach":
        if ev.persistent:
            alert.persistent = True
        db.add(AlertEvent(alert_id=alert.id, type="measurement_attached", actor_user_id=actor_user_id,
                          actor_role=actor_role, note=f"{ev.rule_id}: {ev.reason}",
                          measurement_id=measurement_id))
        return alert

    if ev.alert_action == "raise":
        if LEVEL_RANK[ev.level] > LEVEL_RANK[alert.level]:  # severity never goes down
            old = alert.level
            alert.level, alert.reason_text, alert.next_step_text = ev.level, ev.reason, ev.next_step
            alert.symptom_report_id = symptom_report_id
            db.add(AlertEvent(alert_id=alert.id, type="level_raised", actor_user_id=actor_user_id,
                              actor_role=actor_role, note=f"{ev.rule_id}: {old} -> {ev.level}. {ev.reason}"))
        return alert

    raise ValueError(f"Unknown alert_action {ev.alert_action}")
