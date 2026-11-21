"""Backend process targets for the local staff persistence scenario."""

from http import HTTPStatus

from fastapi import FastAPI
from features.constants import STAFF_ADMIN, STAFF_MODERATOR, STAFF_TEST_DBOS_URL
from features.staff_support import grant_moderator, signed_in

from meritum_backend.main import create_app
from meritum_backend.settings import Settings


def _app() -> FastAPI:
    return create_app(Settings(admin_emails=STAFF_ADMIN, dbos_url=STAFF_TEST_DBOS_URL))


def grant_role() -> None:
    """Start a backend and grant a moderator role through its API.

    Features:
        US-MOD-05, F-25
    """
    with signed_in(_app(), STAFF_ADMIN) as admin:
        grant_moderator(admin)


def verify_role() -> None:
    """Start a backend and check the moderator role after signing in.

    Features:
        US-MOD-05, F-25
    """
    with signed_in(_app(), STAFF_MODERATOR) as moderator:
        response = moderator.get("/api/v1/staff/me")
        assert response.status_code == HTTPStatus.OK, response.text
        assert response.json()["role"] == "moderator"
