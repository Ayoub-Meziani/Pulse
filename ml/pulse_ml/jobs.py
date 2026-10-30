"""The three batch jobs on ONE connection: predict --all, monitor --nights, weekly.

    cd ml && ..\\.venv\\Scripts\\python -m pulse_ml.jobs

Used by scripts/run_cloud_jobs.ps1: through the Supabase pooler, the CLI's temporary login reliably accepts only
the first connection after it is issued, so the jobs share that connection. Prints counts only.
"""
from __future__ import annotations

import json

import pandas as pd

from . import monitor, predict, weekly


def main() -> None:
    with predict.connect(autocommit=True) as conn:
        rows = predict.run(conn, predict.load_bundle(predict.MODEL_VERSION))
        print(json.dumps({"job": "predict", "model_version": predict.MODEL_VERSION, "patients": len(rows),
                          "by_status": pd.Series([r["status"] for r in rows], dtype=str).value_counts().to_dict()}))
        print(json.dumps({"job": "monitor --nights",
                          "flags_written": monitor.run_nights(conn, monitor.load_forest(), 35)}), flush=True)
        print(json.dumps({"job": "weekly", **weekly.run(conn, None)}))


if __name__ == "__main__":
    main()
