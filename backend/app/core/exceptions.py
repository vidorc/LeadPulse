"""Global exception handling.

Turns uncaught exceptions into a consistent JSON error envelope that never
leaks internals (stack traces, SQL, secrets) to clients, while logging the
full detail server-side with the request id for correlation. Also normalizes
FastAPI's validation and HTTP errors into the same envelope shape.

Envelope: ``{"error": {"type": ..., "message": ..., "request_id": ...}}``.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger, request_id_ctx

log = get_logger("error")


def _envelope(type_: str, message, status_code: int, headers=None) -> JSONResponse:
    body = {
        "error": {
            "type": type_,
            "message": message,
            "request_id": request_id_ctx.get(),
        }
    }
    return JSONResponse(status_code=status_code, content=body, headers=headers)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http_exc(request: Request, exc: StarletteHTTPException):
        # Expected, explicit errors (404, 401, 403, 429, ...). Don't log as error.
        return _envelope(
            type_="http_error",
            message=exc.detail,
            status_code=exc.status_code,
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exc(request: Request, exc: RequestValidationError):
        return _envelope(
            type_="validation_error",
            message=exc.errors(),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    @app.exception_handler(Exception)
    async def _unhandled_exc(request: Request, exc: Exception):
        # Unexpected — log the full detail server-side, return a generic message.
        log.error(
            "unhandled_exception",
            exc_info=exc,
            path=request.url.path,
            method=request.method,
        )
        return _envelope(
            type_="internal_error",
            message="An internal error occurred.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
