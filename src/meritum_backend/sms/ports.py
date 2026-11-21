"""Port of the SMS channel: sending a text through the gateway.

Features:
    US-WTY-07, F-32
"""

from typing import Protocol


class SmsSender(Protocol):
    """Sends one SMS (port).

    Features:
        US-WTY-07, F-32
    """

    async def send(self, phone_number: str, text: str) -> str:
        """Queue ``text`` for ``phone_number`` on the gateway.

        Args:
            phone_number: the recipient, E.164.
            text: the message; the caller keeps it to one SMS.

        Returns:
            The gateway's message id.

        Raises:
            httpx2.HTTPError: the gateway refused or did not answer.
        """
        ...
