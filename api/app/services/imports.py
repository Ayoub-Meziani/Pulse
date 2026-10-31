"""File imports by the patient: blood-pressure readings and ring samples (proposed decision D26).

Readings: one ingestion batch per file; the same file again is 409 already_imported. Rows identical to a stored
reading are skipped. Rows measured within FRESH_WINDOW go through exactly the steps of a manual reading
(services/measurements.record_manual_reading), oldest first, so a recheck in the same file joins the episode.
Older rows are history only: a reading from last week must never be answered with "measure again in 60 s".
Rows declared simulated never create or change an alert (generated data never decides a clinical alert, D19);
the rules' result is returned as a preview. Imports cannot start an emergency escalation: the reading rules never
return the emergency level, and the symptom check stays the patient's own step (D25).

Ring samples: stored on the patient's ring and never read by any rule (D18).
"""
from __future__ import annotations

import dataclasses
import hashlib
from collections import Counter
from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from .. import vocab
from ..analysis import evaluate_measurement, evaluate_trend, texts
from ..analysis.rules import is_severe
from ..analysis.types import Evaluation
from ..auth import CurrentUser
from ..errors import ApiError
from ..models import Alert, Device, IngestionBatch, Measurement, WearableSample
from ..schemas import ReadingsImportIn, RingImportIn
from .alerts import active_alerts, apply_evaluation
from .csv_import import CsvFormatError, Rejection, declares_simulated, parse_bp, parse_ring
from .measurements import current_target, invalid_evaluation, recent_readings, to_reading

# Same as the symptom check's window for raising a severe alert (analysis/rules.evaluate_symptoms), so the symptom
# step that follows an import attaches to the alert the import raised. Proposed decision D26.
FRESH_WINDOW = timedelta(hours=1)
SIMULATED = vocab.SIMULATED_PROVENANCE


@dataclasses.dataclass
class ReadingsImport:
    batch: IngestionBatch
    rows_total: int
    inserted: list[Measurement]
    duplicates: int
    rejected: list[dict]
    historical: int
    past_severe: int
    alerts: list[Alert]
    measurement: Measurement | None
    evaluation: Evaluation | None
    preview: list[tuple[Measurement, Evaluation]]
    next_step: str


@dataclasses.dataclass
class RingImport:
    device_id: UUID
    rows_total: int
    inserted_by_metric: dict[str, int]
    duplicates: int
    rejected: list[dict]
    next_step: str


def _invalid_file(code: str, message: str, field: str = "csv") -> ApiError:
    return ApiError(422, "invalid_file", message, [{"field": field, "code": code, "message": message}])


def _zone(tz: str | None, user: CurrentUser) -> tuple[ZoneInfo, str]:
    name = tz or user.timezone
    try:
        return ZoneInfo(name), name
    except (ZoneInfoNotFoundError, ValueError):
        raise _invalid_file("invalid_timezone", "Use an IANA time zone such as Africa/Algiers.", "tz") from None


def _check_label(text: str, simulated: bool, demo_mode: bool) -> None:
    """Never let generated data pass as real, and accept generated data only on a demo server."""
    if simulated and not demo_mode:
        raise _invalid_file("simulated_not_allowed", "Simulated data can only be imported on a demo server.",
                            "provenance")
    if not simulated and declares_simulated(text):
        raise _invalid_file("file_is_simulated", "This file says it is simulated: import it as simulated.",
                            "provenance")


def _rejected(rejections: list[Rejection]) -> list[dict]:
    return [{"row": r.row, "reasons": list(r.reasons)} for r in rejections]


def _refused(row: int, exc: IntegrityError | DataError) -> dict:
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
    return {"row": row, "reasons": [f"refused_by_database:{getattr(diag, 'constraint_name', None) or sqlstate}"]}


def import_readings(db: Session, user: CurrentUser, body: ReadingsImportIn, now: datetime,
                    demo_mode: bool) -> ReadingsImport:
    simulated = body.provenance == SIMULATED
    _check_label(body.csv, simulated, demo_mode)
    tz, tz_name = _zone(body.tz, user)
    try:
        rows, parse_rejections = parse_bp(body.csv, tz)
    except CsvFormatError as e:
        raise _invalid_file(e.code, e.message) from None
    rejected = _rejected(parse_rejections)

    batch = IngestionBatch(patient_id=user.id, source="csv_import", file_name=body.file_name,
                           file_sha256=hashlib.sha256(body.csv.encode("utf-8")).hexdigest(), created_by=user.id)
    try:
        with db.begin_nested():  # a savepoint keeps the request's JWT claims if the file was already imported
            db.add(batch)
            db.flush()
    except IntegrityError:
        raise ApiError(409, "already_imported", "This file was already imported.") from None

    # Exact duplicates of stored readings (an overlapping export) or within the file are skipped; near-duplicates
    # are inserted and flagged possible_duplicate by the database, which keeps them out of the alerts.
    rows.sort(key=lambda r: r.measured_at)
    stored = set()
    if rows:
        stored = set(db.execute(select(Measurement.measured_at, Measurement.systolic, Measurement.diastolic,
                                       Measurement.pulse)
                                .where(Measurement.patient_id == user.id,
                                       Measurement.measured_at >= rows[0].measured_at,
                                       Measurement.measured_at <= rows[-1].measured_at)).all())
    inserted, duplicates = [], 0
    for r in rows:
        key = (r.measured_at, r.systolic, r.diastolic, r.pulse)
        if key in stored:
            duplicates += 1
            continue
        stored.add(key)
        m = Measurement(patient_id=user.id, source="csv_import", provenance=body.provenance,
                        method=vocab.MANUAL_METHOD, systolic=r.systolic, diastolic=r.diastolic, pulse=r.pulse,
                        measured_at=r.measured_at, measured_tz=tz_name, body_position=r.position, arm=r.arm,
                        context=r.context, created_by=user.id, ingestion_batch_id=batch.id)
        try:
            with db.begin_nested():  # one refused row must not abort the import
                db.add(m)
                db.flush()
        except (IntegrityError, DataError) as e:
            rejected.append(_refused(r.row, e))
            continue
        inserted.append(m)

    fresh = [m for m in inserted if m.measured_at >= now - FRESH_WINDOW]
    historical = [m for m in inserted if m.measured_at < now - FRESH_WINDOW]
    target = current_target(db, user.id)
    alerts: dict = {}
    preview: list[tuple[Measurement, Evaluation]] = []
    best: tuple[int, datetime, Measurement, Evaluation] | None = None
    symptom_check = False
    newest_real: Measurement | None = None
    for m in fresh:  # oldest first, the same steps as record_manual_reading
        if m.validation_status == "invalid":
            ev = invalid_evaluation(m)
        else:
            ev = evaluate_measurement(to_reading(m), target, active_alerts(db, user.id))
        if m.provenance == SIMULATED:
            preview.append((m, ev))
            continue
        if m.validation_status != "invalid" and "possible_duplicate" not in m.quality_flags:
            if (alert := apply_evaluation(db, user.id, ev, measurement_id=m.id)) is not None:
                alerts[alert.id] = alert
            newest_real = m
        symptom_check = symptom_check or ev.requires_symptom_check
        candidate = (vocab.LEVEL_RANK[ev.level], m.measured_at, m, ev)
        if best is None or candidate[:2] >= best[:2]:
            best = candidate
    if newest_real is not None:  # the trend rule runs once per file, like once per manual reading
        trend = evaluate_trend(recent_readings(db, user.id, now), target, active_alerts(db, user.id), now)
        if trend is not None and (alert := apply_evaluation(db, user.id, trend, measurement_id=newest_real.id)):
            alerts[alert.id] = alert

    past_severe = sum(1 for m in historical if m.provenance != SIMULATED and m.validation_status != "invalid"
                      and is_severe(m.systolic, m.diastolic))
    evaluation = dataclasses.replace(best[3], requires_symptom_check=symptom_check) if best else None
    if evaluation is not None:
        next_step = evaluation.next_step
    elif past_severe:
        next_step = texts.NEXT_STEP["IMPORT-PAST-SEVERE"]
    elif preview:
        next_step = texts.NEXT_STEP["IMPORT-SIMULATED"]
    elif inserted:
        next_step = texts.NEXT_STEP["IMPORT-HISTORY"]
    else:
        next_step = texts.NEXT_STEP["IMPORT-NOTHING"]

    batch.rows_total = len(rows) + len(parse_rejections)
    batch.rows_inserted, batch.rows_duplicate = len(inserted), duplicates
    batch.rows_rejected, batch.rejections = len(rejected), rejected
    db.commit()
    return ReadingsImport(batch=batch, rows_total=batch.rows_total, inserted=inserted, duplicates=duplicates,
                          rejected=rejected, historical=len(historical), past_severe=past_severe,
                          alerts=list(alerts.values()), measurement=best[2] if best else None,
                          evaluation=evaluation, preview=preview, next_step=next_step)


def ring_device(db: Session, patient_id: UUID, simulated: bool) -> Device:
    """The patient's ring: their first simulator for generated data, their first real wearable otherwise.
    Created when missing (a simulator is always labelled simulated, by database rule)."""
    kind = "simulator" if simulated else "wearable"
    device = db.scalar(select(Device).where(Device.patient_id == patient_id, Device.device_type == kind)
                       .order_by(Device.created_at, Device.id).limit(1))
    if device is None:
        device = Device(patient_id=patient_id, device_type=kind, bp_capability="simulated" if simulated else "none",
                        manufacturer="PULSE" if simulated else None, model="Simulateur" if simulated else None,
                        label="Bague simulée (import)" if simulated else "Bague (import)")
        db.add(device)
        db.flush()
    return device


def import_ring(db: Session, user: CurrentUser, body: RingImportIn, demo_mode: bool) -> RingImport:
    simulated = body.source == "simulated"
    _check_label(body.csv, simulated, demo_mode)
    tz, _ = _zone(body.tz, user)
    try:
        rows, parse_rejections = parse_ring(body.csv, tz)
    except CsvFormatError as e:
        raise _invalid_file(e.code, e.message) from None
    rejected = _rejected(parse_rejections)
    device = ring_device(db, user.id, simulated)

    # A sample already stored for this ring (same metric at the same instant, or the same export id) is skipped,
    # so re-importing a file, or an overlapping export, adds nothing.
    stored_at, stored_ids = set(), set()
    if rows:
        start, end = min(r.measured_at for r in rows), max(r.measured_at for r in rows)
        stored_at = set(db.execute(select(WearableSample.metric, WearableSample.measured_at)
                                   .where(WearableSample.device_id == device.id,
                                          WearableSample.measured_at >= start,
                                          WearableSample.measured_at <= end)).all())
        ids = {r.external_id for r in rows if r.external_id}
        if ids:
            stored_ids = set(db.scalars(select(WearableSample.external_id)
                                        .where(WearableSample.device_id == device.id,
                                               WearableSample.external_id.in_(ids))))
    inserted: Counter[str] = Counter()
    duplicates = 0
    for r in rows:
        if (r.metric, r.measured_at) in stored_at or (r.external_id and r.external_id in stored_ids):
            duplicates += 1
            continue
        stored_at.add((r.metric, r.measured_at))
        if r.external_id:
            stored_ids.add(r.external_id)
        sample = WearableSample(patient_id=user.id, device_id=device.id, metric=r.metric, value=r.value,
                                unit=r.unit, measured_at=r.measured_at, source=body.source,
                                external_id=r.external_id)
        try:
            with db.begin_nested():  # e.g. a value outside the plausible range is refused by the database
                db.add(sample)
                db.flush()
        except (IntegrityError, DataError) as e:
            rejected.append(_refused(r.row, e))
            continue
        inserted[r.metric] += 1
    db.commit()
    return RingImport(device_id=device.id, rows_total=len(rows) + len(parse_rejections),
                      inserted_by_metric=dict(inserted), duplicates=duplicates, rejected=rejected,
                      next_step=texts.NEXT_STEP["IMPORT-RING"])
