"""Fixtures of the notifications tests: the app on in-memory repositories.

The event source is faked: each stream tick runs the next scripted action, e.g.
a workflow saving a notification, instead of sleeping.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from meritum_core.checks.contracts import Notification
from meritum_core.notifications import NotificationRepository

from meritum_backend.auth import Account
from meritum_backend.limits import CheckGate, LimitSettings, get_check_gate
from meritum_backend.limits.adapters import FixedPendingChecks, MemoryRateCounter
from meritum_backend.main import create_app
from meritum_backend.notifications.api import get_ticks, signed_in_account

T0 = datetime(2026, 11, 21, 12, tzinfo=UTC)
SESSION = "0b6f3c1e-5d2a-4f7b-9c8e-1a2b3c4d5e6f"
OTHER = "9f8e7d6c-5b4a-4321-8fed-cba987654321"
ACCOUNT = Account(provider="google", subject="1234567890")
USER = "google:1234567890"

type Action = Callable[[], Awaitable[None]]
type Save = Callable[[Notification], None]


def note(
    note_id: str, session_id: str | None = SESSION, user_id: str | None = None
) -> Notification:
    return Notification(
        id=note_id,
        kind="check_done",
        session_id=session_id,
        user_id=user_id,
        check_id=f"c_{note_id}",
        link=f"/sprawdzenia/c_{note_id}",
        created_at=T0,
        retention_until=T0 + timedelta(days=30),
    )


@pytest.fixture
def app() -> FastAPI:
    built = create_app()
    built.dependency_overrides[signed_in_account] = lambda: None
    gate = CheckGate(MemoryRateCounter(), FixedPendingChecks(), LimitSettings())
    built.dependency_overrides[get_check_gate] = lambda: gate
    return built


@pytest.fixture
def repo(app: FastAPI) -> NotificationRepository:
    return app.state.repositories.notifications


@pytest.fixture
def save(repo: NotificationRepository) -> Save:
    return lambda n: asyncio.run(repo.save(n))


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def script(app: FastAPI, actions: list[Action]) -> None:
    """Make the stream tick once per action, running it first."""

    async def ticks() -> AsyncIterator[None]:
        for action in actions:
            await action()
            yield

    app.dependency_overrides[get_ticks] = lambda: ticks


def sign_in(app: FastAPI) -> None:
    app.dependency_overrides[signed_in_account] = lambda: ACCOUNT
