import structlog

from app.core.config import settings


def get_logger(name: str):
    if not settings.DEBUG:
        structlog.configure(
            processors=[
                # Inject request-scoped context (request_id, method, path) bound
                # in RequestLoggingMiddleware into every log line of the request —
                # so service-layer logs can be traced back to the HTTP request.
                structlog.contextvars.merge_contextvars,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.JSONRenderer(),
            ],
        )
    return structlog.get_logger(name)
