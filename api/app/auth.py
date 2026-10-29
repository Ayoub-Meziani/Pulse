"""Password hashing (stdlib PBKDF2), JWT tokens, and the current-user dependency."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import timedelta

import jwt
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from .db import utcnow
from .errors import ApiError
from .models import User

_ITER = 200_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITER)
    return f"pbkdf2_sha256${_ITER}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt_b64, digest_b64 = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), int(iters))
        return hmac.compare_digest(digest, base64.b64decode(digest_b64))
    except (ValueError, TypeError):
        return False


def create_token(user: User, secret: str, minutes: int) -> str:
    now = utcnow()
    payload = {"sub": str(user.id), "role": user.role, "iat": now, "exp": now + timedelta(minutes=minutes)}
    return jwt.encode(payload, secret, algorithm="HS256")


def get_db(request: Request):
    db = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        raise ApiError(401, "not_authenticated", "Missing bearer token.")
    try:
        payload = jwt.decode(header[7:], request.app.state.settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise ApiError(401, "invalid_token", "Token is invalid or expired.")
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise ApiError(401, "invalid_token", "User no longer exists.")
    return user
