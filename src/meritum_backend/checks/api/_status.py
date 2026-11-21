"""Checks API: POST /api/v1/checks starts a check, GET /api/v1/checks/{id} polls it.

Every channel (web form, extension, Discord, SMS, MCP) calls this one API, so the
result does not depend on the channel (ADR-08).

Features:
    US-SPR-01, US-SPR-07, US-BEZ-02, US-BEZ-03, US-BEZ-04, US-BEZ-07, US-WDR-03,
    US-WDR-08, F-01, F-20, F-21, F-23, F-30, ADR-08
"""

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from fastapi.responses import JSONResponse
from meritum_core.checks import (
    AnalysisStatus,
    CheckRequest,
    CheckResult,
)
from meritum_core.jobs.constants import PROGRESS_KEY
from meritum_core.jobs.contracts import CHECK, CheckInput
from meritum_core.jobs.ports import JobQueue, JobState
from pydantic import BaseModel, ValidationError

from meritum_backend.checks.api._cache import (
    Cache,
    Records,
    fill,
    link_miss,
    serve_from_cache,
    served,
)
from meritum_backend.checks.api._identity import identity
from meritum_backend.checks.api._keyed import InvalidCheck, KeyedErrorsRoute, invalid
from meritum_backend.checks.api._pii import PiiGate
from meritum_backend.checks.constants import (
    AI_DISCLOSURE_HEADER,
    AI_DISCLOSURE_VALUE,
    BAD_SESSION_DETAIL,
    INVALID_URL_KEY,
    NO_SESSION_DETAIL,
    NOT_FOUND_DETAIL,
    PROGRESS_WAIT_SECONDS,
    RECEIVED,
    SESSION_HEADER,
)
from meritum_backend.checks.intake import is_unsupported_link, masked, message_key
from meritum_backend.checks.progress import (
    check_result,
    is_check,
    without_early_verdict,
)
from meritum_backend.health.api import Ready, not_ready_response
from meritum_backend.health.models import NotReady
from meritum_backend.jobs.api import Jobs
from meritum_backend.limits import CheckRefusedError, ClientOrigin, Gate, TooManyChecks
from meritum_backend.settings import Settings, get_settings


class CheckAccepted(BaseModel):
    """202 answer: the check was queued.

    Attributes:
        check_id: the id to poll at GET /api/v1/checks/{check_id}.

    Features:
        US-SPR-01, F-01
    """

    check_id: str


router = APIRouter(
    prefix="/api/v1/checks", tags=["checks"], route_class=KeyedErrorsRoute
)


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CheckAccepted,
    responses={
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": InvalidCheck},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": TooManyChecks},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": NotReady},
    },
)
async def start_check(  # ruff: ignore[too-many-arguments, too-many-positional-arguments] (FastAPI injects each dependency as a parameter)
    request: CheckRequest,
    jobs: Jobs,
    gate: Gate,
    origin: ClientOrigin,
    pii: PiiGate,
    readiness: Ready,
    cache: Cache,
    records: Records,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[str | None, Header(alias=SESSION_HEADER)] = None,
) -> CheckAccepted | JSONResponse:
    """Mask personal data, then enqueue the `check` workflow.

    Args:
        request: text (up to 4000 characters), a full http(s) link or an audio id.
        jobs: the job queue port.
        gate: the shared rate limits and the pending-checks threshold.
        origin: the client address and region the limits count.
        pii: the personal-data masking gate.
        readiness: the readiness probe; a service that is not ready refuses checks.
        cache: the result cache; a hit starts no `check` workflow.
        records: where a hit's CheckRecord goes.
        settings: the app settings (the channel user hash salt).
        session: the random browser session id; no sign-in needed.

    Returns:
        The check id, 422 with a copy key, or 503 NotReady.

    Raises:
        HTTPException: 400 without a valid session, or for Discord, SMS and MCP
            without ``channel_user_id``; 503 when the job queue is unreachable or
            the hash salt is not configured.
        CheckRefusedError: over a rate limit or with too many pending checks;
            answered 429 with Retry-After, nothing enqueued.

    Features:
        US-SPR-01, US-SPR-07, US-BEZ-02, US-BEZ-03, US-BEZ-04, US-BEZ-06, US-WTY-08,
        US-WDR-03, US-WDR-08, US-WTY-03, US-MOD-03, F-01, F-05, F-20, F-23, F-30
    """
    received_at = datetime.now(UTC)
    if is_unsupported_link(request):
        return invalid(INVALID_URL_KEY)
    request, session, hashed = identity(request, session, settings.channel_hash_salt)
    if session is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, NO_SESSION_DETAIL)
    try:
        clean = await masked(request, pii)
    except ValidationError as exc:
        return invalid(message_key(exc.errors()))
    try:
        payload = CheckInput(
            request=clean,
            session_id=session,
            channel_user_hash=hashed,
            received_at=received_at,
        )
    except ValidationError:  # the only field left to fail is session_id
        raise HTTPException(status.HTTP_400_BAD_REQUEST, BAD_SESSION_DETAIL) from None
    if not await readiness.ready():
        return not_ready_response()
    if (refusal := await gate.refusal(origin, request.channel)) is not None:
        raise CheckRefusedError(refusal)
    try:
        hit = await serve_from_cache(jobs, cache, records, payload)
        check_id = hit or await jobs.enqueue(CHECK, payload)
    except Exception as exc:  # DBOS wraps driver errors in its own types
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "job queue unavailable"
        ) from exc
    if hit is None:
        await link_miss(cache, check_id, payload)
    return CheckAccepted(check_id=check_id)


async def _latest_progress(jobs: JobQueue, check_id: str) -> AnalysisStatus | None:
    latest = None
    # a running workflow's stream stays open, so a poll reads it briefly;
    # live steps go through GET /api/v1/checks/{id}/events.
    with contextlib.suppress(TimeoutError):
        async with asyncio.timeout(PROGRESS_WAIT_SECONDS):
            async for value in jobs.stream(check_id, PROGRESS_KEY, AnalysisStatus):
                latest = without_early_verdict(value)
    return latest


def _output_result(state: JobState) -> CheckResult | None:
    if not is_check(state):  # another workflow, e.g. a ping
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_DETAIL)
    return check_result(state)


@router.get(
    "/{check_id}",
    responses={
        status.HTTP_200_OK: {
            "headers": {
                AI_DISCLOSURE_HEADER: {
                    "description": "Set with a result: machine-readable marker of"
                    " AI-generated content (AI Act art. 50(2)).",
                    "schema": {"type": "string", "example": AI_DISCLOSURE_VALUE},
                }
            }
        }
    },
)
async def check_status(
    jobs: Jobs, cache: Cache, check_id: str, response: Response
) -> AnalysisStatus:
    """Read a check's steps and, once it finished, its result.

    Args:
        jobs: the job queue port.
        cache: the result cache; filled with a finished result, read for a hit.
        check_id: the id POST /api/v1/checks returned.
        response: the response; gets the AI-Disclosure header with a result.

    Returns:
        The steps; ``result`` once the check finished (``ai_disclosure`` is true).

    Raises:
        HTTPException: 404 when the id is unknown.

    Features:
        US-SPR-01, US-BEZ-07, US-WTY-03, F-01, F-05, F-21
    """
    state = await jobs.state(check_id)
    if state is None:
        result = await served(jobs, cache, check_id)
        if result is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_DETAIL)
        steps = [RECEIVED]
    else:
        latest = await _latest_progress(jobs, check_id)
        steps = latest.steps if latest else [RECEIVED]
        result = (latest.result if latest else None) or _output_result(state)
        if result is not None:
            await fill(cache, result, datetime.now(UTC))
    if result is not None:
        response.headers[AI_DISCLOSURE_HEADER] = AI_DISCLOSURE_VALUE
    return AnalysisStatus(check_id=check_id, steps=steps, result=result)
