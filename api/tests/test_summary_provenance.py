"""GET /patients/{id}/summary: how many of the counted readings are measured, simulated or estimated.

count_7d_* split exactly the population behind count_7d (valid readings, last 7 days). needs_review readings are in
none of them (count_needs_review_7d), invalid readings in none of them (count_invalid_7d)."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from conftest import auth_header, new_user

pytestmark = pytest.mark.db
API = "/api/v1"
NOW = datetime.now(timezone.utc)


@pytest.fixture
def patient(conn):
    return new_user(conn, "patient", "Nadia M.")


def insert(conn, patient, s, d, at, provenance, source, method="unknown"):
    conn.execute(text("insert into public.measurements (patient_id, systolic, diastolic, measured_at, source, provenance, "
                      "method) values (:p, :s, :d, :at, :src, :prov, :m)"),
                 {"p": patient, "s": s, "d": d, "at": at, "src": source, "prov": provenance, "m": method})


def measured(conn, patient, s, d, days):
    insert(conn, patient, s, d, NOW - timedelta(days=days, hours=1), "measured", "manual")


def simulated(conn, patient, s, d, days):
    insert(conn, patient, s, d, NOW - timedelta(days=days, hours=1), "simulated", "simulated")


def summary(api, patient):
    r = api.get(f"{API}/patients/{patient}/summary", headers=auth_header(patient))
    assert r.status_code == 200, r.text
    return r.json()


def split(s):
    return (s["count_7d_measured"], s["count_7d_simulated"], s["count_7d_estimated"])


def test_empty_history_returns_zero_counts(api, patient):
    s = summary(api, patient)
    assert split(s) == (0, 0, 0) and s["count_7d"] == 0


def test_measured_only(api, conn, patient):
    for days, v in enumerate((130, 132, 134), start=1):
        measured(conn, patient, v, 85, days)
    s = summary(api, patient)
    assert split(s) == (3, 0, 0) and s["count_7d"] == 3


def test_simulated_only_is_visible_as_simulated(api, conn, patient):
    for days, v in enumerate((150, 152, 154, 156), start=1):
        simulated(conn, patient, v, 95, days)
    s = summary(api, patient)
    assert split(s) == (0, 4, 0) and s["count_7d"] == 4
    assert s["avg_systolic_7d"] == 153.0  # unchanged behaviour: simulated readings are still averaged (demo decision)


def test_mixed_history_reconciles_with_count_7d(api, conn, patient):
    for days, v in enumerate((130, 132), start=1):
        measured(conn, patient, v, 85, days)
    for days, v in enumerate((150, 152, 154), start=1):
        simulated(conn, patient, v, 95, days)
    s = summary(api, patient)
    assert split(s) == (2, 3, 0)
    assert sum(split(s)) == s["count_7d"] == 5


def test_only_the_last_seven_days_are_counted(api, conn, patient):
    measured(conn, patient, 130, 85, 2)
    measured(conn, patient, 131, 85, 9)       # outside the 7-day window
    simulated(conn, patient, 150, 95, 3)
    simulated(conn, patient, 151, 95, 20)     # outside the window
    s = summary(api, patient)
    assert split(s) == (1, 1, 0) and s["count_7d"] == 2


def test_needs_review_and_invalid_are_in_no_provenance_count(api, conn, patient):
    measured(conn, patient, 130, 85, 1)
    simulated(conn, patient, 150, 95, 1)
    measured(conn, patient, 262, 120, 2)      # unusual value -> needs_review
    measured(conn, patient, 120, 130, 2)      # systolic below diastolic -> invalid
    simulated(conn, patient, 270, 125, 2)     # simulated and needs_review
    s = summary(api, patient)
    assert (s["count_7d"], s["count_needs_review_7d"], s["count_invalid_7d"]) == (2, 2, 1)
    assert split(s) == (1, 1, 0) and sum(split(s)) == s["count_7d"]


def test_estimated_readings_are_needs_review_under_pulse_v1_so_not_counted_as_estimated(api, conn, patient):
    insert(conn, patient, 128, 82, NOW - timedelta(days=1), "estimated", "device_sync", method="wearable_estimate")
    s = summary(api, patient)
    assert split(s) == (0, 0, 0) and s["count_7d"] == 0 and s["count_needs_review_7d"] == 1


def test_a_wearable_user_without_cuff_readings_still_shows_zero_blood_pressure_counts(api, conn, patient):
    conn.execute(text("insert into public.devices (id, patient_id, device_type, bp_capability) "
                      "values (gen_random_uuid(), :p, 'wearable', 'none')"), {"p": patient})
    s = summary(api, patient)
    assert split(s) == (0, 0, 0)


def test_pct_above_target_and_trend_still_include_simulated_readings(api, conn, patient):
    """Documented behaviour (descriptive only): they use valid readings of any provenance."""
    for days, v in enumerate((150, 152, 154), start=1):
        simulated(conn, patient, v, 95, days)
    s = summary(api, patient)
    assert s["pct_above_target_7d"] == 100.0 and s["count_7d_measured"] == 0
    for days in range(8, 11):
        simulated(conn, patient, 130, 85, days)
    assert summary(api, patient)["trend"] == "rising"


def test_the_summary_never_creates_alerts(api, conn, patient):
    for days, v in enumerate((170, 172, 174), start=1):
        simulated(conn, patient, v, 100, days)
    summary(api, patient)
    n = conn.execute(text("select count(*) from public.alerts where patient_id = :p"), {"p": patient}).scalar()
    assert n == 0
