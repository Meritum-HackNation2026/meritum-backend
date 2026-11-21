"""Steps for the staff scenarios of features/moderation.feature.

Roles and the high-risk topic list through the public HTTP API; the fake login
provider stands in for Google and Microsoft, the repositories are in memory.
"""

import asyncio
from http import HTTPStatus
from urllib.parse import parse_qs, urlparse

from behave import given, then, when
from behave.runner import Context
from fastapi import FastAPI
from fastapi.testclient import TestClient
from meritum_core.moderation import HighRiskTopic

from meritum_backend.auth.adapters import FakeLogin
from meritum_backend.auth.api import get_login
from meritum_backend.auth.constants import FAKE_CODE
from meritum_backend.main import create_app
from meritum_backend.settings import Settings

ADMIN = "admin@example.com"
MODERATOR = "moderator@example.com"
STRANGER = "stranger@example.com"
TOPIC = HighRiskTopic(name="wybory", keywords=["wybory", "lokal wyborczy"])
CLAIM = "Lokal wyborczy w Gdańsku będzie zamknięty w niedzielę."


def _app() -> FastAPI:
    """Build the app with one configured administrator.

    Returns:
        The app; its repositories live as long as it does.
    """
    return create_app(
        Settings(database_url="postgresql://x:x@127.0.0.1:1/x", admin_emails=ADMIN)
    )


def _signed_in(app: FastAPI, email: str) -> TestClient:
    """Sign ``email`` in through the fake provider; https for the Secure cookie.

    Args:
        app: the app.
        email: the e-mail address the provider confirms.

    Returns:
        A client holding the session cookie.
    """
    app.dependency_overrides[get_login] = lambda: FakeLogin(f"sub-{email}", email)
    client = TestClient(app, base_url="https://testserver", follow_redirects=False)
    location = client.get("/api/v1/auth/login/google").headers["location"]
    state = parse_qs(urlparse(location).query)["state"][0]
    client.get(
        "/api/v1/auth/callback/google", params={"code": FAKE_CODE, "state": state}
    )
    return client


def _csrf(client: TestClient) -> dict[str, str]:
    """Headers with the session's CSRF token.

    Args:
        client: a signed-in client.

    Returns:
        The ``X-CSRF-Token`` header.
    """
    return {"X-CSRF-Token": client.get("/api/v1/auth/me").json()["csrf_token"]}


@given("zalogowany administrator")
def admin_signed_in(context: Context) -> None:
    """Sign in the administrator named in the settings.

    Args:
        context: the behave context; gets ``app`` and ``admin``.

    Features:
        US-MOD-05, F-25
    """
    context.app = _app()
    context.admin = _signed_in(context.app, ADMIN)


@when('wysyła POST /api/v1/staff z adresem e-mail i rolą "moderator"')
def admin_grants_moderator(context: Context) -> None:
    """Grant the moderator role.

    Args:
        context: the behave context with ``admin``.

    Features:
        US-MOD-05, F-25
    """
    response = context.admin.post(
        "/api/v1/staff",
        json={"email": MODERATOR, "role": "moderator"},
        headers=_csrf(context.admin),
    )
    assert response.status_code == HTTPStatus.CREATED


@then("osoba może się zalogować do panelu i widzi sprawy, ale nie listę kont")
def moderator_sees_cases_only(context: Context) -> None:
    """Sign the moderator in and check what the panel shows them.

    Args:
        context: the behave context with ``app``.

    Features:
        US-MOD-05, F-25
    """
    moderator = _signed_in(context.app, MODERATOR)
    assert moderator.get("/api/v1/staff/me").json()["role"] == "moderator"
    assert moderator.get("/api/v1/moderation/cases").status_code == HTTPStatus.OK
    assert moderator.get("/api/v1/staff").status_code == HTTPStatus.FORBIDDEN


@given("ktoś bez konta nadanego przez administratora")
def stranger(context: Context) -> None:
    """An app where the person has no staff account.

    Args:
        context: the behave context; gets ``app``.

    Features:
        US-MOD-05, F-25
    """
    context.app = _app()


@when("próbuje się zalogować do panelu")
def stranger_signs_in(context: Context) -> None:
    """Sign in with the shared OIDC login.

    Args:
        context: the behave context with ``app``; gets ``client``.

    Features:
        US-MOD-05, F-25
    """
    context.client = _signed_in(context.app, STRANGER)


@then("dostaje odmowę i nie widzi żadnej sprawy")
def stranger_refused(context: Context) -> None:
    """Check that the panel refuses the person.

    Args:
        context: the behave context with ``client``.

    Features:
        US-MOD-05, F-25
    """
    client = context.client
    assert client.get("/api/v1/staff/me").status_code == HTTPStatus.FORBIDDEN
    cases = client.get("/api/v1/moderation/cases")
    assert cases.status_code == HTTPStatus.FORBIDDEN
    assert "claims" not in cases.text


@given('administrator dodaje temat "wybory" ze słowami kluczowymi')
def admin_adds_topic(context: Context) -> None:
    """Add the topic through the admin API.

    Args:
        context: the behave context; gets ``app``.

    Features:
        US-MOD-05, F-20, F-25
    """
    context.app = _app()
    admin = _signed_in(context.app, ADMIN)
    response = admin.post(
        "/api/v1/moderation/topics", json=TOPIC.model_dump(), headers=_csrf(admin)
    )
    assert response.status_code == HTTPStatus.CREATED


@when("kolejne twierdzenie bez odpowiedzi dotyczy wyborów")
def claim_about_elections(context: Context) -> None:
    """Read the list the worker's topic step reads, as it does for each claim.

    Args:
        context: the behave context with ``app``; gets ``topics``.

    Features:
        US-MOD-05, F-20
    """
    context.topics = asyncio.run(context.app.state.topics.list_topics())


@then("rozpoznawanie tematów używa nowej listy bez restartu usługi")
def topic_list_is_live(context: Context) -> None:
    """The running app's repository has the topic, and its keywords match the claim.

    Args:
        context: the behave context with ``topics``.

    Features:
        US-MOD-05, F-20
    """
    assert context.topics == [TOPIC]
    assert any(word in CLAIM.lower() for word in TOPIC.keywords)
