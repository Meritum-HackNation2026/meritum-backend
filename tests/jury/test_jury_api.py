"""Jury links: issuing, redeeming once, and the read-only session they give."""

import time
from datetime import UTC, datetime, timedelta
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


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/api/v1/jobs/ping", None),
        ("POST", "/api/v1/staff/jury-links", None),
        ("POST", "/api/v1/staff", {"email": "x@example.com", "role": "admin"}),
        ("DELETE", "/api/v1/moderation/topics/wybory", None),
        ("DELETE", "/api/v1/sessions/test-session-id/checks", None),
    ],
)
def test_jury_cannot_change_state_even_with_valid_csrf(
    app: FastAPI, method: str, path: str, body: dict[str, str] | None
) -> None:
    issued = signed_in(app, ADMIN).post("/api/v1/staff/jury-links")
    assert issued.status_code == 201
    juror = TestClient(app, base_url="https://testserver", follow_redirects=False)
    token = urlparse(issued.json()["url"]).fragment
    assert (
        juror.post("/api/v1/auth/jury-links/redeem", json={"token": token}).status_code
        == 303
    )
    csrf = juror.get("/api/v1/auth/me").json()["csrf_token"]
    response = juror.request(method, path, json=body, headers={"X-CSRF-Token": csrf})
    assert response.status_code == 403
    assert response.json()["detail"] == "read-only session"


@pytest.mark.parametrize("role", [None, "moderator", "analyst"])
def test_only_admin_can_issue_jury_links(app: FastAPI, role: str | None) -> None:
    assert member(app, role).post("/api/v1/staff/jury-links").status_code == 403


def test_jury_redemption_is_rate_limited(app: FastAPI) -> None:
    client = TestClient(app, base_url="https://testserver")
    for _ in range(10):
        refused = client.post(
            "/api/v1/auth/jury-links/redeem", json={"token": "a" * 43}
        )
        assert refused.status_code == 404
    limited = client.post("/api/v1/auth/jury-links/redeem", json={"token": "b" * 43})
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "60"


def test_jury_link_uses_admin_deadline_and_requires_csrf(app: FastAPI) -> None:
    admin = signed_in(app, ADMIN)
    deadline = datetime.now(UTC) + timedelta(days=3)
    csrf = admin.headers.pop("X-CSRF-Token")
    path = "/api/v1/staff/jury-links"
    assert admin.post(path).status_code == 403
    admin.headers["X-CSRF-Token"] = csrf
    too_late = deadline + timedelta(days=5)
    assert (
        admin.post(path, params={"expires_at": too_late.isoformat()}).status_code == 422
    )
    issued = admin.post(path, params={"expires_at": deadline.isoformat()})
    assert issued.status_code == 201
    assert issued.headers["cache-control"] == "no-store"
    assert datetime.fromisoformat(issued.json()["expires_at"]) == deadline
    link = urlparse(issued.json()["url"])
    assert link.path == "/panel/jury"
    assert not link.query
    assert len(link.fragment) == 43


def test_jury_can_end_its_session(app: FastAPI) -> None:
    issued = signed_in(app, ADMIN).post("/api/v1/staff/jury-links")
    juror = TestClient(app, base_url="https://testserver", follow_redirects=False)
    token = urlparse(issued.json()["url"]).fragment
    assert (
        juror.post("/api/v1/auth/jury-links/redeem", json={"token": token}).status_code
        == 303
    )
    csrf = juror.get("/api/v1/auth/me").json()["csrf_token"]
    assert juror.post("/api/v1/auth/logout").status_code == 403
    assert (
        juror.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf}).status_code
        == 204
    )
    assert juror.get("/api/v1/auth/me").status_code == 401


def test_malformed_jury_attempts_are_redacted_and_rate_limited(app: FastAPI) -> None:
    client = TestClient(app, base_url="https://testserver")
    path = "/api/v1/auth/jury-links/redeem"
    suspect_token = "z" * 43
    for _ in range(10):
        rejected = client.post(path, json={"token": [suspect_token]})
        assert rejected.status_code == 422
        assert suspect_token not in rejected.text
        assert rejected.headers["cache-control"] == "no-store"
    assert client.post(path, json={"token": suspect_token}).status_code == 429


def test_jury_redemption_needs_a_json_body(app: FastAPI) -> None:
    # a cross-site text/plain form must not swap a signed-in admin for a jury session
    admin = signed_in(app, ADMIN)
    token = urlparse(admin.post("/api/v1/staff/jury-links").json()["url"]).fragment
    forged = admin.post(
        "/api/v1/auth/jury-links/redeem",
        content=f'{{"token": "{token}"}}',
        headers={"Content-Type": "text/plain"},
    )
    assert forged.status_code == 415
    assert admin.get("/api/v1/staff").status_code == 200


def test_jury_session_ends_at_the_link_deadline(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    deadline = datetime.now(UTC) + timedelta(hours=1)
    issued = signed_in(app, ADMIN).post(
        "/api/v1/staff/jury-links", params={"expires_at": deadline.isoformat()}
    )
    juror = TestClient(app, base_url="https://testserver", follow_redirects=False)
    token = urlparse(issued.json()["url"]).fragment
    juror.post("/api/v1/auth/jury-links/redeem", json={"token": token})
    assert juror.get("/api/v1/auth/me").status_code == 200
    later = deadline.timestamp() + 60
    monkeypatch.setattr(time, "time", lambda: later)  # ruff: ignore[shared-clock-mock] -- single-threaded test client
    assert juror.get("/api/v1/auth/me").status_code == 401
