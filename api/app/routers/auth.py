from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..auth import CurrentUser, current_user, user_from_token
from ..db import get_db
from ..errors import AUTH_RESPONSES, ApiError
from ..gotrue import AuthUnavailable, InvalidGrant
from ..schemas import LoginIn, RefreshIn, SessionOut, UserOut

router = APIRouter(tags=["auth"], responses=AUTH_RESPONSES)


def _gotrue(request: Request):
    gotrue = request.app.state.gotrue
    if gotrue is None:
        raise ApiError(503, "auth_unavailable", "Authentication is not configured.")
    return gotrue


def _session(request: Request, db: Session | None, data: dict) -> SessionOut:
    if db is None:
        raise ApiError(503, "database_unavailable", "Database is not configured.")
    user = user_from_token(request, db, data["access_token"])  # never trust an unverified token
    if "expires_at" in data:
        expires_at = datetime.fromtimestamp(int(data["expires_at"]), timezone.utc)
    else:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(data.get("expires_in", 3600)))
    return SessionOut(access_token=data["access_token"], refresh_token=data["refresh_token"],
                      expires_at=expires_at, user=UserOut(**user.as_dict()))


@router.post("/auth/login", response_model=SessionOut,
             summary="Log in with email + password (proxied to Supabase Auth)")
def login(body: LoginIn, request: Request, db: Session | None = Depends(get_db)):
    try:
        data = _gotrue(request).password(body.email.strip().lower(), body.password)
    except InvalidGrant:
        raise ApiError(401, "invalid_credentials", "Email or password is incorrect.") from None
    except AuthUnavailable:
        raise ApiError(503, "auth_unavailable", "Authentication service is unavailable. Try again shortly.") from None
    return _session(request, db, data)


@router.post("/auth/refresh", response_model=SessionOut, summary="Exchange a refresh token for a new session")
def refresh(body: RefreshIn, request: Request, db: Session | None = Depends(get_db)):
    try:
        data = _gotrue(request).refresh(body.refresh_token)
    except InvalidGrant:
        raise ApiError(401, "invalid_token", "Session expired. Log in again.") from None
    except AuthUnavailable:
        raise ApiError(503, "auth_unavailable", "Authentication service is unavailable. Try again shortly.") from None
    return _session(request, db, data)


@router.get("/me", response_model=UserOut, summary="Current user and role")
def me(user: CurrentUser = Depends(current_user)):
    return UserOut(**user.as_dict())
