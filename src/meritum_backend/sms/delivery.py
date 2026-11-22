"""Sends the reply once the check finished; runs after the webhook answered.

The number lives only in this task's memory: a restart loses the reply, never
leaks the number into a store.

Features:
    US-WTY-07, US-BEZ-07, F-32, F-21
"""

import asyncio

from meritum_core.jobs.ports import JobQueue, JobState

from meritum_backend.checks import check_result
from meritum_backend.sms.constants import FINISHED_STATUSES, POLL_ATTEMPTS, POLL_SECONDS
from meritum_backend.sms.ports import SmsSender
from meritum_backend.sms.replies import reply_texts


async def _finished(jobs: JobQueue, check_id: str) -> JobState | None:
    for _ in range(POLL_ATTEMPTS):
        state = await jobs.state(check_id)
        if state is not None and state.status in FINISHED_STATUSES:
            return state
        await asyncio.sleep(POLL_SECONDS)
    return None


async def reply_when_done(  # ruff: ignore[too-many-arguments]  # a background task takes plain values
    jobs: JobQueue,
    sms: SmsSender,
    check_id: str,
    phone_number: str,
    *,
    first_contact: bool,
    gsm7: bool,
    link: str,
) -> None:
    """Wait for the check, then send its verdict (or the failure text).

    Args:
        jobs: the job queue the check runs on.
        sms: the gateway sender.
        check_id: the check's workflow id.
        phone_number: where the reply goes.
        first_contact: the AI notice goes first.
        gsm7: the sms_gsm7 setting.
        link: the full result card; ends the last SMS.

    Features:
        US-WTY-07, US-BEZ-07, F-32, F-21
    """
    state = await _finished(jobs, check_id)
    result = check_result(state) if state is not None else None
    for text in reply_texts(result, first_contact=first_contact, gsm7=gsm7, link=link):
        await sms.send(phone_number, text)
