"""Ring monitor checks (review H2, L4, M6, H6). DB tests run on the LOCAL stack only, rolled back."""
import os
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from pulse_ml import ring

TZ = "Africa/Algiers"


def nights_frame(values: list[float], metric="heart_rate", patient="P1") -> pd.DataFrame:
    """One sample per night at 03:00 local for `len(values)` nights from 2026-01-01."""
    rows = [(patient, metric, v, (datetime(2026, 1, 1, 3, tzinfo=ZoneInfo(TZ)) + timedelta(days=i)).isoformat())
            for i, v in enumerate(values)]
    df = pd.DataFrame(rows, columns=["patient_key", "metric", "value", "measured_at"])
    return ring.night_table(ring.from_csv(df))


def test_csv_and_db_rows_give_identical_nights():  # one shared feature path [H2]
    t0 = datetime(2026, 1, 5, 2, 30, tzinfo=ZoneInfo(TZ))
    data = [("P1", "heart_rate", 61, t0), ("P1", "heart_rate", 65, t0 + timedelta(minutes=10)),
            ("P1", "spo2", 95.5, t0), ("P1", "spo2", 93.0, t0 + timedelta(hours=1)),
            ("P1", "heart_rate", 90, t0 + timedelta(hours=8))]  # daytime: not part of the night
    csv = pd.DataFrame([(p, m, v, t.isoformat()) for p, m, v, t in data],
                       columns=["patient_key", "metric", "value", "measured_at"])
    a = ring.night_table(ring.from_csv(csv))
    b = ring.night_table(ring.from_db([(p, m, Decimal(str(v)), t.astimezone(ZoneInfo("UTC"))) for p, m, v, t in data],
                                      {"P1": TZ}))
    pd.testing.assert_frame_equal(a, b)
    assert a.loc[0, "heart_rate"] == 63 and a.loc[0, "spo2"] == 94.25  # night medians (healthy sleepers dip)


def test_chronic_conditions_change_the_references():
    t = pd.Timestamp("2026-01-05 03:00", tz="UTC")
    rows = [(p, "spo2", v, t + pd.Timedelta(seconds=i)) for p in ("COPD", "OTHER") for i, v in enumerate((91.5, 92.0))]
    rows += [("AF", "hrv_rmssd", 150.0, t), ("AF", "hrv_rmssd", 160.0, t + pd.Timedelta(seconds=5))]
    buckets = ring.live_buckets(ring.from_db(rows, {}))
    conditions = {"COPD": ("copd",), "AF": ("atrial_fibrillation",)}
    flagged = {(f["patient_id"], f["metric"]) for f in ring.live_flags(buckets, conditions=conditions)}
    assert flagged == {("OTHER", "spo2")}   # COPD limit is 88 % (BTS); AF makes ring HRV not interpretable


def test_baseline_uses_only_earlier_nights_and_skips_confirmed():  # [L4]
    nights = nights_frame([60.0 + (i % 3) for i in range(20)] + [120.0])
    last = nights.night.max()
    base = ring.baselines(nights).set_index("night")
    assert base.loc[last, "heart_rate_n"] == 20 and base.loc[last, "heart_rate_med"] == 61
    confirmed = {("P1", nights.night.min(), "heart_rate")}
    assert ring.baselines(nights, confirmed).set_index("night").loc[last, "heart_rate_n"] == 19
    flags = ring.night_flags(ring.personal_z(nights, base.reset_index()))
    assert [(f["metric"], f["kind"]) for f in flags] == [("heart_rate", "outside_reference"),
                                                         ("heart_rate", "personal_anomaly")]


def test_doctor_band_overrides_learned_baseline():
    nights = nights_frame([60.0 + (i % 3) for i in range(20)] + [95.0])
    zdf = ring.personal_z(nights, ring.baselines(nights))
    assert any(f["kind"] == "personal_anomaly" for f in ring.night_flags(zdf))
    bands = {("P1", "heart_rate", "night_median"): ("band-1", 50.0, 100.0)}
    assert not any(f["kind"] == "personal_anomaly" for f in ring.night_flags(zdf, bands))


def test_live_windows_reference_and_sustained_band():
    t = pd.Timestamp("2026-01-05 10:00", tz="UTC")
    rows = [("P1", "spo2", 90.0, t), ("P1", "spo2", 90.4, t + pd.Timedelta(seconds=5)),   # 2 samples < 94
            ("P1", "heart_rate", 130.0, t), ("P1", "heart_rate", 128.0, t + pd.Timedelta(minutes=1)),
            ("P1", "heart_rate", 131.0, t + pd.Timedelta(minutes=10)), ("P1", "heart_rate", 129.0, t + pd.Timedelta(minutes=11))]
    buckets = ring.live_buckets(ring.from_db(rows, {"P1": TZ}))
    bands = {("P1", "heart_rate", "live_10min_median"): ("band-2", 50.0, 110.0)}
    kinds = sorted((f["metric"], f["kind"], f["window_start"].minute) for f in ring.live_flags(buckets, bands))
    assert kinds == [("heart_rate", "outside_reference", 0), ("heart_rate", "outside_reference", 10),
                     ("heart_rate", "personal_anomaly", 10),        # only once sustained over 2 buckets
                     ("spo2", "outside_reference", 0)]


# ---------------------------------------------------------------- local database (rolled back)

@pytest.fixture
def conn():
    psycopg = pytest.importorskip("psycopg")
    from pulse_ml.predict import LOCAL_DB
    try:
        c = psycopg.connect(os.environ.get("PULSE_TEST_DATABASE_URL", LOCAL_DB), autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("local PULSE database not reachable")
    if c.execute("select to_regclass('public.wearable_flags')").fetchone()[0] is None:
        pytest.skip("M7 missing; run `supabase db reset --local`")
    with c.transaction(force_rollback=True):
        yield c
    c.close()


def karim():
    from pulse_data.simulate import PATIENTS, demo_id
    return next(p.id for p in PATIENTS if p.key == "rising"), demo_id("rising:ring")


def ringless_patient_with_test_ring(conn):
    """Amina (assigned, no ring in the seed) + a ring created inside the rolled-back transaction, so a
    demo stream running on the same database cannot mix into the test's 10-minute window."""
    from pulse_data.simulate import PATIENTS
    patient = next(p.id for p in PATIENTS if p.key == "controlled")
    device = conn.execute("insert into public.devices (patient_id, device_type, bp_capability, label)"
                          " values (%s, 'wearable', 'none', 'test ring') returning id::text", (patient,)).fetchone()[0]
    return patient, device


OTHER_TABLES = ("measurements", "alerts", "alert_measurements", "ml_predictions", "weekly_reports", "patient_bands")


def test_live_poll_catches_late_rows_and_writes_only_flags(conn):  # [M6], [H6]
    from pulse_ml.monitor import poll_once
    count = lambda t: conn.execute(f"select count(*) from public.{t}").fetchone()[0]  # noqa: E731
    before = {t: count(t) for t in OTHER_TABLES}
    patient, device = ringless_patient_with_test_ring(conn)
    for i in range(3):
        conn.execute("insert into public.wearable_samples (patient_id, device_id, metric, value, unit, measured_at,"
                     " source, external_id) values (%s, %s, 'spo2', 89.5, 'percent', now() - interval '1 minute',"
                     " 'simulated', %s)", (patient, device, f"test-{i}"))
    ahead = conn.execute("select now() + interval '1 minute'").fetchone()[0]  # watermark already past the rows
    _, written = poll_once(conn, ahead)
    assert written >= 1
    new = conn.execute("select patient_id::text, metric, kind, window_kind from public.wearable_flags"
                       " where created_at = now()").fetchall()  # rows written in this (rolled-back) transaction
    assert (patient, "spo2", "outside_reference", "live_10min") in new
    assert {w for *_, w in new} == {"live_10min"}
    assert poll_once(conn, ahead)[1] == 0                           # dedup: nothing new the second time
    assert {t: count(t) for t in OTHER_TABLES} == before


def test_night_run_flags_the_seeded_episode(conn):
    from pulse_ml.monitor import run_nights
    run_nights(conn)
    patient, _ = karim()
    n = conn.execute("select count(*) from public.wearable_flags where patient_id = %s and metric = 'heart_rate'"
                     " and kind = 'personal_anomaly' and window_start > now() - interval '5 days'",
                     (patient,)).fetchone()[0]
    assert n >= 1
