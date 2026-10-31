"""CSV text parsers for file imports: cuff exports (blood pressure) and ring exports.

Text ports of pulse_data.ingest (the API cannot import that package): same columns, row reasons and unit aliases,
so a file the command-line import accepts is accepted here too. Format checks only; plausibility is decided by the
database (validation trigger pulse-v1 for readings, value ranges for ring samples).
"""
from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

BP_REQUIRED = ("measured_at", "systolic", "diastolic")
RING_REQUIRED = ("measured_at", "metric", "value")
POSITIONS = {"sitting", "standing", "lying"}
ARMS = {"left", "right"}
RING_UNITS = {"heart_rate": "bpm", "hrv_rmssd": "ms", "spo2": "percent", "skin_temperature": "celsius"}
UNIT_ALIASES = {"%": "percent", "°c": "celsius", "c": "celsius", "beats/min": "bpm"}
SIMULATED_MARKERS = ("# simulated", "# synthetic")


class CsvFormatError(Exception):
    """The file cannot be read at all (empty, missing column, broken CSV). Row problems are rejections instead."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass(frozen=True)
class BpRow:
    row: int
    measured_at: datetime
    systolic: int
    diastolic: int
    pulse: int | None
    position: str | None
    arm: str | None
    context: str | None


@dataclass(frozen=True)
class RingRow:
    row: int
    measured_at: datetime
    metric: str
    value: float
    unit: str
    external_id: str | None


@dataclass(frozen=True)
class Rejection:
    row: int
    reasons: tuple[str, ...]


def declares_simulated(text: str) -> bool:
    """True if the first non-empty line is a '# SIMULATED ...' / '# SYNTHETIC ...' comment."""
    first = next((line.strip() for line in text.removeprefix("﻿").splitlines() if line.strip()), "")
    return first.lower().startswith(SIMULATED_MARKERS)


def _rows(text: str, required: tuple[str, ...]) -> list[tuple[int, dict]]:
    """(file line, row) pairs with lower-case headers; '#' lines are comments. StringIO keeps the same line
    splitting as reading a file, so line numbers match the command-line import."""
    lines = [(n, line) for n, line in enumerate(io.StringIO(text.removeprefix("﻿"), newline=""), 1)
             if not line.lstrip().startswith("#")]
    reader = csv.DictReader(line for _, line in lines)
    try:
        if reader.fieldnames is None:
            raise CsvFormatError("empty_file", "The file is empty.")
        reader.fieldnames = [(h or "").strip().lower() for h in reader.fieldnames]
        missing = [c for c in required if c not in reader.fieldnames]
        if missing:
            raise CsvFormatError("missing_column", f"The file is missing column(s): {', '.join(missing)}.")
        return [(lines[reader.line_num - 1][0], {k: (v or "").strip() for k, v in raw.items() if k})
                for raw in reader]
    except csv.Error as e:
        raise CsvFormatError("unreadable", f"The file is not valid CSV ({e}).") from None


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


def parse_bp(text: str, tz: ZoneInfo) -> tuple[list[BpRow], list[Rejection]]:
    """Columns: measured_at, systolic, diastolic required; pulse, unit (mmHg only), position, arm, note optional.
    An external_id column is ignored: a reading id needs a registered device."""
    rows, rejections = [], []
    for line, row in _rows(text, BP_REQUIRED):
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
        rows.append(BpRow(line, measured_at, systolic, diastolic, pulse, position, arm,
                          (row.get("note") or "")[:500] or None))
    return rows, rejections


def parse_ring(text: str, tz: ZoneInfo) -> tuple[list[RingRow], list[Rejection]]:
    """Columns: measured_at, metric, value required; unit (defaults to the metric's), external_id optional."""
    rows, rejections = [], []
    for line, row in _rows(text, RING_REQUIRED):
        reasons: list[str] = []
        metric = row.get("metric", "").lower()
        if metric not in RING_UNITS:
            reasons.append("unknown_metric")
        unit = row.get("unit", "").lower()
        unit = UNIT_ALIASES.get(unit, unit) or RING_UNITS.get(metric, "")
        if metric in RING_UNITS and unit != RING_UNITS[metric]:
            reasons.append("unsupported_unit")
        value = None
        try:
            value = float(row["value"])
            if not math.isfinite(value):
                raise ValueError
        except ValueError:
            reasons.append("not_number_value")
        measured_at = _timestamp(row, tz, reasons)
        if reasons:
            rejections.append(Rejection(line, tuple(reasons)))
            continue
        rows.append(RingRow(line, measured_at, metric, value, unit, row.get("external_id") or None))
    return rows, rejections
