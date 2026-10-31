"""SQLAlchemy mappings of the shared Supabase schema (supabase/migrations). No DDL here.

Only columns the API uses are mapped. Columns computed by database defaults or triggers are
marked FetchedValue so inserts read them back (RETURNING). tests/test_db_models.py checks every
mapped column against the migrated test database.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (ARRAY, Boolean, Date, DateTime, FetchedValue, Float, ForeignKey, Integer, Numeric,
                        SmallInteger, Text)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

TS = DateTime(timezone=True)
TEXT_ARRAY = ARRAY(Text)


def _id() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _server(type_, **kw):
    return mapped_column(type_, server_default=FetchedValue(), **kw)


class AuthUser(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "auth"}
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    email: Mapped[str | None] = mapped_column(Text)


class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("auth.users.id"), primary_key=True)
    role: Mapped[str] = _server(Text)
    display_name: Mapped[str] = mapped_column(Text)
    timezone: Mapped[str] = _server(Text)


class PatientProfile(Base):
    __tablename__ = "patient_profiles"
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("profiles.id"), primary_key=True)
    relevant_conditions: Mapped[list[str]] = _server(TEXT_ARRAY)
    allergies: Mapped[str | None] = mapped_column(Text)
    medication_context: Mapped[str | None] = mapped_column(Text)
    regular_doctor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    regular_clinic: Mapped[str | None] = mapped_column(Text)
    consent_location: Mapped[bool] = _server(Boolean)
    birth_year: Mapped[int | None] = mapped_column(SmallInteger)  # migration M5 (verified live 2026-10-30)


class Assignment(Base):
    __tablename__ = "doctor_patient_assignments"
    id: Mapped[uuid.UUID] = _id()
    doctor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = _server(Text)
    ended_at: Mapped[datetime | None] = mapped_column(TS)


class CarePlan(Base):
    __tablename__ = "care_plans"
    id: Mapped[uuid.UUID] = _id()
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    clinician_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = _server(Text)
    effective_from: Mapped[date] = mapped_column(Date)  # NOT NULL, no DB default: the API sets it
    review_date: Mapped[date | None] = mapped_column(Date)
    target_systolic: Mapped[int | None] = mapped_column(SmallInteger)
    target_diastolic: Mapped[int | None] = mapped_column(SmallInteger)
    monitoring_readings_per_day: Mapped[int | None] = mapped_column(SmallInteger)
    clinician_guidance: Mapped[str] = mapped_column(Text)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class Measurement(Base):
    __tablename__ = "measurements"
    __mapper_args__ = {"eager_defaults": True}
    id: Mapped[uuid.UUID] = _id()
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    source: Mapped[str] = mapped_column(Text)
    provenance: Mapped[str] = mapped_column(Text)
    method: Mapped[str] = mapped_column(Text)
    systolic: Mapped[int] = mapped_column(SmallInteger)
    diastolic: Mapped[int] = mapped_column(SmallInteger)
    pulse: Mapped[int | None] = mapped_column(SmallInteger)
    measured_at: Mapped[datetime] = mapped_column(TS)
    measured_tz: Mapped[str | None] = mapped_column(Text)
    body_position: Mapped[str | None] = mapped_column(Text)
    arm: Mapped[str | None] = mapped_column(Text)
    context: Mapped[str | None] = mapped_column(Text)
    rested_5_min: Mapped[bool | None] = mapped_column(Boolean)  # migration M3
    # Set by the pulse-v1 validation trigger; never written by the API.
    validation_status: Mapped[str] = _server(Text)
    quality_flags: Mapped[list[str]] = _server(TEXT_ARRAY)
    validation_policy_version: Mapped[str] = _server(Text)
    created_by: Mapped[uuid.UUID | None] = _server(UUID(as_uuid=True))  # trigger: coalesce(auth.uid(), value)
    created_at: Mapped[datetime] = _server(TS)


class SymptomReport(Base):
    __tablename__ = "symptom_reports"
    __mapper_args__ = {"eager_defaults": True}
    id: Mapped[uuid.UUID] = _id()
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    symptoms: Mapped[list[str]] = mapped_column(TEXT_ARRAY)
    onset_at: Mapped[datetime | None] = mapped_column(TS)
    reported_at: Mapped[datetime] = _server(TS)
    source: Mapped[str] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class Alert(Base):
    __tablename__ = "alerts"
    __mapper_args__ = {"eager_defaults": True}
    id: Mapped[uuid.UUID] = _id()
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    measurement_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    symptom_report_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    alert_class: Mapped[str] = mapped_column(Text)
    trigger_source: Mapped[str] = _server(Text)
    rule_code: Mapped[str] = mapped_column(Text)
    rule_version: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    actions: Mapped[list[str]] = _server(TEXT_ARRAY)
    status: Mapped[str] = _server(Text)
    persistent: Mapped[bool] = _server(Boolean)  # migration M3
    acknowledged_at: Mapped[datetime | None] = mapped_column(TS)
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(TS)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    resolved_at: Mapped[datetime | None] = mapped_column(TS)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    dismissed_at: Mapped[datetime | None] = mapped_column(TS)  # migration M10
    dismissed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    dismissal_reason: Mapped[str | None] = mapped_column(Text)
    dismissal_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _server(TS)


class AlertMeasurement(Base):  # migration M3
    __tablename__ = "alert_measurements"
    alert_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    measurement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    attached_at: Mapped[datetime] = _server(TS)


class AuditLog(Base):  # read only: written by the private.audit() trigger, append-only since M10
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    table_name: Mapped[str] = mapped_column(Text)
    row_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(Text)
    actor: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    changed_at: Mapped[datetime] = _server(TS)
    old_data: Mapped[dict | None] = mapped_column(JSONB)
    new_data: Mapped[dict | None] = mapped_column(JSONB)


class TrustedContact(Base):
    __tablename__ = "trusted_contacts"
    id: Mapped[uuid.UUID] = _id()
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    name: Mapped[str] = mapped_column(Text)
    relationship: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str] = mapped_column(Text)
    consented_at: Mapped[datetime] = _server(TS)
    active: Mapped[bool] = _server(Boolean)
    priority: Mapped[int] = _server(SmallInteger)  # migration M11: 1 = called first
    phone_verified_at: Mapped[datetime | None] = mapped_column(TS)
    contact_consented_at: Mapped[datetime | None] = mapped_column(TS)


class EmergencyEvent(Base):
    __tablename__ = "emergency_events"
    id: Mapped[uuid.UUID] = _id()
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    alert_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    trigger_reason: Mapped[str] = mapped_column(Text)
    symptoms_snapshot: Mapped[list[str]] = _server(TEXT_ARRAY)
    location_lat: Mapped[float | None] = mapped_column(Float)
    location_lon: Mapped[float | None] = mapped_column(Float)
    location_shared_with_consent: Mapped[bool] = _server(Boolean)
    actions_attempted: Mapped[list] = _server(JSONB)
    reported_outcome: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = _server(TS)
    ended_at: Mapped[datetime | None] = mapped_column(TS)
    # migration M11: escalation (docs/EMERGENCY_ESCALATION_DESIGN.md)
    severity: Mapped[str | None] = mapped_column(Text)
    evidence_provenance: Mapped[str | None] = mapped_column(Text)
    escalation_eligible: Mapped[bool] = _server(Boolean)
    escalation_status: Mapped[str | None] = mapped_column(Text)
    escalation_policy: Mapped[str | None] = mapped_column(Text)
    patient_response: Mapped[str | None] = mapped_column(Text)
    patient_responded_at: Mapped[datetime | None] = mapped_column(TS)
    cancelled_at: Mapped[datetime | None] = mapped_column(TS)
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(TS)
    resolution_outcome: Mapped[str | None] = mapped_column(Text)
    location_captured_at: Mapped[datetime | None] = mapped_column(TS)
    location_accuracy_m: Mapped[float | None] = mapped_column(Float)


class CareFacility(Base):  # migration M11; contacted only with a verified number and an active agreement
    __tablename__ = "care_facilities"
    id: Mapped[uuid.UUID] = _id()
    name: Mapped[str] = mapped_column(Text)
    wilaya: Mapped[str | None] = mapped_column(Text)
    oncall_phone: Mapped[str | None] = mapped_column(Text)
    verified_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    verified_at: Mapped[datetime | None] = mapped_column(TS)
    verification_source: Mapped[str | None] = mapped_column(Text)
    agreement_status: Mapped[str] = _server(Text)
    agreement_ref: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = _server(Boolean)


class DoctorFacilityAffiliation(Base):  # migration M11
    __tablename__ = "doctor_facility_affiliations"
    doctor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    facility_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    active: Mapped[bool] = _server(Boolean)


class EscalationStep(Base):  # migration M11: one target x channel attempt; also the worker's queue
    __tablename__ = "escalation_steps"
    __mapper_args__ = {"eager_defaults": True}
    id: Mapped[uuid.UUID] = _id()
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    stage: Mapped[str] = mapped_column(Text)
    target_kind: Mapped[str] = mapped_column(Text)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    channel: Mapped[str] = mapped_column(Text)
    sequence: Mapped[int] = mapped_column(SmallInteger, default=1)
    status: Mapped[str] = mapped_column(Text, default="scheduled")
    skip_reason: Mapped[str | None] = mapped_column(Text)
    due_at: Mapped[datetime] = mapped_column(TS)
    ack_window_seconds: Mapped[int | None] = mapped_column(Integer)
    ack_deadline: Mapped[datetime | None] = mapped_column(TS)
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0)
    max_attempts: Mapped[int] = mapped_column(SmallInteger, default=3)
    idempotency_key: Mapped[str] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(Text)
    provider_message_id: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(TS)
    delivered_at: Mapped[datetime | None] = mapped_column(TS)
    acknowledged_at: Mapped[datetime | None] = mapped_column(TS)
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = _server(TS)
    updated_at: Mapped[datetime] = _server(TS)


class EscalationTimeline(Base):  # migration M11; append-only (database trigger)
    __tablename__ = "escalation_timeline"
    __mapper_args__ = {"eager_defaults": True}
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    step_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    at: Mapped[datetime] = _server(TS)
    kind: Mapped[str] = mapped_column(Text)
    actor_kind: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)


class Notification(Base):  # migration M11: in-app inbox (patients and doctors)
    __tablename__ = "notifications"
    __mapper_args__ = {"eager_defaults": True}
    id: Mapped[uuid.UUID] = _id()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    patient_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    kind: Mapped[str] = mapped_column(Text)
    alert_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    step_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    urgent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _server(TS)
    read_at: Mapped[datetime | None] = mapped_column(TS)


class DoctorNote(Base):
    __tablename__ = "doctor_notes"
    id: Mapped[uuid.UUID] = _id()
    doctor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    note: Mapped[str] = mapped_column(Text)
    advice: Mapped[str | None] = mapped_column(Text)
    follow_up_at: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = _server(TS)


class JournalEntry(Base):
    __tablename__ = "journal_entries"
    __mapper_args__ = {"eager_defaults": True}
    id: Mapped[uuid.UUID] = _id()
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    category: Mapped[str] = mapped_column(Text)
    entry_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _server(TS)
    doctor_review_status: Mapped[str] = _server(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(TS)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class MlPrediction(Base):  # migration M4; written only by the ML batch job
    __tablename__ = "ml_predictions"
    id: Mapped[uuid.UUID] = _id()
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    target_date: Mapped[date] = mapped_column(Date)
    target: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    predicted_systolic: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    predicted_diastolic: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    interval_systolic_low: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    interval_systolic_high: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    interval_diastolic_low: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    interval_diastolic_high: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    model_version: Mapped[str] = mapped_column(Text)
    trained_on: Mapped[str] = mapped_column(Text)
    features_until: Mapped[datetime] = mapped_column(TS)
    n_readings_used: Mapped[int] = mapped_column(SmallInteger)
    created_at: Mapped[datetime] = _server(TS)


class Device(Base):  # read only: devices are registered by the device sync / simulator, not by the API
    __tablename__ = "devices"
    id: Mapped[uuid.UUID] = _id()
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    device_type: Mapped[str] = mapped_column(Text)
    bp_capability: Mapped[str] = mapped_column(Text)
    manufacturer: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    label: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _server(TS)


class WearableSample(Base):  # migration M6; read only, never an input to rules, alerts or emergency guidance
    __tablename__ = "wearable_samples"
    id: Mapped[uuid.UUID] = _id()
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    metric: Mapped[str] = mapped_column(Text)
    value: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    unit: Mapped[str] = mapped_column(Text)
    measured_at: Mapped[datetime] = mapped_column(TS)
    source: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _server(TS)
