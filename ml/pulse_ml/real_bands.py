"""REAL population bands from NHANES 2017-March 2020: survey-weighted percentiles of seated pulse and BP.

    cd ml && ..\\.venv\\Scripts\\python -m pulse_ml.real_bands      # -> pulse_ml/reference_nhanes.json

Like is compared with like: NHANES pulse is a SEATED cuff pulse (Omron HEM-907XL, 5-minute rest, mean of up to 3
readings), so the bands are used for the patient's seated CUFF pulse (measurements.pulse), never for ring night
heart rate. NHANES BP is exam (office-type) BP, so BP bands are context only; home-BP categories stay ACC/AHA.
Only aggregated statistics are written (NCHS terms). Population: US adults, NOT Algerian adults.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .real_data import SOURCES, load_nhanes, valid_mean

OUT = Path(__file__).resolve().parent / "reference_nhanes.json"
PERCENTILES = (2.5, 10, 25, 50, 75, 90, 97.5)
AGE_BANDS = ((18, 29), (30, 44), (45, 59), (60, 69), (70, 79), (80, 80))   # NHANES top-codes age at 80
MIN_N = 50


def weighted_percentiles(values, weights, qs=PERCENTILES) -> list[float]:
    """Weighted percentiles (midpoint rule on the cumulative weight)."""
    v, w = np.asarray(values, float), np.asarray(weights, float)
    ok = ~np.isnan(v) & ~np.isnan(w) & (w > 0)
    v, w = v[ok], w[ok]
    order = np.argsort(v)
    v, w = v[order], w[order]
    cum = (np.cumsum(w) - 0.5 * w) / w.sum()
    return [round(float(np.interp(q / 100, cum, v)), 1) for q in qs]


def build(df: pd.DataFrame) -> dict:
    df = df[df.age >= 18].assign(pulse=valid_mean(df, "pulse", 25, 250), systolic=valid_mean(df, "sys", 50, 300),
                                 diastolic=valid_mean(df, "dia", 25, 200))
    bands = {}
    for metric in ("pulse", "systolic", "diastolic"):
        for sex, code in (("female", 1.0), ("male", 0.0)):
            for lo, hi in AGE_BANDS:
                g = df[(df.female == code) & df.age.between(lo, hi) & df[metric].notna() & df.weight.gt(0)]
                key = f"{lo}+" if lo == hi else f"{lo}-{hi}"
                if len(g) >= MIN_N:
                    bands.setdefault(metric, {}).setdefault(sex, {})[key] = {
                        "n": int(len(g)), **dict(zip((f"p{q:g}" for q in PERCENTILES),
                                                     weighted_percentiles(g[metric], g.weight)))}
    return {
        "source": f"real:nhanes ({SOURCES['nhanes']['name']})", "credit": SOURCES["nhanes"]["credit"],
        "terms": SOURCES["nhanes"]["licence"],
        "population": "US civilian non-institutionalised adults (18+), survey-weighted with WTMECPRP",
        "measurement": "seated, 5-minute rest, Omron HEM-907XL oscillometric, mean of >= 2 valid of 3 readings",
        "use": "pulse bands: patient's seated cuff pulse only; BP bands: office-type context only",
        "limits": "Not Algerian data; NHANES BP is exam BP, not home BP; percentiles describe a population, "
                  "they are not clinical thresholds. Reviewed as context only (medical mentor, 30 Oct 2026).",
        "percentiles": list(PERCENTILES), "bands": bands,
    }


def main() -> None:
    ref = build(load_nhanes())
    OUT.write_text(json.dumps(ref, indent=2) + "\n", encoding="utf-8")
    pulse = ref["bands"]["pulse"]
    print(json.dumps({"written": OUT.name, "pulse_median_by_group": {s: {a: v["p50"] for a, v in g.items()}
                                                                     for s, g in pulse.items()}}, indent=2))


if __name__ == "__main__":
    main()
