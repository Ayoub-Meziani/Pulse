"""Shared fixtures.

Database tests need the throwaway Postgres (from the repo root: `python scripts/test_db.py up`) and
PULSE_TEST_DATABASE_URL; without it they are skipped. Each test runs inside a transaction that is
rolled back, so tests never see each other's data. Never point this at a shared database.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.db import make_engine

DB_URL = os.getenv("PULSE_TEST_DATABASE_URL")
SUPABASE_URL = "http://supabase.test"
ISSUER = f"{SUPABASE_URL}/auth/v1"
KID = "test-es256"

_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())
TEST_JWKS = {"keys": [{**jwt.algorithms.ECAlgorithm.to_jwk(_PRIVATE_KEY.public_key(), as_dict=True),
                       "kid": KID, "alg": "ES256", "use": "sig"}]}


def mint(sub, *, minutes: int = 60, aud: str = "authenticated", iss: str = ISSUER, kid: str = KID,
         key=None, alg: str = "ES256") -> str:
    """A Supabase-shaped access token signed with the test key."""
    now = datetime.now(timezone.utc)
    claims = {"sub": str(sub), "aud": aud, "iss": iss, "role": "authenticated",
              "iat": now, "exp": now + timedelta(minutes=minutes)}
    return jwt.encode(claims, key or _PRIVATE_KEY, algorithm=alg, headers={"kid": kid})


@pytest.fixture(scope="session")
def engine():
    if not DB_URL:
        if os.getenv("PULSE_REQUIRE_DB"):  # CI: a missing database must fail, not silently skip
            pytest.fail("PULSE_REQUIRE_DB is set but PULSE_TEST_DATABASE_URL is not")
        pytest.skip("PULSE_TEST_DATABASE_URL not set (run: python scripts/test_db.py up)")
    e = make_engine(DB_URL)
    yield e
    e.dispose()


@pytest.fixture
def conn(engine):
    c = engine.connect()
    outer = c.begin()
    yield c
    outer.rollback()
    c.close()


@pytest.fixture
def session_factory(conn):
    """Sessions that join the test transaction (their commits become savepoints)."""
    return sessionmaker(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)


@pytest.fixture
def db(session_factory) -> Session:
    s = session_factory()
    yield s
    s.close()


def new_user(conn, role: str = "patient", name: str = "Test User") -> uuid.UUID:
    """Insert an auth.users row; the on_auth_user_created trigger creates the profile (role patient)."""
    uid = uuid.uuid4()
    conn.execute(text("insert into auth.users (id, email) values (:id, :email)"),
                 {"id": uid, "email": f"{uid.hex[:12]}@pulse.test"})
    conn.execute(text("update public.profiles set role = :role, display_name = :name where id = :id"),
                 {"role": role, "name": name, "id": uid})
    return uid


def assign(conn, doctor: uuid.UUID, patient: uuid.UUID, status: str = "active") -> None:
    conn.execute(text("insert into public.doctor_patient_assignments (doctor_id, patient_id, status, ended_at) "
                      "values (:d, :p, :s, case when :s = 'ended' then now() end)"),
                 {"d": doctor, "p": patient, "s": status})
