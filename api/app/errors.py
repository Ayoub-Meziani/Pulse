"""Uniform error format: {"error": {"code", "message", "details"}}."""
from __future__ import annotations

from typing import NoReturn

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .schemas import ErrorOut


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details=None):
        self.status, self.code, self.message, self.details = status, code, message, details


def not_implemented() -> NoReturn:
    """Contract stage: the route and its response schema are final, the handler is not built yet."""
    raise ApiError(501, "not_implemented", "This endpoint is part of contract v1 but is not implemented yet.")


def _response(description: str) -> dict:
    return {"model": ErrorOut, "description": description}


# Documented on every protected route so the frontend sees the error shape in OpenAPI.
AUTH_RESPONSES = {401: _response("Missing or invalid token"), 403: _response("Not allowed for this user"),
                  404: _response("Not found"), 409: _response("Conflict"),
                  422: _response("Invalid request"), 501: _response("Not implemented yet"),
                  503: _response("Authentication service or database unavailable")}


def _body(code: str, message: str, details=None) -> dict:
    return {"error": {"code": code, "message": message, "details": details}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status, content=_body(exc.code, exc.message, exc.details))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        details = [{"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"]}
                   for e in exc.errors()]
        return JSONResponse(status_code=422, content=_body("invalid_request", "Request is invalid.", details))

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        return JSONResponse(status_code=exc.status_code,
                            content=_body(f"http_{exc.status_code}", str(exc.detail)))

    @app.exception_handler(DBAPIError)
    async def _database(_: Request, exc: DBAPIError):
        status, code, message, details = database_error(exc)
        return JSONResponse(status_code=status, content=_body(code, message, details))


# SQLSTATE -> API error. Never include the SQL statement or its parameters (they hold health values).
_SQLSTATE = {
    "23514": (422, "validation_failed", "A value was rejected by the database."),
    "23503": (422, "invalid_reference", "A referenced record does not exist or belongs to another patient."),
    "23505": (409, "conflict", "This record already exists."),
    "22001": (422, "validation_failed", "A value is too long."),
    "22003": (422, "validation_failed", "A number is out of range."),
    "22P02": (422, "validation_failed", "A value has the wrong format."),
    "42501": (403, "forbidden", "Not allowed."),
}


def database_error(exc: DBAPIError) -> tuple[int, str, str, dict | None]:
    if isinstance(exc, OperationalError):
        return 503, "database_unavailable", "Database is unavailable. Try again shortly.", None
    orig = exc.orig
    sqlstate = getattr(orig, "sqlstate", None)
    status, code, message = _SQLSTATE.get(sqlstate, (500, "internal_error", "Unexpected database error."))
    constraint = getattr(getattr(orig, "diag", None), "constraint_name", None)
    return status, code, message, {"sqlstate": sqlstate, "constraint": constraint}
