"""Port of the Discord channel: answering an interaction after it was deferred.

Features:
    US-WTY-06, F-03
"""

from typing import Protocol


class InteractionReplies(Protocol):
    """Sends the messages of a deferred interaction (port).

    Features:
        US-WTY-06, F-03
    """

    async def edit_original(self, application_id: str, token: str, text: str) -> None:
        """Replace the deferred "thinking…" answer with ``text``.

        Args:
            application_id: the Discord app id from the interaction.
            token: the interaction token (valid 15 minutes).
            text: at most MESSAGE_MAX_CHARS characters.
        """
        ...

    async def follow_up(self, application_id: str, token: str, text: str) -> None:
        """Send one more message to the same interaction.

        Args:
            application_id: the Discord app id from the interaction.
            token: the interaction token (valid 15 minutes).
            text: at most MESSAGE_MAX_CHARS characters.
        """
        ...
