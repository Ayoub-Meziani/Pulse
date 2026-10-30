"""Supabase Auth integration: access-token verification and the current user.

Tokens are verified locally against the project's JWKS (the cloud project signs with ES256,
VERIFIED 2026-10-30): signature, algorithm allow-list (no HS256, no "none"), `exp`,
`aud=authenticated` and `iss=<SUPABASE_URL>/auth/v1`. The role always comes from
public.profiles, never from the token or the client.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from uuid import UUID

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db, set_request_claims
from .errors import ApiError
from .models import AuthUser, Profile

ALLOWED_ALGORITHMS = ("ES256", "RS256")

bearer = HTTPBearer(auto_error=False, description="Supabase Auth access token from POST /auth/login.")


def _invalid() -> ApiError:
    return ApiError(401, "invalid_token", "Session is invalid or expired. Log in again.")


def _unavailable() -> ApiError:
    return ApiError(503, "auth_unavailable", "Authentication service is unavailable. Try again shortly.")


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    role: str
    full_name: str
    email: str
    timezone: str

    def as_dict(self) -> dict:
        return asdict(self)


class TokenVerifier:
    def __init__(self, supabase_url: str | None, jwks: dict | None = None):
        self.issuer = f"{supabase_url.rstrip('/')}/auth/v1" if supabase_url else None
        self._static = {k.key_id: k for k in jwt.PyJWKSet.from_dict(jwks).keys} if jwks else None
        self._client = (jwt.PyJWKClient(f"{self.issuer}/.well-known/jwks.json", cache_keys=True,
                                        lifespan=600, timeout=10)
                        if self.issuer and jwks is None else None)

    def _key(self, token: str, kid: str | None):
        if self._static is not None:
            jwk = self._static.get(kid)
            if jwk is None:
                raise _invalid()
            return jwk.key
        try:
            return self._client.get_signing_key_from_jwt(token).key
        except jwt.PyJWKClientConnectionError:
            raise _unavailable() from None
        except jwt.PyJWKClientError:
            raise _invalid() from None

    def verify(self, token: str) -> dict:
        if self.issuer is None:
            raise _unavailable()
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError:
            raise _invalid() from None
        alg = header.get("alg")
        if alg not in ALLOWED_ALGORITHMS:
            raise _invalid()
        key = self._key(token, header.get("kid"))
        try:
            return jwt.decode(token, key, algorithms=[alg], audience="authenticated", issuer=self.issuer,
                              leeway=30, options={"require": ["exp", "sub", "aud", "iss"]})
        except jwt.PyJWTError:
            raise _invalid() from None


def load_user(db: Session, user_id: UUID) -> CurrentUser | None:
    row = db.execute(select(Profile, AuthUser.email).join(AuthUser, AuthUser.id == Profile.id)
                     .where(Profile.id == user_id)).first()
    if row is None:
        return None
    profile, email = row
    return CurrentUser(id=profile.id, role=profile.role, full_name=profile.display_name,
                       email=email or "", timezone=profile.timezone)


def user_from_token(request: Request, db: Session, token: str) -> CurrentUser:
    claims = request.app.state.verifier.verify(token)
    try:
        user_id = UUID(claims["sub"])
    except (ValueError, TypeError):
        raise _invalid() from None
    user = load_user(db, user_id)
    if user is None:
        raise ApiError(401, "invalid_token", "This account has no PULSE profile.")
    return user


def current_user(request: Request, creds: HTTPAuthorizationCredentials | None = Depends(bearer),
                 db: Session | None = Depends(get_db)) -> CurrentUser:
    if creds is None or creds.scheme.lower() != "bearer" or not creds.credentials:
        raise ApiError(401, "not_authenticated", "Log in first.")
    if db is None:
        raise ApiError(503, "database_unavailable", "Database is not configured.")
    user = user_from_token(request, db, creds.credentials)
    set_request_claims(db, user.id, user.role)
    return user
