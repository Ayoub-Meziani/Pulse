"""Rule test vectors T1-T16 from the conception, plus summary checks."""
from datetime import datetime, timedelta, timezone

import pytest

from app.analysis import (compute_summary, evaluate_measurement, evaluate_symptoms,
                          evaluate_trend, validate_measurement)
from app.analysis.rules import KNOWN_SYMPTOMS, RED_FLAG_SYMPTOMS
from app.analysis.types import ActiveAlert, Reading, Target

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
TARGET = Target(140, 90, is_default=True)


def r(s, d, minutes_ago=0, status="valid", rid=None):
    return Reading(s, d, NOW - timedelta(minutes=minutes_ago), validation_status=status, id=rid)


# ---------------------------------------------------------------- validation (V1-V4)
def test_t13_systolic_not_above_diastolic_rejected():
    v = validate_measurement(120, 130, None, NOW, NOW)
    assert not v.ok and any(e.code == "not_above_diastolic" for e in v.errors)


@pytest.mark.parametrize("s,d,p", [(310, 100, None), (40, 30, None), (150, 25, None), (150, 90, 300)])
def test_t14_out_of_range_rejected(s, d, p):
    v = validate_measurement(s, d, p, NOW, NOW)
    assert not v.ok and any(e.code == "out_of_range" for e in v.errors)


def test_t15_odd_pulse_pressure_is_questionable_and_still_severe():
    v = validate_measurement(200, 190, None, NOW, NOW)
    assert v.ok and v.status == "questionable" and v.notes
    ev = evaluate_measurement(r(200, 190, status="questionable"), TARGET, [])
    assert ev.level == "severe" and ev.rule_id == "R-SEV-1"


def test_t16_future_reading_rejected():
    v = validate_measurement(130, 80, None, NOW + timedelta(hours=1), NOW)
    assert not v.ok and v.errors[0].code == "in_future"


def test_small_clock_skew_accepted():
    assert validate_measurement(130, 80, 70, NOW + timedelta(minutes=2), NOW).ok


# ---------------------------------------------------------------- measurement rules
def test_t1_below_target_no_alert():
    ev = evaluate_measurement(r(128, 82), TARGET, [])
    assert ev.level == "none" and ev.alert_action == "none"


def test_t2_above_target_notice():
    ev = evaluate_measurement(r(146, 88), TARGET, [])
    assert (ev.level, ev.rule_id, ev.alert_action) == ("notice", "R-TGT-1", "create")
    assert "general target" in ev.reason


def test_t3_second_above_target_attaches_to_open_notice():
    open_notice = ActiveAlert(5, "notice", "R-TGT-1", NOW - timedelta(hours=3))
    ev = evaluate_measurement(r(150, 92), TARGET, [open_notice])
    assert ev.alert_action == "attach" and ev.target_alert_id == 5


def test_t6_systolic_boundary_is_severe():
    ev = evaluate_measurement(r(180, 100), TARGET, [])
    assert ev.level == "severe" and ev.requires_symptom_check and ev.recheck_after_seconds == 60


def test_t7_diastolic_boundary_is_severe():
    ev = evaluate_measurement(r(160, 120), TARGET, [])
    assert ev.level == "severe" and "Diastolic" in ev.reason


def test_t8_just_below_severe_is_notice():
    ev = evaluate_measurement(r(179, 119), TARGET, [])
    assert ev.level == "notice"


def test_t9_recheck_still_severe_is_persistent():
    sev = ActiveAlert(9, "severe", "R-SEV-1", NOW - timedelta(seconds=70))
    ev = evaluate_measurement(r(184, 121), TARGET, [sev])
    assert (ev.rule_id, ev.alert_action, ev.target_alert_id, ev.persistent) == ("R-SEV-2", "attach", 9, True)


def test_t10_recheck_lower_keeps_severe_open():
    sev = ActiveAlert(9, "severe", "R-SEV-1", NOW - timedelta(minutes=2))
    ev = evaluate_measurement(r(165, 100), TARGET, [sev])
    assert (ev.level, ev.rule_id, ev.alert_action) == ("severe", "R-SEV-3", "attach")


def test_severe_older_than_recheck_window_starts_new_alert():
    old = ActiveAlert(9, "severe", "R-SEV-1", NOW - timedelta(minutes=40))
    ev = evaluate_measurement(r(185, 110), TARGET, [old])
    assert ev.rule_id == "R-SEV-1" and ev.alert_action == "create"


def test_doctor_target_wording():
    ev = evaluate_measurement(r(132, 82), Target(130, 80, is_default=False), [])
    assert ev.level == "notice" and "your target" in ev.reason


# ---------------------------------------------------------------- trend
def test_t4_trend_alert():
    readings = [r(148, 93, minutes_ago=60 * 24 * k) for k in range(4)]
    ev = evaluate_trend(readings, TARGET, [], NOW)
    assert ev is not None and ev.rule_id == "R-TRD-1" and ev.alert_action == "create"


def test_t5_trend_needs_three_readings():
    readings = [r(160, 100, minutes_ago=60 * 24 * k) for k in range(2)]
    assert evaluate_trend(readings, TARGET, [], NOW) is None


def test_trend_ignores_questionable_and_old_readings():
    readings = [r(160, 100, minutes_ago=10, status="questionable")] * 3 + \
               [r(160, 100, minutes_ago=60 * 24 * 9)] * 3
    assert evaluate_trend(readings, TARGET, [], NOW) is None


def test_trend_attaches_to_open_trend():
    readings = [r(150, 95, minutes_ago=60 * k) for k in range(3)]
    open_trend = ActiveAlert(3, "trend", "R-TRD-1", NOW - timedelta(days=1))
    ev = evaluate_trend(readings, TARGET, [open_trend], NOW)
    assert ev.alert_action == "attach" and ev.target_alert_id == 3


# ---------------------------------------------------------------- symptoms
def test_t11_symptom_with_normal_bp_is_emergency():
    ev = evaluate_symptoms(["chest_pain"], [], NOW)
    assert ev.level == "emergency" and ev.show_emergency and ev.alert_action == "create"


def test_t12_symptom_raises_open_severe_alert():
    sev = ActiveAlert(11, "severe", "R-SEV-1", NOW - timedelta(minutes=3))
    ev = evaluate_symptoms(["vision_change"], [sev], NOW)
    assert (ev.level, ev.alert_action, ev.target_alert_id) == ("emergency", "raise", 11)


def test_no_symptoms_no_alert():
    assert evaluate_symptoms([], [], NOW).alert_action == "none"


def test_unknown_symptom_code_rejected():
    with pytest.raises(ValueError):
        evaluate_symptoms(["headache_xyz"], [], NOW)


def test_non_red_flag_symptom_is_recorded_but_not_emergency():
    ev = evaluate_symptoms(["dizziness", "nausea"], [], NOW)
    assert (ev.level, ev.alert_action, ev.show_emergency) == ("none", "none", False)
    assert "doctor will see" in ev.next_step


def test_red_flag_among_other_symptoms_is_emergency():
    ev = evaluate_symptoms(["dizziness", "difficulty_speaking"], [], NOW)
    assert ev.level == "emergency" and ev.show_emergency
    assert "difficulty speaking" in ev.reason and "dizziness" not in ev.reason


def test_red_flags_are_the_seven_aha_signs():
    assert RED_FLAG_SYMPTOMS == {"chest_pain", "shortness_of_breath", "back_pain", "numbness",
                                 "weakness", "vision_change", "difficulty_speaking"}
    assert RED_FLAG_SYMPTOMS < KNOWN_SYMPTOMS and len(KNOWN_SYMPTOMS) == 13


# ---------------------------------------------------------------- summary
def test_summary_insufficient_data():
    s = compute_summary([r(130, 80)], TARGET, NOW)
    assert s.trend == "insufficient_data" and s.count_7d == 1 and s.pct_above_target_7d == 0.0


def test_summary_rising_and_excludes_questionable():
    prev = [r(130, 80, minutes_ago=60 * 24 * (8 + k)) for k in range(3)]
    last = [r(140, 88, minutes_ago=60 * 24 * k + 30) for k in range(3)]
    odd = [r(200, 190, minutes_ago=5, status="questionable")]
    s = compute_summary(prev + last + odd, TARGET, NOW)
    assert s.trend == "rising"
    assert s.count_7d == 3 and s.count_questionable_7d == 1
    assert s.avg_systolic_7d == 140.0 and s.max_systolic_7d == 140
    assert s.pct_above_target_7d == 100.0
    assert s.last_measured_at == NOW - timedelta(minutes=5)


def test_summary_empty():
    s = compute_summary([], TARGET, NOW)
    assert s.count_7d == 0 and s.avg_systolic_7d is None and s.last_measured_at is None
