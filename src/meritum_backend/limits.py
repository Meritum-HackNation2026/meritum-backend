"""Per-client rate limits (slowapi), answered with HTTP 429 and a plain message."""

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# The client address comes from uvicorn --proxy-headers (X-Forwarded-For set by
# meritum-gateway from Cloudflare's CF-Connecting-IP).
# shortcut: in-memory counters, per process; move to Redis (storage_uri) when the
# API runs more than one process or replica.
limiter = Limiter(key_func=get_remote_address)


def too_many_requests(_request: Request, _exc: Exception) -> JSONResponse:
    """Answer an exceeded limit.

    Args:
        _request: the limited request (unused; the handler signature needs it).
        _exc: the limit error.

    Returns:
        429 with a message for people, not a stack of limit details.

    Features:
        US-BEZ-02
    """
    body = {"detail": "Za dużo zapytań. Spróbuj ponownie za minutę."}
    return JSONResponse(body, status_code=429, headers={"Retry-After": "60"})


__all__ = ["RateLimitExceeded", "limiter", "too_many_requests"]
