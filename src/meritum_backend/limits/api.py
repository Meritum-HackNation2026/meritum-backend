"""FastAPI dependencies of the check limits: the app's gate and the client origin.

Features:
    US-BEZ-02, US-WDR-03, F-20, F-23
"""

import asyncio
import logging
from typing import Annotated, cast

from fastapi import Depends, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from meritum_backend.limits.constants import (
    PRUNE_EVERY_SECONDS,
    REGION_CODE,
    REGION_HEADER,
    RETRY_AFTER_HEADER,
    UNKNOWN_IP,
    UNKNOWN_REGION,
)
from meritum_backend.limits.errors import CheckRefusedError
from meritum_backend.limits.gate import CheckGate
from meritum_backend.limits.models import Origin, Refusal

_log = logging.getLogger(__name__)


class TooManyChecks(BaseModel):
    """429 answer: a message for people, never a verdict.

    Attributes:
        message_key: errors.rate_limited or errors.busy (copy/pl.json).

    Features:
        US-BEZ-02, US-WDR-03, F-20, F-23
    """

    message_key: str


def _too_many(refusal: Refusal) -> JSONResponse:
    body = TooManyChecks(message_key=refusal.message_key).model_dump()
    headers = {RETRY_AFTER_HEADER: str(refusal.retry_after_seconds)}
    return JSONResponse(body, status.HTTP_429_TOO_MANY_REQUESTS, headers)


def get_check_gate(request: Request) -> CheckGate:
    """The gate the app built at startup (overridden in tests).

    Args:
        request: the current request (holds the app state).

    Returns:
        The app's CheckGate.

    Features:
        US-BEZ-02, US-WDR-03, F-20, F-23
    """
    # the app state is untyped; create_app stores a CheckGate there
    return cast("CheckGate", request.app.state.check_gate)


def origin_of(request: Request) -> Origin:
    """Read the client address and its Cloudflare country.

    Args:
        request: the current request; uvicorn --proxy-headers sets the client.

    Returns:
        The origin; a missing or malformed country is ``XX``.

    Features:
        US-BEZ-02, F-20
    """
    ip = request.client.host if request.client else UNKNOWN_IP
    region = request.headers.get(REGION_HEADER, "").upper()
    if not REGION_CODE.fullmatch(region):
        region = UNKNOWN_REGION
    return Origin(ip=ip, region=region)


Gate = Annotated[CheckGate, Depends(get_check_gate)]
"""The app's check gate as a route parameter."""

ClientOrigin = Annotated[Origin, Depends(origin_of)]
"""The request's origin as a route parameter."""


async def admit_stream(gate: Gate, origin: ClientOrigin) -> None:
    """Count a progress stream before it opens (route dependency).

    Args:
        gate: the app's check gate.
        origin: the client address and region.

    Raises:
        CheckRefusedError: the address opened too many streams this minute.

    Features:
        US-BEZ-02, F-20
    """
    if (refusal := await gate.stream_refusal(origin)) is not None:
        raise CheckRefusedError(refusal)


def check_refused(_request: Request, exc: Exception) -> JSONResponse:
    """Answer a CheckRefusedError (exception handler).

    Args:
        _request: the refused request (unused; the handler signature needs it).
        exc: the CheckRefusedError.

    Returns:
        429 with the copy key and Retry-After.

    Features:
        US-BEZ-02, F-20
    """
    # registered for CheckRefusedError only (main.py)
    return _too_many(cast("CheckRefusedError", exc).refusal)


async def _prune_forever(gate: CheckGate, every_seconds: float) -> None:
    while True:
        try:
            await gate.forget_finished()
        except Exception:  # ruff: ignore[blind-except] -- one failed pass must not end the clean-up for good
            _log.warning("counter clean-up failed; retrying", exc_info=True)
        await asyncio.sleep(every_seconds)


def start_pruning(
    gate: CheckGate, every_seconds: float = PRUNE_EVERY_SECONDS
) -> asyncio.Task[None]:
    """Drop finished windows in the background for as long as the API runs.

    Args:
        gate: the app's check gate.
        every_seconds: pause between two clean-ups.

    Returns:
        The task; the lifespan cancels it on shutdown.

    Features:
        US-BEZ-02, F-20
    """
    return asyncio.create_task(_prune_forever(gate, every_seconds))
