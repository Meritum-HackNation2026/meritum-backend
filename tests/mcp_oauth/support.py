"""Helpers of the MCP OAuth tests: the app on the fake login, a connector's flow."""

import base64
import hashlib
from typing import Any
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from meritum_backend.auth.adapters import FakeLogin
from meritum_backend.auth.api import get_login
from meritum_backend.auth.constants import FAKE_CODE
from meritum_backend.main import create_app
from meritum_backend.settings import Settings, get_settings

SETTINGS = Settings(database_url="postgresql://x:x@127.0.0.1:1/x", env="dev")
BASE = "https://meritum-dev.gburek.app"
RESOURCE = f"{BASE}/mcp"
REDIRECT = "https://chatgpt.com/connector_platform_oauth_redirect"
VERIFIER = "v" * 64
CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest())
    .rstrip(b"=")
    .decode()
)


def client() -> TestClient:
    app = create_app(SETTINGS)
    app.dependency_overrides[get_login] = lambda: FakeLogin("acc-7", "ola@example.com")
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    return TestClient(app, base_url="https://testserver", follow_redirects=False)


def register(http: TestClient, redirect: str = REDIRECT) -> str:
    reply = http.post("/api/v1/oauth/register", json={"redirect_uris": [redirect]})
    assert reply.status_code == 201, reply.text
    return str(reply.json()["client_id"])


def authorize_params(client_id: str, **extra: str) -> dict[str, str]:
    return {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT,
        "code_challenge": CHALLENGE,
        "code_challenge_method": "S256",
        "state": "st-1",
        "scope": "mcp",
        "resource": RESOURCE,
    } | extra


def query_of(location: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlparse(location).query).items()}


def sign_in_via_authorize(http: TestClient, params: dict[str, str]) -> str:
    """Run authorize as a signed-out user through the fake login; the final redirect."""
    first = http.get("/api/v1/oauth/authorize", params=params)
    assert first.status_code == 302, first.text
    login = http.get(first.headers["location"])
    assert login.status_code == 302
    state = query_of(login.headers["location"])["state"]
    back = http.get(
        "/api/v1/auth/callback/google", params={"code": FAKE_CODE, "state": state}
    )
    assert back.status_code == 303
    done = http.get(back.headers["location"])
    assert done.status_code == 302, done.text
    return done.headers["location"]


def code_for(http: TestClient, client_id: str) -> str:
    location = sign_in_via_authorize(http, authorize_params(client_id))
    return query_of(location)["code"]


def exchange(
    http: TestClient, client_id: str, code: str, **extra: str
) -> dict[str, Any]:
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT,
        "client_id": client_id,
        "code_verifier": VERIFIER,
        "resource": RESOURCE,
    } | extra
    reply = http.post("/api/v1/oauth/token", data=form)
    return {"status": reply.status_code, **reply.json()}
