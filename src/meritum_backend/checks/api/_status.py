"""Checks API: POST /api/v1/checks starts a check, GET /api/v1/checks/{id} polls it.

Every channel (web form, extension, Discord, SMS, MCP) calls this one API, so the
result does not depend on the channel (ADR-08).

Features:
    US-SPR-01, US-SPR-07, US-BEZ-02, US-BEZ-04, US-BEZ-07, US-WDR-03, F-01, F-20,
    F-21, F-23, ADR-08
"""

import asyncio
import contextlib
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Annotated, Any, cast, override

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from meritum_core.checks import (
    SESSIONLESS_CHANNELS,
    AnalysisStatus,
    CheckRequest,
    CheckResult,
)
from meritum_core.jobs.constants import PROGRESS_KEY
from meritum_core.jobs.contracts import CHECK, CheckInput
from meritum_core.jobs.ports import JobQueue, JobState
from pydantic import BaseModel, ValidationError
from pydantic_core import ErrorDetails

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
    SESSIONLESS_DETAIL,
)
from meritum_backend.checks.intake import is_unsupported_link, masked, message_key
from meritum_backend.checks.progress import (
    check_result,
    is_check,
    without_early_verdict,
)
from meritum_backend.jobs.api import Jobs
from meritum_backend.limits import CheckRefusedError, ClientOrigin, Gate, TooManyChecks


class InvalidCheck(BaseModel):
    """422 answer: what the person must fix, as a key of copy/pl.json.

    Attributes:
        message_key: errors.empty, errors.too_long or errors.invalid_url.

    Features:
        US-SPR-01, US-SPR-07, F-01
    """

    message_key: str


class CheckAccepted(BaseModel):
    """202 answer: the check was queued.

    Attributes:
        check_id: the id to poll at GET /api/v1/checks/{check_id}.

    Features:
        US-SPR-01, F-01
    """

    check_id: str


def _invalid(key: str) -> JSONResponse:
    body = InvalidCheck(message_key=key).model_dump()
    return JSONResponse(body, status_code=status.HTTP_422_UNPROCESSABLE_CONTENT)


class KeyedErrorsRoute(APIRoute):
    """Route that answers a bad body with a copy key, never echoing the input.

    FastAPI's default 422 repeats the sent text, which may hold personal data.

    Features:
        US-SPR-01, US-BEZ-04, F-01, F-20
    """

    @override
    # Any: the exact signature of APIRoute.get_route_handler (Starlette types).
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        """Wrap the default handler.

        Returns:
            The handler that maps validation errors to InvalidCheck.
        """
        handler = super().get_route_handler()

        async def keyed(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError as exc:
                return _invalid(message_key(cast("list[ErrorDetails]", exc.errors())))

        return keyed


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
    },
)
async def start_check(
    request: CheckRequest,
    jobs: Jobs,
    gate: Gate,
    origin: ClientOrigin,
    session: Annotated[str | None, Header(alias=SESSION_HEADER)] = None,
) -> CheckAccepted | JSONResponse:
    """Mask personal data, then enqueue the `check` workflow.

    Args:
        request: text (up to 4000 characters), a full http(s) link or an audio id.
        jobs: the job queue port.
        gate: the shared rate limits and the pending-checks threshold.
        origin: the client address and region the limits count.
        session: the random browser session id; no sign-in needed.

    Returns:
        The check id, or 422 with a copy key.

    Raises:
        HTTPException: 400 without a valid session or for Discord, SMS and MCP
            (they come through their adapters with a hashed user id, backend#27),
            503 when the job queue is unreachable.
        CheckRefusedError: over a rate limit or with too many pending checks;
            answered 429 with Retry-After, nothing enqueued.

    Features:
        US-SPR-01, US-SPR-07, US-BEZ-02, US-BEZ-04, US-WDR-03, F-01, F-20, F-23
    """
    received_at = datetime.now(UTC)
    if is_unsupported_link(request):
        return _invalid(INVALID_URL_KEY)
    if request.channel in SESSIONLESS_CHANNELS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, SESSIONLESS_DETAIL)
    if session is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, NO_SESSION_DETAIL)
    try:
        clean = masked(request)
    except ValidationError as exc:
        return _invalid(message_key(exc.errors()))
    try:
        payload = CheckInput(request=clean, session_id=session, received_at=received_at)
    except ValidationError:  # the only field left to fail is session_id
        raise HTTPException(status.HTTP_400_BAD_REQUEST, BAD_SESSION_DETAIL) from None
    if (refusal := await gate.refusal(origin, request.channel)) is not None:
        raise CheckRefusedError(refusal)
    try:
        check_id = await jobs.enqueue(CHECK, payload)
    except Exception as exc:  # DBOS wraps driver errors in its own types
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "job queue unavailable"
        ) from exc
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
async def check_status(jobs: Jobs, check_id: str, response: Response) -> AnalysisStatus:
    """Read a check's steps and, once it finished, its result.

    Args:
        jobs: the job queue port.
        check_id: the id POST /api/v1/checks returned.
        response: the response; gets the AI-Disclosure header with a result.

    Returns:
        The steps; ``result`` once the check finished (``ai_disclosure`` is true).

    Raises:
        HTTPException: 404 when the id is unknown.

    Features:
        US-SPR-01, US-BEZ-07, F-01, F-21
    """
    state = await jobs.state(check_id)
    if state is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_DETAIL)
    latest = await _latest_progress(jobs, check_id)
    steps = latest.steps if latest else [RECEIVED]
    result = (latest.result if latest else None) or _output_result(state)
    if result is not None:
        response.headers[AI_DISCLOSURE_HEADER] = AI_DISCLOSURE_VALUE
    return AnalysisStatus(check_id=check_id, steps=steps, result=result)
