"""Return path after login: only same-origin relative paths survive (#82)."""

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
    return TestClient(app, base_url="https://testserver", follow_redirects=False)


def landing(client: TestClient, params: dict[str, str]) -> str:
    login = client.get("/api/v1/auth/login/google", params=params)
    assert login.status_code == 302
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
    response = client.get(
        "/api/v1/auth/callback/google", params={"code": FAKE_CODE, "state": state}
    )
    assert response.status_code == 303
    return response.headers["location"]


@pytest.mark.parametrize("path", ["/panel", "/panel/sprawy?id=7#top", "/"])
def test_login_returns_to_a_relative_path(client: TestClient, path: str) -> None:
    assert landing(client, {"return_to": path}) == path


def test_login_without_return_path_goes_home(client: TestClient) -> None:
    assert landing(client, {}) == "/"


@pytest.mark.parametrize(
    "path",
    [
        "https://zly.example/",
        "//zly.example/",
        "/\\zly.example/",
        "\\\\zly.example",
        "javascript:alert(1)",
        "panel",
        "/\t/zly.example",
        "/ /zly.example",
        "/\n",
        "",
        "/" + "a" * 2048,
    ],
)
def test_foreign_or_odd_return_path_goes_home(client: TestClient, path: str) -> None:
    assert landing(client, {"return_to": path}) == "/"


def test_return_path_does_not_survive_into_the_next_login(client: TestClient) -> None:
    assert landing(client, {"return_to": "/panel"}) == "/panel"
    assert landing(client, {}) == "/"


def test_openapi_documents_the_return_path(client: TestClient) -> None:
    paths = client.get("/api/v1/openapi.json").json()["paths"]
    params = paths["/api/v1/auth/login/{provider}"]["get"]["parameters"]
    found = {p["name"]: p for p in params}["return_to"]
    assert found["in"] == "query"
    assert not found.get("required", False)
    assert found["description"]
