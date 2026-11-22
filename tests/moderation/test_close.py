"""Closing a case without an answer: state, record, no notification, roles."""

import asyncio
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from meritum_core.checks.contracts import CaseClaim, ModeratorCase
from tests.staff.test_staff_api import ADMIN, member

from meritum_backend.main import create_app
from meritum_backend.settings import Settings

NOW = datetime(2026, 11, 22, tzinfo=UTC)
URL = "/api/v1/moderation/cases/%23S-12/close"
CLOSURE_URL = "/api/v1/moderation/cases/%23S-12/closure"
BODY = {"reason": "sprawa testowa"}


@pytest.fixture
def app() -> FastAPI:
    app = create_app(
        Settings(database_url="postgresql://x:x@127.0.0.1:1/x", admin_emails=ADMIN)
    )
    case = ModeratorCase(
        id="#S-12",
        state="open",
        reasons=["insufficient_evidence"],
        summary="Paszport",
        claims=[CaseClaim(claim="Paszport zdrożeje.", check_ids=["c1"])],
        first_seen=NOW,
        last_seen=NOW,
    )
    asyncio.run(app.state.cases.save(case))
    return app


def _state(app: FastAPI) -> str:
    case = asyncio.run(app.state.cases.get("#S-12"))
    assert case is not None
    return str(case.state)


def test_close_records_who_and_why_and_closes_the_case(app: FastAPI) -> None:
    moderator = member(app, "moderator")
    response = moderator.post(URL, json=BODY)
    assert response.status_code == 200, response.text
    closure = response.json()
    assert closure["closed_by"] == "moderator@example.com"
    assert closure["reason"] == "sprawa testowa"
    assert _state(app) == "closed"
    assert moderator.get(CLOSURE_URL).json() == closure
    assert asyncio.run(app.state.answers.get("#S-12")) is None


def test_admin_reads_the_closure(app: FastAPI) -> None:
    member(app, "moderator").post(URL, json=BODY)
    assert member(app, "admin").get(CLOSURE_URL).status_code == 200


def test_closing_twice_is_a_conflict(app: FastAPI) -> None:
    moderator = member(app, "moderator")
    moderator.post(URL, json=BODY)
    again = moderator.post(URL, json={"reason": "inny powód"})
    assert again.status_code == 409
    assert moderator.get(CLOSURE_URL).json()["reason"] == "sprawa testowa"


def test_unknown_case_is_404(app: FastAPI) -> None:
    response = member(app, "moderator").post(
        "/api/v1/moderation/cases/%23S-99/close", json=BODY
    )
    assert response.status_code == 404


def test_open_case_has_no_closure(app: FastAPI) -> None:
    assert member(app, "moderator").get(CLOSURE_URL).status_code == 404


@pytest.mark.parametrize("reason", ["", "x" * 501])
def test_reason_is_required_and_bounded(app: FastAPI, reason: str) -> None:
    response = member(app, "moderator").post(URL, json={"reason": reason})
    assert response.status_code == 422
    assert _state(app) == "open"


@pytest.mark.parametrize("role", ["analyst", "admin", None])
def test_only_a_moderator_closes(app: FastAPI, role: str | None) -> None:
    response = member(app, role).post(URL, json=BODY)
    assert response.status_code == 403
    assert _state(app) == "open"


def test_anonymous_cannot_close(app: FastAPI) -> None:
    response = TestClient(app, base_url="https://testserver").post(URL, json=BODY)
    assert response.status_code == 401
    assert _state(app) == "open"
