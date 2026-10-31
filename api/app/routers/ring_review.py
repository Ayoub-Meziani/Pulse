"""Doctor screens for the ring ML outputs: flags and live-v1 early warnings, weekly reports, personal bands.

Assigned doctor only (patients, other doctors and admin: 403, decision M4); 404 feature_disabled unless the server
sets PULSE_SERVE_RING_ML (proposed decision D26). Advisory: never an alert, never patient guidance.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ..auth import CurrentUser, current_user
from ..db import require_session
from ..errors import AUTH_RESPONSES
from ..permissions import require_assigned_doctor
from ..schemas import (BandApproveIn, BandOut, FlagKind, FlagReviewIn, FlagReviewStatus, ReportReviewIn,
                       WearableFlagOut, WeeklyReportOut)
from ..services import patient_data, ring_review

router = APIRouter(tags=["ring review"], responses=AUTH_RESPONSES, dependencies=[Depends(current_user)])


def _today(request: Request, db: Session, patient_id: UUID):
    return patient_data.local_today(db, patient_id, request.app.state.clock())


@router.get("/patients/{patient_id}/wearable-flags", response_model=list[WearableFlagOut],
            summary="Assigned doctor: ring flags and live early warnings, newest first (advisory)")
def list_flags(patient_id: UUID, request: Request, kind: FlagKind | None = None,
               review_status: FlagReviewStatus | None = None, limit: int = Query(100, ge=1, le=500),
               user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    ring_review.require_enabled(request.app.state.settings)
    require_assigned_doctor(db, user, patient_id)
    return ring_review.list_flags(db, patient_id, kind, review_status, limit)


@router.post("/wearable-flags/{flag_id}/review", response_model=WearableFlagOut,
             summary="Assigned doctor: confirm or dismiss a flag (the first reviewer's decision stands)")
def review_flag(flag_id: UUID, body: FlagReviewIn, request: Request,
                user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    ring_review.require_enabled(request.app.state.settings)
    flag = ring_review.get_flag(db, flag_id)
    require_assigned_doctor(db, user, flag.patient_id)
    return ring_review.review_flag(db, flag, user, body, request.app.state.clock())


@router.get("/patients/{patient_id}/weekly-reports", response_model=list[WeeklyReportOut],
            summary="Assigned doctor: weekly reports, newest week first")
def list_reports(patient_id: UUID, request: Request, limit: int = Query(8, ge=1, le=52),
                 user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    ring_review.require_enabled(request.app.state.settings)
    require_assigned_doctor(db, user, patient_id)
    today, served = _today(request, db, patient_id), request.app.state.settings.ml_model_version
    return [ring_review.report_out(r, served, today) for r in ring_review.list_reports(db, patient_id, limit)]


@router.post("/weekly-reports/{report_id}/review", response_model=WeeklyReportOut,
             summary="Assigned doctor: mark a weekly report reviewed, with an optional comment")
def review_report(report_id: UUID, body: ReportReviewIn, request: Request,
                  user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    ring_review.require_enabled(request.app.state.settings)
    report = ring_review.get_report(db, report_id)
    require_assigned_doctor(db, user, report.patient_id)
    report = ring_review.review_report(db, report, user, body, request.app.state.clock())
    return ring_review.report_out(report, request.app.state.settings.ml_model_version,
                                  _today(request, db, report.patient_id))


@router.get("/patients/{patient_id}/bands", response_model=list[BandOut],
            summary="Assigned doctor: personal ring ranges (proposed first, then active)")
def list_bands(patient_id: UUID, request: Request, user: CurrentUser = Depends(current_user),
               db: Session = Depends(require_session)):
    ring_review.require_enabled(request.app.state.settings)
    require_assigned_doctor(db, user, patient_id)
    return ring_review.list_bands(db, patient_id)


@router.post("/bands/{band_id}/approve", response_model=BandOut,
             summary="Assigned doctor: activate a proposed range, optionally edited; the previous one is superseded")
def approve_band(band_id: UUID, body: BandApproveIn, request: Request,
                 user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    ring_review.require_enabled(request.app.state.settings)
    band = ring_review.get_band(db, band_id)
    require_assigned_doctor(db, user, band.patient_id)
    return ring_review.approve_band(db, band, user, body)


@router.post("/bands/{band_id}/reject", response_model=BandOut, summary="Assigned doctor: reject a proposed range")
def reject_band(band_id: UUID, request: Request, user: CurrentUser = Depends(current_user),
                db: Session = Depends(require_session)):
    ring_review.require_enabled(request.app.state.settings)
    band = ring_review.get_band(db, band_id)
    require_assigned_doctor(db, user, band.patient_id)
    return ring_review.reject_band(db, band)
