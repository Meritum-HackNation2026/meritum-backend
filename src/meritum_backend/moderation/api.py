"""Moderation API: the panel's case list and the admin's high-risk topic list.

Cases carry no channel user id or hash (core's ``ModeratorCase``), so neither
does this API. The worker's topic step reads the same topic repository, so a
change applies to the next claim without a restart.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, status
from meritum_core.checks.contracts import ModeratorCase
from meritum_core.moderation import (
    HighRiskTopic,
    HighRiskTopicRepository,
    ModeratorCaseRepository,
)
from meritum_core.moderation.constants import TOPIC_NAME_MAX_CHARS

from meritum_backend.auth.api import CsrfUser
from meritum_backend.moderation.constants import CASE_ROLES
from meritum_backend.staff import StaffMember
from meritum_backend.staff.api import Admin, AnyStaff, StaffGate

router = APIRouter(prefix="/api/v1/moderation", tags=["moderation"])


def get_cases(request: Request) -> ModeratorCaseRepository:
    """The case repository the app built (overridden in tests).

    Args:
        request: the current request (holds the app state).

    Returns:
        The app's case repository.

    Features:
        US-MOD-01, F-25
    """
    return request.app.state.cases


def get_topics(request: Request) -> HighRiskTopicRepository:
    """The high-risk topic repository the app built (overridden in tests).

    Args:
        request: the current request (holds the app state).

    Returns:
        The app's topic repository.

    Features:
        US-MOD-05, F-20
    """
    return request.app.state.topics


Cases = Annotated[ModeratorCaseRepository, Depends(get_cases)]
Topics = Annotated[HighRiskTopicRepository, Depends(get_topics)]
CaseReader = Annotated[StaffMember, Depends(StaffGate(CASE_ROLES))]


@router.get("/cases")
async def list_cases(_member: CaseReader, cases: Cases) -> list[ModeratorCase]:
    """The moderator cases, latest first.

    Args:
        _member: a signed-in moderator or administrator.
        cases: the case repository.

    Returns:
        The cases.

    Features:
        US-MOD-01, US-MOD-05, F-25
    """
    return await cases.list_cases()


@router.get("/topics")
async def list_topics(_member: AnyStaff, topics: Topics) -> list[HighRiskTopic]:
    """The high-risk topics and their keywords; open to every staff role.

    Args:
        _member: a signed-in member with any role.
        topics: the topic repository.

    Returns:
        The topics, sorted by name.

    Features:
        US-MOD-05, F-20, F-25
    """
    return await topics.list_topics()


@router.post("/topics", status_code=status.HTTP_201_CREATED)
async def save_topic(
    topic: HighRiskTopic, _admin: Admin, _csrf: CsrfUser, topics: Topics
) -> HighRiskTopic:
    """Add a topic or replace the one with the same name.

    Args:
        topic: the topic and its keywords.
        _admin: the signed-in administrator.
        _csrf: the account, CSRF checked.
        topics: the topic repository.

    Returns:
        The stored topic.

    Features:
        US-MOD-05, F-20, F-25
    """
    await topics.save_topic(topic)
    return topic


@router.delete("/topics/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_topic(
    name: Annotated[str, Path(max_length=TOPIC_NAME_MAX_CHARS)],
    _admin: Admin,
    _csrf: CsrfUser,
    topics: Topics,
) -> None:
    """Delete a topic; an unknown name does nothing.

    Args:
        name: the topic's name.
        _admin: the signed-in administrator.
        _csrf: the account, CSRF checked.
        topics: the topic repository.

    Features:
        US-MOD-05, F-20, F-25
    """
    await topics.delete_topic(name)
