"""SmsSender over the sms-gate.app Cloud API (Basic Auth).

Features:
    US-WTY-07, F-32
"""

import httpx2
from pydantic import BaseModel, ValidationError

from meritum_backend.sms.constants import GATEWAY_URL, HTTP_TIMEOUT_SECONDS
from meritum_backend.sms.errors import SmsNotSentError


class _Queued(BaseModel):
    id: str


class SmsGateSender:
    """Sends SMS through the gateway phone with ``POST /3rdparty/v1/messages``.

    Each send opens its own short-lived client: replies are rare.

    Args:
        username: SMS_GATEWAY_USERNAME.
        password: SMS_GATEWAY_PASSWORD.
        transport: a mock transport in tests; the network when None.

    Features:
        US-WTY-07, F-32
    """

    def __init__(
        self,
        username: str,
        password: str,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self._auth = httpx2.BasicAuth(username, password)
        self._transport = transport

    async def send(self, phone_number: str, text: str) -> str:
        """Queue one SMS on the gateway.

        Args:
            phone_number: the recipient, E.164.
            text: the message.

        Returns:
            The gateway's message id (its state: GET .../messages/{id}).

        Raises:
            SmsNotSentError: an error status, no answer or an answer without ``id``.
        """
        body = {"textMessage": {"text": text}, "phoneNumbers": [phone_number]}
        try:
            async with httpx2.AsyncClient(
                auth=self._auth,
                transport=self._transport,
                timeout=HTTP_TIMEOUT_SECONDS,
            ) as client:
                response = await client.post(GATEWAY_URL, json=body)
            response.raise_for_status()
            return _Queued.model_validate_json(response.content).id
        except (httpx2.HTTPError, ValidationError) as exc:
            raise SmsNotSentError(type(exc).__name__) from exc
