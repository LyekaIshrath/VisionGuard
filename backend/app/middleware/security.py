from __future__ import annotations
import logging
import re
import uuid
from typing import Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

CSP_DIRECTIVES = "; ".join([
    "default-src 'self'",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "script-src 'self'",
    "img-src 'self' data: blob:",
    "connect-src 'self' ws://localhost:8000 ws://127.0.0.1:8000",
    "worker-src 'none'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response: Response = await call_next(request)
        if response.status_code == 101:
            return response
        response.headers["Content-Security-Policy"] = CSP_DIRECTIVES
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
        return response


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = req_id
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response


_BEARER_PATTERN = re.compile(
    r"(bearer\s+)\S+",
    re.IGNORECASE,
)
_AUTH_PATTERN = re.compile(
    r"(authorization\s*[:=]\s*(?:bearer\s+)?)\S+",
    re.IGNORECASE,
)
_PASSWORD_PATTERN = re.compile(
    r"(password[:\s=]+)\S+",
    re.IGNORECASE,
)


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        msg = _AUTH_PATTERN.sub(r"\1[REDACTED]", msg)
        msg = _BEARER_PATTERN.sub(r"\1[REDACTED]", msg)
        msg = _PASSWORD_PATTERN.sub(r"\1[REDACTED]", msg)
        return msg


def configure_structured_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO
    handler = logging.StreamHandler()
    handler.setFormatter(RedactingFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    ))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
