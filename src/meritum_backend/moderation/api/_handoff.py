"""Hand-off API: „Przekaż moderatorom” and „Zgłoś błąd” at each claim of a result.

Both enqueue the `escalate_claim` workflow and wait for it: the worker groups
similar claims into one case (worker/015), so the backend only reports what was
saved. A case number appears only after the case was saved (ADR-22).

Features:
    US-MOD-03, US-MOD-06, F-24, ADR-22
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Path,
    Request,
    Response,
    status,
)
from meritum_core.checks import Escalation
from meritum_core.jobs.constants import MAX_JUSTIFICATION_CHARS
from meritum_core.jobs.contracts import (
    EscalateClaimInput,
)
from meritum_core.jobs.ports import JobQueue
from pydantic import BaseModel, BeforeValidator, StringConstraints

from meritum_backend.checks import masked_text
from meritum_backend.checks.api import Cache, InvalidCheck, KeyedErrorsRoute, PiiGate
from meritum_backend.jobs.api import Jobs
from meritum_backend.limits import limiter
from meritum_backend.moderation.api._workflow import escalate, has_claim
from meritum_backend.moderation.constants import (
    CLAIM_NOT_FOUND_DETAIL,
    DISPUTE_DONE_KEY,
    ESCALATION_KEY_PREFIX,
    HANDOFF_LIMIT,
    JUSTIFICATION_INPUT_MAX_CHARS,
    NOT_SAVED,
    NOT_SAVED_KEY,
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
    if not isinstance(value, str):
        return value  # left to pydantic: anything but text is refused
    return value.strip() or None


class Dispute(BaseModel):
    """Body of „Zgłoś błąd”.

    Attributes:
        justification: what the person thinks is wrong, optional (a blank one
            counts as none, over JUSTIFICATION_INPUT_MAX_CHARS is refused);
            masked, then cut to MAX_JUSTIFICATION_CHARS before any marker.

    Features:
        US-MOD-06, F-24
    """

    justification: Annotated[
        Annotated[str, StringConstraints(max_length=JUSTIFICATION_INPUT_MAX_CHARS)]
        | None,
        BeforeValidator(_none_when_blank),
    ] = None


router = APIRouter(
    prefix="/api/v1/checks", tags=["moderation"], route_class=KeyedErrorsRoute
)

ClaimIndex = Annotated[int, Path(ge=0)]
type Announce = Callable[[str], None]
"""Schedules the announcement of a case."""


def get_announce(request: Request, background: BackgroundTasks) -> Announce:
    """Schedule the moderators' announcement of a case after the response.

    A slow or failing target never delays the citizen or blocks the case.

    Args:
        request: the current request (holds the app state).
        background: runs the announcement after the response.

    Returns:
        A function that takes the case number.

    Features:
        US-POW-05, US-MOD-01, F-26
    """

    def announce(case_id: str) -> None:
        background.add_task(request.app.state.announcer.announce, case_id)

    return announce


async def _hand_off(
    jobs: JobQueue,
    payload: EscalateClaimInput,
    response: Response,
    announce: Callable[[str], None],
    done_key: str | None = None,
) -> Handoff:
    escalation = await escalate(jobs, payload)
    if escalation is None or escalation.case_id is None:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return Handoff(escalation=NOT_SAVED, message_key=NOT_SAVED_KEY)
    announce(escalation.case_id)
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
async def escalate_claim(  # ruff: ignore[too-many-arguments, too-many-positional-arguments]  # FastAPI injects each part as a parameter
    request: Request,  # ruff: ignore[unused-function-argument] (slowapi reads the client address)
    jobs: Jobs,
    cache: Cache,
    check_id: str,
    claim_index: ClaimIndex,
    response: Response,
    announce: Annotated[Announce, Depends(get_announce)],
) -> Handoff:
    """„Przekaż moderatorom”: turn a recommendation into a saved case.

    Limited to HANDOFF_LIMIT per client address (429 above that).

    Args:
        request: the request; slowapi reads the client address from it.
        jobs: the job queue port.
        cache: the result cache (a hit has no workflow).
        check_id: the finished check.
        claim_index: the claim's position in the check's result.
        response: the response; gets 503 when no case was saved.
        announce: tells the moderators about the case after the response.

    Returns:
        The case created or joined with its number and escalation.created or
        escalation.updated; with 503, escalation recommended (no number) and
        escalation.not_saved when the case was not saved.

    Raises:
        HTTPException: 404 when the check is not finished or has no such claim.

    Features:
        US-MOD-03, F-24, ADR-22
    """
    if not await has_claim(jobs, cache, check_id, claim_index):
        raise HTTPException(status.HTTP_404_NOT_FOUND, CLAIM_NOT_FOUND_DETAIL)
    payload = EscalateClaimInput(
        check_id=check_id, claim_index=claim_index, reason="recommended_clicked"
    )
    return await _hand_off(jobs, payload, response, announce)


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
    cache: Cache,
    check_id: str,
    claim_index: ClaimIndex,
    response: Response,
    announce: Annotated[Announce, Depends(get_announce)],
    pii: PiiGate,
    dispute: Dispute | None = None,
) -> Handoff:
    """„Zgłoś błąd”: a case with reason user_dispute and a masked justification.

    The stored result does not change; a moderator reviews the dispute first.
    Limited to HANDOFF_LIMIT per client address (429 above that).

    Args:
        request: the request; slowapi reads the client address from it.
        jobs: the job queue port.
        cache: the result cache (a hit has no workflow).
        check_id: the finished check.
        claim_index: the claim's position in the check's result.
        response: the response; gets 503 when no case was saved.
        announce: tells the moderators about the case after the response.
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
    if not await has_claim(jobs, cache, check_id, claim_index):
        raise HTTPException(status.HTTP_404_NOT_FOUND, CLAIM_NOT_FOUND_DETAIL)
    reason = dispute.justification if dispute else None
    payload = EscalateClaimInput(
        check_id=check_id,
        claim_index=claim_index,
        reason="user_dispute",
        justification_masked=reason
        and await masked_text(reason, MAX_JUSTIFICATION_CHARS, pii),
    )
    return await _hand_off(
        jobs,
        payload,
        response,
        announce,
        DISPUTE_DONE_KEY,
    )
