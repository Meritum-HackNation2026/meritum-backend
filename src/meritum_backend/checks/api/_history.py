"""GET /api/v1/me/checks: the signed-in citizen's history, the same on every device.

Features:
    US-SPR-10, US-BEZ-05, F-31, ADR-13
"""

from datetime import datetime

from fastapi import APIRouter
from meritum_core.checks.contracts import CheckStatus, Verdict
from pydantic import BaseModel

from meritum_backend.auth.api import CurrentUser
from meritum_backend.checks.api._cache import Records

router = APIRouter(prefix="/api/v1/me", tags=["history"])


class HistoryItem(BaseModel):
    """One past check as the citizen sees it (no audit fields).

    Attributes:
        check_id: the id of the check (opens its result).
        channel: the channel the check came through.
        received_at: when the question arrived.
        question_masked: the question with personal data masked.
        status: the check's status.
        verdicts: the verdict of each claim.

    Features:
        US-SPR-10, F-31
    """

    check_id: str
    channel: str
    received_at: datetime
    question_masked: str
    status: CheckStatus
    verdicts: list[Verdict]


@router.get("/checks")
async def my_checks(account: CurrentUser, records: Records) -> list[HistoryItem]:
    """List the checks sent while signed in with this account, newest first.

    Args:
        account: the signed-in account (401 without a session).
        records: the check records repository.

    Returns:
        The account's checks, on any device that signed in with it.

    Features:
        US-SPR-10, US-BEZ-05, F-31
    """
    found = await records.list_for("user_id", account.user_id)
    found.sort(key=lambda r: r.received_at, reverse=True)
    return [
        HistoryItem(**r.model_dump(include=set(HistoryItem.model_fields)))
        for r in found
    ]
