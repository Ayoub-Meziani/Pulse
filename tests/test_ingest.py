from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfoNotFoundError

import pytest

from pulse_data import simulate
from pulse_data.ingest import parse_csv

SAMPLE = Path(__file__).resolve().parent.parent / "samples" / "readings_sample.csv"


def write(tmp_path, text):
    p = tmp_path / "r.csv"
    p.write_text(text, encoding="utf-8")
    return p


def test_sample_csv_parses_and_rejects_bad_rows():
    readings, rejections = parse_csv(SAMPLE, "Africa/Algiers")
    reasons = sorted(r for rej in rejections for r in rej.reasons)
    assert reasons == ["invalid_timestamp", "missing_diastolic", "unsupported_unit"]
    assert all(r.measured_at.utcoffset() == timedelta(hours=1) for r in readings)  # Algiers is UTC+1
    assert any(r.context == "after coffee" for r in readings)
    assert len(readings) + len(rejections) == 29


def test_row_level_checks(tmp_path):
    p = write(tmp_path, "Measured_At,Systolic,Diastolic,Pulse,Position,Arm\n"
                        "2026-10-01T08:00:00+00:00,130,85,,sitting,left\n"
                        "2026-10-01 09:00,abc,85,70,,\n"
                        "2026-10-01 10:00,130,85,70,upside-down,\n"
                        "2026-10-01 11:00,130,85,70,,middle\n")
    readings, rejections = parse_csv(p, "Africa/Algiers")
    assert len(readings) == 1
    assert readings[0].measured_at.utcoffset() == timedelta(0)  # explicit offset is kept
    assert readings[0].pulse is None
    assert [r.reasons for r in rejections] == [("not_integer_systolic",), ("invalid_position",), ("invalid_arm",)]
    assert [r.row for r in rejections] == [3, 4, 5]


def test_missing_required_column(tmp_path):
    with pytest.raises(ValueError, match="diastolic"):
        parse_csv(write(tmp_path, "measured_at,systolic\n2026-10-01 08:00,120\n"), "Africa/Algiers")


def test_unknown_timezone(tmp_path):
    with pytest.raises(ZoneInfoNotFoundError):
        parse_csv(write(tmp_path, "measured_at,systolic,diastolic\n"), "Mars/Olympus")


def test_seed_is_deterministic_and_labelled_simulated():
    sql = simulate.build_seed_sql("test-only")
    assert sql == simulate.build_seed_sql("test-only")
    block = sql.split("insert into public.measurements")[1].split(";\n")[0]
    rows = [line for line in block.splitlines() if line.startswith("  (")]
    assert rows and all("'simulated', 'simulated'" in line for line in rows)
    assert SAMPLE.read_text().startswith("# SYNTHETIC")
