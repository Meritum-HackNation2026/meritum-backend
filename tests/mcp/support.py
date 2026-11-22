"""Helpers of the MCP tests: the app on fakes and a client over its ASGI interface."""

import asyncio
from typing import Any

from fastapi import FastAPI
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.utilities.asgi_transport import StreamingASGITransport, run_asgi_lifespan
from httpx2 import AsyncClient, Auth, Timeout
from meritum_core.jobs.fakes import InMemoryJobQueue
from pydantic import SecretStr
from tests.conftest import MakeProbe, worker_report

from meritum_backend.checks.adapters import MemoryResultCache
from meritum_backend.checks.api import get_result_cache
from meritum_backend.health.api import get_readiness
from meritum_backend.jobs.api import get_jobs
from meritum_backend.limits import CheckGate, LimitSettings, get_check_gate
from meritum_backend.limits.adapters import FixedPendingChecks, MemoryRateCounter
from meritum_backend.main import create_app
from meritum_backend.mcp.adapters import ApiKeyAuthenticator
from meritum_backend.settings import Settings, get_settings

CLAIM = "Czy od wczoraj w Pcimiu bilety autobusowe można kupić tylko przez aplikację?"
SALT = SecretStr("test-salt")
KEY = "test-key-123"
CLIENT = "chatgpt-1"
OFFLINE_DB = "postgresql://x:x@127.0.0.1:1/x"


def build_app(jobs: InMemoryJobQueue, make_probe: MakeProbe) -> FastAPI:
    settings = Settings(database_url=OFFLINE_DB, channel_hash_salt=SALT)
    app = create_app(settings)
    gate = CheckGate(MemoryRateCounter(), FixedPendingChecks(), LimitSettings())
    cache = MemoryResultCache()
    probe = make_probe(InMemoryJobQueue(), report=worker_report())
    app.state.mcp_auth = ApiKeyAuthenticator({CLIENT: KEY})
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_jobs] = lambda: jobs
    app.dependency_overrides[get_check_gate] = lambda: gate
    app.dependency_overrides[get_result_cache] = lambda: cache
    app.dependency_overrides[get_readiness] = lambda: probe
    return app


def call_tool(
    app: FastAPI,
    arguments: dict[str, Any],
    tool: str = "check_claim",
    gate: CheckGate | None = None,
    headers: dict[str, str] | None = None,
) -> Any:  # ruff: ignore[any-type]
    def factory(
        headers: dict[str, str] | None = None,
        timeout: Timeout | None = None,
        auth: Auth | None = None,
        *,
        follow_redirects: bool = True,
    ) -> AsyncClient:
        transport = StreamingASGITransport(app)
        return AsyncClient(
            transport=transport,
            headers=headers,
            timeout=timeout,
            auth=auth,
            follow_redirects=follow_redirects,
        )

    async def run() -> Any:  # ruff: ignore[any-type]
        transport = StreamableHttpTransport(
            "http://testserver/mcp",
            headers=headers
            if headers is not None
            else {"Authorization": f"Bearer {KEY}"},
            httpx_client_factory=factory,
        )
        async with run_asgi_lifespan(app), Client(transport) as client:
            if gate is not None:
                app.state.check_gate = gate  # the lifespan built the real one
            return await client.call_tool(tool, arguments)

    return asyncio.run(run())
