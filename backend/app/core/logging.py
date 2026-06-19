"""Structured logging configuration.

JSON logs in production (machine-parseable for log aggregation), pretty
console logs in development. A ``request_id`` contextvar is bound to every log
line emitted during a request so traces can be correlated end-to-end.

Call ``configure_logging()`` once at startup (app + worker). Use
``structlog.get_logger(__name__)`` everywhere else.
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar

import structlog

# Bound to each inbound request by RequestContextMiddleware; included in every
# log line via the merge_contextvars processor.
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


def _add_request_id(_logger, _method, event_dict):
    rid = request_id_ctx.get()
    if rid is not None:
        event_dict["request_id"] = rid
    return event_dict


def configure_logging(*, level: str = "INFO", json_logs: bool = True) -> None:
    """Configure structlog + stdlib logging for the whole process."""
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        _add_request_id,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    if json_logs:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[*shared_processors, structlog.processors.format_exc_info, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(level.upper())
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Route stdlib logging (uvicorn, sqlalchemy) through the same stream/level.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.getLevelName(level.upper()),
    )
    # Quiet noisy access logs; our middleware emits structured access events.
    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.access").propagate = False


def get_logger(name: str | None = None):
    return structlog.get_logger(name)
