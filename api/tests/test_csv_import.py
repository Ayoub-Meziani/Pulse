"""CSV text parsers for file imports (no database)."""
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.services.csv_import import CsvFormatError, declares_simulated, parse_bp, parse_ring

ALGIERS = ZoneInfo("Africa/Algiers")


def test_bp_rows_reasons_and_line_numbers():
    text = ("﻿# cuff export\nMeasured_At,Systolic,Diastolic,Pulse,Unit,Position,Arm,Note,External_Id\n"
            "2026-10-01T08:00:00+00:00,130,85,,mmHg,sitting,left,after coffee,dev-1\n"  # offset kept; id ignored
            "2026-10-01 09:00,abc,85,70,,,,,\n"
            "2026-10-01 10:00,130,85,70,kPa,,,,\n"
            "2026-10-01 11:00,130,,70,,,,,\n"
            "yesterday,130,85,70,,upside-down,middle,,\n")
    rows, rejections = parse_bp(text, ALGIERS)
    assert len(rows) == 1 and rows[0].row == 3 and rows[0].context == "after coffee"
    assert rows[0].measured_at.utcoffset() == timedelta(0) and rows[0].pulse is None
    assert [(r.row, r.reasons) for r in rejections] == [
        (4, ("not_integer_systolic",)), (5, ("unsupported_unit",)), (6, ("missing_diastolic",)),
        (7, ("invalid_timestamp", "invalid_position", "invalid_arm"))]


def test_bp_naive_times_use_the_given_zone():
    rows, _ = parse_bp("measured_at,systolic,diastolic\n2026-10-01 08:00,120,80\n", ALGIERS)
    assert rows[0].measured_at.utcoffset() == timedelta(hours=1)


@pytest.mark.parametrize("text,code", [
    ("# only a comment\n", "empty_file"),
    ("measured_at,systolic\n2026-10-01 08:00,120\n", "missing_column"),
])
def test_bp_file_level_errors(text, code):
    with pytest.raises(CsvFormatError) as e:
        parse_bp(text, ALGIERS)
    assert e.value.code == code


def test_ring_rows_units_and_numbers():
    text = ("measured_at,metric,value,unit,external_id\n"
            "2026-10-20 02:00,heart_rate,58,,h1\n"
            "2026-10-20 02:00,spo2,96.5,%,\n"
            "2026-10-20 03:00,skin_temperature,34.1,°C,\n"
            "2026-10-20 03:00,spo2,97,bpm,\n"
            "2026-10-20 03:00,steps,900,,\n"
            "2026-10-20 03:00,heart_rate,nan,,\n"
            "2026-10-20 03:00,heart_rate,inf,,\n")
    rows, rejections = parse_ring(text, ALGIERS)
    assert [(r.metric, r.unit, r.external_id) for r in rows] == [
        ("heart_rate", "bpm", "h1"), ("spo2", "percent", None), ("skin_temperature", "celsius", None)]
    assert [r.reasons for r in rejections] == [("unsupported_unit",), ("unknown_metric",), ("not_number_value",),
                                               ("not_number_value",)]


def test_ring_missing_column():
    with pytest.raises(CsvFormatError) as e:
        parse_ring("measured_at,value\n2026-10-20 02:00,58\n", ALGIERS)
    assert e.value.code == "missing_column"


@pytest.mark.parametrize("text,expected", [
    ("# SIMULATED ring export\nmeasured_at,metric,value\n", True),
    ("﻿\n# synthetic sample\nmeasured_at,systolic,diastolic\n", True),
    ("# cuff export\nmeasured_at,systolic,diastolic\n", False),
    ("measured_at,systolic,diastolic\n# SIMULATED later\n", False),
])
def test_simulated_marker_is_the_first_line_only(text, expected):
    assert declares_simulated(text) is expected


# ---------------------------------------------------------------- docs/data/csv-examples (README promises)
EXAMPLES = Path(__file__).resolve().parents[2] / "docs" / "data" / "csv-examples"


@pytest.mark.parametrize("name,parser,kept,rejected", [
    ("cuff_minimal.csv", parse_bp, 4, []),
    ("cuff_all_columns.csv", parse_bp, 4, []),
    ("cuff_with_errors.csv", parse_bp, 4, [(4, ("not_integer_systolic",)), (5, ("missing_diastolic",)),
                                           (6, ("unsupported_unit",)), (7, ("invalid_position",)),
                                           (8, ("invalid_timestamp",))]),
    ("ring_export.csv", parse_ring, 7, [(10, ("unknown_metric",))]),   # heart rate 400: refused by the database
])
def test_documented_examples_parse_as_the_readme_says(name, parser, kept, rejected):
    text = (EXAMPLES / name).read_text(encoding="utf-8")
    rows, rejections = parser(text, ALGIERS)
    assert declares_simulated(text)                                       # fictional values, labelled
    assert (len(rows), [(r.row, r.reasons) for r in rejections]) == (kept, rejected)
