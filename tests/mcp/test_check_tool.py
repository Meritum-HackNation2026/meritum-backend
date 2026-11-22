"""The MCP tool `check_claim` over Streamable HTTP at /mcp, on a fake JobQueue."""

import asyncio
from typing import Any

import pytest
from fastapi import FastAPI
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError
from fastmcp.utilities.asgi_transport import StreamingASGITransport, run_asgi_lifespan
from httpx2 import AsyncClient, Auth, Timeout
from meritum_core.checks import CheckResult
from meritum_core.jobs.contracts import CheckInput
from meritum_core.jobs.fakes import InMemoryJobQueue
from pydantic import SecretStr
from tests.checks.cache_fakes import FAILURE, RESULT, FinishedWorker
from tests.conftest import MakeProbe, worker_report

from meritum_backend.channels import channel_user_hash
from meritum_backend.checks.adapters import MemoryResultCache
from meritum_backend.checks.api import get_result_cache
from meritum_backend.health.api import get_readiness
from meritum_backend.jobs.api import get_jobs
from meritum_backend.limits import CheckGate, LimitSettings, get_check_gate
from meritum_backend.limits.adapters import FixedPendingChecks, MemoryRateCounter
from meritum_backend.main import create_app
from meritum_backend.settings import Settings, get_settings

CLAIM = "Czy od wczoraj w Pcimiu bilety autobusowe można kupić tylko przez aplikację?"
SALT = SecretStr("test-salt")
OFFLINE_DB = "postgresql://x:x@127.0.0.1:1/x"


def _app(jobs: InMemoryJobQueue, make_probe: MakeProbe) -> FastAPI:
    settings = Settings(database_url=OFFLINE_DB, channel_hash_salt=SALT)
    app = create_app(settings)
    gate = CheckGate(MemoryRateCounter(), FixedPendingChecks(), LimitSettings())
    cache = MemoryResultCache()
    probe = make_probe(InMemoryJobQueue(), report=worker_report())
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_jobs] = lambda: jobs
    app.dependency_overrides[get_check_gate] = lambda: gate
    app.dependency_overrides[get_result_cache] = lambda: cache
    app.dependency_overrides[get_readiness] = lambda: probe
    return app


def _call(app: FastAPI, arguments: dict[str, Any]) -> Any:  # ruff: ignore[any-type]
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
            "http://testserver/mcp", httpx_client_factory=factory
        )
        async with run_asgi_lifespan(app), Client(transport) as client:
            return await client.call_tool(
                "check_claim", arguments, meta={"client_id": "chatgpt-1"}
            )

    return asyncio.run(run())


def test_tool_returns_the_check_result_and_hashes_the_client_id(
    make_probe: MakeProbe,
) -> None:
    jobs = FinishedWorker()

    result = _call(_app(jobs, make_probe), {"text": CLAIM})

    answer = CheckResult.model_validate(result.structured_content)
    assert answer.ai_disclosure is True
    assert answer.claims == RESULT.claims
    [job] = jobs.enqueued
    assert isinstance(job.payload, CheckInput)
    expected = channel_user_hash("mcp", "chatgpt-1", SALT)
    assert job.payload.request.channel == "mcp"
    assert job.payload.session_id == expected
    assert job.payload.channel_user_hash == expected
    assert "chatgpt-1" not in job.payload.model_dump_json()


def test_state_that_is_not_a_verdict_keeps_its_failure_code(
    make_probe: MakeProbe,
) -> None:
    result = _call(_app(FinishedWorker(FAILURE), make_probe), {"text": CLAIM})

    assert result.structured_content["status"] == "technical_failure"
    assert result.structured_content["failure_code"] == "provider_unavailable"
    assert not result.structured_content.get("claims")


def test_refused_input_is_a_tool_error_and_starts_nothing(
    make_probe: MakeProbe,
) -> None:
    jobs = FinishedWorker()

    with pytest.raises(ToolError):
        _call(_app(jobs, make_probe), {"text": "   "})

    assert jobs.enqueued == []
