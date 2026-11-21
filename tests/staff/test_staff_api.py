"""Staff and moderation endpoints: who gets through, for every role."""

from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from meritum_backend.auth.adapters import FakeLogin
from meritum_backend.auth.api import get_login
from meritum_backend.auth.constants import FAKE_CODE
from meritum_backend.main import create_app
from meritum_backend.settings import Settings

ADMIN = "Boss@Example.com"
ROLES = ["moderator", "analyst", "admin"]
TOPIC = {"name": "wybory", "keywords": ["wybory"]}


@pytest.fixture
def app() -> FastAPI:
    settings = Settings(
        database_url="postgresql://x:x@127.0.0.1:1/x", admin_emails=f"{ADMIN}, x@y.pl"
    )
    return create_app(settings)


def signed_in(app: FastAPI, email: str) -> TestClient:
    app.dependency_overrides[get_login] = lambda: FakeLogin("sub", email)
    client = TestClient(app, base_url="https://testserver", follow_redirects=False)
    location = client.get("/api/v1/auth/login/google").headers["location"]
    state = parse_qs(urlparse(location).query)["state"][0]
    client.get(
        "/api/v1/auth/callback/google", params={"code": FAKE_CODE, "state": state}
    )
    client.headers["X-CSRF-Token"] = client.get("/api/v1/auth/me").json()["csrf_token"]
    return client


def member(app: FastAPI, role: str | None) -> TestClient:
    """A client signed in with ``role`` (None: an account without a role)."""
    if role is None:
        return signed_in(app, "nobody@example.com")
    email = f"{role}@example.com"
    admin = signed_in(app, ADMIN.lower())
    assert admin.post("/api/v1/staff", json={"email": email, "role": role}).is_success
    return signed_in(app, email)


CALLS = {
    "me": ("GET", "/api/v1/staff/me", None),
    "accounts": ("GET", "/api/v1/staff", None),
    "grant": ("POST", "/api/v1/staff", {"email": "n@example.com", "role": "analyst"}),
    "revoke": ("DELETE", "/api/v1/staff/n@example.com", None),
    "cases": ("GET", "/api/v1/moderation/cases", None),
    "topics": ("GET", "/api/v1/moderation/topics", None),
    "save_topic": ("POST", "/api/v1/moderation/topics", TOPIC),
    "delete_topic": ("DELETE", "/api/v1/moderation/topics/wybory", None),
}
ALLOWED = {
    "me": {"moderator", "analyst", "admin"},
    "cases": {"moderator", "admin"},
    "topics": {"moderator", "analyst", "admin"},
}  # every other call: admin only


@pytest.mark.parametrize("role", [None, *ROLES])
@pytest.mark.parametrize("call", sorted(CALLS))
def test_each_endpoint_lets_in_only_its_roles(
    app: FastAPI, role: str | None, call: str
) -> None:
    method, path, body = CALLS[call]
    response = member(app, role).request(method, path, json=body)
    allowed = role in ALLOWED.get(call, {"admin"})
    assert response.is_success is allowed, response.text
    if not allowed:
        assert response.status_code == 403


@pytest.mark.parametrize("call", sorted(CALLS))
def test_every_endpoint_needs_a_session(app: FastAPI, call: str) -> None:
    method, path, body = CALLS[call]
    client = TestClient(app, base_url="https://testserver")
    assert client.request(method, path, json=body).status_code == 401


@pytest.mark.parametrize("call", ["grant", "revoke", "save_topic", "delete_topic"])
def test_changes_need_the_csrf_token(app: FastAPI, call: str) -> None:
    method, path, body = CALLS[call]
    admin = signed_in(app, ADMIN)
    del admin.headers["X-CSRF-Token"]
    assert admin.request(method, path, json=body).status_code == 403


def test_configured_admin_matches_any_case(app: FastAPI) -> None:
    body = signed_in(app, "BOSS@example.COM").get("/api/v1/staff/me").json()
    assert body == {"email": "boss@example.com", "role": "admin"}


def test_revoked_member_loses_the_panel(app: FastAPI) -> None:
    moderator = member(app, "moderator")
    admin = signed_in(app, ADMIN)
    assert admin.delete("/api/v1/staff/moderator@example.com").status_code == 204
    assert moderator.get("/api/v1/moderation/cases").status_code == 403


def test_grant_stores_the_address_lower_cased(app: FastAPI) -> None:
    admin = signed_in(app, ADMIN)
    admin.post("/api/v1/staff", json={"email": " Ola@Example.com", "role": "analyst"})
    accounts = admin.get("/api/v1/staff").json()
    assert accounts == [{"email": "ola@example.com", "role": "analyst"}]


@pytest.mark.parametrize(
    "body",
    [
        {"email": "not-an-address", "role": "moderator"},
        {"email": "a@example.com", "role": "owner"},
        {"email": "a@example.com", "role": "moderator", "extra": 1},
    ],
)
def test_grant_rejects_bad_input(app: FastAPI, body: dict[str, object]) -> None:
    assert signed_in(app, ADMIN).post("/api/v1/staff", json=body).status_code == 422


def test_topics_round_trip(app: FastAPI) -> None:
    admin = signed_in(app, ADMIN)
    admin.post("/api/v1/moderation/topics", json=TOPIC)
    assert admin.get("/api/v1/moderation/topics").json() == [TOPIC]
    admin.delete("/api/v1/moderation/topics/wybory")
    assert admin.get("/api/v1/moderation/topics").json() == []


def test_too_long_topic_name_is_rejected(app: FastAPI) -> None:
    admin = signed_in(app, ADMIN)
    assert admin.delete(f"/api/v1/moderation/topics/{'x' * 81}").status_code == 422


def test_configured_admin_with_unverified_address_is_refused(app: FastAPI) -> None:
    app.dependency_overrides[get_login] = lambda: FakeLogin(
        "sub", ADMIN, email_verified=False
    )
    client = TestClient(app, base_url="https://testserver", follow_redirects=False)
    location = client.get("/api/v1/auth/login/microsoft").headers["location"]
    state = parse_qs(urlparse(location).query)["state"][0]
    client.get(
        "/api/v1/auth/callback/microsoft", params={"code": FAKE_CODE, "state": state}
    )
    assert client.get("/api/v1/auth/me").json()["email_verified"] is False
    assert client.get("/api/v1/staff/me").status_code == 403
    assert client.get("/api/v1/staff").status_code == 403
