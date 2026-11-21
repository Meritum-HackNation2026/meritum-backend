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
from meritum_core.observability import SubjectEraser
from pydantic import BaseModel, ValidationError

from meritum_backend.checks import SESSION_HEADER
from meritum_backend.jobs.api import Jobs
from meritum_backend.privacy.constants import (
    BAD_SUBJECT_DETAIL,
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
async def delete_session_checks(
    session_id: str,
    jobs: Jobs,
    eraser: Eraser,
    session: Annotated[str | None, Header(alias=SESSION_HEADER)] = None,
) -> DeletedChecks:
    """Delete the checks of one browser session („Usuń moje sprawdzenia”).

    The random session id is the key: only its holder knows it. A request that
    also names its session in the header must name the same one.

    Args:
        session_id: the random browser session id.
        jobs: the job queue port.
        eraser: the app's SubjectEraser.
        session: the caller's session id, when sent.

    Returns:
        How many records and notifications were deleted right away.

    Raises:
        HTTPException: 403 when the header names another session, 400 for an id
            that is not a browser session id, 503 when the queue or the
            database is unreachable.

    Features:
        US-BEZ-05, US-BEZ-06, US-POW-04, F-20
    """
    if session is not None and session != session_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, NOT_OWN_SESSION_DETAIL)
    # A channel user's records carry their hash as session_id; only their channel
    # may delete them.
    if re.fullmatch(HASH_PATTERN, session_id):
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
