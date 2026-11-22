"""Steps for the moderator answer scenarios: staff sign-in and in-memory stores."""

import asyncio
from datetime import UTC, datetime
from http import HTTPStatus

from behave import given, then, when
from behave.runner import Context
from features.constants import STAFF_ADMIN, STAFF_MODERATOR
from features.staff_support import csrf, grant_moderator, signed_in
from meritum_core.checks.contracts import CaseClaim, CheckRecord, ModeratorCase, Source
from meritum_core.evidence import SourceDocument

from meritum_backend.main import create_app
from meritum_backend.moderation import InMemorySourceDocuments
from meritum_backend.settings import Settings

NOW = datetime(2026, 11, 22, tzinfo=UTC)
CASE_ID = "#S-12"
URL = "/api/v1/moderation/cases/%23S-12/answer"
TEXT = "Opłata za paszport wynosi 140 zł."
SESSIONS = ("session-aaa", "session-bbb")


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


def _moderator_app(context: Context) -> None:
    app = create_app(
        Settings(
            database_url="postgresql://x:x@127.0.0.1:1/x", admin_emails=STAFF_ADMIN
        )
    )
    source = Source(
        id="gov-1",
        title="Komunikat ministerstwa",
        publisher="Ministerstwo",
        publisher_id="ministerstwo",
        url="https://www.gov.pl/komunikat",
        domain="gov.pl",
        kind="instytucja",
        tier="primary",
        fetched_at=NOW,
    )
    app.state.source_documents = InMemorySourceDocuments(
        [SourceDocument(source=source, text=TEXT)]
    )
    claim = CaseClaim(claim="Paszport zdrożeje.", check_ids=["c1", "c2", "c3"])
    case = ModeratorCase(
        id=CASE_ID,
        state="open",
        reasons=["insufficient_evidence"],
        summary="Paszport",
        claims=[claim],
        distinct_askers=3,
        first_seen=NOW,
        last_seen=NOW,
    )
    asyncio.run(app.state.cases.save(case))
    with signed_in(app, STAFF_ADMIN) as admin:
        grant_moderator(admin)
    context.app = app
    context.moderator = signed_in(app, STAFF_MODERATOR)


@given("sprawa z twierdzeniami z 3 sesji, z których jedna usunęła swoje zapisy")
def case_with_three_sessions(context: Context) -> None:
    """Open the case; the third session has no record left.

    Args:
        context: the behave context; gets ``app`` and ``moderator``.
    """
    _moderator_app(context)
    records = context.app.state.repositories.records
    for check_id, session in zip(("c1", "c2"), SESSIONS, strict=True):
        asyncio.run(records.save(_record(check_id, session)))
    context.fragment = TEXT


@given("moderator wkleja fragment, którego nie ma w tekście źródła")
def pasted_fragment(context: Context) -> None:
    """Open the case and pick a fragment the source does not contain.

    Args:
        context: the behave context; gets ``app``, ``moderator`` and ``fragment``.
    """
    _moderator_app(context)
    context.fragment = "Paszport będzie darmowy."


@when("moderator wysyła odpowiedź z cytatem ze źródła z katalogu")
@when("wysyła odpowiedź")
def send_answer(context: Context) -> None:
    """Send the answer with the prepared fragment.

    Args:
        context: the behave context; gets ``response``.
    """
    body = {
        "text": "Opłata wynosi 140 zł.",
        "quotes": [{"source_id": "gov-1", "fragment": context.fragment}],
    }
    context.response = context.moderator.post(
        URL, json=body, headers=csrf(context.moderator)
    )


@then('2 istniejące sesje dostają powiadomienie "moderator_answer" z linkiem')
def askers_notified(context: Context) -> None:
    """Both remaining sessions hold the notification, the third has none.

    Args:
        context: the behave context.
    """
    assert context.response.status_code == HTTPStatus.OK, context.response.text
    inbox = context.app.state.repositories.notifications
    for session in SESSIONS:
        [note] = asyncio.run(inbox.list_for("session_id", session))
        assert (note.kind, note.case_id) == ("moderator_answer", CASE_ID)
        assert note.link == "/odpowiedzi/S-12"
    assert asyncio.run(inbox.list_for("session_id", "session-ccc")) == []


@then('sprawa przechodzi w stan "answered"')
def case_answered(context: Context) -> None:
    """The case is answered.

    Args:
        context: the behave context.
    """
    case = asyncio.run(context.app.state.cases.get(CASE_ID))
    assert case is not None
    assert case.state == "answered"


@then("API odrzuca ją z informacją, który cytat nie przeszedł")
def quote_refused(context: Context) -> None:
    """422 names the failed quote and nothing was sent.

    Args:
        context: the behave context.
    """
    assert context.response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert context.response.json()["detail"]["rejected_quotes"] == [0]
    case = asyncio.run(context.app.state.cases.get(CASE_ID))
    assert case is not None
    assert case.state == "open"
