"""Hand-off API: „Przekaż moderatorom” and „Zgłoś błąd” at each claim of a result.

Both enqueue the `escalate_claim` workflow and wait for it: the worker groups
similar claims into one case (worker/015), so the backend only reports what was
saved. A case number appears only after the case was saved (ADR-22).

Features:
    US-MOD-03, US-MOD-06, F-24, ADR-22
"""

import asyncio
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Request, Response, status
from meritum_core.checks import Escalation
from meritum_core.jobs.constants import MAX_JUSTIFICATION_CHARS
from meritum_core.jobs.contracts import (
    ESCALATE_CLAIM,
    CheckOutput,
    EscalateClaimInput,
    EscalateClaimOutput,
)
from meritum_core.jobs.ports import JobQueue, JobState
from pydantic import BaseModel, BeforeValidator, StringConstraints, ValidationError

from meritum_backend.checks import masked_text
from meritum_backend.checks.api import InvalidCheck, KeyedErrorsRoute, PiiGate
from meritum_backend.jobs.api import Jobs
from meritum_backend.limits import limiter
from meritum_backend.moderation.constants import (
    CLAIM_NOT_FOUND_DETAIL,
    DISPUTE_DONE_KEY,
    ESCALATION_KEY_PREFIX,
    ESCALATION_WAIT_SECONDS,
    HANDOFF_LIMIT,
    NOT_SAVED,
    NOT_SAVED_KEY,
    POLL_SECONDS,
    RUNNING_STATUSES,
    SUCCESS_STATUS,
)


class Handoff(BaseModel):
    """The hand-off's outcome as the citizen sees it.

    Attributes:
        escalation: created or updated with the case number, or recommended
            without one when no case was saved.
        message_key: the copy/pl.json key to show; never says who else asked.

    Features:
        US-MOD-03, US-MOD-06, F-24
    """

    escalation: Escalation
    message_key: str


def _none_when_blank(value: object) -> object:
    return None if isinstance(value, str) and not value.strip() else value


class Dispute(BaseModel):
    """Body of „Zgłoś błąd”.

    Attributes:
        justification: what the person thinks is wrong, optional (a blank one
            counts as none); masked before it leaves.

    Features:
        US-MOD-06, F-24
    """

    justification: Annotated[
        str | None,
        BeforeValidator(_none_when_blank),
        StringConstraints(strip_whitespace=True, max_length=MAX_JUSTIFICATION_CHARS),
    ] = None


router = APIRouter(
    prefix="/api/v1/checks", tags=["moderation"], route_class=KeyedErrorsRoute
)

ClaimIndex = Annotated[int, Path(ge=0)]


async def _has_claim(jobs: JobQueue, check_id: str, claim_index: int) -> bool:
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


async def _escalate(jobs: JobQueue, payload: EscalateClaimInput) -> Escalation | None:
    try:
        async with asyncio.timeout(ESCALATION_WAIT_SECONDS):
            workflow_id = await jobs.enqueue(ESCALATE_CLAIM, payload)
            return _saved(await _finished(jobs, workflow_id))
    except Exception:  # ruff: ignore[blind-except]  # timeout or DBOS error: either way no case was saved
        return None


async def _hand_off(
    jobs: JobQueue,
    payload: EscalateClaimInput,
    response: Response,
    done_key: str | None = None,
) -> Handoff:
    escalation = await _escalate(jobs, payload)
    if escalation is None:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return Handoff(escalation=NOT_SAVED, message_key=NOT_SAVED_KEY)
    key = done_key or f"{ESCALATION_KEY_PREFIX}{escalation.state}"
    return Handoff(escalation=escalation, message_key=key)


@router.post(
    "/{check_id}/claims/{claim_index}/escalate",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": CLAIM_NOT_FOUND_DETAIL},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": Handoff},
    },
)
@limiter.limit(HANDOFF_LIMIT)  # ty: ignore[dynamic-function-decorator-return]  # slowapi ships untyped decorators
async def escalate_claim(
    request: Request,  # ruff: ignore[unused-function-argument] (slowapi reads the client address)
    jobs: Jobs,
    check_id: str,
    claim_index: ClaimIndex,
    response: Response,
) -> Handoff:
    """„Przekaż moderatorom”: turn a recommendation into a saved case.

    Limited to HANDOFF_LIMIT per client address (429 above that).

    Args:
        request: the request; slowapi reads the client address from it.
        jobs: the job queue port.
        check_id: the finished check.
        claim_index: the claim's position in the check's result.
        response: the response; gets 503 when no case was saved.

    Returns:
        The case created or joined with its number and escalation.created or
        escalation.updated; with 503, escalation recommended (no number) and
        escalation.recommended when the case was not saved.

    Raises:
        HTTPException: 404 when the check is not finished or has no such claim.

    Features:
        US-MOD-03, F-24, ADR-22
    """
    if not await _has_claim(jobs, check_id, claim_index):
        raise HTTPException(status.HTTP_404_NOT_FOUND, CLAIM_NOT_FOUND_DETAIL)
    payload = EscalateClaimInput(
        check_id=check_id, claim_index=claim_index, reason="recommended_clicked"
    )
    return await _hand_off(jobs, payload, response)


@router.post(
    "/{check_id}/claims/{claim_index}/dispute",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": CLAIM_NOT_FOUND_DETAIL},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": Handoff},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": InvalidCheck},
    },
)
@limiter.limit(HANDOFF_LIMIT)  # ty: ignore[dynamic-function-decorator-return]  # slowapi ships untyped decorators
async def dispute_claim(  # ruff: ignore[too-many-arguments, too-many-positional-arguments]  # FastAPI injects each part as a parameter
    request: Request,  # ruff: ignore[unused-function-argument] (slowapi reads the client address)
    jobs: Jobs,
    check_id: str,
    claim_index: ClaimIndex,
    response: Response,
    pii: PiiGate,
    dispute: Dispute | None = None,
) -> Handoff:
    """„Zgłoś błąd”: a case with reason user_dispute and a masked justification.

    The stored result does not change; a moderator reviews the dispute first.
    Limited to HANDOFF_LIMIT per client address (429 above that).

    Args:
        request: the request; slowapi reads the client address from it.
        jobs: the job queue port.
        check_id: the finished check.
        claim_index: the claim's position in the check's result.
        response: the response; gets 503 when no case was saved.
        pii: the personal-data masking gate.
        dispute: the person's optional reason, masked here before the workflow
            starts; no body or a blank reason sends none.

    Returns:
        The case with its number and result.report_error_done; with 503,
        escalation recommended (no number) when the case was not saved.

    Raises:
        HTTPException: 404 when the check is not finished or has no such claim.

    Features:
        US-MOD-06, F-24, ADR-22
    """
    if not await _has_claim(jobs, check_id, claim_index):
        raise HTTPException(status.HTTP_404_NOT_FOUND, CLAIM_NOT_FOUND_DETAIL)
    reason = dispute.justification if dispute else None
    payload = EscalateClaimInput(
        check_id=check_id,
        claim_index=claim_index,
        reason="user_dispute",
        justification_masked=reason
        and await masked_text(reason, MAX_JUSTIFICATION_CHARS, pii),
    )
    return await _hand_off(jobs, payload, response, DISPUTE_DONE_KEY)
