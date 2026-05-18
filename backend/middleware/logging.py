"""BTF – Middleware de journalisation des requêtes."""
import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("btf.requests")


class AuditLogMiddleware(BaseHTTPMiddleware):
    SENSITIVE = {"/api/v1/auth", "/admin-secret-gate", "/api/v1/trading", "/api/v1/payments"}

    async def dispatch(self, request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        ms = round((time.perf_counter() - start) * 1000, 1)
        path = request.url.path
        if any(path.startswith(s) for s in self.SENSITIVE):
            logger.info(f"{request.method} {path} | {response.status_code} | {ms}ms | IP={request.client.host}")
        return response
