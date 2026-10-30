from fastapi import APIRouter, Depends

from ..auth import require_token
from ..errors import AUTH_RESPONSES, not_implemented
from ..schemas import LoginIn, RefreshIn, SessionOut, UserOut

router = APIRouter(tags=["auth"], responses=AUTH_RESPONSES)


@router.post("/auth/login", response_model=SessionOut,
             summary="Log in with email + password (proxied to Supabase Auth)")
def login(body: LoginIn):
    not_implemented()


@router.post("/auth/refresh", response_model=SessionOut, summary="Exchange a refresh token for a new session")
def refresh(body: RefreshIn):
    not_implemented()


@router.get("/me", response_model=UserOut, summary="Current user and role")
def me(token: str = Depends(require_token)):
    not_implemented()
