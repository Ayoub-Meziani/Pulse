"""Read the ML batch job's output (docs/engineering/PULSE_ML_REVIEW.md §4). Doctor view only.

The API never runs a model and imports no ML library: it reads rows of public.ml_predictions written
offline by `pulse_ml.predict`. Predictions are never inputs to the rules, alerts or any patient response.
"""
from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import MlPrediction
from ..schemas import Interval, PredictionOut

UNAVAILABLE = dict(target_date=None, predicted_systolic=None, predicted_diastolic=None, interval=None,
                   model_version=None, trained_on=None, generated_at=None)


def _float(v) -> float | None:
    return float(v) if v is not None else None


def latest_prediction(db: Session, patient_id: UUID, model_version: str, today: date) -> PredictionOut:
    row = db.scalar(select(MlPrediction)
                    .where(MlPrediction.patient_id == patient_id, MlPrediction.model_version == model_version)
                    .order_by(MlPrediction.target_date.desc(), MlPrediction.created_at.desc()).limit(1))
    if row is None or row.target_date < today:  # never run, or stale: never show an old estimate as current
        return PredictionOut(status="model_unavailable", **UNAVAILABLE)
    bounds = (row.interval_systolic_low, row.interval_systolic_high,
              row.interval_diastolic_low, row.interval_diastolic_high)
    ok = row.status == "ok"
    interval = (Interval(systolic=(float(bounds[0]), float(bounds[1])), diastolic=(float(bounds[2]), float(bounds[3])))
                if ok and all(b is not None for b in bounds) else None)
    return PredictionOut(status=row.status, target_date=row.target_date,
                         predicted_systolic=_float(row.predicted_systolic) if ok else None,
                         predicted_diastolic=_float(row.predicted_diastolic) if ok else None,
                         interval=interval, model_version=row.model_version, trained_on=row.trained_on,
                         generated_at=row.created_at)
