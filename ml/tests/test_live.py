"""live-v1: warnings BEFORE a limit is crossed, on synthetic minute-level nights (pulse_data.live_sim)."""
import os
import random

import pandas as pd
import pytest

from pulse_ml import live
from pulse_ml.train import ARTIFACTS

PERSONAL = ("heart_rate", "spo2", "hrv_rmssd", "skin_temperature")


@pytest.fixture(scope="module")
def bundle():
    path = ARTIFACTS / live.MODEL_VERSION / "model.joblib"
    if not path.exists():
        pytest.skip("live-v1 not trained: python -m pulse_ml.live_test")
    import joblib
    return joblib.load(path)


def night(situation, seed, conditions=("asthma",)):    # a condition that changes no limit (no random COPD / AF)
    from pulse_data import live_sim
    samples, truth = live_sim.night(random.Random(seed), situation, conditions)
    t = live.table(pd.DataFrame(samples, columns=["metric", "value", "unit", "minute"])[["minute", "metric", "value"]])
    ctx = live.Context(personal={m: truth[f"prev_{m}"] for m in PERSONAL}, conditions=tuple(conditions))
    return t, ctx, truth


def test_falling_oxygen_and_climbing_heart_rate_are_warned_before_the_limit(bundle):
    early = 0
    for seed in range(6):
        for situation in ("oxygen_falling", "heart_rate_climbing"):
            t, ctx, truth = night(situation, seed)
            first = [w["window_start"] for w in live.night_warnings(t, ctx, bundle)
                     if w["metric"] == truth["metric"] and w["window_start"] >= truth["onset"]]
            early += bool(first) and truth["crossing"] is not None and min(first) < truth["crossing"]
    assert early >= 10                                   # of 12 nights (unseen test: 93.5 % and 97.1 %)


def test_loose_ring_and_bathroom_spike_do_not_warn(bundle):
    assert sum(len(live.night_warnings(*night("false_alarm_traps", seed)[:2], bundle)) for seed in range(6)) <= 1


def test_whole_night_equals_minute_by_minute(bundle):
    t, ctx, _ = night("oxygen_falling", 1)
    expected = [(w["metric"], w["window_start"]) for w in live.night_warnings(t, ctx, bundle)]
    got, last = [], {}
    for i in range(len(t)):
        for w in live.latest_warnings(t.iloc[max(0, i - live.HISTORY_MINUTES + 1): i + 1], ctx, bundle, last):
            got.append((w["metric"], w["window_start"]))
            last[w["metric"]] = w["window_start"]
    assert got == sorted(expected, key=lambda x: x[1]) or sorted(got) == sorted(expected)
    assert expected                                       # and it did warn


def test_limits_follow_conditions_and_bands():
    ctx = live.Context(personal={"skin_temperature": 34.0})
    assert live.limit_for("spo2", ctx)[1] == 94 and live.limit_for("heart_rate", ctx)[1] == 100
    assert live.limit_for("spo2", live.Context(personal={}, conditions=("copd",)))[1] == 88
    assert live.limit_for("skin_temperature", ctx)[1] == 35.0
    assert live.limit_for("skin_temperature", live.Context(personal={})) is None      # no normal yet: no fever line
    assert live.limit_for("hrv_rmssd", live.Context(personal={}, conditions=("atrial_fibrillation",))) is None
    band = live.Context(personal={}, bands={"heart_rate": ("b1", 50.0, 90.0)})
    assert live.limit_for("heart_rate", band)[1:] == (90.0, "band:b1", "b1")


def test_quiet_period_and_two_minutes_in_a_row():
    from pulse_ml.live_test import _rule
    assert _rule([True] * 100) == [1, 31, 61, 91]
    assert _rule([True, False, True, False, True]) == []


# ---------------------------------------------------------------- local database (rolled back)

@pytest.fixture
def conn():
    psycopg = pytest.importorskip("psycopg")
    from pulse_ml.predict import LOCAL_DB
    try:
        c = psycopg.connect(os.environ.get("PULSE_TEST_DATABASE_URL", LOCAL_DB), autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("local PULSE database not reachable")
    if c.execute("select count(*) from pg_constraint where conname = 'wearable_flags_forecast_check'").fetchone()[0] == 0:
        pytest.skip("M9 missing; run `supabase migration up --local`")
    with c.transaction(force_rollback=True):
        yield c
    c.close()


def test_live_poll_writes_an_early_warning_and_nothing_else(conn, bundle):
    from pulse_data.simulate import PATIENTS
    from pulse_ml.monitor import poll_once
    t, ctx, truth = night("oxygen_falling", 1)
    w = min(x["window_start"] for x in live.night_warnings(t, ctx, bundle) if x["metric"] == "spo2")
    w = min(w + 3, truth["crossing"] - 1)    # Amina's own normal (her seeded nights) may move the warning a minute
    patient = next(p.id for p in PATIENTS if p.key == "controlled")                   # Amina + a test ring
    device = conn.execute("insert into public.devices (patient_id, device_type, bp_capability, label) values"
                          " (%s, 'wearable', 'none', 'test ring') returning id::text", (patient,)).fetchone()[0]
    ins = ("insert into public.wearable_samples (patient_id, device_id, metric, value, unit, measured_at, source,"
           " external_id) values (%s, %s, %s, %s, %s, {at}, 'simulated', %s)")
    units = {"heart_rate": "bpm", "spo2": "percent", "hrv_rmssd": "ms", "skin_temperature": "celsius"}
    for k in (1, 2, 3):                                  # 3 previous nights at the person's normal (02:00 local)
        for m in PERSONAL:
            at = (f"(date_trunc('day', now() at time zone 'Africa/Algiers') - interval '{k} days' + interval '2 hours')"
                  " at time zone 'Africa/Algiers'")
            conn.execute(ins.format(at=at), (patient, device, m, ctx.personal[m], units[m], f"prev-{k}-{m}"))
    for minute in range(w - live.HISTORY_MINUTES + 1, w + 1):   # the last hour of the night, ending at "now"
        for m, v in t.loc[minute].dropna().items():
            conn.execute(ins.format(at=f"now() - interval '{w - minute} minutes'"),
                         (patient, device, m, round(float(v), 2), units[m], f"live-{minute}-{m}"))
    ahead = conn.execute("select now() + interval '1 minute'").fetchone()[0]
    count = lambda tbl: conn.execute(f"select count(*) from public.{tbl}").fetchone()[0]  # noqa: E731
    before = {tbl: count(tbl) for tbl in ("measurements", "alerts", "ml_predictions", "weekly_reports")}
    poll_once(conn, ahead, bundle)
    rows = conn.execute("select metric, kind, window_kind, score from public.wearable_flags where patient_id = %s"
                        " and created_at = now()", (patient,)).fetchall()
    assert ("spo2", "early_warning", "forecast") in {r[:3] for r in rows}
    assert all(0 < float(r[3]) <= 1 for r in rows if r[1] == "early_warning")
    poll_once(conn, ahead, bundle)                       # same data again: no second warning (30-minute quiet)
    assert conn.execute("select count(*) from public.wearable_flags where patient_id = %s and kind = 'early_warning'"
                        " and metric = 'spo2'", (patient,)).fetchone()[0] == 1
    assert {tbl: count(tbl) for tbl in before} == before
