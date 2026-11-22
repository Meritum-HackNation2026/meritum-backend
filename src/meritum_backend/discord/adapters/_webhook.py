"""InteractionReplies over Discord's interaction webhooks (no bot token needed).

Features:
    US-WTY-06, F-03
"""

import logging
from typing import Any

import httpx2

from meritum_backend.discord.constants import API_URL, EPHEMERAL, HTTP_TIMEOUT_SECONDS
from meritum_backend.discord.messages import Message

# httpx2 logs each request URL at INFO; here the URL holds the interaction token
logging.getLogger("httpx2").setLevel(logging.WARNING)


def _body(message: Message, *, public: bool) -> dict[str, Any]:
    # claim text comes from users: never let it ping @everyone or roles
    flags = {} if public else {"flags": EPHEMERAL}
    return {**message, **flags, "allowed_mentions": {"parse": []}}


class WebhookReplies:
    """Edits the deferred answer through ``/webhooks``.

    Args:
        transport: a mock transport in tests; the network when None.

    Features:
        US-WTY-06, F-03
    """

    def __init__(self, transport: httpx2.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def edit_original(
        self, application_id: str, token: str, message: Message, *, public: bool
    ) -> None:
        """PATCH ``/webhooks/{app}/{token}/messages/@original``.

        Args:
            application_id: the Discord app id.
            token: the interaction token.
            message: the embed, components and content.
            public: visible to the channel; else ephemeral (set when deferred).
        """
        path = f"/webhooks/{application_id}/{token}/messages/@original"
        async with httpx2.AsyncClient(
            base_url=API_URL, transport=self._transport, timeout=HTTP_TIMEOUT_SECONDS
        ) as client:
            response = await client.patch(path, json=_body(message, public=public))
        response.raise_for_status()
