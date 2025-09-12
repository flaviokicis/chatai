"""Application logging configuration and middleware.

This module sets up a structured logging configuration using
``logging.config.dictConfig`` and exposes a FastAPI middleware that injects
request IDs into all log records. Log output uses key-value formatting to
facilitate downstream parsing.
"""

from __future__ import annotations

import logging
import logging.config
import os
import uuid
from contextvars import ContextVar
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware  # type: ignore[import-not-found]

# ---------------------------------------------------------------------------
# Context variable used to propagate per-request IDs to log records
# ---------------------------------------------------------------------------
request_id_ctx_var: ContextVar[str | None] = ContextVar("request_id", default=None)


class RequestIdFilter(logging.Filter):
    """Inject the request ID from contextvars into log records."""

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - small
        record.request_id = request_id_ctx_var.get() or "-"
        return True


def _build_config(log_level: str) -> dict[str, Any]:
    """Build logging configuration dictionary."""

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {"request_id": {"()": RequestIdFilter}},
        "formatters": {
            "kv": {
                "format": (
                    "level=%(levelname)s logger=%(name)s request_id=%(request_id)s "
                    "message=%(message)s"
                )
            }
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",  # Explicitly use stdout instead of stderr
                "formatter": "kv",
                "filters": ["request_id"],
                "level": log_level,
            }
        },
        "root": {"handlers": ["default"], "level": log_level},
    }


def setup_logging() -> None:
    """Configure root logging using key-value formatting.

    The log level can be controlled via the ``LOG_LEVEL`` environment variable.
    """

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.config.dictConfig(_build_config(log_level))


# ---------------------------------------------------------------------------
# FastAPI middleware for request ID injection
# ---------------------------------------------------------------------------
class RequestIdMiddleware(BaseHTTPMiddleware):
    """Populate a unique request ID for each incoming HTTP request.

    The middleware uses the ``X-Request-ID`` header if provided, otherwise a
    new UUID4 value is generated. The request ID is stored in a ContextVar so it
    can be included in every log record via ``RequestIdFilter``. The ID is also
    echoed back to clients in the ``X-Request-ID`` response header.
    """

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        token = request_id_ctx_var.set(request_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            request_id_ctx_var.reset(token)


__all__ = ["RequestIdMiddleware", "request_id_ctx_var", "setup_logging"]

