"""Port of the Discord channel: answering an interaction after it was deferred.

Features:
    US-WTY-06, F-03
"""

from typing import Protocol

from meritum_backend.discord.messages import Message


class InteractionReplies(Protocol):
    """Answers a deferred interaction (port).

    Features:
        US-WTY-06, F-03
    """

    async def edit_original(
        self, application_id: str, token: str, message: Message, *, public: bool
    ) -> None:
        """Replace the deferred "thinking…" answer with ``message``.

        Args:
            application_id: the Discord app id from the interaction.
            token: the interaction token (valid 15 minutes).
            message: the embed, components and content to show.
            public: the interaction was deferred for the whole channel; when False
                the answer is ephemeral.
        """
        ...


class VoiceDownloader(Protocol):
    """Fetches a voice message's bytes from Discord's CDN (port).

    Features:
        US-SPR-11, US-WTY-06, F-08, F-03
    """

    async def download(self, url: str) -> bytes:
        """Return the attachment's bytes.

        Args:
            url: the signed attachment URL; it expires quickly.

        Returns:
            The file's bytes.

        Raises:
            VoiceTooLargeError: The file is over MAX_AUDIO_BYTES.
            VoiceDownloadError: The URL is not Discord's CDN or the fetch failed.
        """
        ...
