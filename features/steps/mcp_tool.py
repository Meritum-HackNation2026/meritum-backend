"""Steps for the MCP tool `check_claim` (channels.feature).

The app runs with a job queue that finishes every check at once; the client is
FastMCP's, talking to /mcp through the app's ASGI interface.
"""

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any, override

from behave import given, then, when
from behave.runner import Context
from fastapi import FastAPI
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.utilities.asgi_transport import StreamingASGITransport, run_asgi_lifespan
from httpx2 import AsyncClient, Auth, Timeout
from meritum_core.checks import CheckResult
from meritum_core.jobs.contracts import CheckInput, CheckOutput
from meritum_core.jobs.fakes import InMemoryJobQueue
from meritum_core.jobs.ports import JobState
from pydantic import SecretStr

from meritum_backend.channels import channel_user_hash
from meritum_backend.jobs.api import get_jobs
from meritum_backend.limits import CheckGate, LimitSettings, get_check_gate
from meritum_backend.limits.adapters import FixedPendingChecks, MemoryRateCounter
from meritum_backend.main import create_app
from meritum_backend.settings import Settings, get_settings

_SALT = SecretStr("behave-salt")
_CLIENT = "chatgpt-behave"
_RESULT = CheckResult.model_validate_json(
    (Path(__file__).parents[1] / "fixtures" / "check_result.json").read_text("utf-8")
)


class _Finished(InMemoryJobQueue):
    """Every job is finished with ``result`` in the workflow output."""

    def __init__(self, result: CheckResult) -> None:
        super().__init__()
        self.result = result

    @override
    async def state(self, workflow_id: str) -> JobState | None:
        if not any(j.workflow_id == workflow_id for j in self.enqueued):
            return None
        update = {"check_id": workflow_id}
        output = CheckOutput(result=self.result.model_copy(update=update))
        dump = output.model_dump(mode="json")
        return JobState(workflow_id=workflow_id, status="SUCCESS", output=dump)


def _prepare(context: Context, result: CheckResult) -> None:
    context.jobs = _Finished(result)
    settings = Settings(
        database_url="postgresql://x:x@127.0.0.1:1/x", channel_hash_salt=_SALT
    )
    app = create_app(settings)
    app.dependency_overrides[get_jobs] = lambda: context.jobs
    app.dependency_overrides[get_settings] = lambda: settings
    gate = CheckGate(MemoryRateCounter(), FixedPendingChecks(), LimitSettings())
    app.dependency_overrides[get_check_gate] = lambda: gate
    context.use_ready_probe(app)
    context.app = app


@given("klient MCP połączony przez Streamable HTTP z /mcp")
def mcp_client(context: Context) -> None:
    """Prepare the app whose /mcp the client will call.

    Args:
        context: the behave context.

    Features:
        US-WDR-06, F-37, ADR-17
    """
    _prepare(context, _RESULT)


@given('sprawdzenie kończy się stanem "technical_failure"')
def technical_failure(context: Context) -> None:
    """Make every check end with a technical failure.

    Args:
        context: the behave context.

    Features:
        US-WDR-06, F-37, ADR-17
    """
    failure = CheckResult(
        check_id="x",
        status="technical_failure",
        message="Spróbuj ponownie.",
        failure_code="provider_unavailable",
        corpus_version=_RESULT.corpus_version,
    )
    _prepare(context, failure)


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


@when('woła narzędzie sprawdzania z tekstem "{text}"')
def call_tool(context: Context, text: str) -> None:
    """Call `check_claim` through /mcp.

    Args:
        context: the behave context.
        text: the claim.

    Features:
        US-WDR-06, F-37, ADR-17
    """
    transport = StreamableHttpTransport(
        "http://testserver/mcp", httpx_client_factory=_factory(context.app)
    )

    async def run() -> dict[str, Any]:
        async with run_asgi_lifespan(context.app), Client(transport) as client:
            called = await client.call_tool(
                "check_claim", {"text": text}, meta={"client_id": _CLIENT}
            )
            return called.structured_content or {}

    context.answer = asyncio.run(run())


@then("dostaje CheckResult z werdyktem, cytatami z linkami, siłą i informacją o AI")
def has_result(context: Context) -> None:
    """The answer is a valid CheckResult with verdicts and the AI notice.

    Args:
        context: the behave context.

    Features:
        US-WDR-06, F-37, ADR-17
    """
    answer = CheckResult.model_validate(context.answer)
    assert answer.claims == _RESULT.claims
    assert answer.ai_disclosure is True


@then("CheckRecord ma session_id równy skrótowi z solą identyfikatora klienta MCP")
def session_is_hash(context: Context) -> None:
    """The queued check carries the salted hash as session id.

    Args:
        context: the behave context.

    Features:
        US-BEZ-06, F-37, ADR-17
    """
    [job] = context.jobs.enqueued
    assert isinstance(job.payload, CheckInput)
    assert job.payload.session_id == channel_user_hash("mcp", _CLIENT, _SALT)


@then('wynik ma stan "technical_failure" i kod awarii, bez werdyktu')
def failure_has_no_verdict(context: Context) -> None:
    """The answer keeps the state and the failure code and has no claims.

    Args:
        context: the behave context.

    Features:
        US-WDR-06, F-37, ADR-17
    """
    assert context.answer["status"] == "technical_failure"
    assert context.answer["failure_code"] == "provider_unavailable"
    assert not context.answer.get("claims")
