"""Descriptive statistics for the patient and doctor views. Pure function.

Questionable readings are counted but excluded from averages and trend.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from statistics import mean

from .rules import is_above_target
from .types import Reading, Summary, Target

TREND_DELTA_SYSTOLIC = 5   # mmHg change in 7-day mean that counts as rising / falling
MIN_READINGS_FOR_TREND = 3


def _within(readings: list[Reading], now: datetime, start_days: int, end_days: int) -> list[Reading]:
    lo, hi = now - timedelta(days=end_days), now - timedelta(days=start_days)
    return [r for r in readings if lo < r.measured_at <= hi]


def _avg(values: list[int]) -> float | None:
    return round(mean(values), 1) if values else None


def compute_summary(readings: list[Reading], target: Target, now: datetime) -> Summary:
    readings = [r for r in readings if r.measured_at <= now]
    last7_all = _within(readings, now, 0, 7)
    last7 = [r for r in last7_all if r.validation_status == "valid"]
    prev7 = [r for r in _within(readings, now, 7, 14) if r.validation_status == "valid"]
    last30 = [r for r in _within(readings, now, 0, 30) if r.validation_status == "valid"]

    if len(last7) >= MIN_READINGS_FOR_TREND and len(prev7) >= MIN_READINGS_FOR_TREND:
        delta = mean(r.systolic for r in last7) - mean(r.systolic for r in prev7)
        trend = "rising" if delta >= TREND_DELTA_SYSTOLIC else \
            "falling" if delta <= -TREND_DELTA_SYSTOLIC else "stable"
    else:
        trend = "insufficient_data"

    above = [r for r in last7 if is_above_target(r.systolic, r.diastolic, target)]
    return Summary(
        window_days=7,
        count_7d=len(last7),
        count_questionable_7d=len(last7_all) - len(last7),
        avg_systolic_7d=_avg([r.systolic for r in last7]),
        avg_diastolic_7d=_avg([r.diastolic for r in last7]),
        avg_systolic_30d=_avg([r.systolic for r in last30]),
        avg_diastolic_30d=_avg([r.diastolic for r in last30]),
        max_systolic_7d=max((r.systolic for r in last7), default=None),
        max_diastolic_7d=max((r.diastolic for r in last7), default=None),
        pct_above_target_7d=round(100 * len(above) / len(last7), 1) if last7 else None,
        days_with_reading_7d=len({r.measured_at.date() for r in last7}),
        trend=trend,
        last_measured_at=max((r.measured_at for r in readings), default=None),
        target=target,
    )
