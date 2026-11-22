"""Privacy API: DELETE /api/v1/sessions/{session_id}/checks and ``delete_subject``.

Deletion reaches every place that keeps a person's checks: the check records,
notifications and moderator case links right away (core's ``SubjectEraser``), and
the DBOS workflow data and uploaded files through the ``delete_subject`` workflow
the worker runs (core/019, worker/024, ADR-31).

Features:
    US-BEZ-05, US-BEZ-06, US-POW-04, F-20, ADR-13, ADR-29
"""

import re
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from meritum_core.checks import SubjectKind
from meritum_core.jobs.constants import HASH_PATTERN
from meritum_core.jobs.contracts import DELETE_SUBJECT, DeleteSubjectInput
from meritum_core.jobs.ports import JobQueue
from meritum_core.notifications import NotificationRepository
from meritum_core.observability import SubjectEraser
from pydantic import BaseModel, ValidationError

from meritum_backend.auth import Account
from meritum_backend.auth.api import CsrfUser
from meritum_backend.checks import SESSION_HEADER
from meritum_backend.jobs.api import Jobs
from meritum_backend.limits import limiter
from meritum_backend.privacy.constants import (
    BAD_SUBJECT_DETAIL,
    DELETE_LIMIT_PER_MINUTE,
    DELETE_LIMIT_SCOPE,
    NOT_OWN_SESSION_DETAIL,
    UNAVAILABLE_DETAIL,
)


class DeletedChecks(BaseModel):
    """202 answer: the deletion ran and the worker got the rest.

    Attributes:
        deleted: check records and notifications deleted right away; DBOS data
            and files follow in the ``delete_subject`` workflow.

    Features:
        US-BEZ-05, F-20
    """

    deleted: int


def get_eraser(request: Request) -> SubjectEraser:
    """The SubjectEraser over the app repositories built at startup.

    Args:
        request: the current request (holds the app state).

    Returns:
        The app's eraser.

    Features:
        US-BEZ-05, F-20
    """
    return request.app.state.repositories.eraser


Eraser = Annotated[SubjectEraser, Depends(get_eraser)]


async def delete_subject(
    kind: SubjectKind, value: str, eraser: SubjectEraser, jobs: JobQueue
) -> int:
    """Delete everything stored about one person, in every channel.

    The workflow goes first: if erasing the app tables then fails, the worker
    still erases them along with the DBOS data and files. An invalid ``value``
    (a raw channel id instead of the hash) fails validation of the workflow
    input with pydantic's ValidationError before anything is deleted.

    Args:
        kind: which identifier names the person.
        value: the session id, the user id or the salted channel user hash
            (never a raw Discord, SMS or MCP id).
        eraser: deletes records, notifications and moderator case links.
        jobs: the queue that gets the ``delete_subject`` workflow.

    Returns:
        How many check records and notifications were deleted right away.

    Features:
        US-BEZ-05, US-BEZ-06, US-POW-04, F-20, ADR-13
    """
    await jobs.enqueue(DELETE_SUBJECT, DeleteSubjectInput(kind=kind, value=value))
    return await eraser.erase(kind, value)


router = APIRouter(prefix="/api/v1/sessions", tags=["privacy"])


@router.delete(
    "/{session_id}/checks",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DeletedChecks,
)
@limiter.shared_limit(f"{DELETE_LIMIT_PER_MINUTE}/minute", scope=DELETE_LIMIT_SCOPE)  # ty: ignore[dynamic-function-decorator-return]
async def delete_session_checks(
    request: Request,  # ruff: ignore[unused-function-argument] (slowapi reads the client address)
    session_id: str,
    jobs: Jobs,
    eraser: Eraser,
    session: Annotated[str | None, Header(alias=SESSION_HEADER)] = None,
) -> DeletedChecks:
    """Delete the checks of one browser session („Usuń moje sprawdzenia”).

    The random session id in the path is the key: only its holder knows it, so
    a session reaches only its own records. The header is optional (the
    extension does not send it); when sent it must name the same session, which
    catches client mistakes, not attackers. Limited per client address.

    Args:
        request: the request; slowapi reads the client address from it.
        session_id: the random browser session id.
        jobs: the job queue port.
        eraser: the app's SubjectEraser.
        session: the caller's session id, when sent.

    Returns:
        How many records and notifications were deleted right away.

    Raises:
        HTTPException: 403 when the header names another session, 400 for an id
            that is not a browser session id, 503 when the queue or the
            database is unreachable (429 above the limit comes from slowapi).

    Features:
        US-BEZ-05, US-BEZ-06, US-POW-04, F-20
    """
    names_other_session = session is not None and session != session_id
    # A channel user's records carry their hash as session_id; only their channel
    # may delete them.
    is_channel_hash = re.fullmatch(HASH_PATTERN, session_id) is not None
    if names_other_session:
        raise HTTPException(status.HTTP_403_FORBIDDEN, NOT_OWN_SESSION_DETAIL)
    if is_channel_hash:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, BAD_SUBJECT_DETAIL)
    try:
        deleted = await delete_subject("session_id", session_id, eraser, jobs)
    except ValidationError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, BAD_SUBJECT_DETAIL) from None
    except Exception as exc:  # DBOS and psycopg wrap driver errors in their own types
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE_DETAIL
        ) from exc
    return DeletedChecks(deleted=deleted)


account_router = APIRouter(prefix="/api/v1/me", tags=["privacy"])


async def _delete_account_data(
    account: Account, jobs: Jobs, eraser: Eraser
) -> DeletedChecks:
    try:
        deleted = await delete_subject("user_id", account.user_id, eraser, jobs)
    except Exception as exc:  # DBOS and psycopg wrap driver errors in their own types
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE_DETAIL
        ) from exc
    return DeletedChecks(deleted=deleted)


async def _clear_account_inbox(request: Request, account: Account) -> int:
    # the eraser keeps case and system notifications; a deleted account keeps none
    inbox: NotificationRepository = request.app.state.repositories.notifications
    try:
        return await inbox.delete_for("user_id", account.user_id)
    except Exception as exc:  # psycopg wraps driver errors in its own types
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE_DETAIL
        ) from exc


@account_router.delete(
    "/checks", status_code=status.HTTP_202_ACCEPTED, response_model=DeletedChecks
)
async def delete_my_history(
    account: CsrfUser, jobs: Jobs, eraser: Eraser
) -> DeletedChecks:
    """Delete the signed-in citizen's history („Usuń moją historię”).

    Same path as the browser session's deletion: records, notifications about
    checks and case links now, DBOS data and files in the ``delete_subject``
    workflow. Case assignments, system messages and evaluation run
    notifications stay (core's ``ERASED_KINDS``). The account stays signed in.

    Args:
        account: the signed-in account (CSRF token checked).
        jobs: the job queue port.
        eraser: the app's SubjectEraser.

    Returns:
        How many records and notifications were deleted right away.

    Features:
        US-SPR-10, US-BEZ-05, F-31, ADR-13
    """
    return await _delete_account_data(account, jobs, eraser)


@account_router.delete(
    "", status_code=status.HTTP_202_ACCEPTED, response_model=DeletedChecks
)
async def delete_my_account(
    request: Request, account: CsrfUser, jobs: Jobs, eraser: Eraser
) -> DeletedChecks:
    """Delete the account („Usuń konto”): its history, notifications and session.

    Meritum keeps no account row, only the provider's id on the account's
    records, so deleting those and ending the session removes the account.
    Unlike „Usuń moją historię”, every notification of the account goes,
    case assignments and system messages included.

    Args:
        request: the request whose session is cleared.
        account: the signed-in account (CSRF token checked).
        jobs: the job queue port.
        eraser: the app's SubjectEraser.

    Returns:
        How many records and notifications were deleted right away.

    Features:
        US-SPR-10, US-BEZ-05, F-31, ADR-13
    """
    deleted = await _delete_account_data(account, jobs, eraser)
    rest = await _clear_account_inbox(request, account)
    request.session.clear()
    return DeletedChecks(deleted=deleted.deleted + rest)
