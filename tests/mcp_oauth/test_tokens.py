"""MCP OAuth tokens on a fixed clock: expiry, audience, key, single use."""

import asyncio
import time

import pytest
from tests.mcp_oauth.support import BASE

from meritum_backend.mcp_oauth import OAuthServer, build_signer
from meritum_backend.settings import Settings


def _server(now: list[float]) -> OAuthServer:
    return OAuthServer(build_signer("k"), BASE, clock=lambda: now[0])


def test_access_token_expires_after_an_hour() -> None:
    now = [1_000_000.0]
    server = _server(now)
    token = server.tokens("google:1", "cid").access_token
    assert asyncio.run(server.authenticate(token)) is not None

    now[0] += 3601

    assert asyncio.run(server.authenticate(token)) is None


def test_token_for_another_audience_or_key_is_refused() -> None:
    now = [1_000_000.0]
    other_key = OAuthServer(build_signer("other"), BASE, clock=lambda: now[0])
    token = other_key.tokens("google:1", "cid").access_token

    assert asyncio.run(_server(now).authenticate(token)) is None
    assert asyncio.run(_server(now).authenticate("not-a-token")) is None


def test_code_expires_after_a_minute() -> None:
    now = [time.time()]
    server = _server(now)
    code = server.code("google:1", "cid", "https://a/cb", "c" * 43)
    now[0] += 61

    assert server.redeem(code, "cid", "https://a/cb", "v" * 64) is None


def test_client_registered_before_the_allowlist_loses_its_other_redirects() -> None:
    old = OAuthServer(
        build_signer("k"), BASE, redirects=frozenset({"https://a.example/cb"})
    )
    client_id = old.register(["https://a.example/cb", "http://localhost:1/cb"])
    assert client_id is not None

    assert _server([0.0]).redirect_uris(client_id) == ["http://localhost:1/cb"]


def test_allowlist_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "MERITUM_MCP_OAUTH_REDIRECT_URIS", "https://a.example/cb, https://b.example/cb"
    )

    allowed = Settings().mcp_oauth_redirect_uris

    assert allowed == frozenset({"https://a.example/cb", "https://b.example/cb"})
