"""One incoming Discord message: the web form's check, answered in place.

Features:
    US-WTY-06, US-BEZ-07, F-03, ADR-08
"""

import re
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from meritum_backend.discord.api import (
    Interaction,
    Ports,
    card_url,
    reply_when_done,
    start,
    user_hash,
)
from meritum_backend.discord.constants import CHANNEL_USER, ERRORS, SEEN_MESSAGES


@dataclass(frozen=True)
class Incoming:
    """A message to answer, free of any Discord library type.

    Attributes:
        message_id: Discord's id of the message (the dedup key).
        user_id: the author's Discord id; start hashes it.
        text: the message without the bot's mention.
        reply: posts one message in the same conversation.

    Features:
        US-WTY-06, F-03
    """

    message_id: str
    user_id: str
    text: str
    reply: Callable[[str], Awaitable[None]]


def strip_mention(content: str, bot_id: int) -> str:
    """Remove the bot's own mentions; other users' mentions stay.

    Args:
        content: the message content.
        bot_id: the bot's user id.

    Returns:
        The content without ``<@id>`` and ``<@!id>``, trimmed.

    Features:
        US-WTY-06
    """
    return re.sub(rf"<@!?{bot_id}>", "", content).strip()


class _Replies:
    """InteractionReplies of a message: every message goes to the same place."""

    def __init__(self, reply: Callable[[str], Awaitable[None]]) -> None:
        self._reply = reply

    async def edit_original(self, application_id: str, token: str, text: str) -> None:
        del application_id, token
        await self._reply(text)

    async def follow_up(self, application_id: str, token: str, text: str) -> None:
        del application_id, token
        await self._reply(text)


class GatewayHandler:
    """Starts a check per message, once per message id.

    Args:
        ports: what POST /api/v1/checks takes.
        remember: how many message ids to remember for the dedup.

    Features:
        US-WTY-06, F-03, ADR-08
    """

    def __init__(self, ports: Ports, remember: int = SEEN_MESSAGES) -> None:
        self.ports = ports
        self._remember = remember
        self._seen = OrderedDict[str, None]()

    def _first_time(self, message_id: str) -> bool:
        if message_id in self._seen:
            return False
        self._seen[message_id] = None
        if len(self._seen) > self._remember:
            self._seen.popitem(last=False)
        return True

    async def handle(self, incoming: Incoming) -> None:
        """Check the message's text and reply with the result.

        A resumed session redelivers events: a message answered once is skipped.

        Args:
            incoming: the message.

        Features:
            US-WTY-06, US-BEZ-07, F-03, ADR-08
        """
        if not self._first_time(incoming.message_id):
            return
        ports = self.ports
        if not incoming.text:
            await incoming.reply(ERRORS["errors.empty"])
            return
        hashed = user_hash(ports.settings, incoming.user_id)
        first = hashed is None or not await ports.records.list_for(CHANNEL_USER, hashed)
        started = await start(ports, incoming.text, incoming.user_id)
        if not isinstance(started, str):
            await incoming.reply(started["data"]["content"])
            return
        target = Interaction(
            application_id="",
            token=incoming.message_id,
            card_url=card_url(ports.settings, started),
            first_contact=first,
        )
        await reply_when_done(
            ports.jobs, ports.cache, _Replies(incoming.reply), started, target
        )
