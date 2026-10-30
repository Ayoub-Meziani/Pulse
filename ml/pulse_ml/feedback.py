"""Doctor feedback -> labels for the ring monitor, with the safeguards of review M5.

    cd ml && ..\\.venv\\Scripts\\python -m pulse_ml.feedback [--out ../data/feedback/ring_labels.csv]
    cd ml && ..\\.venv\\Scripts\\python -m pulse_ml.feedback --gate artifacts/<candidate>/metadata.json

Rules:
- Labels come from doctor-reviewed flags (confirmed / dismissed) and doctor-edited bands.
- They are used ONLY to retune personal_anomaly thresholds, never the reference / safety thresholds.
- Doctors only see flagged windows, so labels cannot measure missed episodes: the injected-episode recall
  of the current model is a regression gate that a retrained model must not fall below.
- Nothing is deployed automatically: a retrained version is only a candidate until a person promotes it.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from . import ring
from .predict import connect
from .train import ARTIFACTS, ROOT

MIN_LABELS = 30          # reviewed personal_anomaly flags needed before any threshold change
GATE_METHOD = "personal_baseline"


def export(conn, out: Path) -> dict:
    rows = conn.execute("""
        select patient_id::text, metric, kind, window_kind, window_start, review_status, model_version
        from public.wearable_flags where review_status in ('confirmed', 'dismissed') order by window_start""").fetchall()
    edited = conn.execute("select count(*) from public.patient_bands where basis = 'doctor'").fetchone()[0]
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["patient_id", "metric", "kind", "window_kind", "window_start", "review_status", "model_version"])
        w.writerows(rows)
    usable = sum(1 for r in rows if r[2] == "personal_anomaly")
    return {"reviewed_flags": len(rows), "usable_personal_anomaly_labels": usable, "doctor_edited_bands": edited,
            "enough_to_retune": usable >= MIN_LABELS, "min_labels": MIN_LABELS}


def gate(candidate: dict, current: dict) -> tuple[bool, str]:
    """A candidate passes only if its injected-episode recall is not below the current model's."""
    new = candidate["test_metrics"][GATE_METHOD]["episode_recall"]
    old = current["test_metrics"][GATE_METHOD]["episode_recall"]
    return new >= old, f"{GATE_METHOD} episode recall: candidate {new} vs current {old}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "feedback" / "ring_labels.csv")
    ap.add_argument("--gate", type=Path, help="candidate metadata.json to check against the current ring model")
    a = ap.parse_args()
    if a.gate:
        current = json.loads((ARTIFACTS / ring.MODEL_VERSION / "metadata.json").read_text(encoding="utf-8"))
        ok, why = gate(json.loads(a.gate.read_text(encoding="utf-8")), current)
        print(json.dumps({"gate_passed": ok, "detail": why, "deploy": "manual only"}))
        raise SystemExit(0 if ok else 1)
    with connect() as conn:
        print(json.dumps(export(conn, a.out)))


if __name__ == "__main__":
    main()
