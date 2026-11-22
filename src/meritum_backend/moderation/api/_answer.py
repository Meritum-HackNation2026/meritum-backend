"""Moderator answers: send one to a case, read it back (panel and askers).

The answer is never public: askers read it only after a ``moderator_answer``
notification reached them.

Features:
    US-MOD-07, US-POW-02, F-39, ADR-06
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from meritum_core.checks.contracts import ModeratorCase
from meritum_core.moderation import ModeratorCaseRepository
from meritum_core.notifications import NotificationRepository

from meritum_backend.auth.api import CsrfUser
from meritum_backend.moderation._answers import (
    Answer,
    AnswerDraft,
    AnswerStore,
    SourceDocuments,
    verify_quotes,
)
from meritum_backend.moderation._askers import notify_askers
from meritum_backend.moderation.api._cases import CaseReader, Cases
from meritum_backend.moderation.constants import (
    ANSWER_NOT_FOUND_DETAIL,
    CASE_ID_PATTERN,
    CASE_NOT_FOUND_DETAIL,
    CASE_NOT_OPEN_DETAIL,
    QUOTES_REFUSED_DETAIL,
)
from meritum_backend.notifications.api import Recipient, recipients
from meritum_backend.staff import StaffMember
from meritum_backend.staff.api import StaffGate

router = APIRouter(prefix="/api/v1/moderation", tags=["moderation"])
CaseId = Annotated[str, Path(pattern=CASE_ID_PATTERN)]
Answerer = Annotated[StaffMember, Depends(StaffGate(frozenset({"moderator"})))]


def get_answers(request: Request) -> AnswerStore:
    """The answer store the app built (overridden in tests).

    Args:
        request: the current request (holds the app state).

    Returns:
        The app's answer store.

    Features:
        US-MOD-07, F-39
    """
    return request.app.state.answers


def get_source_documents(request: Request) -> SourceDocuments:
    """The catalogue's source texts the app built (overridden in tests).

    Args:
        request: the current request (holds the app state).

    Returns:
        The app's source documents.

    Features:
        US-MOD-07, F-39, ADR-06
    """
    return request.app.state.source_documents


def get_inbox(request: Request) -> NotificationRepository:
    """The notifications store (overridden in tests).

    Args:
        request: the current request (holds the app state).

    Returns:
        The app's notification repository.

    Features:
        US-MOD-07, F-39
    """
    return request.app.state.repositories.notifications


Answers = Annotated[AnswerStore, Depends(get_answers)]
Documents = Annotated[SourceDocuments, Depends(get_source_documents)]
Inbox = Annotated[NotificationRepository, Depends(get_inbox)]


@router.post(
    "/cases/{case_id}/answer",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": CASE_NOT_FOUND_DETAIL},
        status.HTTP_409_CONFLICT: {"description": CASE_NOT_OPEN_DETAIL},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": QUOTES_REFUSED_DETAIL},
    },
)
async def answer_case(  # ruff: ignore[too-many-arguments, too-many-positional-arguments]  # FastAPI injects each part as a parameter
    case_id: CaseId,
    draft: AnswerDraft,
    _member: Answerer,
    _csrf: CsrfUser,
    cases: Cases,
    documents: Documents,
    answers: Answers,
    inbox: Inbox,
    request: Request,
) -> Answer:
    """Answer an open case: verify the quotes, notify the askers, mark it answered.

    Nothing is sent or saved when a quote fails: the 422 names the failed ones.

    Args:
        case_id: the case id, e.g. ``#S-12``.
        draft: the answer text and its quotes.
        _member: a signed-in moderator.
        _csrf: the account, CSRF checked.
        cases: the case repository.
        documents: the catalogue's source texts.
        answers: where the answer is kept.
        inbox: the notifications store.
        request: the current request (holds the check records).

    Returns:
        The answer as sent, with the quotes as the sources write them.

    Raises:
        HTTPException: 404 unknown case, 409 not open, 422 with
            ``rejected_quotes`` (indexes) when a quote is not verbatim.

    Features:
        US-MOD-07, US-POW-02, F-39, ADR-06
    """
    case = await open_case(cases, case_id)
    verified, rejected = await verify_quotes(draft.quotes, documents)
    if rejected:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {"message": QUOTES_REFUSED_DETAIL, "rejected_quotes": rejected},
        )
    answer = Answer(case_id=case_id, text=draft.text, quotes=verified)
    await answers.save(answer)
    await cases.save(case.model_copy(update={"state": "answered"}))
    await notify_askers(case, request.app.state.repositories.records, inbox)
    return answer


async def open_case(cases: ModeratorCaseRepository, case_id: str) -> ModeratorCase:
    """The case a moderator may still answer or close.

    Args:
        cases: the case repository.
        case_id: the case id.

    Returns:
        The open case.

    Raises:
        HTTPException: 404 unknown case, 409 not open.

    Features:
        US-MOD-01, US-MOD-07, F-25, F-39
    """
    case = await cases.get(case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, CASE_NOT_FOUND_DETAIL)
    if case.state != "open":
        raise HTTPException(status.HTTP_409_CONFLICT, CASE_NOT_OPEN_DETAIL)
    return case


@router.get("/cases/{case_id}/answer")
async def read_answer(case_id: CaseId, _member: CaseReader, answers: Answers) -> Answer:
    """The answer the panel shows next to its case.

    Args:
        case_id: the case id.
        _member: a signed-in moderator or administrator.
        answers: where the answer is kept.

    Returns:
        The answer.

    Raises:
        HTTPException: 404 when the case has no answer.

    Features:
        US-MOD-07, F-39
    """
    answer = await answers.get(case_id)
    if answer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, ANSWER_NOT_FOUND_DETAIL)
    return answer


@router.get("/answers/{case_id}")
async def read_my_answer(
    case_id: CaseId,
    caller: Annotated[list[Recipient], Depends(recipients)],
    answers: Answers,
    inbox: Inbox,
) -> Answer:
    """The answer to a case, for an asker the notification reached.

    Args:
        case_id: the case id.
        caller: the caller's session and account.
        answers: where the answer is kept.
        inbox: the notifications store.

    Returns:
        The answer.

    Raises:
        HTTPException: 404 unless the caller holds a ``moderator_answer``
            notification for this case (the answer is not public).

    Features:
        US-MOD-07, US-POW-02, F-39
    """
    told = False
    for kind, value in caller:
        told = told or any(
            n.kind == "moderator_answer" and n.case_id == case_id
            for n in await inbox.list_for(kind, value)
        )
    answer = await answers.get(case_id) if told else None
    if answer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, ANSWER_NOT_FOUND_DETAIL)
    return answer
