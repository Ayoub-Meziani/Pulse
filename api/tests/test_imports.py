"""Patient file imports: readings through the reading rules (fresh, measured rows only), ring samples never."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.analysis import texts
from app.config import Settings
from app.main import create_app
from conftest import SUPABASE_URL, TEST_JWKS, assign, auth_header, new_user

pytestmark = pytest.mark.db
API = "/api/v1"


def ago(**kw) -> str:
    return (datetime.now(timezone.utc) - timedelta(**kw)).isoformat()


def csv_of(*rows, header="measured_at,systolic,diastolic,pulse", comment=None) -> str:
    lines = ([comment] if comment else []) + [header] + [",".join(str(v) for v in r) for r in rows]
    return "\n".join(lines) + "\n"


def upload(api, patient, csv, provenance="measured", name="cuff.csv", who=None):
    return api.post(f"{API}/patients/{patient}/imports/readings", headers=auth_header(who or patient),
                    json={"file_name": name, "csv": csv, "provenance": provenance})


def ok(r) -> dict:
    assert r.status_code == 201, r.text
    return r.json()


def alerts_of(conn, patient) -> list:
    return conn.execute(text("select rule_code, alert_class, persistent from public.alerts where patient_id = :p "
                             "order by created_at"), {"p": patient}).all()


@pytest.fixture
def people(conn):
    patient, other = new_user(conn, "patient", "Nadia B."), new_user(conn, "patient")
    doctor = new_user(conn, "doctor")
    assign(conn, doctor, patient)
    return dict(patient=patient, other=other, doctor=doctor)


# ---------------------------------------------------------------- fresh measured rows: the reading rules
def test_fresh_severe_measured_row_opens_the_severe_alert_and_asks_for_the_symptom_check(api, conn, people):
    p = people["patient"]
    body = ok(upload(api, p, csv_of((ago(minutes=5), 186, 118, 96))))
    assert (body["inserted"], body["by_status"]["valid"], body["historical"]) == (1, 1, 0)
    ev = body["evaluation"]
    assert (ev["level"], ev["rule_id"], ev["requires_symptom_check"], ev["recheck_after_seconds"]) == \
        ("severe", "R-SEV-1", True, 60)
    assert body["measurement"]["source"] == "csv_import" and body["measurement"]["provenance"] == "measured"
    assert [(a["level"], a["rule_id"], a["status"]) for a in body["alerts"]] == [("severe", "R-SEV-1", "open")]
    assert body["next_step"] == texts.NEXT_STEP["R-SEV-1"]


def test_highest_level_wins_and_any_row_can_ask_for_the_symptom_check(api, conn, people):
    p = people["patient"]
    body = ok(upload(api, p, csv_of((ago(minutes=8), 186, 118, 96), (ago(minutes=5), 128, 80, 72))))
    ev = body["evaluation"]
    # Same level (severe): the latest result is shown, as after a manual recheck, and the symptom check the
    # first row asked for is still required.
    assert (ev["level"], ev["rule_id"], ev["requires_symptom_check"]) == ("severe", "R-SEV-3", True)
    assert [r[0] for r in alerts_of(conn, p)] == ["R-SEV-1"]  # the lower recheck joins the same episode


def test_two_severe_rows_three_minutes_apart_are_one_persistent_episode(api, conn, people):
    p = people["patient"]
    ok(upload(api, p, csv_of((ago(minutes=8), 186, 118, 96), (ago(minutes=5), 188, 121, 97))))
    assert alerts_of(conn, p) == [("R-SEV-1", "severely_high", True)]


def test_fresh_implausible_row_is_invalid_with_a_symptom_check_and_no_alert(api, conn, people):
    p = people["patient"]
    body = ok(upload(api, p, csv_of((ago(minutes=5), 320, 130, 90))))
    ev = body["evaluation"]
    assert (ev["rule_id"], ev["requires_symptom_check"], body["by_status"]["invalid"]) == ("DATA-INVALID", True, 1)
    assert body["alerts"] == [] and alerts_of(conn, p) == []


def test_fresh_low_row_opens_a_low_alert_and_a_simulated_one_only_previews_it(api, conn, people):
    p = people["patient"]
    body = ok(upload(api, p, csv_of((ago(minutes=5), 85, 55, 70))))
    assert (body["evaluation"]["level"], body["evaluation"]["rule_id"]) == ("low", "R-LOW-1")
    assert alerts_of(conn, p) == [("R-LOW-1", "follow_up", False)]
    sim = ok(upload(api, p, csv_of((ago(minutes=3), 65, 40, 70), comment="# SIMULATED demo"), "simulated"))
    assert [(x["level"], x["rule_id"]) for x in sim["simulated_preview"]] == [("low", "R-LOW-2")]
    assert len(alerts_of(conn, p)) == 1


def test_old_severe_row_is_history_only_and_asks_for_a_reading_now(api, conn, people):
    p = people["patient"]
    body = ok(upload(api, p, csv_of((ago(days=3), 186, 118, 96), (ago(days=2), 132, 84, 70))))
    assert (body["historical"], body["past_severe"], body["evaluation"], body["alerts"]) == (2, 1, None, [])
    assert body["next_step"] == texts.NEXT_STEP["IMPORT-PAST-SEVERE"]
    assert alerts_of(conn, p) == []


def test_fresh_above_target_rows_and_recent_history_feed_the_trend_once(api, conn, people):
    p = people["patient"]
    rows = [(ago(days=d), 152, 95, 80) for d in (3, 2, 1)] + [(ago(minutes=6), 150, 94, 78), (ago(minutes=4), 151, 93, 77)]
    body = ok(upload(api, p, csv_of(*rows)))
    assert sorted(r[0] for r in alerts_of(conn, p)) == ["R-TGT-1", "R-TRD-1"]
    assert {a["rule_id"] for a in body["alerts"]} == {"R-TGT-1", "R-TRD-1"}
    # Once per file: the trend alert is created on the newest row and no later row is attached to it.
    trend = conn.execute(text("select a.id, m.systolic from public.alerts a join public.measurements m "
                              "on m.id = a.measurement_id where a.patient_id = :p and a.rule_code = 'R-TRD-1'"),
                         {"p": p}).one()
    links = conn.execute(text("select count(*) from public.alert_measurements where alert_id = :a"),
                         {"a": trend.id}).scalar()
    assert (trend.systolic, links) == (151, 0)


def test_severe_row_older_than_the_recheck_can_reach_is_history_and_asks_for_a_reading_now(api, conn, people):
    p = people["patient"]
    body = ok(upload(api, p, csv_of((ago(minutes=12), 186, 118, 96))))
    assert (body["historical"], body["past_severe"], body["evaluation"]) == (1, 1, None)
    assert body["next_step"] == texts.NEXT_STEP["IMPORT-PAST-SEVERE"] and alerts_of(conn, p) == []


def test_recheck_after_an_imported_severe_row_joins_the_episode(api, conn, people):
    p = people["patient"]
    assert ok(upload(api, p, csv_of((ago(minutes=8), 186, 118, 96))))["evaluation"]["recheck_after_seconds"] == 60
    recheck = api.post(f"{API}/patients/{p}/measurements", json={"systolic": 184, "diastolic": 121},
                       headers=auth_header(p)).json()
    assert recheck["evaluation"]["rule_id"] == "R-SEV-2"
    assert alerts_of(conn, p) == [("R-SEV-1", "severely_high", True)]


def test_row_older_than_a_reading_already_evaluated_never_reopens_its_episode(api, conn, people):
    p = people["patient"]
    api.post(f"{API}/patients/{p}/measurements", json={"systolic": 186, "diastolic": 118}, headers=auth_header(p))
    body = ok(upload(api, p, csv_of((ago(minutes=6), 186, 118, 96))))   # the cuff's time, typed in later
    assert (body["inserted"], body["historical"], body["past_severe"], body["alerts"]) == (1, 1, 1, [])
    assert alerts_of(conn, p) == [("R-SEV-1", "severely_high", False)]


def test_cuff_export_of_a_reading_typed_by_hand_is_a_duplicate_and_its_recheck_still_counts(api, conn, people):
    p = people["patient"]
    typed = datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(minutes=4)
    api.post(f"{API}/patients/{p}/measurements", headers=auth_header(p),
             json={"systolic": 186, "diastolic": 118, "measured_at": typed.isoformat()})   # no pulse, no seconds
    rows = [((typed + timedelta(seconds=37)).isoformat(), 186, 118, 96),
            ((typed + timedelta(seconds=100)).isoformat(), 186, 118, 97)]               # the recheck, not typed
    body = ok(upload(api, p, csv_of(*rows)))
    assert (body["inserted"], body["duplicates"], body["evaluation"]["rule_id"]) == (1, 1, "R-SEV-2")
    assert alerts_of(conn, p) == [("R-SEV-1", "severely_high", True)]


# ---------------------------------------------------------------- simulated rows: preview, never an alert
def test_simulated_severe_row_creates_no_alert_and_returns_a_preview(api, conn, people):
    p = people["patient"]
    body = ok(upload(api, p, csv_of((ago(minutes=5), 186, 118, 96), comment="# SIMULATED demo"), "simulated"))
    assert (body["alerts"], body["evaluation"], body["measurement"]) == ([], None, None)
    assert [(x["level"], x["rule_id"]) for x in body["simulated_preview"]] == [("severe", "R-SEV-1")]
    assert body["next_step"] == texts.NEXT_STEP["IMPORT-SIMULATED"]
    assert alerts_of(conn, p) == []
    provenance = conn.execute(text("select provenance from public.measurements where patient_id = :p"),
                              {"p": p}).scalar_one()
    assert provenance == "simulated"


def test_all_simulated_recent_rows_never_create_a_trend_alert(api, conn, people):
    p = people["patient"]
    rows = [(ago(days=d), 160, 98, 80) for d in (3, 2, 1)] + [(ago(minutes=5), 158, 97, 80)]
    ok(upload(api, p, csv_of(*rows), "simulated"))
    assert alerts_of(conn, p) == []


def test_a_file_that_says_simulated_cannot_be_imported_as_measured(api, people):
    r = upload(api, people["patient"], csv_of((ago(minutes=5), 130, 80, 70), comment="# SYNTHETIC sample"))
    assert r.status_code == 422 and r.json()["error"]["details"][0]["code"] == "file_is_simulated"


def test_simulated_data_is_refused_outside_demo_mode(conn, session_factory, people):
    app = create_app(Settings(supabase_url=SUPABASE_URL, jwks=TEST_JWKS, demo_mode=False))
    app.state.session_factory = session_factory
    r = upload(TestClient(app), people["patient"], csv_of((ago(minutes=5), 130, 80, 70)), "simulated")
    assert r.status_code == 422 and r.json()["error"]["details"][0]["code"] == "simulated_not_allowed"


# ---------------------------------------------------------------- duplicates, rejections, files
def test_duplicates_and_same_file(api, conn, people):
    p = people["patient"]
    rows = [(ago(days=2), 130, 82, 70), (ago(days=1), 128, 80, 71)]
    first = csv_of(*rows)
    assert ok(upload(api, p, first))["inserted"] == 2
    again = upload(api, p, first)
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_imported"
    overlap = ok(upload(api, p, csv_of(*rows, comment="# export 2"), name="cuff2.csv"))
    assert (overlap["inserted"], overlap["duplicates"], overlap["next_step"]) == \
        (0, 2, texts.NEXT_STEP["IMPORT-NOTHING"])
    batch = conn.execute(text("select rows_total, rows_inserted, rows_duplicate, created_by from "
                              "public.ingestion_batches where patient_id = :p and file_name = 'cuff2.csv'"),
                         {"p": p}).one()
    assert batch == (2, 0, 2, p)


def test_a_stored_row_repeated_in_a_merged_file_is_skipped_every_time(api, people):
    p = people["patient"]
    row = (ago(days=1), 150, 95, 70)
    ok(upload(api, p, csv_of(row)))
    merged = ok(upload(api, p, csv_of(row, row, (ago(hours=20), 140, 88, 72)), name="merged.csv"))
    assert (merged["inserted"], merged["duplicates"]) == (1, 2)


def test_a_typed_entry_and_its_cuff_copy_in_one_file_are_one_reading(api, conn, people):
    p = people["patient"]
    at = ago(minutes=5)
    body = ok(upload(api, p, csv_of((at, 186, 118, ""), (at, 186, 118, 96))))
    assert (body["inserted"], body["duplicates"]) == (1, 1)
    assert alerts_of(conn, p) == [("R-SEV-1", "severely_high", False)]          # not a persistent recheck


def test_a_very_low_row_is_not_hidden_by_a_later_above_target_row(api, people):
    body = ok(upload(api, people["patient"], csv_of((ago(minutes=6), 66, 42, 70), (ago(minutes=4), 150, 92, 72))))
    ev = body["evaluation"]
    assert (ev["level"], ev["rule_id"], ev["requires_symptom_check"], ev["recheck_after_seconds"]) ==         ("low", "R-LOW-2", True, 60)


def test_an_old_very_low_row_asks_for_a_reading_now(api, conn, people):
    p = people["patient"]
    body = ok(upload(api, p, csv_of((ago(minutes=30), 62, 38, 60))))
    assert (body["historical"], body["evaluation"], body["next_step"]) == (1, None, texts.NEXT_STEP["IMPORT-PAST-LOW"])
    assert alerts_of(conn, p) == []


def test_a_real_file_imported_as_simulated_by_mistake_can_be_imported_again(api, conn, people):
    p = people["patient"]
    csv = csv_of((ago(days=2), 130, 82, 70), (ago(days=1), 128, 80, 71))
    assert ok(upload(api, p, csv, "simulated"))["inserted"] == 2
    again = ok(upload(api, p, csv))
    assert (again["inserted"], again["duplicates"]) == (2, 0)
    # The database's possible_duplicate flag ignores the label (policy pulse-v1), so these rows stay out of alerts.


def test_a_file_whose_rows_are_all_rejected_says_so(api, people):
    body = ok(upload(api, people["patient"], csv_of((ago(days=1), "x", 80, 70))))
    assert (body["inserted"], body["duplicates"], body["next_step"]) == (0, 0, texts.NEXT_STEP["IMPORT-REJECTED"])


def test_bad_rows_are_reported_and_the_rest_is_kept(api, people):
    p = people["patient"]
    csv = csv_of((ago(days=1), 130, 82, 70), (ago(days=1, hours=1), "x", 80, 70), (ago(days=2), 128, "", 70),
                 header="measured_at,systolic,diastolic,pulse")
    body = ok(upload(api, p, csv))
    assert body["inserted"] == 1
    assert [(x["row"], x["reasons"]) for x in body["rejected"]] == [(3, ["not_integer_systolic"]),
                                                                    (4, ["missing_diastolic"])]


@pytest.mark.parametrize("csv,code", [
    ("# nothing\n", "empty_file"),
    ("measured_at,systolic\n2026-10-01 08:00,120\n", "missing_column"),
])
def test_unreadable_files_are_422_not_500(api, people, csv, code):
    r = upload(api, people["patient"], csv)
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_file"
    assert r.json()["error"]["details"][0]["code"] == code


def test_unknown_time_zone_is_422(api, people):
    p = people["patient"]
    r = api.post(f"{API}/patients/{p}/imports/readings", headers=auth_header(p),
                 json={"file_name": "a.csv", "csv": csv_of((ago(days=1), 130, 80, 70)), "provenance": "measured",
                       "tz": "Mars/Olympus"})
    assert r.status_code == 422 and r.json()["error"]["details"][0]["code"] == "invalid_timezone"


@pytest.mark.parametrize("who", ["doctor", "other"])
def test_only_the_patient_can_import(api, people, who):
    r = upload(api, people["patient"], csv_of((ago(days=1), 130, 80, 70)), who=people[who])
    assert r.status_code == 403


# ---------------------------------------------------------------- ring samples: never an alert
def ring_csv(*rows, comment="# SIMULATED ring export") -> str:
    return "\n".join([comment, "measured_at,metric,value,unit,external_id"]
                     + [",".join(str(v) for v in r) for r in rows]) + "\n"


def upload_ring(api, patient, csv, source="simulated", who=None):
    return api.post(f"{API}/patients/{patient}/imports/ring", headers=auth_header(who or patient),
                    json={"file_name": "ring.csv", "csv": csv, "source": source})


def test_ring_import_creates_a_simulated_ring_dedups_and_never_alerts(api, conn, people):
    p = people["patient"]
    csv = ring_csv((ago(hours=3), "heart_rate", 58, "bpm", "a1"), (ago(hours=3), "spo2", 89.5, "%", ""),
                   (ago(hours=2), "heart_rate", 400, "bpm", "a2"))
    body = ok(upload_ring(api, p, csv))
    assert body["inserted_by_metric"] == {"heart_rate": 1, "spo2": 1} and body["duplicates"] == 0
    assert body["rejected"][0]["reasons"][0].startswith("refused_by_database")
    assert body["next_step"] == texts.NEXT_STEP["IMPORT-RING"]
    device = conn.execute(text("select device_type, bp_capability from public.devices where id = :d"),
                          {"d": body["device_id"]}).one()
    assert device == ("simulator", "simulated")
    again = ok(upload_ring(api, p, csv))
    assert (again["inserted_by_metric"], again["duplicates"], again["device_id"]) == ({}, 2, body["device_id"])
    assert alerts_of(conn, p) == []  # a low SpO2 never raises an alert (D18)


def test_real_ring_export_goes_to_a_real_wearable(api, conn, people):
    p = people["patient"]
    body = ok(upload_ring(api, p, ring_csv((ago(hours=3), "heart_rate", 61, "", "r1"), comment="# export"),
                          source="csv_import"))
    device = conn.execute(text("select device_type, bp_capability from public.devices where id = :d"),
                          {"d": body["device_id"]}).one()
    assert device == ("wearable", "none")


def test_simulated_ring_file_cannot_pass_as_a_real_export(api, people):
    r = upload_ring(api, people["patient"], ring_csv((ago(hours=3), "heart_rate", 61, "", "")), source="csv_import")
    assert r.status_code == 422
    assert (r.json()["error"]["details"][0]["code"], r.json()["error"]["details"][0]["field"]) ==         ("file_is_simulated", "source")                                                    # RingImportIn.source


def test_only_the_patient_can_import_ring_data(api, people):
    r = upload_ring(api, people["patient"], ring_csv((ago(hours=3), "heart_rate", 61, "", "")),
                    who=people["doctor"])
    assert r.status_code == 403
