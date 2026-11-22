"""Steps for closing a case without an answer: staff sign-in and in-memory stores."""

import asyncio
from datetime import UTC, datetime
from http import HTTPStatus

from behave import given, then, when
from behave.runner import Context
from features.constants import STAFF_ADMIN, STAFF_MODERATOR
from features.staff_support import csrf, grant_moderator, signed_in
from meritum_core.checks.contracts import CaseClaim, CheckRecord, ModeratorCase

from meritum_backend.main import create_app
from meritum_backend.settings import Settings

NOW = datetime(2026, 11, 22, tzinfo=UTC)
CASE_ID = "#S-12"
URL = "/api/v1/moderation/cases/%23S-12/close"
SESSIONS = ("session-aaa", "session-bbb")
ANALYST = "analyst@example.com"


def _record(check_id: str, session: str) -> CheckRecord:
    return CheckRecord(
        check_id=check_id,
        session_id=session,
        channel="web",
        received_at=NOW,
        answered_at=NOW,
        question_masked="paszport",
        status="done",
        verdicts=[],
        source_ids=[],
        corpus_version="test",
        models=[],
        retention_until=NOW,
    )


def _case_app(context: Context, state: str) -> None:
    app = create_app(
        Settings(
            database_url="postgresql://x:x@127.0.0.1:1/x", admin_emails=STAFF_ADMIN
        )
    )
    case = ModeratorCase(
        id=CASE_ID,
        state=state,  # ty: ignore[invalid-argument-type]  # a Literal from the step text
        reasons=["insufficient_evidence"],
        summary="Paszport",
        claims=[CaseClaim(claim="Paszport zdrożeje.", check_ids=["c1", "c2"])],
        distinct_askers=2,
        first_seen=NOW,
        last_seen=NOW,
    )
    asyncio.run(app.state.cases.save(case))
    records = app.state.repositories.records
    for check_id, session in zip(("c1", "c2"), SESSIONS, strict=True):
        asyncio.run(records.save(_record(check_id, session)))
    admin = signed_in(app, STAFF_ADMIN)  # no lifespan: the scenario needs no worker
    grant_moderator(admin)
    body = {"email": ANALYST, "role": "analyst"}
    assert admin.post("/api/v1/staff", json=body, headers=csrf(admin)).is_success
    context.app = app


@given('otwarta sprawa "#S-12" z dwoma pytającymi')
def open_case(context: Context) -> None:
    """An open case asked by two sessions.

    Args:
        context: the behave context; gets ``app``.
    """
    _case_app(context, "open")


@given('sprawa "#S-12" ma stan "{state}"')
def case_in_state(context: Context, state: str) -> None:
    """A case already in ``state``.

    Args:
        context: the behave context; gets ``app``.
        state: the case state.
    """
    _case_app(context, state)


def _close(context: Context, email: str, reason: str) -> None:
    client = signed_in(context.app, email)
    context.response = client.post(URL, json={"reason": reason}, headers=csrf(client))
    context.closer = client


@when('moderator zamyka sprawę z powodem "{reason}"')
def moderator_closes(context: Context, reason: str) -> None:
    """The moderator closes the case.

    Args:
        context: the behave context; gets ``response`` and ``closer``.
        reason: why the case is closed.
    """
    _close(context, STAFF_MODERATOR, reason)


@when('analityk zamyka sprawę z powodem "{reason}"')
def analyst_closes(context: Context, reason: str) -> None:
    """An analyst tries to close the case.

    Args:
        context: the behave context; gets ``response`` and ``closer``.
        reason: why the case is closed.
    """
    _close(context, ANALYST, reason)


def _state(context: Context) -> str:
    case = asyncio.run(context.app.state.cases.get(CASE_ID))
    assert case is not None
    return str(case.state)


@then('sprawa ma stan "closed"')
def case_closed(context: Context) -> None:
    """The close succeeded and the case is closed.

    Args:
        context: the behave context.
    """
    assert context.response.status_code == HTTPStatus.OK, context.response.text
    assert _state(context) == "closed"


@then("żaden pytający nie dostaje powiadomienia")
def nobody_notified(context: Context) -> None:
    """No session holds a notification.

    Args:
        context: the behave context.
    """
    inbox = context.app.state.repositories.notifications
    for session in SESSIONS:
        assert asyncio.run(inbox.list_for("session_id", session)) == []


@then('zamknięcie zapisuje adres moderatora i powód "{reason}"')
def closure_recorded(context: Context, reason: str) -> None:
    """The panel reads who closed the case and why.

    Args:
        context: the behave context.
        reason: the expected reason.
    """
    closure = context.closer.get(URL.replace("/close", "/closure")).json()
    assert closure["closed_by"] == STAFF_MODERATOR
    assert closure["reason"] == reason


@then('API odpowiada {code:d} i sprawa ma stan "{state}"')
def refused(context: Context, code: int, state: str) -> None:
    """The close was refused and the case kept its state.

    Args:
        context: the behave context.
        code: the expected HTTP status.
        state: the state the case keeps.
    """
    assert context.response.status_code == code, context.response.text
    assert _state(context) == state
