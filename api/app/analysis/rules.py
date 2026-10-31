"""Deterministic alert rules. Pure functions, independent of any ML model.

Prototype policy only; thresholds and wording need clinician review.

Rule ids:
  R-EMG-1  any red-flag symptom reported                       -> emergency
  R-SEV-1  systolic >= 180 or diastolic >= 120                 -> severe (symptom check, recheck 60 s)
  R-SEV-2  recheck within 15 min still >= 180 / >= 120         -> severe, persistent (attach)
  R-SEV-3  recheck within 15 min below 180 / 120               -> severe alert stays open (attach); systolic < 70
                                                                  also gets R-LOW-2's symptom check and recheck
  R-TGT-1  reading >= target                                   -> notice (one active notice per patient)
  R-LOW-2  systolic < 70                                       -> low (symptom check, recheck 60 s)
  R-LOW-1  systolic < 90 or diastolic < 60                     -> low (one active low alert per patient)
  R-TRD-1  >= 3 valid readings in 7 days, mean >= target       -> trend (one active trend per patient)

Low pressure (proposed decision D27): below 90/60 is low blood pressure in public guidance (AHA, NHS); it matters
most with dizziness, fainting or confusion. High pressure, an open severe episode and a reading above target take
priority (150/55 is above target, not low). Readings too low to be real are invalid (DATA-INVALID, symptom check).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from statistics import mean

from . import texts
from .types import ActiveAlert, Evaluation, Reading, Target

SEVERE_SYSTOLIC = 180
SEVERE_DIASTOLIC = 120
LOW_SYSTOLIC = 90        # R-LOW-1: below 90 systolic or 60 diastolic (pending clinician review)
LOW_DIASTOLIC = 60
VERY_LOW_SYSTOLIC = 70   # R-LOW-2: symptom check and recheck (pending clinician review)
RECHECK_SECONDS = 60
RECHECK_WINDOW = timedelta(minutes=15)
TREND_WINDOW = timedelta(days=7)
TREND_MIN_READINGS = 3

KNOWN_SYMPTOMS = frozenset(texts.SYMPTOM_LABELS)
# AHA hypertensive-crisis warning signs. Other recorded symptoms are kept for the doctor but do not
# trigger the emergency rule (pending clinician review, e.g. severe_headache, confusion).
RED_FLAG_SYMPTOMS = frozenset({"chest_pain", "shortness_of_breath", "back_pain", "numbness",
                               "weakness", "vision_change", "difficulty_speaking"})


def is_severe(systolic: int, diastolic: int) -> bool:
    return systolic >= SEVERE_SYSTOLIC or diastolic >= SEVERE_DIASTOLIC


def is_low(systolic: int, diastolic: int) -> bool:
    return systolic < LOW_SYSTOLIC or diastolic < LOW_DIASTOLIC


def is_above_target(systolic: float, diastolic: float, target: Target) -> bool:
    return systolic >= target.systolic or diastolic >= target.diastolic


def _recent_severe(reading: Reading, active: list[ActiveAlert]) -> ActiveAlert | None:
    """Active severe/emergency alert triggered within the recheck window before this reading."""
    candidates = [
        a for a in active
        if a.level in ("severe", "emergency")
        and timedelta(0) <= reading.measured_at - a.triggered_at <= RECHECK_WINDOW
    ]
    return max(candidates, key=lambda a: a.triggered_at, default=None)


def _active(active: list[ActiveAlert], level: str) -> ActiveAlert | None:
    found = [a for a in active if a.level == level]
    return max(found, key=lambda a: a.triggered_at, default=None)


def evaluate_measurement(reading: Reading, target: Target,
                         active_alerts: list[ActiveAlert]) -> Evaluation:
    """Primary evaluation shown to the patient right after a reading."""
    s, d = reading.systolic, reading.diastolic
    previous_severe = _recent_severe(reading, active_alerts)

    if is_severe(s, d):
        if previous_severe is not None:
            return Evaluation(
                level="severe", rule_id="R-SEV-2",
                reason=f"Recheck {s}/{d} is still at or above 180/120.",
                next_step=texts.NEXT_STEP["R-SEV-2"],
                alert_action="attach", target_alert_id=previous_severe.id,
                requires_symptom_check=True, persistent=True)
        which = f"Systolic {s} is at or above 180" if s >= SEVERE_SYSTOLIC \
            else f"Diastolic {d} is at or above 120"
        return Evaluation(
            level="severe", rule_id="R-SEV-1", reason=f"{which}.",
            next_step=texts.NEXT_STEP["R-SEV-1"], alert_action="create",
            requires_symptom_check=True, recheck_after_seconds=RECHECK_SECONDS)

    if previous_severe is not None:
        # A fall from crisis level to very low within minutes (a faint, or a cuff fault) still gets R-LOW-2's checks.
        very_low = s < VERY_LOW_SYSTOLIC
        return Evaluation(
            level="severe", rule_id="R-SEV-3",
            reason=f"Recheck {s}/{d} is below 180/120.",
            next_step=texts.NEXT_STEP["R-LOW-2" if very_low else "R-SEV-3"],
            alert_action="attach", target_alert_id=previous_severe.id,
            requires_symptom_check=very_low, recheck_after_seconds=RECHECK_SECONDS if very_low else None)

    if is_above_target(s, d, target):
        label = texts.target_label(target.is_default)
        open_notice = _active(active_alerts, "notice")
        return Evaluation(
            level="notice", rule_id="R-TGT-1",
            reason=f"{s}/{d} is at or above {label} ({target.systolic}/{target.diastolic}).",
            next_step=texts.NEXT_STEP["R-TGT-1"].format(target_label=label),
            alert_action="attach" if open_notice else "create",
            target_alert_id=open_notice.id if open_notice else None)

    # After the target check: a low diastolic with a systolic above target (e.g. 150/55) stays R-TGT-1.
    if is_low(s, d):
        open_low = _active(active_alerts, "low")
        action = dict(alert_action="attach" if open_low else "create",
                      target_alert_id=open_low.id if open_low else None)
        if s < VERY_LOW_SYSTOLIC:
            return Evaluation(level="low", rule_id="R-LOW-2", reason=f"Systolic {s} is below {VERY_LOW_SYSTOLIC}.",
                              next_step=texts.NEXT_STEP["R-LOW-2"], requires_symptom_check=True,
                              recheck_after_seconds=RECHECK_SECONDS, **action)
        which = f"Systolic {s} is below {LOW_SYSTOLIC}" if s < LOW_SYSTOLIC \
            else f"Diastolic {d} is below {LOW_DIASTOLIC}"
        return Evaluation(level="low", rule_id="R-LOW-1", reason=f"{which}.", next_step=texts.NEXT_STEP["R-LOW-1"],
                          **action)

    return Evaluation(level="none", rule_id=None, reason="Below target.",
                      next_step=texts.NEXT_STEP[None], alert_action="none")


def evaluate_trend(readings: list[Reading], target: Target, active_alerts: list[ActiveAlert],
                   now: datetime) -> Evaluation | None:
    """Weekly trend check over VALID readings only. Returns None when no trend alert applies."""
    window = [r for r in readings
              if r.validation_status == "valid" and timedelta(0) <= now - r.measured_at <= TREND_WINDOW]
    if len(window) < TREND_MIN_READINGS:
        return None
    ms, md = mean(r.systolic for r in window), mean(r.diastolic for r in window)
    if not is_above_target(ms, md, target):
        return None
    label = texts.target_label(target.is_default)
    open_trend = _active(active_alerts, "trend")
    return Evaluation(
        level="trend", rule_id="R-TRD-1",
        reason=f"7-day average {ms:.0f}/{md:.0f} over {len(window)} readings is at or above {label} "
               f"({target.systolic}/{target.diastolic}).",
        next_step=texts.NEXT_STEP["R-TRD-1"].format(target_label=label),
        alert_action="attach" if open_trend else "create",
        target_alert_id=open_trend.id if open_trend else None)


def evaluate_symptoms(symptoms: list[str], active_alerts: list[ActiveAlert],
                      now: datetime) -> Evaluation:
    """Symptom check. Any red-flag symptom means emergency, whatever the reading."""
    unknown = [s for s in symptoms if s not in KNOWN_SYMPTOMS]
    if unknown:
        raise ValueError(f"Unknown symptom codes: {unknown}")
    red = [s for s in symptoms if s in RED_FLAG_SYMPTOMS]
    if not red:
        return Evaluation(level="none", rule_id=None, reason="No red-flag symptoms reported.",
                          next_step=texts.NO_RED_FLAG_NEXT_STEP if symptoms
                          else "Follow the instructions for your reading.", alert_action="none")
    labels = ", ".join(texts.SYMPTOM_LABELS[s] for s in red)
    # Raise the most recent active severe alert (from the last hour) instead of creating a second one.
    recent = [a for a in active_alerts
              if a.level in ("severe", "emergency") and now - a.triggered_at <= timedelta(hours=1)]
    target_alert = max(recent, key=lambda a: a.triggered_at, default=None)
    return Evaluation(
        level="emergency", rule_id="R-EMG-1", reason=f"Reported: {labels}.",
        next_step=texts.NEXT_STEP["R-EMG-1"],
        alert_action="raise" if target_alert else "create",
        target_alert_id=target_alert.id if target_alert else None,
        show_emergency=True)
