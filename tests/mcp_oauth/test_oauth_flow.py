"""MCP OAuth: discovery, registration, authorize with PKCE, tokens, /mcp access."""

import asyncio
import logging

import pytest
from tests.mcp_oauth.support import (
    BASE,
    REDIRECT,
    RESOURCE,
    authorize_params,
    client,
    code_for,
    exchange,
    query_of,
    register,
    sign_in_via_authorize,
)

INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}


def test_401_points_to_the_protected_resource_metadata() -> None:
    reply = client().post("/mcp", json=INIT)

    assert reply.status_code == 401
    challenge = reply.headers["WWW-Authenticate"]
    assert (
        f'resource_metadata="{BASE}/.well-known/oauth-protected-resource/mcp"'
        in challenge
    )


@pytest.mark.parametrize(
    "path",
    [
        "/.well-known/oauth-protected-resource",
        "/.well-known/oauth-protected-resource/mcp",
    ],
)
def test_protected_resource_metadata_names_this_server(path: str) -> None:
    body = client().get(path).json()

    assert body["resource"] == RESOURCE
    assert body["authorization_servers"] == [BASE]


def test_authorization_server_metadata_is_what_chatgpt_needs() -> None:
    body = client().get("/.well-known/oauth-authorization-server").json()

    assert body["issuer"] == BASE
    assert body["code_challenge_methods_supported"] == ["S256"]
    assert body["authorization_response_iss_parameter_supported"] is True
    assert body["registration_endpoint"] == f"{BASE}/api/v1/oauth/register"
    assert body["token_endpoint_auth_methods_supported"] == ["none"]


def test_full_flow_gives_a_token_that_opens_mcp() -> None:
    http = client()
    client_id = register(http)
    location = sign_in_via_authorize(http, authorize_params(client_id))
    answer = query_of(location)
    assert location.startswith(REDIRECT)
    assert answer["state"] == "st-1"
    assert answer["iss"] == BASE

    tokens = exchange(http, client_id, answer["code"])

    assert tokens["status"] == 200
    assert tokens["token_type"] == "Bearer"  # ruff: ignore[hardcoded-password-string]
    assert tokens["expires_in"] == 3600
    gate = http.app.state.mcp_auth  # ty: ignore[missing-attribute]
    caller = asyncio.run(gate.authenticate(tokens["access_token"]))
    assert caller is not None
    assert caller.client_id == "oauth:google:acc-7"


def test_signed_in_user_gets_the_code_without_a_new_login() -> None:
    http = client()
    client_id = register(http)
    sign_in_via_authorize(http, authorize_params(client_id))

    again = http.get("/api/v1/oauth/authorize", params=authorize_params(client_id))

    assert again.status_code == 302
    assert "code" in query_of(again.headers["location"])


def test_wrong_pkce_verifier_is_refused() -> None:
    http = client()
    client_id = register(http)

    tokens = exchange(
        http, client_id, code_for(http, client_id), code_verifier="x" * 64
    )

    assert tokens == {"status": 400, "error": "invalid_grant"}


def test_code_works_once() -> None:
    http = client()
    client_id = register(http)
    code = code_for(http, client_id)
    exchange(http, client_id, code)

    assert exchange(http, client_id, code)["error"] == "invalid_grant"


def test_code_of_another_client_is_refused() -> None:
    http = client()
    mine, other = register(http), register(http, "https://example.com/cb")

    assert exchange(http, other, code_for(http, mine))["error"] == "invalid_grant"


@pytest.mark.parametrize(
    "redirect",
    ["https://evil.example/cb", REDIRECT + "/x", REDIRECT.replace("https", "http")],
)
def test_unregistered_redirect_uri_is_an_error_page_not_a_redirect(
    redirect: str,
) -> None:
    http = client()
    params = authorize_params(register(http), redirect_uri=redirect)

    reply = http.get("/api/v1/oauth/authorize", params=params)

    assert reply.status_code == 400
    assert "location" not in reply.headers


def test_forged_client_id_is_refused() -> None:
    reply = client().get(
        "/api/v1/oauth/authorize", params=authorize_params("forged.client")
    )

    assert reply.status_code == 400


@pytest.mark.parametrize(
    ("extra", "error"),
    [
        ({"code_challenge_method": "plain"}, "invalid_request"),
        ({"code_challenge": ""}, "invalid_request"),
        ({"scope": "mcp admin"}, "invalid_scope"),
        ({"resource": "https://elsewhere.example/mcp"}, "invalid_target"),
        ({"response_type": "token"}, "unsupported_response_type"),
    ],
)
def test_bad_authorize_request_goes_back_with_an_error(
    extra: dict[str, str], error: str
) -> None:
    http = client()
    params = authorize_params(register(http), **extra)

    reply = http.get("/api/v1/oauth/authorize", params=params)

    assert reply.status_code == 302
    answer = query_of(reply.headers["location"])
    assert answer["error"] == error
    assert answer["state"] == "st-1"
    assert answer["iss"] == BASE


@pytest.mark.parametrize(
    "uris",
    [[], ["http://example.com/cb"], ["javascript:alert(1)"], ["https://a/#frag"]],
)
def test_registration_needs_https_or_loopback_redirects(uris: list[str]) -> None:
    reply = client().post("/api/v1/oauth/register", json={"redirect_uris": uris})

    assert reply.status_code == 400
    assert reply.json()["error"] == "invalid_redirect_uri"


def test_loopback_redirect_may_use_http() -> None:
    reply = client().post(
        "/api/v1/oauth/register", json={"redirect_uris": ["http://127.0.0.1:3333/cb"]}
    )

    assert reply.status_code == 201


def test_refresh_token_gives_new_tokens() -> None:
    http = client()
    client_id = register(http)
    tokens = exchange(http, client_id, code_for(http, client_id))

    reply = http.post(
        "/api/v1/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": client_id,
        },
    )

    assert reply.status_code == 200
    assert reply.json()["access_token"]


def test_access_token_is_not_a_refresh_token() -> None:
    http = client()
    client_id = register(http)
    tokens = exchange(http, client_id, code_for(http, client_id))

    reply = http.post(
        "/api/v1/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["access_token"],
            "client_id": client_id,
        },
    )

    assert reply.json()["error"] == "invalid_grant"


def test_no_secret_reaches_the_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    http = client()
    client_id = register(http)
    code = code_for(http, client_id)
    tokens = exchange(http, client_id, code)

    for secret in (code, tokens["access_token"], tokens["refresh_token"]):
        assert secret not in caplog.text
