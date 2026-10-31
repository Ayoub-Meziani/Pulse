from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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


def test_demo_csv_today_is_simulated_and_never_in_the_future(tmp_path):
    now = datetime(2026, 10, 31, 10, 7, 42, 123, tzinfo=ZoneInfo("Africa/Algiers"))
    path = simulate.write_demo_csv_today(tmp_path, now)
    assert path.name == "cuff_nadia_today.csv" and path.read_text(encoding="utf-8").startswith("# SIMULATED")
    readings, rejected = parse_csv(path, "UTC")
    assert not rejected
    assert [(r.systolic, r.diastolic) for r in readings] == [(152, 94), (186, 118)]       # above target, then severe
    assert [r.measured_at for r in readings] == [now.replace(hour=9, minute=27, second=0, microsecond=0),
                                                 now.replace(minute=5, second=0, microsecond=0)]
    assert all(r.measured_at.utcoffset() == timedelta(hours=1) for r in readings)         # ISO with offset
    later = simulate.write_demo_csv_today(tmp_path / "b", now + timedelta(minutes=3))
    assert later.read_bytes() != path.read_bytes()                                        # another sha each run


@pytest.mark.parametrize("url, env, ok", [
    ("postgresql://postgres:postgres@127.0.0.1:55322/postgres", {}, True),
    ("postgresql://postgres:postgres@localhost:55322/postgres", {"PGHOST": "db.example.com"}, True),
    ("host=/var/run/postgresql dbname=postgres", {}, True),
    ("postgresql://postgres.ref:x@aws-0-eu-central-1.pooler.supabase.com:6543/postgres", {}, False),
    ("postgresql://", {"PGHOST": "aws-0-eu-central-1.pooler.supabase.com"}, False),
    ("host=127.0.0.1,db.example.com dbname=postgres", {}, False),
    ("postgresql://127.0.0.1/postgres?hostaddr=203.0.113.7", {}, False),
    ("postgresql://127.0.0.1/postgres", {"PGHOSTADDR": "203.0.113.7"}, False),
    ("postgresql:///postgres?service=pulse", {}, False),                 # libpq takes the host from pg_service.conf
    ("service=pulse", {}, False),
    ("postgresql://", {"PGSERVICE": "pulse"}, False),
    ("postgresql://postgres:postgres@127.0.0.1:55322/postgres", {"PGSERVICE": "pulse"}, False),  # may add a hostaddr
])
def test_require_local_refuses_any_non_local_host(monkeypatch, url, env, ok):
    from pulse_data.localdb import require_local
    for k in ("PGHOST", "PGHOSTADDR", "PGSERVICE"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    if ok:
        require_local(url)
    else:
        with pytest.raises(SystemExit):
            require_local(url)


def test_stream_refuses_a_cloud_database_with_no_unlock(monkeypatch):
    import sys
    from pulse_data import stream
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres.ref:x@aws-0-eu-central-1.pooler.supabase.com:6543/postgres")
    monkeypatch.setattr(stream.psycopg, "connect", lambda *a, **k: pytest.fail("connected to a cloud database"))
    argv = ["stream", "--patient-email", "patient.b@demo.pulse.test", "--scenario", "oxygen_falling"]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit, match="refusing"):
        stream.main()
    monkeypatch.setattr(sys, "argv", argv + ["--i-confirmed-cloud"])
    with pytest.raises(SystemExit) as refused:
        stream.main()
    assert refused.value.code == 2                        # argparse: the old unlock flag no longer exists


def test_seed_is_deterministic_and_labelled_simulated():
    sql = simulate.build_seed_sql("test-only")
    assert sql == simulate.build_seed_sql("test-only")
    block = sql.split("insert into public.measurements")[1].split(";\n")[0]
    rows = [line for line in block.splitlines() if line.startswith("  (")]
    assert rows and all("'simulated', 'simulated'" in line for line in rows)
    assert SAMPLE.read_text().startswith("# SYNTHETIC")
