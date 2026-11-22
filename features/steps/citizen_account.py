"""Steps for the citizen account: history across devices, no account, deleting it.

The app runs on core's in-memory app repositories and InMemoryJobQueue; the
login is the fake provider, so no network and no database.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import cast

from behave import given, then, when
from behave.runner import Context
from fastapi.testclient import TestClient
from meritum_core.checks.contracts import CheckRecord, Notification
from meritum_core.jobs.fakes import InMemoryJobQueue
from meritum_core.observability import AppRepositories, build_app_repositories
from meritum_core.shared.database import DatabaseSettings

from meritum_backend.auth.adapters import FakeLogin
from meritum_backend.auth.api import get_login
from meritum_backend.auth.constants import FAKE_CODE
from meritum_backend.checks.constants import SESSION_HEADER
from meritum_backend.jobs.api import get_jobs
from meritum_backend.limits import CheckGate, LimitSettings, get_check_gate
from meritum_backend.limits.adapters import FixedPendingChecks, MemoryRateCounter
from meritum_backend.main import create_app
from meritum_backend.settings import Settings

USER = "google:1234567890"
T0 = datetime(2026, 11, 21, 12, tzinfo=UTC)
SETTINGS = Settings(database_url="postgresql://x:x@127.0.0.1:1/x", env="dev")


def _record(check_id: str, session_id: str) -> CheckRecord:
    return CheckRecord(
        check_id=check_id,
        session_id=session_id,
        user_id=USER,
        channel="web",
        received_at=T0,
        answered_at=T0,
        question_masked="Czy we Włoszech był strajk generalny?",
        status="done",
        verdicts=["confirmed"],
        source_ids=[],
        corpus_version="2026-11-21.1",
        models=[],
        retention_until=T0 + timedelta(days=30),
    )


def _client(context: Context) -> TestClient:
    """A new device: its own cookie jar on the same app and repositories.

    Args:
        context: the behave context with ``repos`` and ``jobs``.

    Returns:
        A client without a session.
    """
    app = create_app(SETTINGS)
    app.state.repositories = context.repos
    app.dependency_overrides[get_jobs] = lambda: context.jobs
    app.dependency_overrides[get_login] = lambda: FakeLogin(
        "1234567890", "o@example.com"
    )
    return TestClient(app, base_url="https://testserver", follow_redirects=False)


def _sign_in(client: TestClient) -> None:
    location = client.get("/api/v1/auth/login/google").headers["location"]
    state = location.split("state=")[1].split("&")[0]
    client.get(
        "/api/v1/auth/callback/google", params={"code": FAKE_CODE, "state": state}
    )
    client.headers["X-CSRF-Token"] = client.get("/api/v1/auth/me").json()["csrf_token"]


def _seed(context: Context, count: int) -> None:
    context.repos = build_app_repositories(DatabaseSettings())
    context.jobs = InMemoryJobQueue()
    for i in range(count):
        asyncio.run(context.repos.records.save(_record(f"c_{i}", f"phone-session-{i}")))
    note = Notification(
        id="n_1",
        kind="check_done",
        user_id=USER,
        check_id="c_0",
        link="/sprawdzenia/c_0",
        created_at=T0,
        retention_until=T0 + timedelta(days=30),
    )
    asyncio.run(context.repos.notifications.save(note))


@given("obywatel zalogowany kontem Google sprawdził 2 informacje na telefonie")
def checked_on_phone(context: Context) -> None:
    """Two checks saved with the account's user id from another session.

    Features:
        US-SPR-10, F-31
    """
    _seed(context, 2)


@when("loguje się tym samym kontem na komputerze")
def signs_in_on_computer(context: Context) -> None:
    """A second client (new cookie jar) signs in with the same account.

    Features:
        US-SPR-10, F-31
    """
    context.client = _client(context)
    _sign_in(context.client)


@then("GET /api/v1/me/checks zwraca te 2 sprawdzenia")
def history_is_listed(context: Context) -> None:
    """The history holds both checks.

    Features:
        US-SPR-10, F-31
    """
    items = context.client.get("/api/v1/me/checks").json()
    assert {i["check_id"] for i in items} == {"c_0", "c_1"}


@given("obywatel nie jest zalogowany")
def anonymous(context: Context) -> None:
    """A client without a session cookie.

    Features:
        US-SPR-10, F-31
    """
    _seed(context, 0)
    context.client = _client(context)


@when("wysyła sprawdzenie")
def sends_a_check(context: Context) -> None:
    """POST /api/v1/checks with a browser session header only.

    Features:
        US-SPR-10, F-31
    """
    app = context.client.app
    gate = CheckGate(MemoryRateCounter(), FixedPendingChecks(), LimitSettings())
    app.dependency_overrides[get_check_gate] = lambda: gate
    context.use_ready_probe(app)
    context.response = context.client.post(
        "/api/v1/checks",
        json={"text": "Czy we Włoszech był strajk generalny?", "channel": "web"},
        headers={SESSION_HEADER: "session-0123456789"},
    )


@then("dostaje wynik, a historia zostaje tylko w sessionStorage przeglądarki")
def no_account_history(context: Context) -> None:
    """The check is accepted and carries no user id, so no account history grows.

    Features:
        US-SPR-10, F-31
    """
    assert context.response.status_code == HTTPStatus.ACCEPTED
    assert context.jobs.enqueued[0].payload.user_id is None
    assert (
        context.client.get("/api/v1/me/checks").status_code == HTTPStatus.UNAUTHORIZED
    )


@given("zalogowany obywatel z 2 sprawdzeniami")
def signed_in_with_checks(context: Context) -> None:
    """A signed-in client and two saved checks.

    Features:
        US-SPR-10, F-31
    """
    _seed(context, 2)
    context.client = _client(context)
    _sign_in(context.client)


@when("wybiera „Usuń konto”")
def deletes_the_account(context: Context) -> None:
    """DELETE /api/v1/me with the CSRF token.

    Features:
        US-SPR-10, US-BEZ-05, F-31
    """
    context.response = context.client.delete("/api/v1/me")


@then("konto, historia sprawdzeń i powiadomienia konta są usunięte")
def account_is_gone(context: Context) -> None:
    """Records and notifications are gone and the session no longer works.

    Features:
        US-SPR-10, US-BEZ-05, F-31
    """
    repos = cast("AppRepositories", context.repos)
    assert context.response.status_code == HTTPStatus.ACCEPTED
    assert asyncio.run(repos.records.list_for("user_id", USER)) == []
    assert asyncio.run(repos.notifications.list_for("user_id", USER)) == []
    assert context.client.get("/api/v1/auth/me").status_code == HTTPStatus.UNAUTHORIZED
