"""Doctor notes. The note text is private to the patient's actively assigned doctors.

The patient sees only the advice and follow-up date of notes that have one (note = null); a note
without either is not shown to the patient at all. Unassigned or formerly assigned doctors and
admin get 403. Notes are never read by the emergency card, events, alerts or summaries.
The database audit trigger records every insert/update with the doctor as actor.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..auth import CurrentUser
from ..models import DoctorNote, Profile
from ..schemas import NoteIn, NoteOut


def _out(note: DoctorNote, doctor_name: str, private: bool) -> NoteOut:
    return NoteOut(id=note.id, doctor_id=note.doctor_id, doctor_name=doctor_name, created_at=note.created_at,
                   note=note.note if private else None, advice=note.advice, follow_up_at=note.follow_up_at)


def create_note(db: Session, doctor: CurrentUser, patient_id: UUID, data: NoteIn) -> NoteOut:
    note = DoctorNote(doctor_id=doctor.id, patient_id=patient_id, note=data.note, advice=data.advice,
                      follow_up_at=data.follow_up_at)
    db.add(note)
    db.commit()
    return _out(note, db.get(Profile, doctor.id).display_name, private=True)


def list_notes(db: Session, patient_id: UUID, private: bool) -> list[NoteOut]:
    q = (select(DoctorNote, Profile.display_name).join(Profile, Profile.id == DoctorNote.doctor_id)
         .where(DoctorNote.patient_id == patient_id))
    if not private:
        q = q.where(or_(DoctorNote.advice.is_not(None), DoctorNote.follow_up_at.is_not(None)))
    rows = db.execute(q.order_by(DoctorNote.created_at.desc(), DoctorNote.id)).all()
    return [_out(n, name, private) for n, name in rows]
