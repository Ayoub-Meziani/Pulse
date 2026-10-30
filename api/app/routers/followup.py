"""Doctor notes (private to assigned doctors; the patient sees advice only) and the patient journal."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ..auth import CurrentUser, current_user
from ..db import require_session
from ..errors import AUTH_RESPONSES
from ..permissions import is_assigned, require_assigned_doctor, require_patient_access
from ..schemas import JournalCategory, JournalIn, JournalOut, NoteIn, NoteOut
from ..services import journal, notes

router = APIRouter(tags=["follow-up"], responses=AUTH_RESPONSES, dependencies=[Depends(current_user)])


@router.get("/patients/{patient_id}/notes", response_model=list[NoteOut],
            summary="Doctor sees full notes; the patient sees advice and follow-up date only")
def list_notes(patient_id: UUID, user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    require_patient_access(db, user, patient_id)  # the patient or an actively assigned doctor; admin: 403
    private = user.role == "doctor" and is_assigned(db, user.id, patient_id)
    return notes.list_notes(db, patient_id, private=private)


@router.post("/patients/{patient_id}/notes", response_model=NoteOut, status_code=201,
             summary="Assigned doctor only")
def create_note(patient_id: UUID, body: NoteIn, user: CurrentUser = Depends(current_user),
                db: Session = Depends(require_session)):
    require_assigned_doctor(db, user, patient_id)
    return notes.create_note(db, user, patient_id, body)


@router.get("/patients/{patient_id}/journal", response_model=list[JournalOut],
            summary="Journal, newest first (patient or assigned doctor); optional category filter")
def list_journal(patient_id: UUID, category: JournalCategory | None = None, limit: int = Query(100, ge=1, le=500),
                 user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    require_patient_access(db, user, patient_id)  # the patient or an actively assigned doctor; admin: 403
    return journal.list_entries(db, patient_id, category, limit)


@router.post("/patients/{patient_id}/journal", response_model=JournalOut, status_code=201,
             summary="Patient only: add an entry (symptoms, food, activity, medication, question for the doctor)")
def create_journal(patient_id: UUID, body: JournalIn, user: CurrentUser = Depends(current_user),
                   db: Session = Depends(require_session)):
    require_patient_access(db, user, patient_id, write=True)
    return journal.create_entry(db, user, body)


@router.post("/journal/{entry_id}/review", response_model=JournalOut,
             summary="Assigned doctor: mark an entry read (repeating it keeps the first review)")
def review_journal(entry_id: UUID, request: Request, user: CurrentUser = Depends(current_user),
                   db: Session = Depends(require_session)):
    entry = journal.get_entry(db, entry_id)
    require_assigned_doctor(db, user, entry.patient_id)
    return journal.review_entry(db, entry, user, request.app.state.clock())
