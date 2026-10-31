"""FastAPI application factory. Run from api/: uvicorn app.main:create_app --factory --reload

Supabase integration in progress (PULSE_DB_INTEGRATION_PLAN.md §7): auth, /me and permissions
are live; other routes keep their final schema and return 501 until implemented.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import FastAPI

from .auth import TokenVerifier
from .config import Settings, load_settings
from .db import make_engine, make_session_factory
from .errors import install_error_handlers
from .gotrue import GoTrue
from .routers import alerts, auth, emergency, escalation, followup, patients, profile, wearables

API_PREFIX = "/api/v1"
API_VERSION = "1.0.0-contract"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_app(settings: Settings | None = None, clock: Callable[[], datetime] = utcnow) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(title="PULSE API", version=API_VERSION,
                  description="Hypertension monitoring prototype. Not a medical device.",
                  openapi_url=f"{API_PREFIX}/openapi.json", docs_url=f"{API_PREFIX}/docs")
    app.state.settings = settings
    app.state.clock = clock
    app.state.emergency_config = emergency.build_config(settings)  # fails fast on a broken configuration
    # The engine connects lazily; without PULSE_DATABASE_URL protected routes answer 503.
    app.state.session_factory = (make_session_factory(make_engine(settings.database_url))
                                 if settings.database_url else None)
    app.state.verifier = TokenVerifier(settings.supabase_url, settings.jwks)
    app.state.gotrue = (GoTrue(settings.supabase_url, settings.supabase_anon_key)
                        if settings.supabase_url and settings.supabase_anon_key else None)
    install_error_handlers(app)

    @app.get(f"{API_PREFIX}/health", tags=["meta"])
    def health():
        return {"status": "ok"}

    for r in (auth.router, patients.router, profile.router, alerts.router, emergency.public,
              emergency.router, escalation.router, followup.router, wearables.router):
        app.include_router(r, prefix=API_PREFIX)
    return app
