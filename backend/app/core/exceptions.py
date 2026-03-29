from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


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
