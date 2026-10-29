"""Settings from environment variables. Never commit real secrets (.env is gitignored)."""
from __future__ import annotations

import os
from dataclasses import dataclass

DEV_SECRET = "dev-only-insecure-secret-change-me-0000000"


@dataclass(frozen=True)
class Settings:
    env: str
    database_url: str
    jwt_secret: str
    jwt_minutes: int


def load_settings() -> Settings:
    env = os.getenv("PULSE_ENV", "dev")
    secret = os.getenv("PULSE_JWT_SECRET", DEV_SECRET)
    if env != "dev" and secret == DEV_SECRET:
        raise RuntimeError("Set PULSE_JWT_SECRET when PULSE_ENV is not 'dev'.")
    return Settings(
        env=env,
        database_url=os.getenv("PULSE_DATABASE_URL", "sqlite:///./pulse.db"),
        jwt_secret=secret,
        jwt_minutes=int(os.getenv("PULSE_JWT_MINUTES", "720")),
    )
