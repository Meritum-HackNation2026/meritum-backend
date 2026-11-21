"""InteractionReplies over Discord's interaction webhooks (no bot token needed).

Features:
    US-WTY-06, F-03
"""

import logging
from typing import Any

import httpx2

from meritum_backend.discord.constants import API_URL, EPHEMERAL, HTTP_TIMEOUT_SECONDS

# httpx2 logs each request URL at INFO; here the URL holds the interaction token
logging.getLogger("httpx2").setLevel(logging.WARNING)


def _body(text: str) -> dict[str, Any]:
    # claim text comes from users: never let it ping @everyone or roles
    return {"content": text, "flags": EPHEMERAL, "allowed_mentions": {"parse": []}}


class WebhookReplies:
    """Edits the deferred answer and posts follow-ups through ``/webhooks``.

    Args:
        transport: a mock transport in tests; the network when None.

    Features:
        US-WTY-06, F-03
    """

    def __init__(self, transport: httpx2.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def _send(self, method: str, path: str, text: str) -> None:
        async with httpx2.AsyncClient(
            base_url=API_URL, transport=self._transport, timeout=HTTP_TIMEOUT_SECONDS
        ) as client:
            response = await client.request(method, path, json=_body(text))
        response.raise_for_status()

    async def edit_original(self, application_id: str, token: str, text: str) -> None:
        """PATCH ``/webhooks/{app}/{token}/messages/@original``.

        Args:
            application_id: the Discord app id.
            token: the interaction token.
            text: the message.
        """
        path = f"/webhooks/{application_id}/{token}/messages/@original"
        await self._send("PATCH", path, text)

    async def follow_up(self, application_id: str, token: str, text: str) -> None:
        """POST ``/webhooks/{app}/{token}`` (ephemeral, like the first answer).

        Args:
            application_id: the Discord app id.
            token: the interaction token.
            text: the message.
        """
        await self._send("POST", f"/webhooks/{application_id}/{token}", text)
