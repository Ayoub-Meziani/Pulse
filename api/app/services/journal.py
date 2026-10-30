"""Patient journal (C §14.1): short entries — symptoms, food, physical activity, medication, a question for the
doctor — that the patient's assigned doctor reads and marks reviewed.

The journal is the patient's own words. PULSE stores it and shows it; it never analyses it, never feeds it to
the rules, alerts or emergency guidance, and never answers with diet, exercise or medication advice (the
doctor answers through a note's `advice`).
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import CurrentUser
from ..errors import ApiError
from ..models import JournalEntry
from ..schemas import JournalIn, JournalOut


def journal_out(e: JournalEntry) -> JournalOut:
    return JournalOut(id=e.id, category=e.category, entry_text=e.entry_text, created_at=e.created_at,
                      doctor_review_status=e.doctor_review_status, reviewed_at=e.reviewed_at)


def create_entry(db: Session, patient: CurrentUser, data: JournalIn) -> JournalOut:
    entry = JournalEntry(patient_id=patient.id, category=data.category, entry_text=data.entry_text.strip())
    if not entry.entry_text:
        raise ApiError(422, "validation_failed", "The entry is empty.",
                       [{"field": "entry_text", "code": "empty", "message": "Write a few words."}])
    db.add(entry)
    db.commit()
    return journal_out(entry)


def list_entries(db: Session, patient_id: UUID, category: str | None, limit: int) -> list[JournalOut]:
    q = select(JournalEntry).where(JournalEntry.patient_id == patient_id)
    if category:
        q = q.where(JournalEntry.category == category)
    rows = db.scalars(q.order_by(JournalEntry.created_at.desc(), JournalEntry.id).limit(limit))
    return [journal_out(e) for e in rows]


def get_entry(db: Session, entry_id: UUID) -> JournalEntry:
    entry = db.get(JournalEntry, entry_id)
    if entry is None:
        raise ApiError(404, "not_found", "Journal entry not found.")
    return entry


def review_entry(db: Session, entry: JournalEntry, doctor: CurrentUser, now: datetime) -> JournalOut:
    """Marks the entry read by an assigned doctor. Repeating it keeps the first review (idempotent)."""
    if entry.doctor_review_status != "reviewed":
        entry.doctor_review_status, entry.reviewed_by, entry.reviewed_at = "reviewed", doctor.id, now
        db.commit()
    return journal_out(entry)
