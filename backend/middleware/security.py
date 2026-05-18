"""
BTF – Middlewares de Sécurité
En-têtes de sécurité, Rate Limiting, Protection IP.
"""

import time
import logging
from collections import defaultdict
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("btf.security")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Ajoute les en-têtes de sécurité HTTP à chaque réponse."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"]    = "nosniff"
        response.headers["X-Frame-Options"]            = "DENY"
        response.headers["X-XSS-Protection"]           = "1; mode=block"
        response.headers["Referrer-Policy"]             = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"]          = "camera=(), microphone=(), geolocation=()"
        response.headers["Strict-Transport-Security"]   = "max-age=31536000; includeSubDomains; preload"
        response.headers["Content-Security-Policy"]     = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "connect-src 'self' wss://btf.bf; "
            "img-src 'self' data: https:;"
        )
        # Supprimer les en-têtes qui révèlent la stack
        response.headers.pop("server", None)
        response.headers.pop("x-powered-by", None)
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate Limiting par IP.
    Limite configurable : max_requests par window_seconds.
    """

    def __init__(self, app, max_requests: int = 200, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        ip = request.client.host
        now = time.time()
        window_start = now - self.window_seconds

        # Nettoyer les anciennes entrées
        self._requests[ip] = [t for t in self._requests[ip] if t > window_start]

        if len(self._requests[ip]) >= self.max_requests:
            logger.warning(f"Rate limit atteint: IP={ip}")
            return JSONResponse(
                status_code=429,
                content={"detail": "Trop de requêtes. Veuillez patienter."},
                headers={"Retry-After": str(self.window_seconds)},
            )

        self._requests[ip].append(now)
        return await call_next(request)


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Journalise toutes les requêtes sensibles."""

    SENSITIVE_PATHS = {"/api/v1/auth", "/admin-secret-gate", "/api/v1/trading", "/api/v1/payments"}

    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration = round((time.time() - start) * 1000, 2)

        path = request.url.path
        if any(path.startswith(p) for p in self.SENSITIVE_PATHS):
            logger.info(
                f"{request.method} {path} | "
                f"IP={request.client.host} | "
                f"Status={response.status_code} | "
                f"{duration}ms"
            )

        return response
