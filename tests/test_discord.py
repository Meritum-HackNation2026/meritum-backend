import json
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi.testclient import TestClient
from httpx2 import Response

from meritum_backend.discord.constants import (
    CHECK,
    CHECK_MESSAGE,
    COMMANDS,
    TEXT_OPTION,
)
from meritum_backend.main import create_app
from meritum_backend.settings import Settings, get_settings

URL = "/api/v1/discord/interactions"
KEY = Ed25519PrivateKey.generate()
PUBLIC_HEX = KEY.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()


def make_client(public_key: str | None) -> TestClient:
    settings = Settings(discord_public_key=public_key)
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def signed(
    client: TestClient, payload: dict[str, Any], *, key: Ed25519PrivateKey = KEY
) -> Response:
    body = json.dumps(payload).encode()
    timestamp = "1795265000"
    signature = key.sign(timestamp.encode() + body).hex()
    return client.post(
        URL,
        content=body,
        headers={
            "X-Signature-Ed25519": signature,
            "X-Signature-Timestamp": timestamp,
            "Content-Type": "application/json",
        },
    )


@pytest.fixture
def client() -> TestClient:
    return make_client(PUBLIC_HEX)


def test_ping_gets_pong(client: TestClient) -> None:
    response = signed(client, {"type": 1})
    assert response.status_code == 200
    assert response.json() == {"type": 1}


def test_bad_or_missing_signature_is_rejected(client: TestClient) -> None:
    assert (
        signed(client, {"type": 1}, key=Ed25519PrivateKey.generate()).status_code == 401
    )
    assert client.post(URL, json={"type": 1}).status_code == 401
    bad_hex = client.post(
        URL,
        json={"type": 1},
        headers={"X-Signature-Ed25519": "zz", "X-Signature-Timestamp": "1"},
    )
    assert bad_hex.status_code == 401


def test_endpoint_is_off_without_public_key() -> None:
    assert make_client(None).post(URL, json={"type": 1}).status_code == 404


def test_slash_command_gets_ephemeral_answer(client: TestClient) -> None:
    payload = {
        "type": 2,
        "data": {
            "name": CHECK,
            "options": [{"name": TEXT_OPTION, "value": "Ziemia jest płaska"}],
        },
    }
    data = signed(client, payload).json()
    assert data["type"] == 4
    assert data["data"]["flags"] == 64
    assert "Przyjąłem" in data["data"]["content"]


def test_message_command_reads_the_target_message(client: TestClient) -> None:
    payload = {
        "type": 2,
        "data": {
            "name": CHECK_MESSAGE,
            "target_id": "42",
            "resolved": {
                "messages": {"42": {"content": "Szczepionki zawierają chipy"}}
            },
        },
    }
    assert "Przyjąłem" in signed(client, payload).json()["data"]["content"]


def test_too_short_text_is_explained(client: TestClient) -> None:
    payload = {
        "type": 2,
        "data": {"name": CHECK, "options": [{"name": TEXT_OPTION, "value": "x"}]},
    }
    assert "co najmniej 3 znaki" in signed(client, payload).json()["data"]["content"]


def test_commands_match_the_handler() -> None:
    names = {c["name"] for c in COMMANDS}
    assert names == {CHECK, CHECK_MESSAGE}
