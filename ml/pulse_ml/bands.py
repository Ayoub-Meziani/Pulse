"""Proposed personal ring bands. The model only PROPOSES; a doctor activates through private.approve_band.

Band = personal median of the last 28 nights ± max(3 × robust SD, floor), then clipped to the cited
reference on the clinically meaningful side (never more permissive than the reference there).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import reference, ring

SPREAD = 3.0
FLOOR = {"heart_rate": 5.0, "hrv_rmssd": 5.0, "spo2": 1.5, "skin_temperature": 0.5}


def propose(nights: pd.DataFrame, metric: str) -> tuple[float, float] | None:
    """nights: one patient's night_table rows (last 28 days). None if fewer than 14 nights."""
    v = nights[metric].dropna().to_numpy()
    if len(v) < ring.MIN_BASELINE_NIGHTS:
        return None
    med = float(np.median(v))
    half = max(SPREAD * 1.4826 * float(np.median(np.abs(v - med))), FLOOR[metric])
    low, high = med - half, med + half
    ref = reference.RING_REFERENCE.get(metric)
    if ref:
        if "low" in ref["flag_sides"]:
            low = max(low, ref["low"])
            high = max(high, low + FLOOR[metric])
        if "high" in ref["flag_sides"]:
            high = min(high, ref["high"])
            low = min(low, high - FLOOR[metric])
    return round(low, 2), round(high, 2)


def propose_for_patient(nights: pd.DataFrame) -> list[dict]:
    return [{"metric": m, "statistic": ring.NIGHT_STAT[m], "low": b[0], "high": b[1]}
            for m in ring.METRICS if (b := propose(nights, m)) is not None]
