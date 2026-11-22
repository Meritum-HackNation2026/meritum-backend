"""Fixtures of the SMS tests: the app with a signing key, a fake gateway and fakes."""

import hashlib
import hmac
import json
import time
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from meritum_core.jobs.fakes import InMemoryJobQueue
from meritum_core.observability import AppRepositories, build_app_repositories
from meritum_core.shared.database import DatabaseSettings
from pydantic import SecretStr

from meritum_backend.jobs.api import get_jobs
from meritum_backend.limits import CheckGate, LimitSettings, get_check_gate
from meritum_backend.limits.adapters import FixedPendingChecks, MemoryRateCounter
from meritum_backend.main import create_app
from meritum_backend.privacy import get_eraser
from meritum_backend.settings import Settings, get_settings
from meritum_backend.sms.api import get_records, get_sms

URL = "/api/v1/sms/webhook"
KEY = "test-signing-key"
GATEWAY_NUMBER = "+48 500 000 000"
SENDER = "+48600700800"

type Post = Callable[..., Response]


class FakeSms:
    """SmsSender that records what it would send."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send(self, phone_number: str, text: str) -> str:
        self.sent.append((phone_number, text))
        return f"m{len(self.sent)}"


def event(text: str, *, event_id: str = "e1", sender: str = SENDER) -> dict[str, Any]:
    return {
        "deviceId": "dev1",
        "event": "sms:received",
        "id": event_id,
        "webhookId": "meritum-dev-sms-received",
        "payload": {
            "message": text,
            "sender": sender,
            "recipient": None,
            "phoneNumber": sender,
            "receivedAt": "2026-11-21T21:42:27.000+01:00",
            "messageId": "m1",
            "simNumber": 1,
        },
    }


def sign(body: bytes, timestamp: str, key: str = KEY) -> str:
    return hmac.new(key.encode(), body + timestamp.encode(), hashlib.sha256).hexdigest()


@pytest.fixture
def jobs() -> InMemoryJobQueue:
    return InMemoryJobQueue()


@pytest.fixture
def sms() -> FakeSms:
    return FakeSms()


@pytest.fixture
def repositories() -> AppRepositories:
    return build_app_repositories(DatabaseSettings())


@pytest.fixture
def gate() -> CheckGate:
    return CheckGate(MemoryRateCounter(), FixedPendingChecks(), LimitSettings())


@pytest.fixture
def client(
    gate: CheckGate,
    jobs: InMemoryJobQueue,
    sms: FakeSms,
    repositories: AppRepositories,
    quick_polls: None,
) -> TestClient:
    del quick_polls
    settings = Settings(
        sms_gateway_webhook_signing_key=SecretStr(KEY),
        sms_gateway_number=GATEWAY_NUMBER,
        channel_hash_salt=SecretStr("test-salt"),
    )
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_jobs] = lambda: jobs
    app.dependency_overrides[get_check_gate] = lambda: gate
    app.dependency_overrides[get_sms] = lambda: sms
    app.dependency_overrides[get_records] = lambda: repositories.records
    app.dependency_overrides[get_eraser] = lambda: repositories.eraser
    return TestClient(app)


@pytest.fixture
def post(client: TestClient) -> Post:
    def send(
        payload: dict[str, Any],
        *,
        timestamp: str | None = None,
        key: str = KEY,
    ) -> Response:
        body = json.dumps(payload).encode()
        stamp = timestamp or str(int(time.time()))
        headers = {
            "X-Signature": sign(body, stamp, key),
            "X-Timestamp": stamp,
            "Content-Type": "application/json",
        }
        return client.post(URL, content=body, headers=headers)

    return send


@pytest.fixture
def quick_polls(monkeypatch: pytest.MonkeyPatch) -> None:
    # TestClient runs background tasks before it returns
    monkeypatch.setattr("meritum_backend.sms.delivery.POLL_SECONDS", 0)
    monkeypatch.setattr("meritum_backend.sms.delivery.POLL_ATTEMPTS", 2)
