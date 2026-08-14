from typing import Any, Generic, Optional, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class StandardResponse(BaseModel, Generic[T]):
    success: bool = True
    message: Optional[str] = None
    data: Optional[T] = None


def standard_response(
    data: Any = None,
    message: Optional[str] = None,
    success: bool = True,
) -> StandardResponse:
    """Helper to return standardized API responses."""
    return StandardResponse(success=success, message=message, data=data)
