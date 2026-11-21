"""Auth endpoints through HTTP with the fake login provider."""

from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from meritum_backend.auth.adapters import FakeLogin
from meritum_backend.auth.api import get_login
from meritum_backend.auth.constants import FAKE_CODE
from meritum_backend.main import create_app
from meritum_backend.settings import Settings, get_settings

SETTINGS = Settings(database_url="postgresql://x:x@127.0.0.1:1/x", env="dev")


@pytest.fixture
def client() -> TestClient:
    app = create_app(SETTINGS)
    app.dependency_overrides[get_login] = lambda: FakeLogin("acc-7", "ola@example.com")
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    # https: the session cookie is Secure, httpx sends it only over https.
    return TestClient(app, base_url="https://testserver", follow_redirects=False)


def start_login(client: TestClient, provider: str = "google") -> str:
    response = client.get(f"/api/v1/auth/login/{provider}")
    assert response.status_code == 302
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["redirect_uri"] == [
        f"https://meritum-dev.gburek.app/api/v1/auth/callback/{provider}"
    ]
    return query["state"][0]


def sign_in(client: TestClient, provider: str = "google") -> str:
    state = start_login(client, provider)
    response = client.get(
        f"/api/v1/auth/callback/{provider}", params={"code": FAKE_CODE, "state": state}
    )
    assert response.status_code == 303
    return response.headers["set-cookie"]


def test_login_sets_a_hardened_session_cookie(client: TestClient) -> None:
    cookie = sign_in(client).lower()
    assert cookie.startswith("meritum_session=")
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=lax" in cookie
    assert "max-age=28800" in cookie


def test_me_returns_the_provider_account(client: TestClient) -> None:
    sign_in(client, "microsoft")
    body = client.get("/api/v1/auth/me").json()
    assert body["provider"] == "microsoft"
    assert body["subject"] == "acc-7"
    assert body["email"] == "ola@example.com"
    assert body["csrf_token"]


def test_me_without_session_is_401(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401


@pytest.mark.parametrize("state", ["forged", ""])
def test_forged_state_creates_no_session(client: TestClient, state: str) -> None:
    start_login(client)
    response = client.get(
        "/api/v1/auth/callback/google", params={"code": FAKE_CODE, "state": state}
    )
    assert response.status_code == 400
    assert client.get("/api/v1/auth/me").status_code == 401


def test_state_is_single_use(client: TestClient) -> None:
    state = start_login(client)
    params = {"code": FAKE_CODE, "state": state}
    assert client.get("/api/v1/auth/callback/google", params=params).status_code == 303
    client.cookies.clear()
    assert client.get("/api/v1/auth/callback/google", params=params).status_code == 400


def test_refused_code_creates_no_session(client: TestClient) -> None:
    state = start_login(client)
    response = client.get(
        "/api/v1/auth/callback/google", params={"code": "bad", "state": state}
    )
    assert response.status_code == 400
    assert client.get("/api/v1/auth/me").status_code == 401


def test_callback_for_another_provider_is_refused(client: TestClient) -> None:
    state = start_login(client, "google")
    response = client.get(
        "/api/v1/auth/callback/microsoft", params={"code": FAKE_CODE, "state": state}
    )
    assert response.status_code == 400


def test_unknown_provider_is_404(client: TestClient) -> None:
    assert client.get("/api/v1/auth/login/github").status_code == 404


def test_logout_needs_the_csrf_token(client: TestClient) -> None:
    sign_in(client)
    token = client.get("/api/v1/auth/me").json()["csrf_token"]
    assert client.post("/api/v1/auth/logout").status_code == 403
    bad = {"X-CSRF-Token": "nope"}
    assert client.post("/api/v1/auth/logout", headers=bad).status_code == 403
    response = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": token})
    assert response.status_code == 204
    assert "expires=thu, 01 jan 1970" in response.headers["set-cookie"].lower()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_logout_without_session_is_401(client: TestClient) -> None:
    assert client.post("/api/v1/auth/logout").status_code == 401


def test_tampered_cookie_is_not_a_session(client: TestClient) -> None:
    sign_in(client)
    value = client.cookies["meritum_session"]
    client.cookies.clear()
    client.cookies.set("meritum_session", value[:-2] + "xx")
    assert client.get("/api/v1/auth/me").status_code == 401


def test_factory_registers_only_configured_providers() -> None:
    settings = Settings(google_client_id="id", google_client_secret="s")  # ruff: ignore[hardcoded-password-func-arg] -- fake value
    assert create_app(settings).state.login.providers == frozenset({"google"})
