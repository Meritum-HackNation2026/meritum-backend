import asyncio
import base64
import json

import httpx2
import pytest

from meritum_backend.sms.adapters import SmsGateSender
from meritum_backend.sms.constants import GATEWAY_URL

PHONE = "+48600700800"


def test_send_posts_the_text_with_basic_auth() -> None:
    seen: list[httpx2.Request] = []

    def gateway(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(202, json={"id": "abc", "state": "Pending"})

    sender = SmsGateSender("user", "pass", transport=httpx2.MockTransport(gateway))

    message_id = asyncio.run(sender.send(PHONE, "Fałszywe"))

    [request] = seen
    assert message_id == "abc"
    assert str(request.url) == GATEWAY_URL
    credentials = base64.b64encode(b"user:pass").decode()
    assert request.headers["Authorization"] == f"Basic {credentials}"
    assert json.loads(request.content) == {
        "textMessage": {"text": "Fałszywe"},
        "phoneNumbers": [PHONE],
    }


def test_gateway_error_raises() -> None:
    refused = httpx2.MockTransport(lambda _: httpx2.Response(401))
    sender = SmsGateSender("user", "wrong", transport=refused)

    with pytest.raises(httpx2.HTTPStatusError):
        asyncio.run(sender.send(PHONE, "Fałszywe"))
