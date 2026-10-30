"""Minimal client for Supabase Auth (GoTrue) token grants, used by /auth/login and /auth/refresh.

The frontend never talks to Supabase: FastAPI proxies these two grants with the publishable
(anon) key. Passwords and tokens are never logged.
"""
from __future__ import annotations

import httpx


class InvalidGrant(Exception):
    """Wrong email/password or an expired/revoked refresh token."""


class AuthUnavailable(Exception):
    """Supabase Auth could not be reached or answered with a server error."""


class GoTrue:
    def __init__(self, supabase_url: str, anon_key: str, timeout: float = 10.0,
                 transport: httpx.BaseTransport | None = None):
        self._client = httpx.Client(base_url=f"{supabase_url.rstrip('/')}/auth/v1",
                                    headers={"apikey": anon_key}, timeout=timeout, transport=transport)

    def _token(self, grant: str, body: dict) -> dict:
        try:
            r = self._client.post("/token", params={"grant_type": grant}, json=body)
        except httpx.HTTPError as exc:
            raise AuthUnavailable(type(exc).__name__) from None
        if r.status_code in (400, 401, 403, 422):
            raise InvalidGrant()
        if r.status_code != 200:
            raise AuthUnavailable(f"status {r.status_code}")
        return r.json()

    def password(self, email: str, password: str) -> dict:
        return self._token("password", {"email": email, "password": password})

    def refresh(self, refresh_token: str) -> dict:
        return self._token("refresh_token", {"refresh_token": refresh_token})
