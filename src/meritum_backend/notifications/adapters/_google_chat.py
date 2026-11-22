"""ExternalNotifier over a Google Chat incoming webhook.

Features:
    US-POW-05, US-MOD-01, F-26
"""

import json

import httpx2

from meritum_backend.notifications.adapters._signing import post
from meritum_backend.notifications.constants import CHAT_TEXT
from meritum_backend.notifications.models import CaseAlert


class GoogleChatNotifier:
    """POSTs ``{"text"}``; the space's webhook address carries its own key.

    Args:
        url: the space's incoming-webhook address.
        transport: a mock transport in tests; the network when None.

    Features:
        US-POW-05, US-MOD-01, F-26
    """

    def __init__(
        self, url: str, transport: httpx2.AsyncBaseTransport | None = None
    ) -> None:
        self._url = url
        self._transport = transport

    async def send(self, alert: CaseAlert) -> None:
        """Deliver the alert as a chat message.

        Args:
            alert: the case to announce.
        """
        text = CHAT_TEXT.format(
            case=alert.case_id,
            reasons=", ".join(alert.reasons) or "-",
            url=alert.panel_url,
        )
        body = json.dumps({"text": text}).encode()
        headers = {"Content-Type": "application/json; charset=UTF-8"}
        await post(self._url, body, headers, self._transport)
