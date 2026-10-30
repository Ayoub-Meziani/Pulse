"""Supabase Auth integration against the test database: login/refresh proxy, token verification, /me."""
import secrets
import time
import uuid

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth import TokenVerifier
from app.config import Settings
from app.db import set_request_claims
from app.errors import ApiError
from app.gotrue import GoTrue
from app.main import create_app
from conftest import SUPABASE_URL, TEST_JWKS, mint, new_user

pytestmark = pytest.mark.db
API = "/api/v1"
PASSWORD = "correct horse battery staple"


class FakeGoTrue:
    """Answers like Supabase Auth's /token endpoint; tokens are signed with the test key."""

    def __init__(self):
        self.users: dict[str, uuid.UUID] = {}
        self.refresh_tokens: dict[str, uuid.UUID] = {}
        self.down = False
        self.last_apikey = None

    def _session(self, uid):
        rt = secrets.token_urlsafe(16)
        self.refresh_tokens[rt] = uid
        return {"access_token": mint(uid), "refresh_token": rt, "token_type": "bearer",
                "expires_in": 3600, "expires_at": int(time.time()) + 3600, "user": {"id": str(uid)}}

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("down", request=request)
        self.last_apikey = request.headers.get("apikey")
        body, grant = request.read(), request.url.params["grant_type"]
        import json
        data = json.loads(body)
        if grant == "password":
            uid = self.users.get(data["email"])
            if uid is None or data["password"] != PASSWORD:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json=self._session(uid))
        uid = self.refresh_tokens.pop(data.get("refresh_token"), None)
        if uid is None:
            return httpx.Response(400, json={"error": "invalid_grant"})
        return httpx.Response(200, json=self._session(uid))


@pytest.fixture
def gotrue():
    return FakeGoTrue()


@pytest.fixture
def client(session_factory, gotrue):
    app = create_app(Settings(supabase_url=SUPABASE_URL, supabase_anon_key="anon-test-key", jwks=TEST_JWKS,
                              demo_number="+213 555 12 34 56"))
    app.state.session_factory = session_factory
    app.state.gotrue = GoTrue(SUPABASE_URL, "anon-test-key", transport=httpx.MockTransport(gotrue.handler))
    return TestClient(app)


@pytest.fixture
def patient(conn, gotrue):
    uid = new_user(conn, "patient", "Karim B.")
    email = conn.execute(text("select email from auth.users where id = :id"), {"id": uid}).scalar_one()
    gotrue.users[email] = uid
    return uid, email


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------- login / refresh
def test_login_returns_session_and_profile(client, patient, gotrue):
    uid, email = patient
    r = client.post(f"{API}/auth/login", json={"email": f"  {email.upper()} ", "password": PASSWORD})
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["user"] == {"id": str(uid), "role": "patient", "full_name": "Karim B.", "email": email,
                         "timezone": "Africa/Algiers"}
    assert s["token_type"] == "bearer" and s["refresh_token"]
    assert gotrue.last_apikey == "anon-test-key"  # publishable key stays server-side
    assert client.get(f"{API}/me", headers=bearer(s["access_token"])).json()["id"] == str(uid)


def test_wrong_password_is_invalid_credentials(client, patient):
    r = client.post(f"{API}/auth/login", json={"email": patient[1], "password": "nope"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_credentials"


def test_unknown_email_gives_the_same_answer(client):
    r = client.post(f"{API}/auth/login", json={"email": "nobody@pulse.test", "password": PASSWORD})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_credentials"


def test_auth_service_down_is_503(client, patient, gotrue):
    gotrue.down = True
    r = client.post(f"{API}/auth/login", json={"email": patient[1], "password": PASSWORD})
    assert r.status_code == 503 and r.json()["error"]["code"] == "auth_unavailable"


def test_refresh_rotates_and_rejects_reuse(client, patient):
    s = client.post(f"{API}/auth/login", json={"email": patient[1], "password": PASSWORD}).json()
    r = client.post(f"{API}/auth/refresh", json={"refresh_token": s["refresh_token"]})
    assert r.status_code == 200 and r.json()["refresh_token"] != s["refresh_token"]
    again = client.post(f"{API}/auth/refresh", json={"refresh_token": s["refresh_token"]})
    assert again.status_code == 401 and again.json()["error"]["code"] == "invalid_token"


def test_login_for_account_without_profile_is_rejected(client, conn, gotrue):
    uid = new_user(conn)
    conn.execute(text("delete from public.profiles where id = :id"), {"id": uid})  # inside the test transaction
    gotrue.users["orphan@pulse.test"] = uid
    r = client.post(f"{API}/auth/login", json={"email": "orphan@pulse.test", "password": PASSWORD})
    assert r.status_code == 401


# ---------------------------------------------------------------- /me and token verification
def test_me_returns_role_from_database_not_token(client, conn):
    doctor = new_user(conn, "doctor", "Dr. Amina S.")
    r = client.get(f"{API}/me", headers=bearer(mint(doctor)))
    assert r.status_code == 200 and r.json()["role"] == "doctor" and r.json()["full_name"] == "Dr. Amina S."


OTHER_KEY = ec.generate_private_key(ec.SECP256R1())


@pytest.mark.parametrize("make_token", [
    lambda uid: "not-a-jwt",
    lambda uid: mint(uid, minutes=-5),                               # expired (beyond 30 s leeway)
    lambda uid: mint(uid, aud="anon"),                               # wrong audience
    lambda uid: mint(uid, iss="https://evil.example/auth/v1"),       # wrong issuer
    lambda uid: mint(uid, kid="unknown-kid"),                        # unknown key id
    lambda uid: mint(uid, key=OTHER_KEY),                            # signed by another key
    lambda uid: mint(uid, key="x" * 32, alg="HS256"),                # algorithm confusion
    lambda uid: jwt.encode({"sub": str(uid), "aud": "authenticated"}, None, algorithm="none"),
    lambda uid: mint("not-a-uuid"),                                  # malformed subject
    lambda uid: mint(uuid.uuid4()),                                  # valid token, no profile
], ids=["garbage", "expired", "audience", "issuer", "kid", "other-key", "hs256", "alg-none", "bad-sub", "no-profile"])
def test_bad_tokens_are_rejected(client, conn, make_token):
    uid = new_user(conn)
    r = client.get(f"{API}/me", headers=bearer(make_token(uid)))
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_token"


def test_missing_token_is_not_authenticated(client):
    r = client.get(f"{API}/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "not_authenticated"


def test_unreachable_jwks_is_503_not_401():
    verifier = TokenVerifier("http://127.0.0.1:9")  # nothing listens on port 9
    with pytest.raises(ApiError) as exc:
        verifier.verify(mint(uuid.uuid4(), iss="http://127.0.0.1:9/auth/v1"))
    assert exc.value.status == 503


def test_request_claims_make_auth_uid_the_caller(conn, db):
    uid = new_user(conn)
    set_request_claims(db, uid, "patient")
    assert db.execute(text("select auth.uid()")).scalar_one() == uid


def test_triggers_record_the_caller_as_created_by(conn, db):
    from app import models, vocab
    uid = new_user(conn)
    set_request_claims(db, uid, "patient")
    m = models.Measurement(patient_id=uid, source=vocab.MANUAL_SOURCE, provenance=vocab.MANUAL_PROVENANCE,
                           method=vocab.MANUAL_METHOD, systolic=130, diastolic=85,
                           measured_at=db.execute(text("select now()")).scalar_one())
    db.add(m)
    db.flush()
    assert m.created_by == uid  # set by private.validate_measurement() from auth.uid()
