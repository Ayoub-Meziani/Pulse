"""Measurement ingestion.

Adapters normalise source data into `Reading`; `import_readings` stores them as one batch.
Schema/format checks happen here. Plausibility validation is done by the database trigger
(private.validate_measurement) so manual entry, imports and device sync share one policy.

    python -m pulse_data.ingest import-csv --patient amina.demo@pulse.test \
        --file samples/readings_sample.csv --provenance simulated --tz Africa/Algiers

Ring / bracelet samples (heart rate, HRV, SpO2, skin temperature; never blood pressure, never an alert input):

    python -m pulse_data.ingest import-wearable-csv --patient patient.b@demo.pulse.test \
        --file data/demo/ring_karim_28_nights.csv --source simulated
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .localdb import require_local

LOCAL_DB ="postgresql://postgres:postgres@127.0.0.1:55322/postgres"  # local Supabase stack only
REQUIRED = ("measured_at", "systolic", "diastolic")
POSITIONS = {"sitting", "standing", "lying"}
ARMS = {"left", "right"}
WEARABLE_REQUIRED = ("measured_at", "metric", "value")
WEARABLE_UNITS = {"heart_rate": "bpm", "hrv_rmssd": "ms", "spo2": "percent", "skin_temperature": "celsius"}
UNIT_ALIASES = {"%": "percent", "°c": "celsius", "c": "celsius", "beats/min": "bpm"}


@dataclass(frozen=True)
class Reading:
    """Normalised measurement every adapter maps into (docs/DEVICE_INTEGRATION.md)."""
    measured_at: datetime            # timezone-aware
    systolic: int                    # mmHg
    diastolic: int                   # mmHg
    pulse: int | None = None         # bpm
    measured_tz: str | None = None   # IANA zone the reading was taken in
    external_id: str | None = None   # device-supplied reading id; never invented
    body_position: str | None = None
    arm: str | None = None
    context: str | None = None
    quality_flags: tuple[str, ...] = ()  # device-reported, e.g. ("body_movement",)
    row: int | None = None           # source line, for rejection reports


@dataclass(frozen=True)
class WearableSample:
    """One ring / bracelet value, as stored in public.wearable_samples."""
    measured_at: datetime            # timezone-aware
    metric: str                      # a WEARABLE_UNITS key
    value: float
    unit: str
    external_id: str | None = None   # sample id from the export; never invented
    row: int | None = None


@dataclass(frozen=True)
class Rejection:
    row: int | None
    reasons: tuple[str, ...]


class DuplicateFileError(Exception):
    pass


def parse_csv(path: str | Path, default_tz: str) -> tuple[list[Reading], list[Rejection]]:
    """Parse a cuff-export style CSV. Lines starting with '#' are comments.

    Columns (case-insensitive): measured_at, systolic, diastolic required; pulse, unit (mmHg only),
    external_id, position, arm, note optional. Naive timestamps are read in `default_tz`.
    """
    tz = ZoneInfo(default_tz)  # raises for unknown zones
    readings: list[Reading] = []
    rejections: list[Rejection] = []
    for line, row in _csv_rows(path, REQUIRED):
        reasons: list[str] = []

        def integer(name: str, required: bool) -> int | None:
            if not row.get(name):
                if required:
                    reasons.append(f"missing_{name}")
                return None
            try:
                return int(row[name])
            except ValueError:
                reasons.append(f"not_integer_{name}")
                return None

        systolic, diastolic, pulse = integer("systolic", True), integer("diastolic", True), integer("pulse", False)
        if (row.get("unit") or "mmHg").lower() != "mmhg":
            reasons.append("unsupported_unit")
        measured_at = _timestamp(row, tz, reasons)
        position, arm = row.get("position", "").lower() or None, row.get("arm", "").lower() or None
        if position and position not in POSITIONS:
            reasons.append("invalid_position")
        if arm and arm not in ARMS:
            reasons.append("invalid_arm")

        if reasons:
            rejections.append(Rejection(line, tuple(reasons)))
            continue
        readings.append(Reading(measured_at, systolic, diastolic, pulse, default_tz, row.get("external_id") or None,
                                position, arm, (row.get("note") or "")[:500] or None, row=line))
    return readings, rejections


def _csv_rows(path: str | Path, required: tuple[str, ...]) -> list[tuple[int, dict]]:
    """(source line, row) pairs with lower-case headers; lines starting with '#' are comments."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        lines = [(n, line) for n, line in enumerate(f, 1) if not line.lstrip().startswith("#")]
    reader = csv.DictReader(line for _, line in lines)
    if reader.fieldnames is None:
        raise ValueError("CSV is empty")
    reader.fieldnames = [(h or "").strip().lower() for h in reader.fieldnames]
    missing = [c for c in required if c not in reader.fieldnames]
    if missing:
        raise ValueError(f"CSV is missing required column(s): {', '.join(missing)}")
    return [(lines[reader.line_num - 1][0], {k: (v or "").strip() for k, v in raw.items() if k}) for raw in reader]


def _timestamp(row: dict, tz: ZoneInfo, reasons: list[str]) -> datetime | None:
    if not row.get("measured_at"):
        reasons.append("missing_measured_at")
        return None
    try:
        at = datetime.fromisoformat(row["measured_at"])
    except ValueError:
        reasons.append("invalid_timestamp")
        return None
    return at if at.tzinfo else at.replace(tzinfo=tz)


def parse_wearable_csv(path: str | Path, default_tz: str) -> tuple[list[WearableSample], list[Rejection]]:
    """Parse a ring / bracelet export. Columns: measured_at, metric, value required; unit, external_id optional.
    Metrics: heart_rate (bpm), hrv_rmssd (ms), spo2 (percent), skin_temperature (celsius). Plausible ranges are
    checked by the database, which refuses the row."""
    tz = ZoneInfo(default_tz)
    samples: list[WearableSample] = []
    rejections: list[Rejection] = []
    for line, row in _csv_rows(path, WEARABLE_REQUIRED):
        reasons: list[str] = []
        metric = row.get("metric", "").lower()
        if metric not in WEARABLE_UNITS:
            reasons.append("unknown_metric")
        unit = row.get("unit", "").lower()
        unit = UNIT_ALIASES.get(unit, unit) or WEARABLE_UNITS.get(metric, "")
        if metric in WEARABLE_UNITS and unit != WEARABLE_UNITS[metric]:
            reasons.append("unsupported_unit")
        try:
            value = float(row["value"])
        except ValueError:
            reasons.append("not_number_value")
        measured_at = _timestamp(row, tz, reasons)
        if reasons:
            rejections.append(Rejection(line, tuple(reasons)))
            continue
        samples.append(WearableSample(measured_at, metric, value, unit, row.get("external_id") or None, line))
    return samples, rejections


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def import_readings(conn, patient_id: str, readings: list[Reading], *, source: str, provenance: str,
                    method: str = "unknown", device_id: str | None = None, file_name: str | None = None,
                    sha256: str | None = None, rejections: list[Rejection] = ()) -> dict:
    """Store readings as one ingestion batch in a single transaction and return a summary.

    Device duplicates (same device + external_id) are skipped and counted. Rows the database
    refuses (e.g. values outside storage bounds) become rejections; the rest of the batch is kept.
    """
    import psycopg

    if device_id is None and any(r.external_id for r in readings):
        raise ValueError("readings with external_id need a device_id")
    rejected = [{"row": r.row, "reasons": list(r.reasons)} for r in rejections]
    statuses: Counter[str] = Counter()
    duplicates = 0
    with conn.transaction():
        try:
            with conn.transaction():
                batch_id = conn.execute(
                    "insert into public.ingestion_batches (patient_id, source, device_id, file_name, file_sha256)"
                    " values (%s, %s, %s, %s, %s) returning id",
                    (patient_id, source, device_id, file_name, sha256)).fetchone()[0]
        except psycopg.errors.UniqueViolation as e:
            raise DuplicateFileError("this file was already imported for this patient") from e
        for r in readings:
            try:
                with conn.transaction():  # savepoint: one refused row must not abort the batch
                    row = conn.execute(
                        "insert into public.measurements (patient_id, device_id, ingestion_batch_id, source, provenance,"
                        " method, systolic, diastolic, pulse, measured_at, measured_tz, body_position, arm, context,"
                        " external_id, quality_flags) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                        " on conflict (device_id, external_id) where external_id is not null do nothing"
                        " returning validation_status",
                        (patient_id, device_id, batch_id, source, provenance, method, r.systolic, r.diastolic, r.pulse,
                         r.measured_at, r.measured_tz, r.body_position, r.arm, r.context, r.external_id,
                         list(r.quality_flags))).fetchone()
            except (psycopg.errors.IntegrityError, psycopg.errors.DataError) as e:
                rejected.append({"row": r.row, "reasons": [f"refused_by_database:{e.diag.constraint_name or e.sqlstate}"]})
                continue
            if row is None:
                duplicates += 1
            else:
                statuses[row[0]] += 1
        summary = {
            "batch_id": str(batch_id),
            "rows_total": len(readings) + len(rejections),
            "rows_inserted": sum(statuses.values()),
            "rows_duplicate": duplicates,
            "rows_rejected": len(rejected),
            "validation_status": dict(statuses),
            "rejections": rejected,
        }
        conn.execute(
            "update public.ingestion_batches set rows_total = %s, rows_inserted = %s, rows_duplicate = %s,"
            " rows_rejected = %s, rejections = %s where id = %s",
            (summary["rows_total"], summary["rows_inserted"], duplicates, len(rejected), json.dumps(rejected), batch_id))
    return summary


def ring_device(conn, patient_id: str, *, simulated: bool, create: bool) -> str:
    """The patient's ring: their first simulator device for simulated data, their first real wearable otherwise.
    With create=True a missing ring is added (a simulator is always labelled simulated, by database rule)."""
    kind = "simulator" if simulated else "wearable"
    found = conn.execute("select id from public.devices where patient_id = %s and device_type = %s"
                         " order by created_at, id limit 1", (patient_id, kind)).fetchone()
    if found:
        return str(found[0])
    if not create:
        raise SystemExit(f"this patient has no {kind} device; import a ring CSV first")
    label = "Bague simulée (import CSV)" if simulated else "Bague (import CSV)"
    return str(conn.execute(
        "insert into public.devices (patient_id, device_type, bp_capability, manufacturer, model, label)"
        " values (%s, %s, %s, %s, %s, %s) returning id",
        (patient_id, kind, "simulated" if simulated else "none", "PULSE" if simulated else None,
         "Simulateur" if simulated else None, label)).fetchone()[0])


def import_wearable(conn, patient_id: str, device_id: str, samples: list[WearableSample], *, source: str,
                    rejections: list[Rejection] = ()) -> dict:
    """Store ring samples; returns counts only. A sample already stored for the same device (same external_id,
    or same metric at the same instant when the export has no id) is skipped, so re-importing a file adds nothing."""
    import psycopg

    rejected = [{"row": r.row, "reasons": list(r.reasons)} for r in rejections]
    inserted: Counter[str] = Counter()
    duplicates = 0
    with conn.transaction():
        for s in samples:
            try:
                with conn.transaction():  # savepoint: one refused row must not abort the import
                    row = conn.execute(
                        "insert into public.wearable_samples (patient_id, device_id, metric, value, unit, measured_at,"
                        " source, external_id) select %s::uuid, %s::uuid, %s::text, %s::numeric, %s::text,"
                        " %s::timestamptz, %s::text, %s::text where not exists (select 1 from public.wearable_samples"
                        " where device_id = %s::uuid and metric = %s::text and measured_at = %s::timestamptz)"
                        " on conflict (device_id, external_id) where external_id is not null do nothing returning id",
                        (patient_id, device_id, s.metric, s.value, s.unit, s.measured_at, source, s.external_id,
                         device_id, s.metric, s.measured_at)).fetchone()
            except (psycopg.errors.IntegrityError, psycopg.errors.DataError) as e:
                rejected.append({"row": s.row, "reasons": [f"refused_by_database:{e.diag.constraint_name or e.sqlstate}"]})
                continue
            if row is None:
                duplicates += 1
            else:
                inserted[s.metric] += 1
    return {"device_id": device_id, "rows_total": len(samples) + len(rejections),
            "rows_inserted": sum(inserted.values()), "rows_duplicate": duplicates, "rows_rejected": len(rejected),
            "inserted_by_metric": dict(inserted), "rejections": rejected}


def resolve_patient(conn, who: str) -> str:
    try:
        pid = str(uuid.UUID(who))
    except ValueError:
        found = conn.execute("select id from auth.users where email = %s", (who,)).fetchone()
        if not found:
            raise SystemExit(f"no user with email {who}")
        pid = str(found[0])
    role = conn.execute("select role from public.profiles where id = %s", (pid,)).fetchone()
    if not role or role[0] != "patient":
        raise SystemExit(f"{who} is not a patient profile")
    return pid


def main(argv: list[str] | None = None) -> int:
    import psycopg

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("import-csv", help="import a cuff-export CSV for one patient")
    c.add_argument("--patient", required=True, help="patient email or uuid")
    c.add_argument("--file", required=True, type=Path)
    c.add_argument("--provenance", required=True, choices=["measured", "estimated", "simulated"],
                   help="what the file really contains; synthetic files must say 'simulated'")
    c.add_argument("--method", default="unknown",
                   choices=["cuff_oscillometric", "cuff_auscultatory", "wearable_estimate", "unknown"])
    c.add_argument("--tz", default="Africa/Algiers", help="time zone for timestamps without an offset")
    c.add_argument("--device", help="devices.id, required if the CSV has external_id")
    w = sub.add_parser("import-wearable-csv", help="import ring / bracelet samples (HR, HRV, SpO2, skin temperature)")
    w.add_argument("--patient", required=True, help="patient email or uuid")
    w.add_argument("--file", required=True, type=Path)
    w.add_argument("--source", required=True, choices=["simulated", "csv_import"],
                   help="what the file really contains; synthetic files must say 'simulated'")
    w.add_argument("--device", help="devices.id; default: the patient's ring, created if missing")
    w.add_argument("--tz", default="Africa/Algiers", help="time zone for timestamps without an offset")
    a = ap.parse_args(argv)
    url = os.environ.get("DATABASE_URL", LOCAL_DB)
    require_local(url)

    if a.cmd == "import-wearable-csv":
        samples, rejections = parse_wearable_csv(a.file, a.tz)
        with psycopg.connect(url, autocommit=True) as conn:
            patient_id = resolve_patient(conn, a.patient)
            device = a.device or ring_device(conn, patient_id, simulated=a.source == "simulated", create=True)
            summary = import_wearable(conn, patient_id, device, samples, source=a.source, rejections=rejections)
        print(json.dumps(summary, indent=2))
        return 0

    readings, rejections = parse_csv(a.file, a.tz)
    with psycopg.connect(url, autocommit=True) as conn:
        patient_id = resolve_patient(conn, a.patient)
        try:
            summary = import_readings(conn, patient_id, readings, source="csv_import", provenance=a.provenance,
                                      method=a.method, device_id=a.device, file_name=a.file.name,
                                      sha256=file_sha256(a.file), rejections=rejections)
        except DuplicateFileError as e:
            print(f"refused: {e}", file=sys.stderr)
            return 1
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
