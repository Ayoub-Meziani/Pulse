"""Database engine and per-request sessions.

The API connects with one privileged role (it bypasses RLS) and enforces access in
permissions.py. Each request sets `request.jwt.claims` for its transaction so database
triggers that call auth.uid() (audit actor, measurements.created_by) record the real user.
The schema belongs to supabase/migrations; the API never creates or alters tables.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from uuid import UUID

from fastapi import Request
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    if url.startswith("postgresql://"):  # Supabase-style URL -> psycopg 3 driver
        url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return create_engine(url, pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def set_request_claims(db: Session, user_id: UUID, role: str) -> None:
    """Transaction-local claims so auth.uid() inside triggers returns this user.

    Both the current (`request.jwt.claims`) and the legacy (`request.jwt.claim.sub`) settings are
    set, so it works with either version of Supabase's auth.uid()."""
    claims = json.dumps({"sub": str(user_id), "role": "authenticated", "app_role": role})
    db.execute(text("select set_config('request.jwt.claims', :claims, true), "
                    "set_config('request.jwt.claim.sub', :sub, true)"), {"claims": claims, "sub": str(user_id)})


def get_db(request: Request) -> Iterator[Session | None]:
    """Yields None when no database is configured (contract-only runs); callers decide the error."""
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        yield None
        return
    db = factory()
    try:
        yield db
    finally:
        db.close()
