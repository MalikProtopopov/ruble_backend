import traceback

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

logger = get_logger(__name__)


class AppError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400, details: dict | None = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found", details: dict | None = None):
        super().__init__(code="NOT_FOUND", message=message, status_code=404, details=details)


class ConflictError(AppError):
    def __init__(self, message: str = "Conflict", details: dict | None = None):
        super().__init__(code="CONFLICT", message=message, status_code=409, details=details)


class ForbiddenError(AppError):
    def __init__(self, message: str = "Forbidden", details: dict | None = None):
        super().__init__(code="FORBIDDEN", message=message, status_code=403, details=details)


class BusinessLogicError(AppError):
    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(code=code, message=message, status_code=422, details=details)


def register_exception_handlers(app: FastAPI):
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        # Log the cause of every business/expected error so failures are
        # debuggable from the logs (request_id is bound by the middleware).
        logger.warning(
            "request_error",
            code=exc.code,
            message=exc.message,
            status_code=exc.status_code,
            details=exc.details,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        # 422 from request-body/query validation. Log the exact fields that
        # failed so client/contract mismatches are visible (e.g. wrong amount).
        errors = exc.errors()
        logger.warning(
            "request_validation_error",
            errors=[
                {"loc": list(e.get("loc", [])), "msg": e.get("msg"), "type": e.get("type")}
                for e in errors
            ],
        )
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder({"detail": errors}),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # Anything not converted to an AppError — log the full traceback so the
        # root cause is in the logs, and return a clean 500 to the client.
        logger.error(
            "unhandled_exception",
            error=str(exc),
            error_type=type(exc).__name__,
            traceback=traceback.format_exc(),
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Внутренняя ошибка сервера",
                    "details": {},
                }
            },
        )
