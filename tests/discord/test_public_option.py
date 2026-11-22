import json
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from tests.checks.cache_fakes import FinishedWorker
from tests.conftest import MakeProbe
from tests.discord.fakes import FakeReplies, make_client

KEY = Ed25519PrivateKey.generate()
PUBLIC_HEX = KEY.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
STAMP = "1795265000"


def _slash(*options: dict[str, Any]) -> bytes:
    data = {
        "name": "sprawdz",
        "options": [{"name": "tekst", "value": "Ziemia jest płaska"}, *options],
    }
    payload = {
        "type": 2,
        "application_id": "app1",
        "token": "tok1",
        "member": {"user": {"id": "1234567890"}},
        "data": data,
    }
    return json.dumps(payload).encode()


@pytest.mark.parametrize(
    ("options", "deferred", "public"),
    [
        ([{"name": "publiczne", "value": True}], {}, True),
        ([{"name": "publiczne", "value": False}], {"flags": 64}, False),
        ([], {"flags": 64}, False),
    ],
)
def test_result_is_ephemeral_unless_publiczne_is_true(
    make_probe: MakeProbe,
    options: list[dict[str, Any]],
    deferred: dict[str, int],
    public: bool,  # ruff: ignore[boolean-type-hint-positional-argument] -- a parameter of the test case
) -> None:
    replies = FakeReplies()
    client = make_client(PUBLIC_HEX, make_probe, FinishedWorker(), replies)
    body = _slash(*options)
    headers = {
        "X-Signature-Ed25519": KEY.sign(STAMP.encode() + body).hex(),
        "X-Signature-Timestamp": STAMP,
    }
    response = client.post(
        "/api/v1/discord/interactions", content=body, headers=headers
    )
    assert response.json() == {"type": 5, "data": deferred}
    assert replies.sent[0][2] is public
