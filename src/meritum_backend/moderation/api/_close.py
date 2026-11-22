"""Closing a case without an answer: a test or groundless case leaves the list.

Nothing reaches the askers; the panel keeps who closed the case and why.

Features:
    US-MOD-01, US-MOD-07, F-25, F-39
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from meritum_backend.auth.api import CsrfUser
from meritum_backend.moderation._closures import (
    CaseClosure,
    ClosureDraft,
    ClosureStore,
)
from meritum_backend.moderation.api._answer import Answerer, CaseId, open_case
from meritum_backend.moderation.api._cases import CaseReader, Cases
from meritum_backend.moderation.constants import (
    CASE_NOT_FOUND_DETAIL,
    CASE_NOT_OPEN_DETAIL,
    CLOSURE_NOT_FOUND_DETAIL,
)

router = APIRouter(prefix="/api/v1/moderation", tags=["moderation"])


def get_closures(request: Request) -> ClosureStore:
    """The closure store the app built (overridden in tests).

    Args:
        request: the current request (holds the app state).

    Returns:
        The app's closure store.

    Features:
        US-MOD-01, F-25
    """
    return request.app.state.closures


Closures = Annotated[ClosureStore, Depends(get_closures)]


@router.post(
    "/cases/{case_id}/close",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": CASE_NOT_FOUND_DETAIL},
        status.HTTP_409_CONFLICT: {"description": CASE_NOT_OPEN_DETAIL},
    },
)
async def close_case(
    case_id: CaseId,
    draft: ClosureDraft,
    member: Answerer,
    _csrf: CsrfUser,
    cases: Cases,
    closures: Closures,
) -> CaseClosure:
    """Close an open case without sending an answer or a notification.

    ``open_case`` answers 404 for an unknown case and 409 for one not open.

    Args:
        case_id: the case id, e.g. ``#S-12``.
        draft: the reason.
        member: the signed-in moderator, recorded as the closer.
        _csrf: the account, CSRF checked.
        cases: the case repository.
        closures: where the close is kept.

    Returns:
        The close as recorded.

    Features:
        US-MOD-01, US-MOD-07, F-25, F-39
    """
    case = await open_case(cases, case_id)
    closure = CaseClosure(
        case_id=case_id,
        closed_by=member.email,
        reason=draft.reason,
        closed_at=datetime.now(UTC),
    )
    await closures.save(closure)
    await cases.save(case.model_copy(update={"state": "closed"}))
    return closure


@router.get("/cases/{case_id}/closure")
async def read_closure(
    case_id: CaseId, _member: CaseReader, closures: Closures
) -> CaseClosure:
    """Who closed the case without an answer, and why.

    Args:
        case_id: the case id.
        _member: a signed-in moderator or administrator.
        closures: where the close is kept.

    Returns:
        The close.

    Raises:
        HTTPException: 404 when the case was not closed this way.

    Features:
        US-MOD-01, F-25
    """
    closure = await closures.get(case_id)
    if closure is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, CLOSURE_NOT_FOUND_DETAIL)
    return closure
