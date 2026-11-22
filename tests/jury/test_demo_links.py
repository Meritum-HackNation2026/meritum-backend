"""Demo links: reusable, technical accounts only, dev only, expiring, revocable."""

from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from meritum_backend.main import create_app
from meritum_backend.settings import Settings, get_settings

from .test_jury_api import ADMIN, member, signed_in

DB = "postgresql://x:x@127.0.0.1:1/x"
PATH = "/api/v1/staff/demo-links"


@pytest.fixture
def app() -> FastAPI:
    return create_app(Settings(database_url=DB, admin_emails=ADMIN))


def anonymous(app: FastAPI) -> TestClient:
    return TestClient(app, base_url="https://testserver", follow_redirects=False)


def issue(app: FastAPI, account: str) -> str:
    response = signed_in(app, ADMIN).post(PATH, json={"account": account})
    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    url = str(response.json()["url"])
    return urlparse(url).path


def test_citizen_link_is_reusable_and_lands_on_home(app: FastAPI) -> None:
    path = issue(app, "obywatel")
    for _ in range(2):  # another device, another visit
        visitor = anonymous(app)
        redirect = visitor.get(path)
        assert redirect.status_code == 303
        assert redirect.headers["location"] == "/"
        assert path.rsplit("/", 1)[1] not in redirect.headers["location"]
        assert visitor.get("/api/v1/auth/me").status_code == 200
        assert visitor.get("/api/v1/staff/me").status_code == 403  # no panel role


def test_admin_link_opens_the_panel_but_cannot_persist_privileges(
    app: FastAPI,
) -> None:
    visitor = anonymous(app)
    redirect = visitor.get(issue(app, "admin"))
    assert redirect.headers["location"] == "/panel"
    assert visitor.get("/api/v1/staff/me").json()["role"] == "admin"
    assert visitor.get("/api/v1/staff").status_code == 200
    csrf = {"X-CSRF-Token": visitor.get("/api/v1/auth/me").json()["csrf_token"]}
    for method, path, body in [
        ("POST", "/api/v1/staff", {"email": "x@example.com", "role": "admin"}),
        ("DELETE", "/api/v1/staff/x@example.com", None),
        ("POST", "/api/v1/staff/jury-links", None),
        ("POST", PATH, {"account": "admin"}),
        ("POST", PATH + "/revoke", {"account": "admin", "token": "a" * 43}),
    ]:
        refused = visitor.request(method, path, json=body, headers=csrf)
        assert refused.status_code == 403, path


@pytest.mark.parametrize("role", [None, "moderator", "analyst"])
def test_only_a_real_admin_issues_demo_links(app: FastAPI, role: str | None) -> None:
    body = {"account": "admin"}
    assert member(app, role).post(PATH, json=body).status_code == 403


def test_unknown_account_and_bad_deadline_are_rejected(app: FastAPI) -> None:
    admin = signed_in(app, ADMIN)
    assert admin.post(PATH, json={"account": "root"}).status_code == 422
    late = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    refused = admin.post(PATH, json={"account": "admin", "expires_at": late})
    assert refused.status_code == 422


def test_expired_link_gives_no_session(app: FastAPI) -> None:
    admin = signed_in(app, ADMIN)
    soon = datetime.now(UTC) + timedelta(seconds=1)
    issued = admin.post(PATH, json={"account": "admin", "expires_at": soon.isoformat()})
    path = urlparse(issued.json()["url"]).path
    visitor = anonymous(app)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            "meritum_backend.jury.api._demo.datetime",
            type("D", (), {"now": staticmethod(lambda _tz: soon + timedelta(1))}),
        )
        assert visitor.get(path).status_code == 404
    assert visitor.get("/api/v1/auth/me").status_code == 401


def test_revoked_link_stops_working(app: FastAPI) -> None:
    admin = signed_in(app, ADMIN)
    path = urlparse(admin.post(PATH, json={"account": "admin"}).json()["url"]).path
    token = path.rsplit("/", 1)[1]
    wrong = admin.post(PATH + "/revoke", json={"account": "obywatel", "token": token})
    assert wrong.status_code == 404  # the link is bound to its account
    assert anonymous(app).get(path).status_code == 303
    assert (
        admin.post(
            PATH + "/revoke", json={"account": "admin", "token": token}
        ).status_code
        == 204
    )
    visitor = anonymous(app)
    assert visitor.get(path).status_code == 404
    assert visitor.get("/api/v1/auth/me").status_code == 401


@pytest.mark.parametrize("token", ["x" * 43, "short", "é" * 43])
def test_unknown_or_malformed_tokens_are_refused(app: FastAPI, token: str) -> None:
    visitor = anonymous(app)
    assert visitor.get(f"/api/v1/auth/demo/{token}").status_code == 404
    assert visitor.get("/api/v1/auth/me").status_code == 401


def test_a_jury_link_never_opens_a_demo_session(app: FastAPI) -> None:
    admin = signed_in(app, ADMIN)
    jury = urlparse(admin.post("/api/v1/staff/jury-links").json()["url"]).fragment
    assert anonymous(app).get(f"/api/v1/auth/demo/{jury}").status_code == 404


def test_demo_links_do_not_exist_on_prd() -> None:
    prd = create_app(Settings(database_url=DB, admin_emails=ADMIN))
    prd.dependency_overrides[get_settings] = lambda: Settings(env="prd")
    assert (
        signed_in(prd, ADMIN).post(PATH, json={"account": "admin"}).status_code == 404
    )
    assert anonymous(prd).get("/api/v1/auth/demo/" + "a" * 43).status_code == 404


def test_demo_redemption_is_rate_limited(app: FastAPI) -> None:
    client = anonymous(app)
    for _ in range(10):
        assert client.get("/api/v1/auth/demo/" + "a" * 43).status_code == 404
    assert client.get("/api/v1/auth/demo/" + "a" * 43).status_code == 429
