"""Who may call /mcp: no credential, a wrong key, a right key, OAuth tokens, limits."""

import asyncio
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastmcp.exceptions import ToolError
from httpx2 import AsyncClient, MockTransport, Request, Response
from meritum_core.jobs.fakes import InMemoryJobQueue
from tests.checks.cache_fakes import FinishedWorker
from tests.conftest import MakeProbe
from tests.mcp.support import CLAIM, KEY, build_app, call_tool

from meritum_backend.limits import CheckGate, LimitSettings, get_check_gate
from meritum_backend.limits.adapters import FixedPendingChecks, MemoryRateCounter
from meritum_backend.mcp import McpSettings, build_mcp_auth
from meritum_backend.mcp.adapters import IntrospectionAuthenticator

GOOD = "good-token"
INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}


def _post(app: FastAPI, headers: dict[str, str]) -> Response:
    return TestClient(app).post("/mcp", json=INIT, headers=headers)


def test_no_credential_is_401_with_the_way_to_authenticate(
    make_probe: MakeProbe,
) -> None:
    jobs = InMemoryJobQueue()

    reply = _post(build_app(jobs, make_probe), {})

    assert reply.status_code == 401
    assert reply.headers["WWW-Authenticate"].startswith("Bearer")
    assert "Authorization: Bearer" in reply.json()["message"]
    assert jobs.enqueued == []


@pytest.mark.parametrize(
    "headers",
    [
        {"Authorization": "Bearer wrong-key"},
        {"X-API-Key": "wrong-key"},
        {"Authorization": "Basic dGVzdDp0ZXN0"},
        {"Authorization": "Bearer "},
    ],
)
def test_wrong_key_is_401_and_never_echoed(
    make_probe: MakeProbe, headers: dict[str, str]
) -> None:
    reply = _post(build_app(InMemoryJobQueue(), make_probe), headers)

    assert reply.status_code == 401
    assert "wrong-key" not in reply.text


def test_x_api_key_header_is_accepted(make_probe: MakeProbe) -> None:
    result = call_tool(
        build_app(FinishedWorker(), make_probe),
        {"text": CLAIM},
        headers={"X-API-Key": KEY},
    )

    assert result.structured_content["status"] == "done"


def test_nothing_configured_lets_nobody_in() -> None:
    assert _no_one_gets_in()


def _no_one_gets_in() -> bool:
    auth = build_mcp_auth(McpSettings(api_keys=""))  # type: ignore[arg-type]
    return asyncio.run(auth.authenticate("anything")) is None


def test_rate_limited_client_gets_a_tool_error_without_a_verdict(
    make_probe: MakeProbe,
) -> None:
    jobs = FinishedWorker()
    gate = CheckGate(
        MemoryRateCounter(),
        FixedPendingChecks(),
        LimitSettings(checks_per_client_per_minute=1),
    )
    app = build_app(jobs, make_probe)
    app.dependency_overrides[get_check_gate] = lambda: gate
    call_tool(app, {"text": CLAIM})

    with pytest.raises(ToolError, match="Za dużo sprawdzeń"):
        call_tool(app, {"text": CLAIM})

    assert len(jobs.enqueued) == 1


def test_key_never_reaches_the_logs(
    make_probe: MakeProbe, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    _post(
        build_app(InMemoryJobQueue(), make_probe), {"Authorization": "Bearer s3cret-x"}
    )
    call_tool(build_app(FinishedWorker(), make_probe), {"text": CLAIM})

    assert "s3cret-x" not in caplog.text
    assert KEY not in caplog.text


def _oauth(active: dict[str, object], status: int = 200) -> IntrospectionAuthenticator:
    def handler(request: Request) -> Response:
        assert request.headers["Authorization"].startswith("Basic ")
        token = request.content.decode().split("=", 1)[1]
        return Response(status, json=active if token == GOOD else {"active": False})

    http = AsyncClient(transport=MockTransport(handler))
    return IntrospectionAuthenticator("https://idp.test/introspect", "api", "pw", http)


def test_oauth_token_of_a_known_client() -> None:
    asyncio.run(_known_client())


async def _known_client() -> None:
    auth = _oauth({"active": True, "client_id": "claude-ai"})

    client = await auth.authenticate("good-token")

    assert client is not None
    assert client.client_id == "claude-ai"
    assert await auth.authenticate("expired-token") is None


def test_oauth_server_error_denies_access() -> None:
    asyncio.run(_server_error())


async def _server_error() -> None:
    auth = _oauth({"active": True, "client_id": "claude-ai"}, status=500)

    assert await auth.authenticate("good-token") is None
