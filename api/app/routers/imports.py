"""Patient file imports: a cuff export (readings, through the same rules as manual entry for fresh rows) and a
ring export (never read by any rule). CSV text in a JSON body; see services/imports.py for the rules (D26)."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..auth import CurrentUser, current_user
from ..db import require_session
from ..errors import AUTH_RESPONSES
from ..permissions import require_patient_access
from ..schemas import (ImportResult, ImportStatusCounts, MeasurementOut, ReadingsImportIn, RejectedRow,
                       RingImportIn, RingImportResult, SimulatedPreview)
from ..services import imports
from .alerts import alert_out
from .patients import evaluation_out

router = APIRouter(tags=["imports"], responses=AUTH_RESPONSES, dependencies=[Depends(current_user)])


@router.post("/patients/{patient_id}/imports/readings", response_model=ImportResult, status_code=201,
             summary="Patient: import a cuff CSV; fresh measured rows go through the reading rules, simulated never alert")
def import_readings(patient_id: UUID, body: ReadingsImportIn, request: Request,
                    user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    require_patient_access(db, user, patient_id, write=True)
    r = imports.import_readings(db, user, body, request.app.state.clock(), request.app.state.settings.demo_mode)
    counts = ImportStatusCounts()
    for m in r.inserted:
        setattr(counts, m.validation_status, getattr(counts, m.validation_status) + 1)
    return ImportResult(
        batch_id=r.batch.id, rows_total=r.rows_total, inserted=len(r.inserted), duplicates=r.duplicates,
        rejected=[RejectedRow(**x) for x in r.rejected], by_status=counts, historical=r.historical,
        past_severe=r.past_severe, alerts=[alert_out(a) for a in r.alerts],
        measurement=MeasurementOut.model_validate(r.measurement) if r.measurement else None,
        evaluation=evaluation_out(r.evaluation) if r.evaluation else None,
        simulated_preview=[SimulatedPreview(measured_at=m.measured_at, level=ev.level, rule_id=ev.rule_id)
                           for m, ev in r.preview],
        next_step=r.next_step)


@router.post("/patients/{patient_id}/imports/ring", response_model=RingImportResult, status_code=201,
             summary="Patient: import a ring CSV (heart rate, HRV, SpO2, skin temperature); never raises an alert")
def import_ring(patient_id: UUID, body: RingImportIn, request: Request,
                user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    require_patient_access(db, user, patient_id, write=True)
    r = imports.import_ring(db, user, body, request.app.state.settings.demo_mode)
    return RingImportResult(device_id=r.device_id, rows_total=r.rows_total, inserted_by_metric=r.inserted_by_metric,
                            duplicates=r.duplicates, rejected=[RejectedRow(**x) for x in r.rejected],
                            next_step=r.next_step)
