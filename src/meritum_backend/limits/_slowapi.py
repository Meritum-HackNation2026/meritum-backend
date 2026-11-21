"""Per-client rate limits (slowapi), answered with HTTP 429 and a plain message."""

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from meritum_backend.constants import MINUTE_SECONDS
from meritum_backend.limits.constants import (
    DAY_SECONDS,
    RATE_LIMITED_DAILY_KEY,
    RATE_LIMITED_KEY,
)

# The client address comes from uvicorn --proxy-headers (X-Forwarded-For set by
# meritum-gateway from Cloudflare's CF-Connecting-IP).
# shortcut: in-memory counters, per process; move to Redis (storage_uri) when the
# API runs more than one process or replica.
limiter = Limiter(key_func=get_remote_address)


def too_many_requests(_request: Request, exc: Exception) -> JSONResponse:
    """Answer an exceeded limit, with the wait of the limit that was hit.

    Args:
        _request: the limited request (unused; the handler signature needs it).
        exc: the limit error; its window sets Retry-After.

    Returns:
        429 with a copy/pl.json key (errors.rate_limited_daily for a daily
        limit, errors.rate_limited otherwise) and a message for people, not a
        stack of limit details.

    Features:
        US-BEZ-02
    """
    hit = exc.limit if isinstance(exc, RateLimitExceeded) else None
    window = hit.limit.get_expiry() if hit is not None else MINUTE_SECONDS
    when = "za minutę" if window <= MINUTE_SECONDS else "później"
    key = RATE_LIMITED_DAILY_KEY if window >= DAY_SECONDS else RATE_LIMITED_KEY
    body = {"message_key": key, "detail": f"Za dużo zapytań. Spróbuj ponownie {when}."}
    return JSONResponse(body, status_code=429, headers={"Retry-After": str(window)})


__all__ = ["RateLimitExceeded", "limiter", "too_many_requests"]
