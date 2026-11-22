"""Demo link scenarios through the public HTTP API."""

from datetime import datetime, timedelta
from http import HTTPStatus
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlparse

from behave import given, then, when
from behave.runner import Context
from fastapi.testclient import TestClient

LINKS = "/api/v1/staff/demo-links"


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.get("/api/v1/auth/me").json()["csrf_token"]}


def _open(context: Context) -> TestClient:
    visitor = TestClient(
        context.app, base_url="https://testserver", follow_redirects=False
    )
    context.visit = visitor.get(context.demo_path)
    context.visitor = visitor
    return visitor


@given('administrator utworzył link demo dla konta technicznego "{account}"')
def admin_issues_demo_link(context: Context, account: str) -> None:
    """Create a demo link through the staff API.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """
    context.execute_steps("Given zalogowany administrator")
    response = context.admin.post(
        LINKS, json={"account": account}, headers=_csrf(context.admin)
    )
    assert response.status_code == HTTPStatus.CREATED, response.text
    context.demo_account = account
    context.demo_path = urlparse(response.json()["url"]).path
    context.demo_expiry = response.json()["expires_at"]


@given("administrator cofnął link demo")
def admin_revokes_demo_link(context: Context) -> None:
    """Revoke the link through the staff API.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """
    body = {
        "account": context.demo_account,
        "token": context.demo_path.rsplit("/", 1)[1],
    }
    response = context.admin.post(
        LINKS + "/revoke", json=body, headers=_csrf(context.admin)
    )
    assert response.status_code == HTTPStatus.NO_CONTENT, response.text


@when("członek jury otwiera link demo")
def jury_opens_demo_link(context: Context) -> None:
    """Open the link in a client with no session.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """
    _open(context)


@when("kolejna osoba otwiera ten sam link demo")
def other_opens_demo_link(context: Context) -> None:
    """Open the same link from another device.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """
    context.first = context.visitor
    _open(context)


@when("członek jury otwiera link demo po terminie")
def jury_opens_expired_demo_link(context: Context) -> None:
    """Move the clock beyond the deadline, then open the link.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """
    deadline = datetime.fromisoformat(context.demo_expiry)
    clock = SimpleNamespace(now=lambda _tz: deadline + timedelta(seconds=1))
    with patch("meritum_backend.jury.api._demo.datetime", clock):
        _open(context)


@then('dostaje sesję tego konta i trafia na adres "{location}"')
def lands_signed_in(context: Context, location: str) -> None:
    """Observe the redirect and the session cookie.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """
    assert context.visit.status_code == HTTPStatus.SEE_OTHER
    assert context.visit.headers["location"] == location
    assert context.visitor.get("/api/v1/auth/me").status_code == HTTPStatus.OK


@then("ta sesja ma rolę administratora")
def session_is_admin(context: Context) -> None:
    """Check the panel role of the demo administrator.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """
    assert context.visitor.get("/api/v1/staff/me").json()["role"] == "admin"


@then("kolejna osoba dostaje nową sesję tego samego konta")
def second_session(context: Context) -> None:
    """Both visitors are signed in, each with their own session.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """
    assert context.visit.status_code == HTTPStatus.SEE_OTHER
    for client in (context.first, context.visitor):
        assert client.get("/api/v1/auth/me").status_code == HTTPStatus.OK


@then("dostaje odmowę i pozostaje bez sesji")
def refused_without_session(context: Context) -> None:
    """Observe the refusal and an unsigned client.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """
    assert context.visit.status_code == HTTPStatus.NOT_FOUND
    assert context.visitor.get("/api/v1/auth/me").status_code == HTTPStatus.UNAUTHORIZED


@when("administrator pobiera listę linków demo")
def admin_lists_demo_links(context: Context) -> None:
    """Read the demo links from the staff API.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """
    context.demo_list = context.admin.get(LINKS)


@then("lista zawiera metadane wydanego linku bez tokenu")
def shows_safe_demo_metadata(context: Context) -> None:
    """Check that the list exposes only management metadata.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """
    response = context.demo_list
    assert response.status_code == HTTPStatus.OK, response.text
    (link,) = response.json()
    assert set(link) == {"id", "account", "issued_at", "expires_at"}
    assert link["account"] == context.demo_account
    assert link["expires_at"] == context.demo_expiry
    assert context.demo_path.rsplit("/", 1)[1] not in response.text
