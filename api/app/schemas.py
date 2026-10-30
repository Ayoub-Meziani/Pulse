"""Request/response models: THE API CONTRACT (v1).

FastAPI generates OpenAPI from these (GET /api/v1/openapi.json, exported to
contract/openapi.json). Change only through a coordinated PR approved by the
integration lead; see CLAUDE.md and PULSE_INTEGRATION_CONTRACTS.md.

Vocabularies follow the shared Supabase schema (supabase/migrations on branch AI),
except where the frontend already depends on the API names (Level, full_name).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

Role = Literal["patient", "doctor", "admin"]
Source = Literal["manual", "device_sync", "csv_import", "simulated"]
Provenance = Literal["measured", "estimated", "simulated"]
Method = Literal["cuff_oscillometric", "cuff_auscultatory", "wearable_estimate", "unknown"]
ValidationStatus = Literal["valid", "needs_review", "invalid"]
Level = Literal["none", "notice", "trend", "severe", "emergency"]
AlertLevel = Literal["notice", "trend", "severe", "emergency"]
AlertStatus = Literal["open", "acknowledged", "reviewed", "resolved"]
Symptom = Literal["chest_pain", "shortness_of_breath", "back_pain", "weakness", "numbness",
                  "vision_change", "difficulty_speaking", "severe_headache", "confusion",
                  "dizziness", "nausea", "palpitations", "other"]
Position = Literal["sitting", "standing", "lying"]
Arm = Literal["left", "right"]
Trend = Literal["rising", "stable", "falling", "insufficient_data"]
AGE_DESCRIPTION = ("Approximate age in years (current year - birth_year, may be 1 year high). Null when the patient "
                   "has not entered a birth year, or before migration M5 (patient_profiles.birth_year) is applied.")
PHONE_PATTERN = r"^\+?[0-9 ()-]{6,20}$"


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- auth
class LoginIn(BaseModel):
    email: str
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class UserOut(ORM):
    id: UUID
    role: Role
    full_name: str
    email: str
    timezone: str = Field(description="IANA time zone used to display times, e.g. Africa/Algiers.")


class SessionOut(BaseModel):
    access_token: str
    refresh_token: str
    expires_at: datetime
    token_type: Literal["bearer"] = "bearer"
    user: UserOut


# ---------------------------------------------------------------- measurements
class MeasurementIn(BaseModel):
    """Bounds below are the database storage limits only (CHECK constraints), so impossible input gets
    one consistent 422. Plausibility (e.g. systolic > 300 = invalid) is decided by the database policy
    pulse-v1 after the reading is stored, and reported in measurement.validation_status."""
    systolic: int = Field(ge=1, le=400)
    diastolic: int = Field(ge=1, le=300)
    pulse: int | None = Field(None, ge=1, le=400)
    measured_at: AwareDatetime | None = Field(None, description="Defaults to server time when omitted.")
    measured_tz: str | None = Field(None, description="IANA zone where the reading was taken; defaults to the profile time zone.")
    body_position: Position | None = None
    arm: Arm | None = None
    rested_5_min: bool | None = None
    context: str | None = Field(None, max_length=500)


class MeasurementOut(ORM):
    id: UUID
    patient_id: UUID
    systolic: int
    diastolic: int
    pulse: int | None
    measured_at: datetime
    measured_tz: str | None
    created_at: datetime
    source: Source
    provenance: Provenance
    method: Method
    body_position: Position | None
    arm: Arm | None
    rested_5_min: bool | None
    context: str | None
    validation_status: ValidationStatus = Field(description="Computed by the database (policy pulse-v1); never sent by clients.")
    quality_flags: list[str]
    validation_policy_version: str


class EvaluationOut(BaseModel):
    """Deterministic rule result, always returned in the same response as the reading or symptom report.

    Reading flagged invalid by the database: level="none", rule_id="DATA-INVALID", no alert, next_step asks
    to measure again; if the reading is above the plausibility limits (systolic > 300 or diastolic > 200)
    requires_symptom_check is true so a typo never hides a possible crisis."""
    level: Level = Field(description="none | notice (above target) | trend | severe (>= 180 or >= 120) | emergency (red-flag symptom).")
    rule_id: str | None = Field(description="Rule that decided the level: R-EMG-1, R-SEV-1/2/3, R-TGT-1, R-TRD-1, or DATA-INVALID.")
    reason: str
    next_step: str
    requires_symptom_check: bool = Field(description="Show the symptom checklist now and POST symptom-reports.")
    recheck_after_seconds: int | None = Field(description="If set and no red-flag symptom: show a timer, then ask for a new reading.")
    show_emergency: bool = Field(description="Open the emergency screen immediately.")


class AlertBrief(BaseModel):
    id: UUID
    level: AlertLevel
    rule_id: str
    status: AlertStatus
    persistent: bool


class MeasurementResult(BaseModel):
    measurement: MeasurementOut
    evaluation: EvaluationOut
    alert: AlertBrief | None = Field(None, description="Alert created, attached to, or raised by this reading.")
    trend_alert: AlertBrief | None = None


# ---------------------------------------------------------------- symptoms
class SymptomReportIn(BaseModel):
    symptoms: list[Symptom] = Field(default_factory=list, description="Empty list = none of these.")
    measurement_id: UUID | None = Field(None, description="The reading that led to this check. Must be one of the "
                                        "patient's readings (else 422); not stored until migration M7 adds the column.")
    onset_at: AwareDatetime | None = None
    notes: str | None = Field(None, max_length=1000)


class SymptomReportOut(ORM):
    id: UUID
    patient_id: UUID
    symptoms: list[Symptom]
    measurement_id: UUID | None = Field(description="Always null until migration M7 stores the link.")
    onset_at: datetime | None
    reported_at: datetime
    source: str


class SymptomResult(BaseModel):
    report: SymptomReportOut = Field(description="Always stored, including an empty 'none of these' answer (migration M3, live).")
    evaluation: EvaluationOut
    alert: AlertBrief | None = None


# ---------------------------------------------------------------- alerts
class AlertOut(BaseModel):
    id: UUID
    patient_id: UUID
    level: AlertLevel
    rule_id: str
    status: AlertStatus
    persistent: bool
    reason: str
    next_step: str
    measurement_id: UUID | None
    symptom_report_id: UUID | None
    created_at: datetime
    acknowledged_at: datetime | None
    reviewed_at: datetime | None
    resolved_at: datetime | None
    resolution_note: str | None


class AlertDetail(AlertOut):
    measurements: list[MeasurementOut] = Field(description="Readings attached to this alert episode, oldest first.")


class TransitionIn(BaseModel):
    to: Literal["acknowledged", "reviewed", "resolved"]
    note: str | None = Field(None, max_length=2000, description="Required to resolve a severe or emergency alert.")


# ---------------------------------------------------------------- summary / history
class TargetOut(BaseModel):
    systolic: int
    diastolic: int
    is_default: bool


class SummaryOut(BaseModel):
    window_days: int
    timezone: str
    count_7d: int
    count_needs_review_7d: int
    count_invalid_7d: int
    avg_systolic_7d: float | None
    avg_diastolic_7d: float | None
    avg_systolic_30d: float | None
    avg_diastolic_30d: float | None
    max_systolic_7d: int | None
    max_diastolic_7d: int | None
    pct_above_target_7d: float | None
    days_with_reading_7d: int
    trend: Trend
    last_measured_at: datetime | None
    target: TargetOut


class SessionMean(BaseModel):
    systolic: float
    diastolic: float
    count: int


class DailyPoint(BaseModel):
    local_date: date
    morning: SessionMean | None = Field(description="Valid readings before 12:00 local time.")
    evening: SessionMean | None
    count_valid: int
    count_needs_review: int


# ---------------------------------------------------------------- patients (doctor view)
class PatientListItem(BaseModel):
    id: UUID
    full_name: str
    age: int | None = Field(description=AGE_DESCRIPTION)
    highest_active_alert: AlertLevel | None
    active_alert_count: int
    latest_measurement: MeasurementOut | None
    last_measured_at: datetime | None
    avg_systolic_7d: float | None
    avg_diastolic_7d: float | None


# ---------------------------------------------------------------- profile, contacts, care plan
class ProfileOut(BaseModel):
    full_name: str
    email: str
    timezone: str
    birth_year: int | None
    relevant_conditions: list[str]
    allergies: str | None
    medication_context: str | None
    regular_doctor_id: UUID | None
    regular_doctor_name: str | None
    regular_clinic: str | None
    consent_location: bool


class ProfileIn(BaseModel):
    """PUT replaces the whole profile: every field is required (send null or [] to clear a value), so a
    partial form can never silently erase allergies, conditions or location consent."""
    full_name: str = Field(min_length=1, max_length=120)
    timezone: str = Field(description="IANA time zone, e.g. Africa/Algiers.")
    birth_year: int | None = Field(ge=1900, le=2100, description="Year only (data minimisation). Stored by migration M5; "
                                   "the API also rejects years after the current year.")
    relevant_conditions: list[str]
    allergies: str | None
    medication_context: str | None = Field(description="As entered by the patient; PULSE never interprets it.")
    regular_clinic: str | None
    consent_location: bool


class TrustedContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    relationship: str | None = Field(None, max_length=60)
    phone: str = Field(pattern=PHONE_PATTERN)
    contact_consented: Literal[True] = Field(description="The patient confirms the contact agreed to be listed.")
    active: bool = True


class TrustedContactPatch(BaseModel):
    """A different phone number may be a different person who never consented: changing `phone` is refused
    (422 consent_required); delete the contact and add the new number with contact_consented=true."""
    name: str | None = Field(None, min_length=1, max_length=120)
    relationship: str | None = Field(None, max_length=60)
    phone: str | None = Field(None, pattern=PHONE_PATTERN)
    active: bool | None = None


class TrustedContactOut(BaseModel):
    id: UUID
    name: str
    relationship: str | None
    phone: str
    consented_at: datetime
    active: bool


class CarePlanOut(BaseModel):
    id: UUID | None
    target_systolic: int
    target_diastolic: int
    is_default: bool
    effective_from: date | None
    review_date: date | None
    monitoring_readings_per_day: int | None
    clinician_guidance: str | None


class CarePlanIn(BaseModel):
    target_systolic: int = Field(ge=90, le=200)
    target_diastolic: int = Field(ge=50, le=130)
    review_date: date | None = None
    monitoring_readings_per_day: int | None = Field(None, ge=1, le=12)
    clinician_guidance: str = Field(min_length=1, max_length=4000)


# ---------------------------------------------------------------- emergency
class EmergencyNumber(BaseModel):
    id: str
    label_fr: str
    label_ar: str
    number: str | None = Field(description="Null = not configured (demo mode without PULSE_DEMO_NUMBER, dev only): "
                                           "disable the call button and show a configuration warning.")
    verified: bool = Field(description="False until the team has confirmed the number (decision D3).")
    source: str


class ClientFallback(BaseModel):
    severe_systolic: int
    severe_diastolic: int
    red_flag_symptoms: list[Symptom]


class EmergencyConfigOut(BaseModel):
    version: str
    country: Literal["DZ"] = "DZ"
    demo_mode: bool
    numbers: list[EmergencyNumber]
    primary_number_id: str
    disclaimer_fr: str
    disclaimer_ar: str
    client_fallback: ClientFallback = Field(description="Used by the frontend ONLY when the API cannot be reached.")


class ContactBrief(BaseModel):
    name: str
    relationship: str | None
    phone: str


class LastReading(BaseModel):
    systolic: int
    diastolic: int
    measured_at: datetime
    validation_status: ValidationStatus
    source: Source = Field(description="Show 'simulated' readings as simulated, never as a real measurement.")
    provenance: Provenance


class EmergencyCardOut(BaseModel):
    full_name: str
    age: int | None = Field(description=AGE_DESCRIPTION)
    relevant_conditions: list[str]
    allergies: str | None
    medication_context: str | None
    primary_contact: ContactBrief | None
    regular_doctor_name: str | None
    regular_clinic: str | None
    last_reading: LastReading | None
    generated_at: datetime


TriggerReason = Literal["symptom", "severe_reading", "manual"]
ActionType = Literal["screen_opened", "emergency_call_tapped", "contact_call_tapped", "share_opened",
                     "share_failed", "location_granted", "location_denied", "location_timeout",
                     "outcome_reported"]


class EmergencyEventIn(BaseModel):
    id: UUID = Field(description="Generated by the client so retries are idempotent.")
    trigger_reason: TriggerReason
    alert_id: UUID | None = None
    symptoms_snapshot: list[Symptom] = Field(default_factory=list)
    started_at: AwareDatetime


class EmergencyActionIn(BaseModel):
    client_action_id: UUID
    action: ActionType
    at: AwareDatetime
    detail: str | None = Field(None, max_length=500)


class EmergencyActionsIn(BaseModel):
    actions: list[EmergencyActionIn] = Field(min_length=1, max_length=50)


class Location(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class EmergencyEventPatch(BaseModel):
    location: Location | None = None
    location_shared_with_consent: bool | None = None
    reported_outcome: str | None = Field(None, max_length=500)
    ended_at: AwareDatetime | None = None


class EmergencyActionOut(BaseModel):
    client_action_id: UUID
    action: ActionType
    at: datetime
    detail: str | None
    confirmed: Literal[False] = Field(False, description="PULSE cannot verify that a call or share happened.")


class EmergencyEventOut(BaseModel):
    id: UUID
    patient_id: UUID
    trigger_reason: TriggerReason
    alert_id: UUID | None
    symptoms_snapshot: list[Symptom]
    started_at: datetime
    ended_at: datetime | None
    actions: list[EmergencyActionOut]
    reported_outcome: str | None
    location: Location | None


class EmergencyReportOut(BaseModel):
    event: EmergencyEventOut
    alert: AlertOut | None
    readings: list[MeasurementOut] = Field(description="Readings from started_at - 24 h to started_at + 24 h.")
    symptom_reports: list[SymptomReportOut]


# ---------------------------------------------------------------- follow-up
class NoteIn(BaseModel):
    note: str = Field(min_length=1, max_length=8000)
    advice: str | None = Field(None, max_length=4000)
    follow_up_at: AwareDatetime | None = None


class NoteOut(BaseModel):
    id: UUID
    doctor_id: UUID
    doctor_name: str
    created_at: datetime
    note: str | None = Field(description="Private clinical note; null when the reader is the patient.")
    advice: str | None
    follow_up_at: datetime | None


JournalCategory = Literal["symptoms", "food", "activity", "medication", "question", "other"]


class JournalIn(BaseModel):
    category: JournalCategory
    entry_text: str = Field(min_length=1, max_length=4000)


class JournalOut(BaseModel):
    id: UUID
    category: JournalCategory
    entry_text: str
    created_at: datetime
    doctor_review_status: Literal["not_reviewed", "reviewed"]
    reviewed_at: datetime | None


# ---------------------------------------------------------------- ML (doctor only)
PREDICTION_LIMITATIONS = ("Model estimate trained on synthetic data only. Not a measurement, "
                          "not clinically validated, not used for alerts.")


class Interval(BaseModel):
    systolic: tuple[float, float]
    diastolic: tuple[float, float]


class PredictionOut(BaseModel):
    status: Literal["ok", "insufficient_history", "model_unavailable"]
    target: Literal["morning_mean_bp"] = "morning_mean_bp"
    target_date: date | None
    predicted_systolic: float | None
    predicted_diastolic: float | None
    interval: Interval | None
    model_version: str | None
    trained_on: str | None
    generated_at: datetime | None
    limitations: str = PREDICTION_LIMITATIONS


# ---------------------------------------------------------------- errors
class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict | list | None = None


class ErrorOut(BaseModel):
    error: ErrorBody
