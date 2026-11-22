"""Moderator answers: verbatim quotes, notifications to askers who still exist."""

import asyncio
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from meritum_core.checks.contracts import (
    CaseClaim,
    CheckRecord,
    ModeratorCase,
    Notification,
    Source,
)
from meritum_core.evidence import SourceDocument
from tests.staff.test_staff_api import ADMIN, member

from meritum_backend.main import create_app
from meritum_backend.moderation import InMemorySourceDocuments
from meritum_backend.settings import Settings

NOW = datetime(2026, 11, 22, tzinfo=UTC)
SOURCE = Source(
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
TEXT = "Opłata za paszport wynosi 140 zł. Wniosek złożysz online."
QUOTE = {"source_id": "gov-1", "fragment": "Opłata za paszport wynosi 140 zł."}
BODY = {"text": "Paszport kosztuje 140 zł.", "quotes": [QUOTE]}
URL = "/api/v1/moderation/cases/%23S-12/answer"


def _record(check_id: str, session: str, user: str | None = None) -> CheckRecord:
    return CheckRecord(
        check_id=check_id,
        session_id=session,
        user_id=user,
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


@pytest.fixture
def app() -> FastAPI:
    app = create_app(
        Settings(database_url="postgresql://x:x@127.0.0.1:1/x", admin_emails=ADMIN)
    )
    claim = CaseClaim(claim="Paszport zdrożeje.", check_ids=["c1", "c2", "c3"])
    case = ModeratorCase(
        id="#S-12",
        state="open",
        reasons=["insufficient_evidence"],
        summary="Paszport",
        claims=[claim],
        distinct_askers=3,
        first_seen=NOW,
        last_seen=NOW,
    )
    records = app.state.repositories.records
    # c3's session deleted its records (US-BEZ-05): no record, no notification
    asyncio.run(records.save(_record("c1", "session-aaa")))
    asyncio.run(records.save(_record("c2", "session-bbb")))
    asyncio.run(app.state.cases.save(case))
    app.state.source_documents = InMemorySourceDocuments(
        [SourceDocument(source=SOURCE, text=TEXT)]
    )
    return app


def _inbox(app: FastAPI, session: str) -> list[Notification]:
    return asyncio.run(
        app.state.repositories.notifications.list_for("session_id", session)
    )


def test_answer_notifies_existing_askers_and_answers_the_case(app: FastAPI) -> None:
    moderator = member(app, "moderator")
    response = moderator.post(URL, json=BODY)
    assert response.status_code == 200, response.text
    for session in ("session-aaa", "session-bbb"):
        [note] = _inbox(app, session)
        assert note.kind == "moderator_answer"
        assert note.case_id == "#S-12"
        assert note.link == "/odpowiedzi/S-12"
    assert _inbox(app, "session-ccc") == []
    case = asyncio.run(app.state.cases.get("#S-12"))
    assert case is not None
    assert case.state == "answered"


def test_answer_is_not_a_public_page_and_names_no_asker(app: FastAPI) -> None:
    moderator = member(app, "moderator")
    moderator.post(URL, json=BODY)
    panel = moderator.get(URL).json()
    assert panel["text"] == BODY["text"]
    assert panel["quotes"][0]["fragment"] == QUOTE["fragment"]
    assert "session-aaa" not in str(panel)
    asker = TestClient(app).get(
        "/api/v1/moderation/answers/%23S-12",
        headers={"X-Meritum-Session": "session-aaa"},
    )
    assert asker.json() == panel
    stranger = TestClient(app).get(
        "/api/v1/moderation/answers/%23S-12",
        headers={"X-Meritum-Session": "session-zzz"},
    )
    assert stranger.status_code == 404


def test_quote_not_in_the_source_is_refused_with_its_index(app: FastAPI) -> None:
    bad = {"source_id": "gov-1", "fragment": "Paszport będzie darmowy."}
    response = member(app, "moderator").post(
        URL, json={"text": "x", "quotes": [QUOTE, bad]}
    )
    assert response.status_code == 422
    assert response.json()["detail"]["rejected_quotes"] == [1]
    assert _inbox(app, "session-aaa") == []
    case = asyncio.run(app.state.cases.get("#S-12"))
    assert case is not None
    assert case.state == "open"


def test_unknown_source_counts_as_a_rejected_quote(app: FastAPI) -> None:
    response = member(app, "moderator").post(
        URL, json={"text": "x", "quotes": [{**QUOTE, "source_id": "nope"}]}
    )
    assert response.status_code == 422


def test_answered_case_cannot_be_answered_twice(app: FastAPI) -> None:
    moderator = member(app, "moderator")
    assert moderator.post(URL, json=BODY).status_code == 200
    assert moderator.post(URL, json=BODY).status_code == 409


def test_unknown_case_is_404(app: FastAPI) -> None:
    response = member(app, "moderator").post(
        "/api/v1/moderation/cases/%23S-99/answer", json=BODY
    )
    assert response.status_code == 404


def test_analyst_cannot_answer(app: FastAPI) -> None:
    assert member(app, "analyst").post(URL, json=BODY).status_code == 403
