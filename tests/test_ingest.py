from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfoNotFoundError

import pytest

from pulse_data import simulate
from pulse_data.ingest import WEARABLE_UNITS, parse_csv, parse_wearable_csv

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


def test_wearable_csv_row_checks(tmp_path):
    p = write(tmp_path, "# ring export\nMeasured_At,Metric,Value,Unit,External_Id\n"
                        "2026-10-20 02:00,heart_rate,58,,h1\n"        # unit defaults to the metric's own
                        "2026-10-20T02:00:00+00:00,spo2,96.5,%,\n"      # unit alias, explicit offset kept
                        "2026-10-20 03:00,skin_temperature,34.1,°C,\n"
                        "2026-10-20 03:00,spo2,97,bpm,\n"               # wrong unit
                        "2026-10-20 03:00,steps,900,,\n"                 # not a ring metric in PULSE
                        "2026-10-20 03:00,heart_rate,fast,,\n"
                        "later,heart_rate,60,,\n")
    samples, rejections = parse_wearable_csv(p, "Africa/Algiers")
    assert [(s.metric, s.unit) for s in samples] == [("heart_rate", "bpm"), ("spo2", "percent"),
                                                      ("skin_temperature", "celsius")]
    assert samples[0].measured_at.utcoffset() == timedelta(hours=1) and samples[0].external_id == "h1"
    assert samples[1].measured_at.utcoffset() == timedelta(0) and samples[1].external_id is None
    assert [r.reasons for r in rejections] == [("unsupported_unit",), ("unknown_metric",), ("not_number_value",),
                                               ("invalid_timestamp",)]
    assert [r.row for r in rejections] == [6, 7, 8, 9]


def test_wearable_csv_missing_column(tmp_path):
    with pytest.raises(ValueError, match="metric"):
        parse_wearable_csv(write(tmp_path, "measured_at,value\n2026-10-20 02:00,58\n"), "Africa/Algiers")


def test_demo_csvs_are_simulated_reproducible_and_import_clean(tmp_path):
    end = date(2026, 10, 30)
    ring, cuff = simulate.write_demo_csvs(tmp_path / "a", end)
    ring2, cuff2 = simulate.write_demo_csvs(tmp_path / "b", end)
    assert ring.read_bytes() == ring2.read_bytes() and cuff.read_bytes() == cuff2.read_bytes()
    assert ring.read_text(encoding="utf-8").startswith("# SIMULATED")
    assert cuff.read_text(encoding="utf-8").startswith("# SIMULATED")
    samples, rejected = parse_wearable_csv(ring, "Africa/Algiers")
    assert not rejected and {s.metric for s in samples} == set(WEARABLE_UNITS)
    assert max(s.measured_at for s in samples).date() == end            # nothing after the last day
    assert len({s.external_id for s in samples}) == len(samples)
    readings, rejected = parse_csv(cuff, "Africa/Algiers")
    assert not rejected and len(readings) > 10
    assert max(r.measured_at for r in readings).date() <= end - timedelta(days=11)  # history before the app


def test_seed_is_deterministic_and_labelled_simulated():
    sql = simulate.build_seed_sql("test-only")
    assert sql == simulate.build_seed_sql("test-only")
    block = sql.split("insert into public.measurements")[1].split(";\n")[0]
    rows = [line for line in block.splitlines() if line.startswith("  (")]
    assert rows and all("'simulated', 'simulated'" in line for line in rows)
    assert SAMPLE.read_text().startswith("# SYNTHETIC")
