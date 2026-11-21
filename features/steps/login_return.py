"""Steps for the return path after login (features/moderation.feature, #82)."""

from http import HTTPStatus
from urllib.parse import parse_qs, urlparse

from behave import given, then, when
from behave.runner import Context
from fastapi.testclient import TestClient

from meritum_backend.auth.adapters import FakeLogin
from meritum_backend.auth.api import get_login
from meritum_backend.auth.constants import FAKE_CODE
from meritum_backend.main import create_app
from meritum_backend.settings import Settings


def _start(context: Context, return_to: str) -> None:
    """Start a Google login that asks to come back to ``return_to``.

    Args:
        context: the behave context; gets ``client`` and ``state``.
        return_to: the return path sent to the login endpoint.
    """
    app = create_app(Settings(database_url="postgresql://x:x@127.0.0.1:1/x"))
    app.dependency_overrides[get_login] = lambda: FakeLogin("sub-1", "m@example.com")
    context.client = TestClient(
        app, base_url="https://testserver", follow_redirects=False
    )
    response = context.client.get(
        "/api/v1/auth/login/google", params={"return_to": return_to}
    )
    assert response.status_code == HTTPStatus.FOUND, response.text
    context.state = parse_qs(urlparse(response.headers["location"]).query)["state"][0]


@given("moderator otwiera {path} i nie jest zalogowany")
@given("żądanie logowania z adresem powrotu {path}")
def login_requested(context: Context, path: str) -> None:
    """Start a login from ``path`` without a session.

    Args:
        context: the behave context.
        path: the page the login started from.

    Features:
        US-MOD-05, F-25
    """
    _start(context, path)


@when("loguje się przez dostawcę OIDC")
@when("logowanie się kończy")
def login_finishes(context: Context) -> None:
    """Come back from the provider with a valid code.

    Args:
        context: the behave context with ``client`` and ``state``; gets ``response``.

    Features:
        US-MOD-05, F-25
    """
    context.response = context.client.get(
        "/api/v1/auth/callback/google",
        params={"code": FAKE_CODE, "state": context.state},
    )


@then("po powrocie z logowania trafia na {path}")
@then("backend przekierowuje na {path}")
def lands_on(context: Context, path: str) -> None:
    """Check where the browser goes after login.

    Args:
        context: the behave context with ``response``.
        path: the expected page.

    Features:
        US-MOD-05, F-25
    """
    assert context.response.status_code == HTTPStatus.SEE_OTHER
    assert context.response.headers["location"] == path
