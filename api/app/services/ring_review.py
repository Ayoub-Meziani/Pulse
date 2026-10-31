"""The assigned doctor's view of the ring ML outputs: flags (including live-v1 early warnings), weekly reports and
personal bands, written by the offline jobs in ml/ (migrations M7, M9).

Doctor only (decision M4: patients never see model output). Advisory: nothing here is read by the rules, alerts or
emergency guidance, and nothing notifies anyone. Served only when settings.serve_ring_ml is on (proposed D26):
the retrained models need review before serving (D22).
"""
from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..auth import CurrentUser
from ..config import Settings
from ..errors import ApiError
from ..models import PatientBand, WearableFlag, WeeklyReport
from ..schemas import (BandApproveIn, BandOut, FlagReviewIn, ReportReviewIn, WearableFlagOut, WeeklyReportOut)

BAND_ORDER = {"proposed": 0, "active": 1, "superseded": 2, "rejected": 3}


def require_enabled(settings: Settings) -> None:
    if not settings.serve_ring_ml:
        raise ApiError(404, "feature_disabled", "Ring model outputs are not served on this server.")


def _float(v) -> float | None:
    return float(v) if v is not None else None


# ---------------------------------------------------------------- flags
def flag_out(f: WearableFlag) -> WearableFlagOut:
    return WearableFlagOut(id=f.id, patient_id=f.patient_id, metric=f.metric, kind=f.kind, window_kind=f.window_kind,
                           window_start=f.window_start, window_end=f.window_end, value=_float(f.value),
                           score=_float(f.score), reference_basis=f.reference_basis, band_id=f.band_id,
                           model_version=f.model_version, review_status=f.review_status, reviewed_at=f.reviewed_at,
                           review_note=f.review_note, created_at=f.created_at)


def list_flags(db: Session, patient_id: UUID, kind: str | None, review_status: str | None,
               limit: int) -> list[WearableFlagOut]:
    q = select(WearableFlag).where(WearableFlag.patient_id == patient_id)
    if kind:
        q = q.where(WearableFlag.kind == kind)
    if review_status:
        q = q.where(WearableFlag.review_status == review_status)
    q = q.order_by(WearableFlag.window_start.desc(), WearableFlag.created_at.desc()).limit(limit)
    return [flag_out(f) for f in db.scalars(q)]


def get_flag(db: Session, flag_id: UUID) -> WearableFlag:
    flag = db.get(WearableFlag, flag_id)
    if flag is None:
        raise ApiError(404, "not_found", "Flag not found.")
    return flag


def _already_reviewed(reviewed_by: UUID | None, user: CurrentUser) -> None:
    """The first reviewer's decision stands (as the database policies say for doctors); they may update it."""
    if reviewed_by is not None and reviewed_by != user.id:
        raise ApiError(409, "already_reviewed", "Another doctor already reviewed this.")


def review_flag(db: Session, flag: WearableFlag, user: CurrentUser, body: FlagReviewIn,
                now: datetime) -> WearableFlagOut:
    _already_reviewed(flag.reviewed_by, user)
    flag.review_status, flag.reviewed_by, flag.reviewed_at = body.review_status, user.id, now
    flag.review_note = body.review_note.strip() if body.review_note and body.review_note.strip() else None
    db.commit()
    return flag_out(flag)


# ---------------------------------------------------------------- weekly reports
def report_out(r: WeeklyReport, served_model: str, today: date) -> WeeklyReportOut:
    """The summary is passed through except the free-text reference line, and an estimate from a model the API does
    not serve (or an old one) is hidden, as /predictions/latest does."""
    summary = {k: v for k, v in (r.summary or {}).items() if k != "reference"}
    estimate = summary.get("mbp_estimate")
    if estimate is not None:
        served = (r.model_versions or {}).get("mbp") == served_model
        target = estimate.get("target_date") if isinstance(estimate, dict) else None
        if not (served and target and date.fromisoformat(target) >= today):
            summary["mbp_estimate"] = None
    return WeeklyReportOut(id=r.id, patient_id=r.patient_id, week_start=r.week_start,
                           home_bp_category=r.home_bp_category, control_status=r.control_status,
                           next_week_above_target_prob=_float(r.next_week_above_target_prob),
                           model_versions=r.model_versions or {}, summary=summary, status=r.status,
                           reviewed_at=r.reviewed_at, doctor_comment=r.doctor_comment, created_at=r.created_at,
                           updated_at=r.updated_at)


def list_reports(db: Session, patient_id: UUID, limit: int) -> list[WeeklyReport]:
    return list(db.scalars(select(WeeklyReport).where(WeeklyReport.patient_id == patient_id)
                           .order_by(WeeklyReport.week_start.desc()).limit(limit)))


def get_report(db: Session, report_id: UUID) -> WeeklyReport:
    report = db.get(WeeklyReport, report_id)
    if report is None:
        raise ApiError(404, "not_found", "Report not found.")
    return report


def review_report(db: Session, report: WeeklyReport, user: CurrentUser, body: ReportReviewIn,
                  now: datetime) -> WeeklyReport:
    _already_reviewed(report.reviewed_by, user)
    report.status, report.reviewed_by, report.reviewed_at = "reviewed", user.id, now
    report.doctor_comment = body.doctor_comment.strip() if body.doctor_comment and body.doctor_comment.strip() else None
    db.commit()
    db.refresh(report)  # updated_at is set by the database trigger
    return report


# ---------------------------------------------------------------- personal bands
def band_out(b: PatientBand) -> BandOut:
    return BandOut(id=b.id, patient_id=b.patient_id, metric=b.metric, statistic=b.statistic, low=float(b.low),
                   high=float(b.high), basis=b.basis, status=b.status, proposed_model_version=b.proposed_model_version,
                   approved_at=b.approved_at, effective_from=b.effective_from, supersedes_id=b.supersedes_id,
                   created_at=b.created_at)


def list_bands(db: Session, patient_id: UUID) -> list[BandOut]:
    bands = db.scalars(select(PatientBand).where(PatientBand.patient_id == patient_id)
                       .order_by(PatientBand.created_at.desc()))
    return [band_out(b) for b in sorted(bands, key=lambda b: BAND_ORDER.get(b.status, 9))]


def get_band(db: Session, band_id: UUID) -> PatientBand:
    band = db.get(PatientBand, band_id)
    if band is None:
        raise ApiError(404, "not_found", "Band not found.")
    return band


def _proposed_only(band: PatientBand, to: str) -> None:
    if band.status != "proposed":
        raise ApiError(409, "invalid_transition", f"A band that is {band.status} cannot become {to}.",
                       {"from": band.status, "to": to})


def approve_band(db: Session, band: PatientBand, user: CurrentUser, body: BandApproveIn) -> BandOut:
    """private.approve_band supersedes the active band and activates this one in one step; it checks that the
    signed-in doctor (request JWT claims) is the approving one and is actively assigned."""
    _proposed_only(band, "active")
    db.execute(text("select private.approve_band(cast(:band as uuid), cast(:doctor as uuid), "
                    "cast(:low as numeric), cast(:high as numeric))"),
               {"band": str(band.id), "doctor": str(user.id), "low": body.low, "high": body.high})
    db.expire_all()
    approved = db.get(PatientBand, band.id)
    db.commit()
    return band_out(approved)


def reject_band(db: Session, band: PatientBand) -> BandOut:
    _proposed_only(band, "rejected")
    band.status = "rejected"
    db.commit()
    return band_out(band)
