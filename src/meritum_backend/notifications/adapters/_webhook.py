"""ExternalNotifier over a general webhook (JSON signed with a secret).

Features:
    US-POW-05, US-MOD-01, F-26
"""

import httpx2

from meritum_backend.notifications.adapters._signing import post_signed
from meritum_backend.notifications.constants import CASE_EVENT
from meritum_backend.notifications.models import CaseAlert


class WebhookNotifier:
    """POSTs ``{"event", "case_id", "reasons", "panel_url"}`` signed with HMAC.

    Args:
        url: the administrator's https address.
        secret: signs each body (``X-Meritum-Signature``).
        transport: a mock transport in tests; the network when None.

    Features:
        US-POW-05, US-MOD-01, F-26
    """

    def __init__(
        self,
        url: str,
        secret: str,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = url
        self._secret = secret
        self._transport = transport

    async def send(self, alert: CaseAlert) -> None:
        """Deliver the alert.

        Args:
            alert: the case to announce.
        """
        payload = {
            "event": CASE_EVENT,
            "case_id": alert.case_id,
            "reasons": alert.reasons,
            "panel_url": alert.panel_url,
        }
        await post_signed(self._url, payload, self._secret, self._transport)
