import asyncio
import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi.testclient import TestClient
from httpx2 import Response
from meritum_core.checks.contracts import CheckRecord
from meritum_core.checks.fakes import InMemoryCheckRecordRepository
from meritum_core.jobs.contracts import DELETE_SUBJECT
from meritum_core.jobs.fakes import InMemoryJobQueue
from pydantic import SecretStr
from tests.checks.cache_fakes import RESULT, FinishedWorker
from tests.conftest import MakeProbe
from tests.discord.fakes import FailedWorker, FakeReplies, make_client, repositories

from meritum_backend.channels import channel_user_hash
from meritum_backend.discord.constants import (
    CHANNEL_USER,
    CHECK,
    CHECK_MESSAGE,
    COMMANDS,
    DELETE_MY_DATA,
    DELETED,
    FAILURE_TEXT,
    POLL_SECONDS,
    TEXT_OPTION,
)

URL = "/api/v1/discord/interactions"
KEY = Ed25519PrivateKey.generate()
PUBLIC_HEX = KEY.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()


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
def replies() -> FakeReplies:
    return FakeReplies()


@pytest.fixture
def jobs() -> FinishedWorker:
    return FinishedWorker()


@pytest.fixture
def client(
    make_probe: MakeProbe, jobs: FinishedWorker, replies: FakeReplies
) -> TestClient:
    return make_client(PUBLIC_HEX, make_probe, jobs, replies)


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


def test_endpoint_is_off_without_public_key(make_probe: MakeProbe) -> None:
    assert make_client(None, make_probe).post(URL, json={"type": 1}).status_code == 404


def _slash(text: str) -> dict[str, Any]:
    return {
        "type": 2,
        "application_id": "app1",
        "token": "tok1",
        "member": {"user": {"id": "1234567890"}},
        "data": {"name": CHECK, "options": [{"name": TEXT_OPTION, "value": text}]},
    }


def test_slash_command_defers_then_sends_the_result(
    client: TestClient, jobs: FinishedWorker, replies: FakeReplies
) -> None:
    data = signed(client, _slash("Ziemia jest płaska")).json()
    assert data == {"type": 5, "data": {"flags": 64}}
    assert jobs.checks()
    kinds = [kind for kind, _, _ in replies.sent]
    assert kinds == ["edit"] + ["follow_up"] * len(RESULT.claims)
    first = replies.sent[0][2]
    assert first.startswith("Jestem botem Meritum, systemem AI.")
    assert f"/sprawdzenie/{jobs.checks()[0]}" in first
    assert {target for _, target, _ in replies.sent} == {"app1/tok1"}


def test_check_carries_the_user_hash_not_the_id(
    client: TestClient, jobs: FinishedWorker
) -> None:
    signed(client, _slash("Ziemia jest płaska"))
    payload = jobs.enqueued[0].payload.model_dump_json()
    expected = channel_user_hash("discord", "1234567890", SecretStr("salt"))
    assert "1234567890" not in payload
    assert expected in payload


def test_message_command_reads_the_target_message(
    client: TestClient, jobs: FinishedWorker
) -> None:
    payload = {
        "type": 2,
        "user": {"id": "777"},
        "data": {
            "name": CHECK_MESSAGE,
            "target_id": "42",
            "resolved": {
                "messages": {"42": {"content": "Szczepionki zawierają chipy"}}
            },
        },
    }
    assert signed(client, payload).json()["type"] == 5
    assert "Szczepionki zawierają chipy" in jobs.enqueued[0].payload.model_dump_json()


def test_too_short_text_is_explained(client: TestClient) -> None:
    payload = {
        "type": 2,
        "data": {"name": CHECK, "options": [{"name": TEXT_OPTION, "value": "x"}]},
    }
    assert "co najmniej 3 znaki" in signed(client, payload).json()["data"]["content"]


def test_commands_match_the_handler() -> None:
    names = {c["name"] for c in COMMANDS}
    assert names == {CHECK, CHECK_MESSAGE, DELETE_MY_DATA}


def test_usun_moje_dane_deletes_records_and_replies_ephemerally(
    make_probe: MakeProbe, replies: FakeReplies
) -> None:
    jobs = InMemoryJobQueue()
    client = make_client(PUBLIC_HEX, make_probe, jobs, replies)
    repos = repositories(client)
    hashed = channel_user_hash("discord", "1234567890", SecretStr("salt"))
    now = datetime.now(UTC)
    for i in range(2):
        record = CheckRecord(
            check_id=f"c{i}",
            session_id=hashed,
            channel="discord",
            channel_user_hash=hashed,
            received_at=now,
            answered_at=now,
            question_masked="Pytanie",
            status="done",
            verdicts=["false"],
            source_ids=[],
            corpus_version="test",
            models=[],
            retention_until=now + timedelta(days=30),
        )
        asyncio.run(repos.records.save(record))
    payload = {
        "type": 2,
        "application_id": "app1",
        "token": "tok1",
        "member": {"user": {"id": "1234567890"}},
        "data": {"name": DELETE_MY_DATA},
    }
    body = signed(client, payload).json()
    assert body == {"type": 4, "data": {"content": DELETED, "flags": 64}}
    assert asyncio.run(repos.records.list_for(CHANNEL_USER, hashed)) == []
    assert jobs.enqueued[0].spec == DELETE_SUBJECT


def test_signed_body_that_is_not_an_object_is_rejected(client: TestClient) -> None:
    body = b"[1]"
    timestamp = "1795265000"
    signature = KEY.sign(timestamp.encode() + body).hex()
    headers = {"X-Signature-Ed25519": signature, "X-Signature-Timestamp": timestamp}
    assert client.post(URL, content=body, headers=headers).status_code == 400


def test_failed_check_answers_at_once(
    make_probe: MakeProbe, replies: FakeReplies
) -> None:
    client = make_client(PUBLIC_HEX, make_probe, FailedWorker(), replies)
    started = time.monotonic()
    signed(client, _slash("Ziemia jest płaska"))
    assert time.monotonic() - started < POLL_SECONDS
    assert [kind for kind, _, _ in replies.sent] == ["edit"]
    assert FAILURE_TEXT in replies.sent[0][2]


def test_no_ai_notice_for_a_user_with_earlier_checks(
    make_probe: MakeProbe, replies: FakeReplies
) -> None:
    records = InMemoryCheckRecordRepository()
    hashed = channel_user_hash("discord", "1234567890", SecretStr("salt"))
    now = datetime.now(UTC)
    earlier = CheckRecord(
        check_id="old",
        session_id=hashed,
        channel="discord",
        channel_user_hash=hashed,
        received_at=now,
        answered_at=now,
        question_masked="Ziemia jest płaska",
        status="done",
        verdicts=["false"],
        source_ids=[],
        corpus_version="test",
        models=[],
        retention_until=now + timedelta(days=30),
    )
    asyncio.run(records.save(earlier))
    client = make_client(PUBLIC_HEX, make_probe, FinishedWorker(), replies, records)
    signed(client, _slash("Ziemia jest płaska"))
    assert "systemem AI" not in replies.sent[0][2]
