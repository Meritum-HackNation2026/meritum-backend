"""Delete a Discord user's checks from /usun-moje-dane.

Features:
    US-BEZ-05, US-BEZ-06, F-20
"""

from typing import Any

from meritum_core.jobs.ports import JobQueue
from meritum_core.observability import SubjectEraser

from meritum_backend.discord.api._intake import message, user_hash
from meritum_backend.discord.constants import CHANNEL_USER, DELETED, FAILURE_TEXT
from meritum_backend.privacy import delete_subject
from meritum_backend.settings import Settings


async def delete_my_data(
    settings: Settings, user_id: str, eraser: SubjectEraser, jobs: JobQueue
) -> dict[str, Any]:
    """Erase every check record for the asking Discord user.

    Args:
        settings: holds the channel hash salt.
        user_id: the Discord user id.
        eraser: deletes records, notifications and moderator links.
        jobs: the queue for the ``delete_subject`` workflow.

    Returns:
        An ephemeral confirmation, or a refusal when hashing is unavailable.

    Features:
        US-BEZ-05, US-BEZ-06, F-20
    """
    hashed = user_hash(settings, user_id)
    if hashed is None:
        return message(FAILURE_TEXT)
    await delete_subject(CHANNEL_USER, hashed, eraser, jobs)
    return message(DELETED)
