"""Bearer-token dependency.

Contract stage: every protected route declares the bearer scheme (so OpenAPI shows it) and rejects
requests without a token. Token verification against Supabase Auth (JWKS, ES256 on the cloud
project) and profile loading arrive with the database integration (implementation plan Phase 2).
"""
from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .errors import ApiError

bearer = HTTPBearer(auto_error=False, description="Supabase Auth access token from POST /auth/login.")


def require_token(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
    if creds is None or creds.scheme.lower() != "bearer" or not creds.credentials:
        raise ApiError(401, "not_authenticated", "Log in first.")
    return creds.credentials
