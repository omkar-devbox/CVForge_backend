from typing import Optional
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


class TenantMiddleware(BaseHTTPMiddleware):
    """Middleware to extract multi-tenancy header X-Tenant-ID into request state."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        tenant_id: Optional[str] = request.headers.get("X-Tenant-ID")
        request.state.tenant_id = tenant_id
        response = await call_next(request)
        return response
