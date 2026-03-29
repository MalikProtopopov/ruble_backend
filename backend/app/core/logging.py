import structlog

from app.core.config import settings


def get_logger(name: str):
    if not settings.DEBUG:
        structlog.configure(
            processors=[
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.JSONRenderer(),
            ],
        )
    return structlog.get_logger(name)
