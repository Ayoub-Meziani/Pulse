"""Devices and wearable samples of one patient, read only.

Wearables are an optional, additional source. Nothing here is imported by the rules, the alert service,
the symptom check or the emergency path, and no sample is ever turned into a blood-pressure reading.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Device, WearableSample
from ..schemas import DeviceOut, WearableSampleOut

SIMULATOR = "simulator"


def list_devices(db: Session, patient_id: UUID) -> list[DeviceOut]:
    rows = db.scalars(select(Device).where(Device.patient_id == patient_id).order_by(Device.created_at, Device.id))
    return [DeviceOut(id=d.id, device_type=d.device_type, bp_capability=d.bp_capability,
                      is_simulated=d.device_type == SIMULATOR, manufacturer=d.manufacturer, model=d.model,
                      label=d.label, created_at=d.created_at) for d in rows]


def list_samples(db: Session, patient_id: UUID, metric: str | None, device_id: UUID | None,
                 start: datetime | None, end: datetime | None, limit: int) -> list[WearableSampleOut]:
    q = select(WearableSample).where(WearableSample.patient_id == patient_id)
    if metric:
        q = q.where(WearableSample.metric == metric)
    if device_id:
        q = q.where(WearableSample.device_id == device_id)
    if start:
        q = q.where(WearableSample.measured_at >= start)
    if end:
        q = q.where(WearableSample.measured_at <= end)
    q = q.order_by(WearableSample.measured_at.desc(), WearableSample.id).limit(limit)
    return [WearableSampleOut(id=s.id, device_id=s.device_id, metric=s.metric, value=float(s.value), unit=s.unit,
                              measured_at=s.measured_at, source=s.source) for s in db.scalars(q)]
