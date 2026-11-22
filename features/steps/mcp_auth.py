"""Steps for MCP authentication and limits (security.feature).

They build on the app of the step "klient MCP połączony przez Streamable HTTP".
"""

import asyncio
from collections.abc import Callable
from http import HTTPStatus

from behave import given, then, when
from behave.runner import Context
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError
from fastmcp.utilities.asgi_transport import StreamingASGITransport, run_asgi_lifespan
from httpx2 import AsyncClient, Auth, Timeout

from meritum_backend.limits import CheckGate, LimitSettings, get_check_gate
from meritum_backend.limits.adapters import FixedPendingChecks, MemoryRateCounter

_INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
_TEXT = "Czy od wczoraj w Pcimiu bilety autobusowe można kupić tylko przez aplikację?"


def _post(context: Context, headers: dict[str, str]) -> None:
    context.reply = TestClient(context.app).post("/mcp", json=_INIT, headers=headers)


@when("żądanie do /mcp przychodzi bez klucza i bez tokenu OAuth")
def without_key(context: Context) -> None:
    """Call /mcp with no credential.

    Args:
        context: the behave context.

    Features:
        US-WDR-06, US-BEZ-02, F-37
    """
    _post(context, {})


@when("żądanie do /mcp przychodzi z kluczem, którego serwer nie zna")
def wrong_key(context: Context) -> None:
    """Call /mcp with a key the server does not know.

    Args:
        context: the behave context.

    Features:
        US-WDR-06, US-BEZ-02, F-37
    """
    _post(context, {"Authorization": "Bearer not-a-known-key"})


@then("serwer odpowiada 401 z opisem metody uwierzytelniania i nie zleca sprawdzenia")
def unauthorized(context: Context) -> None:
    """The answer is 401 with the way to authenticate; no check was queued.

    Args:
        context: the behave context.

    Features:
        US-WDR-06, US-BEZ-02, F-37
    """
    assert context.reply.status_code == HTTPStatus.UNAUTHORIZED
    assert "Bearer" in context.reply.headers["WWW-Authenticate"]
    assert "Authorization: Bearer" in context.reply.json()["message"]
    assert "not-a-known-key" not in context.reply.text
    assert context.jobs.enqueued == []


@given("limit {limit:d} sprawdzenia na minutę dla klienta MCP")
def client_limit(context: Context, limit: int) -> None:
    """Limit the checks one MCP client may start per minute.

    Args:
        context: the behave context.
        limit: checks per minute.

    Features:
        US-BEZ-02, F-37
    """
    gate = CheckGate(
        MemoryRateCounter(),
        FixedPendingChecks(),
        LimitSettings(checks_per_client_per_minute=limit),
    )
    context.app.dependency_overrides[get_check_gate] = lambda: gate
    context.mcp_check_gate = gate


def _factory(app: FastAPI) -> Callable[..., AsyncClient]:
    def make(
        headers: dict[str, str] | None = None,
        timeout: Timeout | None = None,
        auth: Auth | None = None,
        *,
        follow_redirects: bool = True,
    ) -> AsyncClient:
        return AsyncClient(
            transport=StreamingASGITransport(app),
            headers=headers,
            timeout=timeout,
            auth=auth,
            follow_redirects=follow_redirects,
        )

    return make


@when("klient MCP woła narzędzie sprawdzania dwa razy")
def twice(context: Context) -> None:
    """Call `check_claim` twice, keeping the second outcome.

    Args:
        context: the behave context.

    Features:
        US-BEZ-02, F-37
    """
    _call_after_check(context, "check_claim", {"text": _TEXT})


@when("klient MCP sprawdza twierdzenie, a potem szuka źródeł")
def check_then_search(context: Context) -> None:
    """Spend the client quota on a check and use the same client for a search.

    Args:
        context: the behave context.

    Features:
        US-BEZ-02, F-37
    """
    _call_after_check(context, "search_sources", {"query": "ostrzeżenia IMGW"})


def _call_after_check(context: Context, tool: str, arguments: dict[str, str]) -> None:
    transport = StreamableHttpTransport(
        "http://testserver/mcp",
        headers={"Authorization": "Bearer behave-key"},
        httpx_client_factory=_factory(context.app),
    )

    async def run() -> str:
        async with run_asgi_lifespan(context.app), Client(transport) as client:
            context.app.state.check_gate = context.mcp_check_gate
            await client.call_tool("check_claim", {"text": _TEXT})
            try:
                await client.call_tool(tool, arguments)
            except ToolError as exc:
                return str(exc)
        return ""

    context.tool_error = asyncio.run(run())


@then("drugie wywołanie kończy się błędem narzędzia o limicie, bez werdyktu")
def limit_error(context: Context) -> None:
    """The second call is a tool error about the limit.

    Args:
        context: the behave context.

    Features:
        US-BEZ-02, F-37
    """
    assert "Za dużo sprawdzeń" in context.tool_error


@then("wyszukiwanie kończy się błędem narzędzia o limicie")
def search_limit_error(context: Context) -> None:
    """The search tool reports the rate limit.

    Args:
        context: the behave context.

    Features:
        US-BEZ-02, F-37
    """
    assert "Za dużo wyszukiwań" in context.tool_error
