from typing import Any, Dict, Optional
from fastapi import Request, status
from fastapi.responses import JSONResponse


class AppException(Exception):
    """Base application exception."""

    def __init__(
        self,
        message: str = "An unexpected error occurred.",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Any] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(self.message)


class NotFoundException(AppException):
    """Resource not found exception."""

    def __init__(self, resource: str = "Resource", identifier: Any = None):
        message = f"{resource} not found"
        if identifier:
            message += f" with ID: {identifier}"
        super().__init__(
            message=message, status_code=status.HTTP_404_NOT_FOUND
        )


class ValidationException(AppException):
    """Validation or business logic failure exception."""

    def __init__(self, message: str = "Invalid request data", details: Any = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Global exception handler for AppException."""
    content: Dict[str, Any] = {
        "success": False,
        "error": {
            "message": exc.message,
            "code": exc.__class__.__name__,
        },
    }
    if exc.details:
        content["error"]["details"] = exc.details

    return JSONResponse(status_code=exc.status_code, content=content)
