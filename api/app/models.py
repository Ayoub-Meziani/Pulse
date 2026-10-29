"""SQLAlchemy models: the persisted part of the integration contract.

Change these only through a coordinated PR (see CLAUDE.md). No migration tool
yet: the schema is created on startup and `python -m app.seed --reset` rebuilds
the demo database. Add Alembic before any data must survive a schema change.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, UTCDateTime, utcnow

ACTIVE_ALERT_STATES = ("new", "acknowledged", "escalated")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(String(16))  # patient | doctor
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class DoctorPatientAssignment(Base):
    __tablename__ = "doctor_patient_assignments"
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    assigned_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class CarePlan(Base):
    __tablename__ = "care_plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    target_systolic: Mapped[int] = mapped_column(Integer)
    target_diastolic: Mapped[int] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    effective_from: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Measurement(Base):
    __tablename__ = "measurements"
    __table_args__ = (UniqueConstraint("patient_id", "source", "external_id", name="uq_measurement_source_ref"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    systolic: Mapped[int] = mapped_column(Integer)
    diastolic: Mapped[int] = mapped_column(Integer)
    pulse: Mapped[int | None] = mapped_column(Integer, nullable=True)
    measured_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    source: Mapped[str] = mapped_column(String(16))  # manual | device | imported | simulated
    source_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)  # device id, file, scenario
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)  # for de-duplication
    context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    validation_status: Mapped[str] = mapped_column(String(16))  # valid | questionable
    validation_notes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))


class SymptomReport(Base):
    __tablename__ = "symptom_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    symptoms: Mapped[list] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    measurement_id: Mapped[int | None] = mapped_column(ForeignKey("measurements.id"), nullable=True)
    reported_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    level: Mapped[str] = mapped_column(String(16))  # notice | trend | severe | emergency
    rule_id: Mapped[str] = mapped_column(String(16))
    reason_text: Mapped[str] = mapped_column(Text)
    next_step_text: Mapped[str] = mapped_column(Text)
    measurement_id: Mapped[int | None] = mapped_column(ForeignKey("measurements.id"), nullable=True)
    symptom_report_id: Mapped[int | None] = mapped_column(ForeignKey("symptom_reports.id"), nullable=True)
    state: Mapped[str] = mapped_column(String(16), default="new")
    persistent: Mapped[bool] = mapped_column(Boolean, default=False)
    triggered_at: Mapped[datetime] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    events: Mapped[list["AlertEvent"]] = relationship(order_by="AlertEvent.id")


class AlertEvent(Base):
    """Append-only audit trail for alerts."""
    __tablename__ = "alert_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id"), index=True)
    type: Mapped[str] = mapped_column(String(24))  # state_change | level_raised | measurement_attached | note
    from_state: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_state: Mapped[str | None] = mapped_column(String(16), nullable=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_role: Mapped[str] = mapped_column(String(16))  # patient | doctor | system
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    measurement_id: Mapped[int | None] = mapped_column(ForeignKey("measurements.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
