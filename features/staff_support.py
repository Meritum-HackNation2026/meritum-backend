"""HTTP helpers for staff scenarios with the fake OIDC provider."""

from http import HTTPStatus
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI
from fastapi.testclient import TestClient
from features.constants import STAFF_MODERATOR

from meritum_backend.auth.adapters import FakeLogin
from meritum_backend.auth.api import get_login
from meritum_backend.auth.constants import FAKE_CODE


def signed_in(app: FastAPI, email: str) -> TestClient:
    """Sign ``email`` in through the fake provider; https for the Secure cookie.

    Args:
        app: the app.
        email: the e-mail address the provider confirms.

    Returns:
        A client holding the session cookie.

    Features:
        US-MOD-05, F-25
    """
    app.dependency_overrides[get_login] = lambda: FakeLogin(f"sub-{email}", email)
    client = TestClient(app, base_url="https://testserver", follow_redirects=False)
    location = client.get("/api/v1/auth/login/google").headers["location"]
    state = parse_qs(urlparse(location).query)["state"][0]
    client.get(
        "/api/v1/auth/callback/google", params={"code": FAKE_CODE, "state": state}
    )
    return client


def csrf(client: TestClient) -> dict[str, str]:
    """Headers with the session's CSRF token.

    Args:
        client: a signed-in client.

    Returns:
        The ``X-CSRF-Token`` header.

    Features:
        US-MOD-05, F-25
    """
    return {"X-CSRF-Token": client.get("/api/v1/auth/me").json()["csrf_token"]}


def grant_moderator(admin: TestClient) -> None:
    """Grant the moderator role through the staff API.

    Args:
        admin: a client signed in as an administrator.

    Features:
        US-MOD-05, F-25
    """
    response = admin.post(
        "/api/v1/staff",
        json={"email": STAFF_MODERATOR, "role": "moderator"},
        headers=csrf(admin),
    )
    assert response.status_code == HTTPStatus.CREATED, response.text
