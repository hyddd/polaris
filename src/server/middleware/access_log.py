"""Access log middleware — unified format via polaris logger."""

import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("polaris.access")


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = (time.monotonic() - start) * 1000
        logger.info(
            f"{request.client.host} {request.method} {request.url.path} "
            f"{response.status_code} {duration_ms:.0f}ms"
        )
        return response
