"""Steps for „Usuń moją historię” and the account's other notifications (#142).

The app runs on core's in-memory app repositories and InMemoryJobQueue; the
login is the fake provider, so no network and no database.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from http import HTTPStatus

from behave import given, then, when
from behave.runner import Context
from fastapi.testclient import TestClient
from meritum_core.checks.contracts import CheckRecord, Notification
from meritum_core.jobs.fakes import InMemoryJobQueue
from meritum_core.observability import build_app_repositories
from meritum_core.shared.database import DatabaseSettings

from meritum_backend.auth.adapters import FakeLogin
from meritum_backend.auth.api import get_login
from meritum_backend.auth.constants import FAKE_CODE
from meritum_backend.jobs.api import get_jobs
from meritum_backend.main import create_app
from meritum_backend.settings import Settings

USER = "google:1234567890"
T0 = datetime(2026, 11, 22, 12, tzinfo=UTC)
SETTINGS = Settings(database_url="postgresql://x:x@127.0.0.1:1/x", env="dev")
LATER = {"created_at": T0, "retention_until": T0 + timedelta(days=30)}


def _note(note_id: str, kind: str, **fields: object) -> Notification:
    base = {"id": note_id, "kind": kind, "user_id": USER, "link": "/"}
    return Notification.model_validate(base | LATER | fields)


async def _seed_account(context: Context) -> None:
    repos = context.repos
    await repos.records.save(
        CheckRecord(
            check_id="c_1",
            session_id="phone-session-1",
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
    )
    await repos.notifications.save(_note("n_done", "check_done", check_id="c_1"))
    await repos.notifications.save(_note("n_case", "case_assigned", case_id="#S-1"))
    await repos.notifications.save(
        _note("n_sys", "system", message_code="maintenance_planned")
    )


def _signed_in(context: Context) -> TestClient:
    app = create_app(SETTINGS)
    app.state.repositories = context.repos
    app.dependency_overrides[get_jobs] = lambda: context.jobs
    app.dependency_overrides[get_login] = lambda: FakeLogin(
        "1234567890", "o@example.com"
    )
    client = TestClient(app, base_url="https://testserver", follow_redirects=False)
    location = client.get("/api/v1/auth/login/google").headers["location"]
    state = location.split("state=")[1].split("&")[0]
    client.get(
        "/api/v1/auth/callback/google", params={"code": FAKE_CODE, "state": state}
    )
    client.headers["X-CSRF-Token"] = client.get("/api/v1/auth/me").json()["csrf_token"]
    return client


@given(
    "zalogowany użytkownik ma sprawdzenie z powiadomieniem check_done, powiadomienie "
    "case_assigned o sprawie #S-1 i powiadomienie system"
)
def account_with_inbox(context: Context) -> None:
    """A signed-in account with one check and three notifications.

    Features:
        US-SPR-10, US-BEZ-05, US-POW-04, F-31
    """
    context.repos = build_app_repositories(DatabaseSettings())
    context.jobs = InMemoryJobQueue()
    asyncio.run(_seed_account(context))
    context.client = _signed_in(context)


@when("wysyła DELETE /api/v1/me/checks")
def deletes_history(context: Context) -> None:
    """„Usuń moją historię” with the CSRF token.

    Features:
        US-SPR-10, US-BEZ-05, F-31
    """
    context.response = context.client.delete("/api/v1/me/checks")
    assert context.response.status_code == HTTPStatus.ACCEPTED


@then("GET /api/v1/notifications zwraca tylko powiadomienia case_assigned i system")
def only_case_and_system_left(context: Context) -> None:
    """The check notification is gone; the case and system ones stay.

    Features:
        US-BEZ-05, US-POW-04, F-26
    """
    notes = context.client.get("/api/v1/notifications").json()
    assert sorted(n["kind"] for n in notes) == ["case_assigned", "system"]


@then("GET /api/v1/me/checks zwraca pustą listę")
def history_is_empty(context: Context) -> None:
    """The account's check records are gone.

    Features:
        US-SPR-10, US-BEZ-05, F-31
    """
    assert context.client.get("/api/v1/me/checks").json() == []
