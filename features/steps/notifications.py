"""Steps for notifications.feature: the inbox on core's in-memory repositories.

A fake event source drives the stream: each tick first runs what a workflow
would do (save a notification), so no step sleeps.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from http import HTTPStatus

from behave import given, then, when
from behave.runner import Context
from fastapi.testclient import TestClient
from meritum_core.checks.contracts import Notification

from meritum_backend.auth import Account
from meritum_backend.checks.constants import SESSION_HEADER
from meritum_backend.limits import CheckGate, LimitSettings, get_check_gate
from meritum_backend.limits.adapters import FixedPendingChecks, MemoryRateCounter
from meritum_backend.main import create_app
from meritum_backend.notifications.api import get_ticks, signed_in_account
from meritum_backend.settings import Settings

SESSION = "0b6f3c1e-5d2a-4f7b-9c8e-1a2b3c4d5e6f"
OTHER_DEVICE = "9f8e7d6c-5b4a-4321-8fed-cba987654321"
ACCOUNT = Account(provider="google", subject="1234567890")
URL = "/api/v1/notifications"
T0 = datetime(2026, 11, 21, 12, tzinfo=UTC)


def _note(
    note_id: str, session_id: str | None, user_id: str | None = None
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


def _app(context: Context, account: Account | None = None) -> None:
    app = create_app(Settings(database_url="postgresql://x:x@127.0.0.1:1/x"))
    gate = CheckGate(MemoryRateCounter(), FixedPendingChecks(), LimitSettings())
    app.dependency_overrides[get_check_gate] = lambda: gate
    app.dependency_overrides[signed_in_account] = lambda: account
    context.app = app
    context.store = app.state.repositories.notifications
    context.client = TestClient(app)


def _save(context: Context, note: Notification) -> None:
    asyncio.run(context.store.save(note))


@given("sesja ma otwarty strumień GET /api/v1/notifications/stream")
def stream_open(context: Context) -> None:
    """Build the app; the stream opens in the next step.

    Args:
        context: the behave context.

    Features:
        US-POW-01, F-26
    """
    _app(context)


@when("workflow sprawdzania tej sesji się kończy")
def check_workflow_done(context: Context) -> None:
    """Read the stream while the workflow saves its check_done notification.

    Args:
        context: the behave context; gets ``events``.

    Features:
        US-POW-01, F-26
    """

    async def ticks() -> AsyncIterator[None]:
        await context.store.save(_note("n1", SESSION))
        yield

    context.app.dependency_overrides[get_ticks] = lambda: ticks
    with context.client.stream("GET", f"{URL}/stream?session={SESSION}") as response:
        lines = [x for x in response.iter_lines() if x.startswith("data:")]
    context.events = [json.loads(x.removeprefix("data:")) for x in lines]


@then(
    'sesja dostaje Notification z kind "check_done", check_id '
    "i linkiem do wyniku, bez treści pytania"
)
def got_check_done(context: Context) -> None:
    """One event with codes and ids only.

    Args:
        context: the behave context.

    Features:
        US-POW-01, F-26
    """
    (event,) = context.events
    assert event["kind"] == "check_done"
    assert event["check_id"] == "c_n1"
    assert event["link"] == "/sprawdzenia/c_n1"
    assert set(event) <= set(Notification.model_fields)
    assert not {"question", "question_masked", "text"} & set(event)


@given("sesja dostała 2 powiadomienia i nie zareagowała")
def two_unread(context: Context) -> None:
    """Save two notifications for the session.

    Args:
        context: the behave context.

    Features:
        US-POW-04, F-26
    """
    _app(context)
    _save(context, _note("n1", SESSION))
    _save(context, _note("n2", SESSION))


@when("klient otwiera GET /api/v1/notifications")
def open_inbox(context: Context) -> None:
    """List the session's inbox.

    Args:
        context: the behave context; gets ``inbox``.

    Features:
        US-POW-04, F-26
    """
    context.inbox = context.client.get(URL, headers={SESSION_HEADER: SESSION}).json()


@then(
    'lista ma 2 powiadomienia ze stanem "unread", '
    'a POST /api/v1/notifications/{{id}}/read zmienia stan na "read"'
)
def inbox_and_read(context: Context) -> None:
    """Both unread; marking one read shows in the next listing.

    Args:
        context: the behave context.

    Features:
        US-POW-04, F-26
    """
    assert [n["status"] for n in context.inbox] == ["unread", "unread"]
    mine = {SESSION_HEADER: SESSION}
    response = context.client.post(f"{URL}/n1/read", headers=mine)
    assert response.status_code == HTTPStatus.NO_CONTENT
    status = {
        n["id"]: n["status"] for n in context.client.get(URL, headers=mine).json()
    }
    assert status == {"n1": "read", "n2": "unread"}


@given("powiadomienie ma user_id zalogowanego obywatela")
def account_note(context: Context) -> None:
    """Save a notification addressed to the signed-in account.

    Args:
        context: the behave context.

    Features:
        US-POW-04, F-26
    """
    _app(context, ACCOUNT)
    _save(context, _note("u1", None, f"{ACCOUNT.provider}:{ACCOUNT.subject}"))


@when("obywatel otwiera skrzynkę na innym urządzeniu")
def other_device(context: Context) -> None:
    """List the inbox from another browser session of the same account.

    Args:
        context: the behave context; gets ``inbox``.

    Features:
        US-POW-04, F-26
    """
    context.inbox = context.client.get(
        URL, headers={SESSION_HEADER: OTHER_DEVICE}
    ).json()


@then("widzi to powiadomienie")
def sees_it(context: Context) -> None:
    """The account's notification is listed.

    Args:
        context: the behave context.

    Features:
        US-POW-04, F-26
    """
    assert [n["id"] for n in context.inbox] == ["u1"]
