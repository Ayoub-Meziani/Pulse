"""Request/response models: THE API CONTRACT.

FastAPI generates OpenAPI from these (GET /api/v1/openapi.json, exported to
contract/openapi.json). Change only through a coordinated PR approved by the
integration lead; see CLAUDE.md.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

Role = Literal["patient", "doctor"]
Source = Literal["manual", "device", "imported", "simulated"]
LevelOut = Literal["none", "notice", "trend", "severe", "emergency"]
AlertLevel = Literal["notice", "trend", "severe", "emergency"]
AlertState = Literal["new", "acknowledged", "escalated", "dismissed", "reviewed", "closed"]
SymptomCode = Literal["chest_pain", "short_breath", "back_pain", "numbness",
                      "weakness", "vision_change", "speech_difficulty"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- auth
class LoginIn(BaseModel):
    email: str
    password: str


class UserOut(ORM):
    id: int
    role: Role
    full_name: str
    email: str


class LoginOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserOut


# ---------------------------------------------------------------- measurements
class MeasurementContext(BaseModel):
    rested_5_min: bool | None = None
    position: Literal["sitting", "standing", "lying"] | None = None
    arm: Literal["left", "right"] | None = None


class MeasurementIn(BaseModel):
    systolic: int
    diastolic: int
    pulse: int | None = None
    measured_at: AwareDatetime | None = Field(None, description="Defaults to server time when omitted.")
    source: Source = "manual"
    source_ref: str | None = Field(None, max_length=200,
                                   description="Device id, import file name or simulator scenario.")
    external_id: str | None = Field(None, max_length=200,
                                    description="Stable id from the source; duplicates are rejected (409).")
    context: MeasurementContext | None = None


class MeasurementOut(ORM):
    id: int
    patient_id: int
    systolic: int
    diastolic: int
    pulse: int | None
    measured_at: datetime
    received_at: datetime
    source: Source
    source_ref: str | None
    external_id: str | None
    context: dict | None
    validation_status: Literal["valid", "questionable"]
    validation_notes: list[str] | None


class EvaluationOut(BaseModel):
    level: LevelOut
    rule_id: str | None
    reason: str
    next_step: str
    requires_symptom_check: bool
    recheck_after_seconds: int | None
    show_emergency: bool


class AlertBrief(ORM):
    id: int
    level: AlertLevel
    rule_id: str
    state: AlertState
    persistent: bool


class MeasurementResult(BaseModel):
    measurement: MeasurementOut
    evaluation: EvaluationOut
    alert: AlertBrief | None = Field(None, description="Alert created, attached to, or raised by this reading.")
    trend_alert: AlertBrief | None = None


# ---------------------------------------------------------------- symptoms
class SymptomReportIn(BaseModel):
    symptoms: list[SymptomCode] = Field(default_factory=list, description="Empty list = none of these.")
    measurement_id: int | None = None
    notes: str | None = Field(None, max_length=1000)


class SymptomReportOut(ORM):
    id: int
    patient_id: int
    symptoms: list[SymptomCode]
    measurement_id: int | None
    notes: str | None
    reported_at: datetime


class SymptomResult(BaseModel):
    report: SymptomReportOut
    evaluation: EvaluationOut
    alert: AlertBrief | None = None


# ---------------------------------------------------------------- alerts
class AlertEventOut(ORM):
    id: int
    type: str
    from_state: str | None
    to_state: str | None
    actor_user_id: int | None
    actor_role: str
    note: str | None
    measurement_id: int | None
    created_at: datetime


class AlertOut(ORM):
    id: int
    patient_id: int
    level: AlertLevel
    rule_id: str
    reason_text: str
    next_step_text: str
    measurement_id: int | None
    symptom_report_id: int | None
    state: AlertState
    persistent: bool
    triggered_at: datetime
    created_at: datetime
    updated_at: datetime


class AlertDetail(AlertOut):
    events: list[AlertEventOut]


# ---------------------------------------------------------------- summary / doctor list
class TargetOut(BaseModel):
    systolic: int
    diastolic: int
    is_default: bool


class SummaryOut(BaseModel):
    window_days: int
    count_7d: int
    count_questionable_7d: int
    avg_systolic_7d: float | None
    avg_diastolic_7d: float | None
    avg_systolic_30d: float | None
    avg_diastolic_30d: float | None
    max_systolic_7d: int | None
    max_diastolic_7d: int | None
    pct_above_target_7d: float | None
    days_with_reading_7d: int
    trend: Literal["rising", "stable", "falling", "insufficient_data"]
    last_measured_at: datetime | None
    target: TargetOut


class PatientListItem(BaseModel):
    id: int
    full_name: str
    highest_active_alert: AlertLevel | None
    active_alert_count: int
    latest_measurement: MeasurementOut | None
    last_measured_at: datetime | None
    avg_systolic_7d: float | None
    avg_diastolic_7d: float | None


# ---------------------------------------------------------------- errors
class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict | list | None = None


class ErrorOut(BaseModel):
    error: ErrorBody
