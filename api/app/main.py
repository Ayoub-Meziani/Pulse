"""FastAPI application factory. Run from api/: uvicorn app.main:create_app --factory --reload

Contract v1 stage: all routes and schemas are final; most handlers return 501 until the
Supabase database integration lands (PULSE_BACKEND_IMPLEMENTATION_PLAN.md).
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import FastAPI

from .config import Settings, load_settings
from .errors import install_error_handlers
from .routers import alerts, auth, emergency, followup, patients, profile

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
    install_error_handlers(app)

    @app.get(f"{API_PREFIX}/health", tags=["meta"])
    def health():
        return {"status": "ok"}

    for r in (auth.router, patients.router, profile.router, alerts.router, emergency.public,
              emergency.router, followup.router):
        app.include_router(r, prefix=API_PREFIX)
    return app
