"""A signed-in citizen sees their history anywhere and deletes it or the account."""

import asyncio

import pytest
from fastapi.testclient import TestClient
from meritum_core.jobs.contracts import DeleteSubjectInput
from meritum_core.jobs.fakes import InMemoryJobQueue
from meritum_core.observability import AppRepositories

from meritum_backend.auth.adapters import FakeLogin
from meritum_backend.auth.api import get_login
from meritum_backend.auth.constants import FAKE_CODE
from meritum_backend.jobs.api import get_jobs
from meritum_backend.limits import limiter
from meritum_backend.main import create_app
from meritum_backend.settings import Settings

from .conftest import USER, Remaining

SETTINGS = Settings(database_url="postgresql://x:x@127.0.0.1:1/x", env="dev")


def citizen(repos: AppRepositories, jobs: InMemoryJobQueue) -> TestClient:
    """A client signed in as google:1234567890, the owner of check ``c_u``."""
    limiter.reset()
    app = create_app(SETTINGS)
    app.state.repositories = repos
    app.dependency_overrides[get_jobs] = lambda: jobs
    app.dependency_overrides[get_login] = lambda: FakeLogin(
        "1234567890", "o@example.com"
    )
    client = TestClient(app, base_url="https://testserver", follow_redirects=False)
    state = (
        client.get("/api/v1/auth/login/google").headers["location"].split("state=")[1]
    )
    client.get(
        "/api/v1/auth/callback/google",
        params={"code": FAKE_CODE, "state": state.split("&")[0]},
    )
    client.headers["X-CSRF-Token"] = client.get("/api/v1/auth/me").json()["csrf_token"]
    return client


def test_history_lists_the_accounts_checks_only(repos: AppRepositories) -> None:
    client = citizen(repos, InMemoryJobQueue())
    items = client.get("/api/v1/me/checks").json()
    assert [i["check_id"] for i in items] == ["c_u"]
    assert items[0]["question_masked"] == "Czy we Włoszech był strajk generalny?"
    assert "models" not in items[0]


def test_history_needs_a_signed_in_account(repos: AppRepositories) -> None:
    app = create_app(SETTINGS)
    app.state.repositories = repos
    assert TestClient(app).get("/api/v1/me/checks").status_code == 401


def test_delete_history_removes_the_accounts_checks(
    repos: AppRepositories, remaining: Remaining
) -> None:
    jobs = InMemoryJobQueue()
    client = citizen(repos, jobs)
    response = client.delete("/api/v1/me/checks")
    assert response.status_code == 202
    assert response.json() == {"deleted": 2}
    assert asyncio.run(repos.records.list_for("user_id", USER)) == []
    assert remaining(repos) == {"c_s", "c_o", "c_d"}
    assert [j.payload for j in jobs.enqueued] == [
        DeleteSubjectInput(kind="user_id", value=USER)
    ]
    assert client.get("/api/v1/auth/me").status_code == 200


def test_delete_account_removes_history_and_ends_the_session(
    repos: AppRepositories,
) -> None:
    client = citizen(repos, InMemoryJobQueue())
    assert client.delete("/api/v1/me").status_code == 202
    assert asyncio.run(repos.records.list_for("user_id", USER)) == []
    assert asyncio.run(repos.notifications.list_for("user_id", USER)) == []
    assert client.get("/api/v1/auth/me").status_code == 401


@pytest.mark.parametrize("path", ["/api/v1/me/checks", "/api/v1/me"])
def test_deletion_needs_the_csrf_token(repos: AppRepositories, path: str) -> None:
    client = citizen(repos, InMemoryJobQueue())
    del client.headers["X-CSRF-Token"]
    assert client.delete(path).status_code == 403
    assert asyncio.run(repos.records.list_for("user_id", USER)) != []
