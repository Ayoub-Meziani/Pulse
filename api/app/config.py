"""Settings from environment variables. Never commit real secrets (.env is gitignored)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

# Decision D3 is open: neither number is confirmed for the main emergency button. Both stay
# verified=False until a medical mentor confirms them. Never dial them in tests or the demo.
DEFAULT_EMERGENCY_NUMBERS = (
    {"id": "dz-14", "label_fr": "Protection civile", "label_ar": "الحماية المدنية", "number": "14",
     "verified": False, "source": "Widely listed for Protection civile; UK FCDO lists 14 as fire. Unconfirmed (D3)."},
    {"id": "dz-1021", "label_fr": "Protection civile (ambulance)", "label_ar": "الحماية المدنية (إسعاف)",
     "number": "1021", "verified": False,
     "source": "UK FCDO lists 1021 as ambulance; Wikipedia lists it as Civil Defence. Unconfirmed (D3)."},
)
DEMO_NUMBER_ID = "demo"


@dataclass(frozen=True)
class Settings:
    env: str = "dev"
    database_url: str | None = None
    supabase_url: str | None = None          # e.g. https://<ref>.supabase.co ; tokens must have iss <url>/auth/v1
    supabase_anon_key: str | None = None     # publishable key, used server-side only for the login proxy
    jwks: dict | None = None                 # tests only: static JWKS instead of fetching <url>/auth/v1/.well-known/jwks.json
    # Demo mode replaces the emergency number with a teammate's phone and shows a DEMO banner.
    demo_mode: bool = True
    demo_number: str | None = None
    emergency_numbers: tuple[dict, ...] = field(default=DEFAULT_EMERGENCY_NUMBERS)
    primary_number_id: str = "dz-14"
    # Only ml_predictions rows of this model version are served (approved: mbp-v1, PULSE_ML_REVIEW.md).
    ml_model_version: str = "mbp-v1"


def _bool(value: str | None, default: bool) -> bool:
    return default if value is None else value.strip().lower() in ("1", "true", "yes", "on")


def load_settings() -> Settings:
    env = os.getenv("PULSE_ENV", "dev")
    numbers = os.getenv("PULSE_EMERGENCY_NUMBERS")
    if numbers:
        try:
            parsed = json.loads(numbers)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"PULSE_EMERGENCY_NUMBERS is not valid JSON: {exc}") from exc
        if not isinstance(parsed, list) or not all(isinstance(n, dict) for n in parsed):
            raise RuntimeError("PULSE_EMERGENCY_NUMBERS must be a JSON list of objects.")
    settings = Settings(
        env=env,
        database_url=os.getenv("PULSE_DATABASE_URL"),
        supabase_url=os.getenv("SUPABASE_URL"),
        supabase_anon_key=os.getenv("SUPABASE_ANON_KEY"),
        demo_mode=_bool(os.getenv("PULSE_DEMO_MODE"), True),
        demo_number=os.getenv("PULSE_DEMO_NUMBER"),
        emergency_numbers=tuple(parsed) if numbers else DEFAULT_EMERGENCY_NUMBERS,
        primary_number_id=os.getenv("PULSE_PRIMARY_NUMBER_ID", "dz-14"),
        ml_model_version=os.getenv("PULSE_ML_MODEL_VERSION", "mbp-v1"),
    )
    if env != "dev" and settings.demo_mode and not settings.demo_number:
        raise RuntimeError("Set PULSE_DEMO_NUMBER (a teammate's phone) when PULSE_DEMO_MODE is on.")
    return settings
