"""The result cache on the check path: serve a hit, link a miss, fill a result.

Features:
    US-WTY-03, US-MOD-03, F-05, ADR-19, ADR-22
"""

import contextlib
from datetime import datetime
from typing import Annotated, cast
from uuid import uuid4

from fastapi import Depends, Request
from meritum_core.checks import CheckRecordRepository, CheckResult, Escalation
from meritum_core.jobs.contracts import (
    ESCALATE_CLAIM,
    CheckInput,
    EscalateClaimInput,
    EscalateClaimOutput,
)
from meritum_core.jobs.ports import JobQueue
from pydantic import ValidationError

from meritum_backend.checks.cache import (
    cache_entry,
    hit_record,
    input_key,
    served_result,
    unanswered,
)
from meritum_backend.checks.constants import CACHE_HIT_REASON
from meritum_backend.checks.ports import ResultCache


def get_result_cache(request: Request) -> ResultCache:
    """The result cache the app built (overridden in tests).

    Args:
        request: the current request (holds the app state).

    Returns:
        The app's ResultCache.

    Features:
        US-WTY-03, F-05
    """
    # the app state is untyped; create_app stores a ResultCache there
    return cast("ResultCache", request.app.state.result_cache)


def get_records(request: Request) -> CheckRecordRepository:
    """The check records repository core built for the app.

    Args:
        request: the current request (holds the app state).

    Returns:
        The app's CheckRecordRepository.

    Features:
        US-WTY-03, US-OBS-01
    """
    return cast("CheckRecordRepository", request.app.state.repositories.records)


Cache = Annotated[ResultCache, Depends(get_result_cache)]
"""The result cache as a FastAPI dependency."""

Records = Annotated[CheckRecordRepository, Depends(get_records)]
"""The check records repository as a FastAPI dependency."""


def _escalation_id(check_id: str, claim_index: int) -> str:
    return f"{check_id}-escalate-{claim_index}"


async def serve_from_cache(
    jobs: JobQueue,
    cache: ResultCache,
    records: CheckRecordRepository,
    payload: CheckInput,
) -> str | None:
    """Answer from the cache: record the hit and escalate unanswered claims.

    Args:
        jobs: the job queue; only ``escalate_claim`` runs, never ``check``.
        cache: the result cache.
        records: where the hit's CheckRecord goes (cache_hit true).
        payload: the masked request with its session.

    Returns:
        The new check's id on a hit; None on a miss.

    Features:
        US-WTY-03, US-MOD-03, F-05
    """
    key, session = input_key(payload.request), payload.session_id
    if key is None or session is None:
        return None
    entry = await cache.lookup(key, payload.received_at)
    if entry is None:
        return None
    check_id = uuid4().hex
    await cache.link(check_id, key)
    await records.save(hit_record(check_id, session, entry, payload))
    for index in unanswered(entry):
        job = EscalateClaimInput(
            check_id=check_id, claim_index=index, reason=CACHE_HIT_REASON
        )
        workflow_id = _escalation_id(check_id, index)
        await jobs.enqueue(ESCALATE_CLAIM, job, workflow_id=workflow_id)
    return check_id


async def link_miss(cache: ResultCache, check_id: str, payload: CheckInput) -> None:
    """Remember the key of a check that runs, so its result can fill the cache.

    Args:
        cache: the result cache.
        check_id: the started workflow.
        payload: its masked request.

    Features:
        US-WTY-03, F-05
    """
    if (key := input_key(payload.request)) is not None:
        await cache.link(check_id, key)


async def fill(cache: ResultCache, result: CheckResult, now: datetime) -> None:
    """Cache a finished check's substantive part; a technical failure never.

    Args:
        cache: the result cache.
        result: the result the worker produced.
        now: when it is stored.

    Features:
        US-WTY-03, F-05, ADR-22
    """
    if (entry := cache_entry(result, now)) is not None:
        await cache.fill(result.check_id, entry)


async def _escalation(jobs: JobQueue, check_id: str, index: int) -> Escalation | None:
    state = await jobs.state(_escalation_id(check_id, index))
    if state is None or state.output is None:
        return None
    with contextlib.suppress(ValidationError):
        return EscalateClaimOutput.model_validate(state.output).escalation
    return None


async def served(
    jobs: JobQueue, cache: ResultCache, check_id: str
) -> CheckResult | None:
    """Read the result of a check served from the cache.

    Args:
        jobs: the job queue with this check's own escalations.
        cache: the result cache.
        check_id: the id POST returned.

    Returns:
        The result with this check's escalation; None for an unknown id.

    Features:
        US-WTY-03, US-MOD-03, F-05
    """
    entry = await cache.entry_of(check_id)
    if entry is None:
        return None
    found = [await _escalation(jobs, check_id, i) for i in unanswered(entry)]
    escalation = next((e for e in found if e is not None), None)
    return served_result(check_id, entry, escalation)
