"""Jury link scenarios through the public HTTP API."""

from datetime import datetime, timedelta
from http import HTTPStatus
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlparse

from behave import given, then, when
from behave.runner import Context
from fastapi.testclient import TestClient


@given("administrator utworzył ważny link jury")
def admin_issues_jury_link(context: Context) -> None:
    """Create a jury link through the staff API.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """
    context.execute_steps("Given zalogowany administrator")
    csrf = context.admin.get("/api/v1/auth/me").json()["csrf_token"]
    response = context.admin.post(
        "/api/v1/staff/jury-links", headers={"X-CSRF-Token": csrf}
    )
    assert response.status_code == HTTPStatus.CREATED, response.text
    context.jury_token = urlparse(response.json()["url"]).fragment
    context.jury_expiry = response.json()["expires_at"]


@when("członek jury realizuje link")
def jury_redeems_link(context: Context) -> None:
    """Redeem the link using a client without an OIDC account.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """
    context.juror = TestClient(context.app, base_url="https://testserver")
    context.redemption = context.juror.post(
        "/api/v1/auth/jury-links/redeem",
        json={"token": context.jury_token},
        follow_redirects=False,
    )


@then("dostaje sesję analityka tylko do odczytu i trafia na stronę ewaluacji")
def jury_is_read_only(context: Context) -> None:
    """Observe the evaluation redirect and staff permissions.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """
    assert context.redemption.status_code == HTTPStatus.SEE_OTHER
    assert context.redemption.headers["location"] == "/panel/eval"
    member = context.juror.get("/api/v1/staff/me").json()
    assert member["role"] == "analyst"
    assert member["read_only"] is True
    assert (
        context.juror.get("/api/v1/moderation/cases").status_code
        == HTTPStatus.FORBIDDEN
    )
    assert (
        context.juror.get("/api/v1/moderation/topics").status_code
        == HTTPStatus.FORBIDDEN
    )
    csrf = {"X-CSRF-Token": context.juror.get("/api/v1/auth/me").json()["csrf_token"]}
    refused = context.juror.post("/api/v1/staff/jury-links", headers=csrf)
    assert refused.status_code == HTTPStatus.FORBIDDEN


@when("kolejna osoba realizuje ten sam link")
def jury_replays_link(context: Context) -> None:
    """Try the token from a separate session.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """
    assert context.redemption.status_code == HTTPStatus.SEE_OTHER
    jury_redeems_link(context)


@then("kolejna osoba dostaje odmowę i pozostaje bez sesji")
def jury_replay_refused(context: Context) -> None:
    """Verify that a consumed token cannot create another session.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """
    assert context.redemption.status_code == HTTPStatus.NOT_FOUND
    assert context.juror.get("/api/v1/auth/me").status_code == HTTPStatus.UNAUTHORIZED


@when("członek jury realizuje link po okresie oceny")
def jury_redeems_expired_link(context: Context) -> None:
    """Move the clock beyond the deadline returned by the issuance API.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """
    deadline = datetime.fromisoformat(context.jury_expiry)
    clock = SimpleNamespace(now=lambda _tz: deadline + timedelta(seconds=1))
    with patch("meritum_backend.jury.api._redemption.datetime", clock):
        jury_redeems_link(context)


@then("dostaje informację o wygaśnięciu i pozostaje bez sesji")
def jury_expired_refused(context: Context) -> None:
    """Observe expired-link status and an unsigned client.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """
    assert context.redemption.status_code == HTTPStatus.GONE
    assert context.redemption.json()["detail"] == "jury link expired"
    assert context.juror.get("/api/v1/auth/me").status_code == HTTPStatus.UNAUTHORIZED
