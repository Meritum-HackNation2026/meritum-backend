"""ExternalNotifier over the Cloudflare e-mail Worker (infra/009).

Features:
    US-POW-05, US-MOD-01, F-26
"""

from collections.abc import Sequence

import httpx2

from meritum_backend.notifications.adapters._signing import post_signed
from meritum_backend.notifications.models import CaseAlert
from meritum_backend.notifications.ports import NotifyError


class EmailWorkerNotifier:
    """Asks the Worker to mail each moderator: ``{"to", "case", "panel_url"}``.

    The Worker sends only to addresses verified in Email Routing and builds the
    text itself, so nothing but the number and the link travels.

    Args:
        url: the Worker's address.
        secret: the shared signing secret.
        recipients: the moderators' addresses.
        transport: a mock transport in tests; the network when None.

    Features:
        US-POW-05, US-MOD-01, F-26
    """

    def __init__(
        self,
        url: str,
        secret: str,
        recipients: Sequence[str],
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = url
        self._secret = secret
        self._recipients = recipients
        self._transport = transport

    async def send(self, alert: CaseAlert) -> None:
        """Mail every moderator; one refusal is raised after the others were tried.

        Args:
            alert: the case to announce.

        Raises:
            NotifyError: the Worker refused at least one address.
        """
        failed = 0
        for address in self._recipients:
            body = {
                "to": address,
                "case": alert.case_number,
                "panel_url": alert.panel_url,
            }
            try:
                await post_signed(self._url, body, self._secret, self._transport)
            except NotifyError:
                failed += 1
        if failed:
            msg = f"{failed} of {len(self._recipients)} mails failed"
            raise NotifyError(msg)
