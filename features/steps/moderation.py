"""Steps for features/moderation.feature: OIDC login through the public HTTP API.

The fake login provider stands in for Google and Microsoft (no network in CI).
"""

from http import HTTPStatus
from urllib.parse import parse_qs, urlparse

from behave import given, then, when
from behave.runner import Context
from fastapi.testclient import TestClient

from meritum_backend.auth.adapters import FakeLogin
from meritum_backend.auth.api import get_login
from meritum_backend.auth.constants import FAKE_CODE, GOOGLE
from meritum_backend.main import create_app
from meritum_backend.settings import Settings

SUBJECT = "google-account-1"
EMAIL = "moderator@example.com"


def _client() -> TestClient:
    """Build the app with the fake provider; https so the Secure cookie is sent.

    Returns:
        A client that keeps cookies and does not follow redirects.
    """
    settings = Settings(
        database_url="postgresql://x:x@127.0.0.1:1/x",
        google_client_id="client-id",
        google_client_secret="client-secret",  # ruff: ignore[hardcoded-password-func-arg] -- fake value, the fake provider ignores it
    )
    app = create_app(settings)
    assert GOOGLE in app.state.login.providers  # the factory registered Google
    app.dependency_overrides[get_login] = lambda: FakeLogin(SUBJECT, EMAIL)
    return TestClient(app, base_url="https://testserver", follow_redirects=False)


def _state(client: TestClient) -> str:
    """Start a Google login.

    Args:
        client: the test client.

    Returns:
        The state sent to the provider.
    """
    location = client.get("/api/v1/auth/login/google").headers["location"]
    return parse_qs(urlparse(location).query)["state"][0]


def _sign_in(context: Context) -> None:
    """Go through login and callback with a valid code; keeps the callback response.

    Args:
        context: the behave context with ``client``; gets ``response``.
    """
    state = _state(context.client)
    context.response = context.client.get(
        "/api/v1/auth/callback/google", params={"code": FAKE_CODE, "state": state}
    )


@given("dostawca OIDC Google skonfigurowany z identyfikatorem klienta i sekretem")
def google_configured(context: Context) -> None:
    """Build the app with Google settings and the fake provider.

    Args:
        context: the behave context; gets ``client``.

    Features:
        US-MOD-05, F-25
    """
    context.client = _client()


@when(
    "użytkownik przechodzi przez GET /api/v1/auth/login/google"
    " i wraca z poprawnym kodem"
)
def user_signs_in(context: Context) -> None:
    """Follow login and come back with the provider's code.

    Args:
        context: the behave context with ``client``; gets ``response``.

    Features:
        US-MOD-05, F-25
    """
    _sign_in(context)


@then("dostaje ciasteczko sesji z flagami HttpOnly, Secure i SameSite=Lax")
def session_cookie_is_hardened(context: Context) -> None:
    """Check the flags of the session cookie.

    Args:
        context: the behave context with ``response``.

    Features:
        US-MOD-05, F-25
    """
    cookie = context.response.headers["set-cookie"].lower()
    assert cookie.startswith("meritum_session=")
    assert all(flag in cookie for flag in ("httponly", "secure", "samesite=lax"))


@then("GET /api/v1/auth/me zwraca identyfikator konta od dostawcy i adres e-mail")
def me_returns_account(context: Context) -> None:
    """Read the current account.

    Args:
        context: the behave context with ``client``.

    Features:
        US-MOD-05, US-SPR-10, F-25
    """
    body = context.client.get("/api/v1/auth/me").json()
    assert (body["subject"], body["email"]) == (SUBJECT, EMAIL)


@given("powrót od dostawcy z parametrem state, który nie pasuje do sesji")
def forged_state(context: Context) -> None:
    """Start a login; the callback will carry another state.

    Args:
        context: the behave context; gets ``client``.

    Features:
        US-MOD-05, F-25
    """
    context.client = _client()
    _state(context.client)


@when("backend obsługuje powrót")
def callback_with_forged_state(context: Context) -> None:
    """Send the callback with a forged state.

    Args:
        context: the behave context with ``client``; gets ``response``.

    Features:
        US-MOD-05, F-25
    """
    context.response = context.client.get(
        "/api/v1/auth/callback/google", params={"code": FAKE_CODE, "state": "forged"}
    )


@then("odmawia logowania i nie tworzy sesji")
def login_refused(context: Context) -> None:
    """Check the refusal and that no session exists.

    Args:
        context: the behave context with ``client`` and ``response``.

    Features:
        US-MOD-05, F-25
    """
    assert context.response.status_code == HTTPStatus.BAD_REQUEST
    assert context.client.get("/api/v1/auth/me").status_code == HTTPStatus.UNAUTHORIZED


@given("zalogowany użytkownik")
def signed_in(context: Context) -> None:
    """Sign in through the fake provider.

    Args:
        context: the behave context; gets ``client``.

    Features:
        US-MOD-05, F-25
    """
    context.client = _client()
    _sign_in(context)


@when("wysyła POST /api/v1/auth/logout")
def sends_logout(context: Context) -> None:
    """Log out with the session's CSRF token.

    Args:
        context: the behave context with ``client``; gets ``response``.

    Features:
        US-MOD-05, F-25
    """
    token = context.client.get("/api/v1/auth/me").json()["csrf_token"]
    context.response = context.client.post(
        "/api/v1/auth/logout", headers={"X-CSRF-Token": token}
    )


@then("ciasteczko jest unieważnione, a GET /api/v1/auth/me zwraca 401")
def cookie_invalidated(context: Context) -> None:
    """Check the expired cookie and that the account is gone.

    Args:
        context: the behave context with ``client`` and ``response``.

    Features:
        US-MOD-05, F-25
    """
    assert context.response.status_code == HTTPStatus.NO_CONTENT
    assert "expires=thu, 01 jan 1970" in context.response.headers["set-cookie"].lower()
    assert context.client.get("/api/v1/auth/me").status_code == HTTPStatus.UNAUTHORIZED
