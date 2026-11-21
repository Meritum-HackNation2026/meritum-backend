"""Check progress as Server-Sent Events: GET /api/v1/checks/{id}/events.

The `check` workflow writes AnalysisStatus values to its progress stream; this
router forwards them as they come, so the client needs no polling. The stream is
read through JobQueue from the start on every connection: a client that
reconnects gets the steps so far, and a disconnect only stops the reading, never
the workflow.

Features:
    US-SPR-02, F-09
"""

from collections.abc import AsyncIterable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.sse import EventSourceResponse
from meritum_core.checks import AnalysisStatus
from meritum_core.jobs.constants import PROGRESS_KEY

from meritum_backend.checks.api._cache import Cache, fill, served
from meritum_backend.checks.constants import NOT_FOUND_DETAIL, RECEIVED
from meritum_backend.checks.progress import (
    check_result,
    is_check,
    without_early_verdict,
)
from meritum_backend.jobs.api import Jobs
from meritum_backend.limits import TooManyChecks, admit_stream

router = APIRouter(prefix="/api/v1/checks", tags=["checks"])


async def _known_check(jobs: Jobs, cache: Cache, check_id: str) -> str:
    # checked before the stream opens: once it does, the status is already 200
    state = await jobs.state(check_id)
    if state is None and await cache.entry_of(check_id) is not None:
        return check_id  # served from the result cache: no workflow
    if state is None or not is_check(state):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_DETAIL)
    return check_id


@router.get(
    "/{check_id}/events",
    response_class=EventSourceResponse,
    dependencies=[Depends(admit_stream)],
    responses={status.HTTP_429_TOO_MANY_REQUESTS: {"model": TooManyChecks}},
)
async def check_events(
    jobs: Jobs, cache: Cache, check_id: Annotated[str, Depends(_known_check)]
) -> AsyncIterable[AnalysisStatus]:
    """Stream a check's progress until the workflow ends.

    A result reaches the client only once ``verify_citations`` is done or
    skipped, so a preliminary answer never carries a verdict. When the workflow
    finished, the last event holds the full CheckResult and the stream closes.
    The response has no AI-Disclosure header: headers go out before the first
    event, when no result is known yet; ``result.ai_disclosure`` marks it.

    Args:
        jobs: the job queue port.
        cache: the result cache; a hit has no workflow, only its result.
        check_id: the id POST /api/v1/checks returned; 404 when unknown.
            Opening a stream counts against the address's own stream budget
            (429 above it).

    Yields:
        One AnalysisStatus per progress value, then the final one with ``result``.

    Features:
        US-SPR-02, US-BEZ-02, US-WTY-03, F-05, F-09, F-20
    """
    last = AnalysisStatus(check_id=check_id, steps=[RECEIVED])
    state = await jobs.state(check_id)
    if state is None:
        yield last.model_copy(update={"result": await served(jobs, cache, check_id)})
        return
    async for progress in jobs.stream(check_id, PROGRESS_KEY, AnalysisStatus):
        last = without_early_verdict(progress)
        yield last
    state = await jobs.state(check_id)
    result = check_result(state) if state is not None else None
    if result is not None:
        await fill(cache, result, datetime.now(UTC))
    if result is not None and result != last.result:
        yield last.model_copy(update={"result": result})
