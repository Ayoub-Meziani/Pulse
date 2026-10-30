"""SQLAlchemy mappings of the shared Supabase schema (supabase/migrations). No DDL here.

Only columns the API uses are mapped. Columns computed by database defaults or triggers are
marked FetchedValue so inserts read them back (RETURNING). tests/test_db_models.py checks every
mapped column against the migrated test database.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (ARRAY, Boolean, Date, DateTime, FetchedValue, Float, ForeignKey, Numeric,
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
    # birth_year (migration M5) is deliberately NOT mapped until M5 is verified on the live project:
    # mapping it would break every patient_profiles query on the live schema (M1-M4).


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
    created_at: Mapped[datetime] = _server(TS)


class AlertMeasurement(Base):  # migration M3
    __tablename__ = "alert_measurements"
    alert_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    measurement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    attached_at: Mapped[datetime] = _server(TS)


class TrustedContact(Base):
    __tablename__ = "trusted_contacts"
    id: Mapped[uuid.UUID] = _id()
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    name: Mapped[str] = mapped_column(Text)
    relationship: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str] = mapped_column(Text)
    consented_at: Mapped[datetime] = _server(TS)
    active: Mapped[bool] = _server(Boolean)


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
