"""POST /api/v1/checks from Discord, SMS and MCP: the user id becomes its hash."""

import logging
from typing import Protocol

import pytest
from httpx2 import Response
from meritum_core.checks.contracts import Channel
from meritum_core.jobs.contracts import CheckInput
from meritum_core.jobs.fakes import InMemoryJobQueue
from pydantic import SecretStr

from meritum_backend.channels import channel_user_hash
from meritum_backend.checks.constants import SESSION_HEADER
from meritum_backend.settings import Settings

from .conftest import OFFLINE_DB, MakeClient


class Post(Protocol):
    def __call__(
        self, body: dict[str, str], salt: SecretStr | None = ...
    ) -> Response: ...


SALT = SecretStr("test-salt")
USER = "1234567890"


def _body(channel: str = "discord", user: str | None = USER) -> dict[str, str]:
    body = {"channel": channel, "text": "Czy to prawda?"}
    return body if user is None else {**body, "channel_user_id": user}


@pytest.fixture
def post(make_client: MakeClient, jobs: InMemoryJobQueue) -> Post:
    def send(body: dict[str, str], salt: SecretStr | None = SALT) -> Response:
        settings = Settings(database_url=OFFLINE_DB, channel_hash_salt=salt)
        client = make_client(jobs, settings)
        headers = {SESSION_HEADER: "session-0123456789"}
        return client.post("/api/v1/checks", json=body, headers=headers)

    return send


@pytest.mark.parametrize("channel", ["discord", "sms", "mcp"])
def test_channel_user_id_reaches_the_workflow_only_as_its_hash(
    post: Post,
    jobs: InMemoryJobQueue,
    channel: Channel,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG):
        response = post(_body(channel))
    assert response.status_code == 202
    [job] = jobs.enqueued
    assert isinstance(job.payload, CheckInput)
    hashed = channel_user_hash(channel, USER, SALT)
    assert job.payload.channel_user_hash == hashed == job.payload.session_id
    assert USER not in job.payload.model_dump_json()
    assert USER not in caplog.text


def test_two_requests_of_one_user_share_the_hash(
    post: Post, jobs: InMemoryJobQueue
) -> None:
    post(_body())
    post(_body())
    first, second = jobs.enqueued
    assert isinstance(first.payload, CheckInput)
    assert isinstance(second.payload, CheckInput)
    assert first.payload.channel_user_hash == second.payload.channel_user_hash


def test_sessionless_check_without_user_id_is_400(
    post: Post, jobs: InMemoryJobQueue
) -> None:
    response = post(_body("sms", None))
    assert response.status_code == 400
    assert "channel_user_id" in response.json()["detail"]
    assert jobs.enqueued == []


@pytest.mark.parametrize("salt", [None, SecretStr("")])
def test_without_a_salt_nothing_starts(
    post: Post, jobs: InMemoryJobQueue, salt: SecretStr | None
) -> None:
    response = post(_body(), salt)
    assert response.status_code == 503
    assert jobs.enqueued == []


@pytest.mark.parametrize("channel", ["web", "extension"])
def test_browser_channels_with_a_user_id_are_422(
    post: Post, jobs: InMemoryJobQueue, channel: str
) -> None:
    response = post(_body(channel))
    assert response.status_code == 422
    assert USER not in response.text
    assert jobs.enqueued == []
