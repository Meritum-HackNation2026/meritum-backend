"""One incoming Discord message: the web form's check, answered in place.

Features:
    US-WTY-06, US-BEZ-07, F-03, ADR-08
"""

import re
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from meritum_backend.checks.api import (
    AUDIO_FORMATS,
    AUDIO_MAX_MB,
    AUDIO_MAX_MINUTES,
    AudioRefusedError,
    AudioStoreError,
    store_audio,
)
from meritum_backend.discord.api import (
    Interaction,
    Ports,
    card_url,
    reply_when_done,
    start,
    user_hash,
)
from meritum_backend.discord.constants import (
    AUDIO_REFUSALS,
    CHANNEL_USER,
    ERRORS,
    FAILURE_TEXT,
    SEEN_MESSAGES,
)
from meritum_backend.discord.errors import VoiceDownloadError, VoiceTooLargeError
from meritum_backend.discord.ports import VoiceDownloader


@dataclass(frozen=True)
class Incoming:
    """A message to answer, free of any Discord library type.

    Attributes:
        message_id: Discord's id of the message (the dedup key).
        user_id: the author's Discord id; start hashes it.
        text: the message without the bot's mention.
        reply: posts one message in the same conversation.
        voice_url: the signed URL of a voice message's OGG attachment, if any.

    Features:
        US-WTY-06, F-03
    """

    message_id: str
    user_id: str
    text: str
    reply: Callable[[str], Awaitable[None]]
    voice_url: str | None = None


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
        voice: downloads voice message attachments; None answers them with the
            technical failure text.

    Features:
        US-WTY-06, F-03, ADR-08
    """

    def __init__(
        self,
        ports: Ports,
        remember: int = SEEN_MESSAGES,
        voice: VoiceDownloader | None = None,
    ) -> None:
        self.ports = ports
        self._voice = voice
        self._remember = remember
        self._seen = OrderedDict[str, None]()

    def _first_time(self, message_id: str) -> bool:
        if message_id in self._seen:
            return False
        self._seen[message_id] = None
        if len(self._seen) > self._remember:
            self._seen.popitem(last=False)
        return True

    async def _store_voice(self, incoming: Incoming) -> str | None:
        """Download the attachment now (its URL expires) and keep it.

        Returns:
            The audio id, or None after the reason was sent: no verdict.
        """
        blobs = self.ports.blobs
        if self._voice is None or blobs is None or incoming.voice_url is None:
            await incoming.reply(FAILURE_TEXT)
            return None
        try:
            data = await self._voice.download(incoming.voice_url)
            return await store_audio(blobs, data)
        except VoiceTooLargeError:
            key = "errors.audio_too_large"
        except AudioRefusedError as refused:
            key = refused.key
        except VoiceDownloadError, AudioStoreError:
            await incoming.reply(FAILURE_TEXT)
            return None
        await incoming.reply(
            AUDIO_REFUSALS[key].format(
                max_mb=AUDIO_MAX_MB,
                max_minutes=AUDIO_MAX_MINUTES,
                formats=", ".join(AUDIO_FORMATS),
            )
        )
        return None

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
        audio_id = None
        if incoming.voice_url is not None:
            audio_id = await self._store_voice(incoming)
            if audio_id is None:
                return
        elif not incoming.text:
            await incoming.reply(ERRORS["errors.empty"])
            return
        hashed = user_hash(ports.settings, incoming.user_id)
        first = hashed is None or not await ports.records.list_for(CHANNEL_USER, hashed)
        started = await start(ports, incoming.text, incoming.user_id, audio_id)
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
