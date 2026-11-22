"""Steps for the moderator alert scenarios of features/notifications.feature.

The administrator sets a webhook through the staff API; the target is a mock
transport, so nothing leaves the process (no network in CI).
"""

import asyncio
import json
from datetime import UTC, datetime

import httpx2
from behave import given, then, when
from behave.runner import Context
from features.constants import STAFF_ADMIN, STAFF_MODERATOR, STAFF_TEST_DBOS_URL
from features.staff_support import csrf, grant_moderator, signed_in
from meritum_core.checks.contracts import CaseClaim, ModeratorCase

from meritum_backend.main import create_app
from meritum_backend.notifications import CaseAnnouncer, staff_inbox_id
from meritum_backend.notifications.adapters import WebhookNotifier
from meritum_backend.notifications.constants import SEND_ATTEMPTS
from meritum_backend.settings import Settings

TARGET = "https://hooks.example/meritum"
NOW = datetime(2026, 11, 22, tzinfo=UTC)
CASE = ModeratorCase(
    id="#S-12",
    state="open",
    reasons=["insufficient_evidence", "user_dispute"],
    summary="Twierdzenie bez dowodów",
    claims=[CaseClaim(claim="Lokal wyborczy jest zamknięty.", check_ids=["c_1"])],
    first_seen=NOW,
    last_seen=NOW,
)


async def _no_pause(seconds: float) -> None:
    await asyncio.sleep(0 * seconds)


@given("administrator ustawił webhook dla moderatorów")
def _(context: Context) -> None:
    app = create_app(
        Settings(database_url=STAFF_TEST_DBOS_URL, admin_emails=STAFF_ADMIN)
    )
    admin = signed_in(app, STAFF_ADMIN)
    grant_moderator(admin)
    body = {"kind": "webhook", "url": TARGET, "secret": "shared-key"}
    admin.put("/api/v1/staff/notifications", json=body, headers=csrf(admin))
    context.app, context.status, context.requests = app, 200, []


@given("webhook odpowiada kodem {code:d}")
def _(context: Context, code: int) -> None:
    context.status = code


@when("powstaje nowa sprawa moderatora")
def _(context: Context) -> None:
    app = context.app

    def target(request: httpx2.Request) -> httpx2.Response:
        context.requests.append(request)
        return httpx2.Response(context.status)

    transport = httpx2.MockTransport(target)
    app.state.announcer = CaseAnnouncer(
        app.state.repositories.cases,
        app.state.repositories.staff,
        app.state.admin_emails,
        app.state.repositories.notifications,
        app.state.notifier_configs,
        lambda config, _: WebhookNotifier(config.url or "", "shared-key", transport),
        "https://meritum.example",
        _no_pause,
    )
    asyncio.run(app.state.repositories.cases.save(CASE))
    asyncio.run(app.state.announcer.announce(CASE.id))


@then(
    "webhook dostaje zdarzenie z numerem sprawy, powodami i linkiem do panelu, "
    "bez identyfikatorów kanałów"
)
def _(context: Context) -> None:
    [request] = context.requests
    assert request.headers["X-Meritum-Signature"].startswith("sha256=")
    assert json.loads(request.content) == {
        "event": "case_assigned",
        "case_id": "#S-12",
        "reasons": ["insufficient_evidence", "user_dispute"],
        "panel_url": "https://meritum.example/moderator/cases/S-12",
    }


@then('moderatorzy dostają Notification "case_assigned" z case_id w panelu')
def _(context: Context) -> None:
    store = context.app.state.repositories.notifications
    [note] = asyncio.run(store.list_for("user_id", staff_inbox_id(STAFF_MODERATOR)))
    assert (note.kind, note.case_id) == ("case_assigned", "#S-12")
    assert note.link == "/moderator/cases/S-12"


@then('sprawa i Notification "case_assigned" istnieją mimo awarii')
def _(context: Context) -> None:
    assert asyncio.run(context.app.state.repositories.cases.get(CASE.id)) == CASE
    store = context.app.state.repositories.notifications
    notes = asyncio.run(store.list_for("user_id", staff_inbox_id(STAFF_MODERATOR)))
    assert [n.kind for n in notes] == ["case_assigned"]


@then("system ponawia wysyłkę {tries:d} razy i zapisuje błąd")
def _(context: Context, tries: int) -> None:
    assert tries == SEND_ATTEMPTS == len(context.requests)
