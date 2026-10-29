"""Demo seed: 1 doctor, 3 assigned patients, 1 unassigned patient, 30 days of readings.

ALL DATA IS FICTIONAL AND SYNTHETIC (source="simulated"). Readings go through the
same ingestion service as real ones, so every seeded alert is produced by the rules.

Usage (from api/):  python -m app.seed --reset
"""
from __future__ import annotations

import argparse
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .auth import hash_password
from .config import load_settings
from .db import Base, make_session_factory, utcnow
from .models import DoctorPatientAssignment, User
from .schemas import MeasurementIn
from .services.measurements import ingest_measurement

DEMO_PASSWORD = "demo1234"  # demo accounts only; documented in README

DOCTOR = ("doctor", "Dr. Amina S.", "amina@pulse.demo")
PATIENTS = [
    ("karim@pulse.demo", "Karim B.", "rising"),      # demo patient: drifts from ~135/85 to ~152/95
    ("nadia@pulse.demo", "Nadia M.", "stable"),      # stable near 128/80
    ("youssef@pulse.demo", "Youssef T.", "spike"),   # stable, one severe reading 3 days ago
]
UNASSIGNED = ("samir@pulse.demo", "Samir K.", "stable")  # for permission tests / demos


def _scenario_readings(kind: str, now: datetime, rng: random.Random):
    """Two readings a day (08:00 and 20:00 UTC) for 30 days, deterministic."""
    out = []
    for day in range(30, 0, -1):
        for hour in (8, 20):
            t = (now - timedelta(days=day)).replace(hour=hour, minute=0, second=0, microsecond=0)
            progress = (30 - day) / 30
            if kind == "rising":
                s, d = 135 + 17 * progress, 85 + 10 * progress
            else:
                s, d = 128, 80
            s, d = round(s + rng.gauss(0, 4)), round(d + rng.gauss(0, 3))
            out.append((t, s, d, round(72 + rng.gauss(0, 5))))
    if kind == "spike":
        t = (now - timedelta(days=3)).replace(hour=14, minute=10, second=0, microsecond=0)
        out.append((t, 186, 112, 95))
    return sorted(out)


def _user(db: Session, role: str, name: str, email: str) -> User:
    u = User(role=role, full_name=name, email=email, password_hash=hash_password(DEMO_PASSWORD))
    db.add(u)
    db.flush()
    return u


def seed(db: Session, now: datetime | None = None) -> dict:
    now = now or utcnow()
    rng = random.Random(42)
    doctor = _user(db, *DOCTOR)
    created = {"doctor": doctor.id, "patients": {}}
    for email, name, kind in PATIENTS + [UNASSIGNED]:
        p = _user(db, "patient", name, email)
        if (email, name, kind) != UNASSIGNED:
            db.add(DoctorPatientAssignment(doctor_id=doctor.id, patient_id=p.id))
        db.commit()
        created["patients"][email] = p.id
        for i, (t, s, d, pulse) in enumerate(_scenario_readings(kind, now, rng)):
            data = MeasurementIn(systolic=s, diastolic=d, pulse=pulse, measured_at=t, source="simulated",
                                 source_ref=f"seed:{kind}", external_id=f"seed-{email}-{i}")
            ingest_measurement(db, p, data, actor=p, now=t + timedelta(minutes=1))
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="Drop and recreate all tables first.")
    args = parser.parse_args()
    settings = load_settings()
    factory = make_session_factory(settings.database_url)
    engine = factory.kw["bind"]
    if args.reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with factory() as db:
        if db.query(User).count() and not args.reset:
            raise SystemExit("Database already has users. Use --reset to rebuild the demo data.")
        created = seed(db, datetime.now(timezone.utc))
    print(f"Seeded {settings.database_url}: doctor id {created['doctor']}, patients {created['patients']}")
    print(f"All demo accounts use the password '{DEMO_PASSWORD}'. Data is synthetic.")


if __name__ == "__main__":
    main()
