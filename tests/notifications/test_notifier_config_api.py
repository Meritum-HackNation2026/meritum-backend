"""The administrator's notification target: who may set it, and what is shown back."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.staff.test_staff_api import ADMIN, member, signed_in

from meritum_backend.main import create_app
from meritum_backend.settings import Settings

PATH = "/api/v1/staff/notifications"
WEBHOOK = {"kind": "webhook", "url": "https://hooks.example/x", "secret": "s3cret"}


@pytest.fixture
def app() -> FastAPI:
    settings = Settings(
        database_url="postgresql://x:x@127.0.0.1:1/x", admin_emails=ADMIN
    )
    return create_app(settings)


def test_the_admin_sets_a_webhook_and_never_gets_the_secret_back(app: FastAPI) -> None:
    admin = signed_in(app, ADMIN.lower())

    put = admin.put(PATH, json=WEBHOOK)

    shown = {"kind": "webhook", "url": "https://hooks.example/x", "secret_set": True}
    assert put.json() == shown
    assert admin.get(PATH).json() == shown
    assert "s3cret" not in admin.get(PATH).text


def test_a_later_choice_replaces_the_earlier_one(app: FastAPI) -> None:
    admin = signed_in(app, ADMIN.lower())
    admin.put(PATH, json=WEBHOOK)

    admin.put(PATH, json={"kind": "email"})

    assert admin.get(PATH).json() == {"kind": "email", "url": None, "secret_set": False}


def test_nothing_set_is_a_404_and_clearing_goes_back_to_it(app: FastAPI) -> None:
    admin = signed_in(app, ADMIN.lower())
    assert admin.get(PATH).status_code == 404
    admin.put(PATH, json=WEBHOOK)

    assert admin.delete(PATH).status_code == 204

    assert admin.get(PATH).status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "webhook"},
        {"kind": "google_chat", "url": "http://insecure.example/x"},
        {"kind": "sms", "url": "https://hooks.example/x"},
    ],
)
def test_an_incomplete_or_insecure_target_is_refused(
    app: FastAPI, body: dict[str, str]
) -> None:
    admin = signed_in(app, ADMIN.lower())
    assert admin.put(PATH, json=body).status_code == 422


@pytest.mark.parametrize("role", ["moderator", "analyst", None])
def test_only_the_admin_may_touch_it(app: FastAPI, role: str | None) -> None:
    client = member(app, role)
    assert client.get(PATH).status_code == 403
    assert client.put(PATH, json=WEBHOOK).status_code == 403
    assert client.delete(PATH).status_code == 403


def test_changes_need_a_session_and_the_csrf_token(app: FastAPI) -> None:
    anonymous = TestClient(app, base_url="https://testserver")
    assert anonymous.put(PATH, json=WEBHOOK).status_code == 401
    admin = signed_in(app, ADMIN.lower())
    del admin.headers["X-CSRF-Token"]
    assert admin.put(PATH, json=WEBHOOK).status_code == 403
