"""MCP OAuth tokens on a fixed clock: expiry, audience, key, single use."""

import asyncio
import time

from tests.mcp_oauth.support import BASE

from meritum_backend.mcp_oauth import OAuthServer, build_signer


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
