"""FastAPI application factory. Run from api/: uvicorn app.main:create_app --factory --reload"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from fastapi import FastAPI

from .config import Settings, load_settings
from .db import Base, make_session_factory, utcnow
from .errors import install_error_handlers
from .routers import alerts, auth, patients

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None, clock: Callable[[], datetime] = utcnow) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(title="PULSE API", version="0.1.0",
                  description="Hypertension monitoring prototype. Not a medical device.",
                  openapi_url=f"{API_PREFIX}/openapi.json", docs_url=f"{API_PREFIX}/docs")
    app.state.settings = settings
    app.state.clock = clock
    app.state.session_factory = make_session_factory(settings.database_url)
    Base.metadata.create_all(app.state.session_factory.kw["bind"])
    install_error_handlers(app)

    @app.get(f"{API_PREFIX}/health", tags=["meta"])
    def health():
        return {"status": "ok"}

    for r in (auth.router, patients.router, alerts.router):
        app.include_router(r, prefix=API_PREFIX)
    return app

