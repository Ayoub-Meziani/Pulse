"""Step 6: doctor patient list, summary, profile, trusted contacts, care plan, emergency card.

Privacy rules applied here: doctor notes are never read by this module; the emergency card carries
only what a bystander or responder needs (no M6 risk-factor fields, no wearable data, no notes);
trusted contacts are only stored with the patient's confirmation that the contact agreed.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import vocab
from ..analysis import compute_summary
from ..auth import CurrentUser
from ..errors import ApiError
from ..models import Alert, Assignment, AuthUser, CarePlan, Measurement, PatientProfile, Profile, TrustedContact
from ..schemas import (CarePlanIn, CarePlanOut, ContactBrief, EmergencyCardOut, LastReading, MeasurementOut,
                       PatientListItem, ProfileIn, ProfileOut, SummaryOut, TargetOut, TrustedContactIn,
                       TrustedContactOut, TrustedContactPatch)
from .alerts import OUR_CLASSES
from .measurements import current_target, to_reading


def _zone(tz: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("Africa/Algiers")


def _check_timezone(tz: str) -> None:
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise ApiError(422, "validation_failed", "Invalid time zone.",
                       [{"field": "timezone", "code": "invalid_timezone",
                         "message": "Use an IANA time zone such as Africa/Algiers."}]) from None


def age_from(birth_year: int | None, today: date) -> int | None:
    return today.year - birth_year if birth_year else None


def _profile(db: Session, patient_id: UUID) -> Profile:
    p = db.get(Profile, patient_id)
    if p is None or p.role != "patient":
        raise ApiError(404, "not_found", "Patient not found.")
    return p


def _latest_usable(db: Session, patient_id: UUID) -> Measurement | None:
    return db.scalar(select(Measurement).where(Measurement.patient_id == patient_id,
                                               Measurement.validation_status != "invalid")
                     .order_by(Measurement.measured_at.desc(), Measurement.created_at.desc()).limit(1))


# ---------------------------------------------------------------- summary
def summary(db: Session, patient_id: UUID, now: datetime) -> SummaryOut:
    tz = _profile(db, patient_id).timezone
    zone = _zone(tz)
    rows = list(db.scalars(select(Measurement).where(Measurement.patient_id == patient_id,
                                                     Measurement.measured_at > now - timedelta(days=30),
                                                     Measurement.measured_at <= now)))
    usable = [to_reading(m) for m in rows if m.validation_status != "invalid"]
    # Local time so "days with a reading" counts the patient's days, not UTC days.
    usable = [r.__class__(r.systolic, r.diastolic, r.measured_at.astimezone(zone), r.pulse, r.validation_status, r.id)
              for r in usable]
    target = current_target(db, patient_id)
    s = compute_summary(usable, target, now.astimezone(zone))
    week = [m for m in rows if m.measured_at > now - timedelta(days=7)]
    return SummaryOut(
        window_days=s.window_days, timezone=tz, count_7d=s.count_7d,
        count_needs_review_7d=sum(m.validation_status == "needs_review" for m in week),
        count_invalid_7d=sum(m.validation_status == "invalid" for m in week),
        avg_systolic_7d=s.avg_systolic_7d, avg_diastolic_7d=s.avg_diastolic_7d,
        avg_systolic_30d=s.avg_systolic_30d, avg_diastolic_30d=s.avg_diastolic_30d,
        max_systolic_7d=s.max_systolic_7d, max_diastolic_7d=s.max_diastolic_7d,
        pct_above_target_7d=s.pct_above_target_7d, days_with_reading_7d=s.days_with_reading_7d,
        trend=s.trend, last_measured_at=s.last_measured_at,
        target=TargetOut(systolic=target.systolic, diastolic=target.diastolic, is_default=target.is_default))


# ---------------------------------------------------------------- doctor list
def doctor_patient_list(db: Session, doctor: CurrentUser, now: datetime) -> list[PatientListItem]:
    patients = db.execute(
        select(Profile, PatientProfile.birth_year)
        .join(Assignment, Assignment.patient_id == Profile.id)
        .outerjoin(PatientProfile, PatientProfile.user_id == Profile.id)
        .where(Assignment.doctor_id == doctor.id, Assignment.status == "active", Profile.role == "patient")).all()
    items = []
    for p, birth_year in patients:
        actives = db.execute(select(Alert.alert_class, func.count()).where(
            Alert.patient_id == p.id, Alert.status.in_(vocab.ACTIVE_ALERT_STATUSES),
            Alert.alert_class.in_(OUR_CLASSES)).group_by(Alert.alert_class)).all()
        levels = [vocab.ALERT_CLASS_TO_LEVEL[c] for c, _ in actives]
        latest = _latest_usable(db, p.id)
        s = summary(db, p.id, now)
        items.append(PatientListItem(
            id=p.id, full_name=p.display_name, age=age_from(birth_year, now.astimezone(_zone(p.timezone)).date()),
            highest_active_alert=max(levels, key=vocab.LEVEL_RANK.get, default=None),
            active_alert_count=sum(n for _, n in actives),
            latest_measurement=MeasurementOut.model_validate(latest) if latest else None,
            last_measured_at=latest.measured_at if latest else None,
            avg_systolic_7d=s.avg_systolic_7d, avg_diastolic_7d=s.avg_diastolic_7d))
    # Most urgent first; among equals, the patient not heard from for longest first (no reading = first).
    items.sort(key=lambda i: (-vocab.LEVEL_RANK[i.highest_active_alert or "none"],
                              i.last_measured_at.timestamp() if i.last_measured_at else float("-inf")))
    return items


# ---------------------------------------------------------------- profile
def get_profile(db: Session, patient_id: UUID, today: date) -> ProfileOut:
    p = _profile(db, patient_id)
    email = db.scalar(select(AuthUser.email).where(AuthUser.id == patient_id)) or ""
    pp = db.get(PatientProfile, patient_id)
    doctor_name = (db.scalar(select(Profile.display_name).where(Profile.id == pp.regular_doctor_id))
                   if pp and pp.regular_doctor_id else None)
    return ProfileOut(full_name=p.display_name, email=email, timezone=p.timezone,
                      birth_year=pp.birth_year if pp else None,
                      relevant_conditions=list(pp.relevant_conditions) if pp else [],
                      allergies=pp.allergies if pp else None, medication_context=pp.medication_context if pp else None,
                      regular_doctor_id=pp.regular_doctor_id if pp else None, regular_doctor_name=doctor_name,
                      regular_clinic=pp.regular_clinic if pp else None,
                      consent_location=pp.consent_location if pp else False)


def put_profile(db: Session, patient: CurrentUser, data: ProfileIn, today: date) -> ProfileOut:
    _check_timezone(data.timezone)
    if data.birth_year is not None and data.birth_year > today.year:
        raise ApiError(422, "validation_failed", "Birth year cannot be in the future.",
                       [{"field": "birth_year", "code": "in_future", "message": "Use your year of birth."}])
    p = _profile(db, patient.id)
    p.display_name, p.timezone = data.full_name.strip(), data.timezone
    pp = db.get(PatientProfile, patient.id)
    if pp is None:
        pp = PatientProfile(user_id=patient.id)
        db.add(pp)
    pp.birth_year, pp.relevant_conditions = data.birth_year, [c.strip() for c in data.relevant_conditions if c.strip()]
    pp.allergies, pp.medication_context = data.allergies, data.medication_context
    pp.regular_clinic, pp.consent_location = data.regular_clinic, data.consent_location
    db.commit()
    return get_profile(db, patient.id, today)


# ---------------------------------------------------------------- trusted contacts
def _contact_out(c: TrustedContact) -> TrustedContactOut:
    return TrustedContactOut(id=c.id, name=c.name, relationship=c.relationship, phone=c.phone,
                             consented_at=c.consented_at, active=c.active)


def list_contacts(db: Session, patient_id: UUID) -> list[TrustedContactOut]:
    q = select(TrustedContact).where(TrustedContact.patient_id == patient_id).order_by(TrustedContact.consented_at)
    return [_contact_out(c) for c in db.scalars(q)]


def add_contact(db: Session, patient: CurrentUser, data: TrustedContactIn, now: datetime) -> TrustedContactOut:
    # contact_consented=True is required by the schema; consented_at records when the patient confirmed it.
    c = TrustedContact(patient_id=patient.id, name=data.name.strip(), relationship=data.relationship,
                       phone=data.phone.strip(), consented_at=now, active=data.active)
    db.add(c)
    db.commit()
    return _contact_out(c)


def own_contact(db: Session, patient: CurrentUser, contact_id: UUID) -> TrustedContact:
    c = db.get(TrustedContact, contact_id)
    if c is None or patient.role != "patient" or c.patient_id != patient.id:
        raise ApiError(404, "not_found", "Contact not found.")  # same answer for someone else's contact
    return c


def patch_contact(db: Session, patient: CurrentUser, contact_id: UUID, data: TrustedContactPatch) -> TrustedContactOut:
    c = own_contact(db, patient, contact_id)
    if data.phone is not None and data.phone.strip() != c.phone:
        # A new number may be a different person, whose consent was never given: add a new contact instead.
        raise ApiError(422, "consent_required", "A new phone number needs the contact's consent.",
                       [{"field": "phone", "code": "consent_required",
                         "message": "Remove this contact and add the new number with contact_consented=true."}])
    if data.name is not None:
        c.name = data.name.strip()
    if data.relationship is not None:
        c.relationship = data.relationship
    if data.active is not None:
        c.active = data.active
    db.commit()
    return _contact_out(c)


def delete_contact(db: Session, patient: CurrentUser, contact_id: UUID) -> None:
    db.delete(own_contact(db, patient, contact_id))  # the patient withdraws the contact; their number is removed
    db.commit()


# ---------------------------------------------------------------- care plan
def get_care_plan(db: Session, patient_id: UUID) -> CarePlanOut:
    _profile(db, patient_id)
    plan = db.scalar(select(CarePlan).where(CarePlan.patient_id == patient_id, CarePlan.status == "active"))
    target = current_target(db, patient_id)
    if plan is None:
        return CarePlanOut(id=None, target_systolic=target.systolic, target_diastolic=target.diastolic,
                           is_default=True, effective_from=None, review_date=None,
                           monitoring_readings_per_day=None, clinician_guidance=None)
    return CarePlanOut(id=plan.id, target_systolic=target.systolic, target_diastolic=target.diastolic,
                       is_default=target.is_default, effective_from=plan.effective_from, review_date=plan.review_date,
                       monitoring_readings_per_day=plan.monitoring_readings_per_day,
                       clinician_guidance=plan.clinician_guidance)


def put_care_plan(db: Session, doctor: CurrentUser, patient_id: UUID, data: CarePlanIn, today: date) -> CarePlanOut:
    if data.target_systolic <= data.target_diastolic:
        raise ApiError(422, "validation_failed", "Systolic target must be above the diastolic target.",
                       [{"field": "target_systolic", "code": "not_above_diastolic", "message": "Check the targets."}])
    if data.review_date is not None and data.review_date < today:
        raise ApiError(422, "validation_failed", "Review date cannot be before today.",
                       [{"field": "review_date", "code": "in_past", "message": "Choose today or a later date."}])
    old = db.scalar(select(CarePlan).where(CarePlan.patient_id == patient_id, CarePlan.status == "active"))
    if old is not None:
        old.status = "superseded"
        db.flush()  # one active plan per patient (unique index): retire the old one first
    db.add(CarePlan(patient_id=patient_id, clinician_id=doctor.id, status="active", effective_from=today,
                    review_date=data.review_date, target_systolic=data.target_systolic,
                    target_diastolic=data.target_diastolic, monitoring_readings_per_day=data.monitoring_readings_per_day,
                    clinician_guidance=data.clinician_guidance.strip(), supersedes_id=old.id if old else None))
    db.commit()
    return get_care_plan(db, patient_id)


# ---------------------------------------------------------------- emergency card
def emergency_card(db: Session, patient_id: UUID, now: datetime) -> EmergencyCardOut:
    p = _profile(db, patient_id)
    pp = db.get(PatientProfile, patient_id)
    contact = db.scalar(select(TrustedContact).where(TrustedContact.patient_id == patient_id,
                                                     TrustedContact.active.is_(True))
                        .order_by(TrustedContact.consented_at).limit(1))
    last = _latest_usable(db, patient_id)
    doctor_name = (db.scalar(select(Profile.display_name).where(Profile.id == pp.regular_doctor_id))
                   if pp and pp.regular_doctor_id else None)
    return EmergencyCardOut(
        full_name=p.display_name, age=age_from(pp.birth_year if pp else None, now.astimezone(_zone(p.timezone)).date()),
        relevant_conditions=list(pp.relevant_conditions) if pp else [],
        allergies=pp.allergies if pp else None, medication_context=pp.medication_context if pp else None,
        primary_contact=ContactBrief(name=contact.name, relationship=contact.relationship, phone=contact.phone)
        if contact else None,
        regular_doctor_name=doctor_name, regular_clinic=pp.regular_clinic if pp else None,
        last_reading=LastReading(systolic=last.systolic, diastolic=last.diastolic, measured_at=last.measured_at,
                                 validation_status=last.validation_status, source=last.source,
                                 provenance=last.provenance) if last else None,
        generated_at=now)


def local_today(db: Session, patient_id: UUID, now: datetime) -> date:
    """The patient's calendar date (their profile time zone), used for plan dates and ages."""
    return now.astimezone(_zone(_profile(db, patient_id).timezone)).date()
