"""Sends the result once the check finished; runs after the deferred answer.

The interaction token lives only in this task's memory: a restart loses the
reply, never leaks the token into a store.

Features:
    US-WTY-06, US-BEZ-07, F-03, F-21
"""

import asyncio
from dataclasses import dataclass

from fastapi import HTTPException, Response
from meritum_core.checks import CheckResult
from meritum_core.jobs.ports import JobQueue

from meritum_backend.checks import ResultCache
from meritum_backend.checks.api import check_status
from meritum_backend.discord.constants import (
    FINISHED_STATUSES,
    POLL_ATTEMPTS,
    POLL_SECONDS,
)
from meritum_backend.discord.messages import reply_messages
from meritum_backend.discord.ports import InteractionReplies


@dataclass(frozen=True)
class Interaction:
    """Where the reply to one deferred interaction goes.

    Attributes:
        application_id: the Discord app id.
        token: the interaction token.
        card_url: the full result card of the check.
        first_contact: the user hash has no earlier checks.

    Features:
        US-WTY-06, US-BEZ-07, F-03, F-21
    """

    application_id: str
    token: str
    card_url: str
    first_contact: bool


async def _result(
    jobs: JobQueue, cache: ResultCache, check_id: str
) -> CheckResult | None:
    for _ in range(POLL_ATTEMPTS):
        # read before the result, so a check that ends in between is read again
        state = await jobs.state(check_id)
        try:
            status = await check_status(jobs, cache, check_id, Response())
        except HTTPException:
            return None
        if status.result is not None:
            return status.result
        if state is not None and state.status in FINISHED_STATUSES:
            return None  # the workflow ended without a result: it failed
        await asyncio.sleep(POLL_SECONDS)
    return None


async def reply_when_done(
    jobs: JobQueue,
    cache: ResultCache,
    replies: InteractionReplies,
    check_id: str,
    interaction: Interaction,
) -> None:
    """Wait for the check (as GET /api/v1/checks/{id} does), then send its messages.

    Args:
        jobs: the job queue the check runs on.
        cache: the result cache (a hit has no workflow).
        replies: the Discord sender.
        check_id: the check's id.
        interaction: where the reply goes.

    Features:
        US-WTY-06, US-BEZ-07, F-03, F-21
    """
    result = await _result(jobs, cache, check_id)
    first, *rest = reply_messages(
        result, interaction.card_url, first_contact=interaction.first_contact
    )
    app, token = interaction.application_id, interaction.token
    await replies.edit_original(app, token, first)
    for text in rest:
        await replies.follow_up(app, token, text)
