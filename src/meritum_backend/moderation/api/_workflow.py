"""The workflows behind a hand-off: the finished check and `escalate_claim`.

Features:
    US-MOD-03, US-MOD-06, F-24, ADR-22
"""

import asyncio

from meritum_core.checks import Escalation
from meritum_core.jobs.contracts import (
    ESCALATE_CLAIM,
    CheckOutput,
    EscalateClaimInput,
    EscalateClaimOutput,
)
from meritum_core.jobs.ports import JobQueue, JobState
from pydantic import ValidationError

from meritum_backend.moderation.constants import (
    ESCALATION_WAIT_SECONDS,
    POLL_SECONDS,
    RUNNING_STATUSES,
    SUCCESS_STATUS,
)


async def has_claim(jobs: JobQueue, check_id: str, claim_index: int) -> bool:
    """Whether the check is finished and has a claim at ``claim_index``.

    Args:
        jobs: the job queue port.
        check_id: the check's workflow id.
        claim_index: the claim's position in its result.

    Returns:
        True when the claim exists.

    Features:
        US-MOD-03, F-24, ADR-22
    """
    state = await jobs.state(check_id)
    if state is None or state.output is None:
        return False
    try:
        result = CheckOutput.model_validate(state.output).result
    except ValidationError:  # another workflow's id
        return False
    return claim_index < len(result.claims)


def _saved(state: JobState | None) -> Escalation | None:
    succeeded = state is not None and state.status == SUCCESS_STATUS
    if not succeeded or state.output is None:
        return None
    try:
        escalation = EscalateClaimOutput.model_validate(state.output).escalation
    except ValidationError:
        return None
    return None if escalation.case_id is None else escalation


async def _finished(jobs: JobQueue, workflow_id: str) -> JobState | None:
    state = await jobs.state(workflow_id)
    while state is not None and state.status in RUNNING_STATUSES:
        await asyncio.sleep(POLL_SECONDS)
        state = await jobs.state(workflow_id)
    return state


async def escalate(jobs: JobQueue, payload: EscalateClaimInput) -> Escalation | None:
    """Run `escalate_claim` and wait for the saved case.

    Args:
        jobs: the job queue port.
        payload: the hand-off.

    Returns:
        The escalation with its case, or None when no case was saved in time.

    Features:
        US-MOD-03, US-MOD-06, F-24, ADR-22
    """
    try:
        async with asyncio.timeout(ESCALATION_WAIT_SECONDS):
            workflow_id = await jobs.enqueue(ESCALATE_CLAIM, payload)
            return _saved(await _finished(jobs, workflow_id))
    except Exception:  # ruff: ignore[blind-except]  # timeout or DBOS error: either way no case was saved
        return None
