"""A check sent while signed in carries the account's user id, an anonymous one none."""

from typing import cast

from fastapi import FastAPI
from meritum_core.jobs.contracts import CheckInput
from meritum_core.jobs.fakes import InMemoryJobQueue

from meritum_backend.auth.adapters import FakeLogin
from meritum_backend.auth.api import get_login
from meritum_backend.auth.constants import FAKE_CODE
from meritum_backend.checks.constants import SESSION_HEADER

from .conftest import MakeClient

BODY = {"text": "Czy we Włoszech był strajk generalny?", "channel": "web"}
HEAD = {SESSION_HEADER: "session-0123456789"}


def _sent(jobs: InMemoryJobQueue) -> CheckInput:
    payload = jobs.enqueued[0].payload
    assert isinstance(payload, CheckInput)
    return payload


def test_anonymous_check_has_no_user_id(make_client: MakeClient) -> None:
    jobs = InMemoryJobQueue()
    assert (
        make_client(jobs).post("/api/v1/checks", json=BODY, headers=HEAD).status_code
        == 202
    )
    assert _sent(jobs).user_id is None


def test_signed_in_check_has_the_provider_user_id(make_client: MakeClient) -> None:
    jobs = InMemoryJobQueue()
    client = make_client(jobs)
    client.base_url = "https://testserver"  # the session cookie is Secure
    cast("FastAPI", client.app).dependency_overrides[get_login] = lambda: FakeLogin(
        "42", "o@example.com"
    )
    state = client.get("/api/v1/auth/login/google", follow_redirects=False)
    state = state.headers["location"].split("state=")[1].split("&")[0]
    client.get(
        "/api/v1/auth/callback/google",
        params={"code": FAKE_CODE, "state": state},
        follow_redirects=False,
    )
    assert client.post("/api/v1/checks", json=BODY, headers=HEAD).status_code == 202
    assert _sent(jobs).user_id == "google:42"
