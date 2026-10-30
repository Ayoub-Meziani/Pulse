"""Doctor notes and the patient journal."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from ..auth import require_token
from ..errors import AUTH_RESPONSES, not_implemented
from ..schemas import JournalIn, JournalOut, NoteIn, NoteOut

router = APIRouter(tags=["follow-up"], responses=AUTH_RESPONSES, dependencies=[Depends(require_token)])


@router.get("/patients/{patient_id}/notes", response_model=list[NoteOut],
            summary="Doctor sees full notes; the patient sees advice and follow-up date only")
def list_notes(patient_id: UUID):
    not_implemented()


@router.post("/patients/{patient_id}/notes", response_model=NoteOut, status_code=201,
             summary="Assigned doctor only")
def create_note(patient_id: UUID, body: NoteIn):
    not_implemented()


@router.get("/patients/{patient_id}/journal", response_model=list[JournalOut], summary="Deferrable")
def list_journal(patient_id: UUID):
    not_implemented()


@router.post("/patients/{patient_id}/journal", response_model=JournalOut, status_code=201,
             summary="Patient only (deferrable)")
def create_journal(patient_id: UUID, body: JournalIn):
    not_implemented()


@router.post("/journal/{entry_id}/review", response_model=JournalOut, summary="Assigned doctor (deferrable)")
def review_journal(entry_id: UUID):
    not_implemented()
