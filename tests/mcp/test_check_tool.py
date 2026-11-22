"""The MCP tool `check_claim` over Streamable HTTP at /mcp, on a fake JobQueue."""

import pytest
from fastmcp.exceptions import ToolError
from meritum_core.checks import CheckResult
from meritum_core.jobs.contracts import CheckInput
from tests.checks.cache_fakes import FAILURE, RESULT, FinishedWorker
from tests.conftest import MakeProbe
from tests.mcp.support import CLAIM, SALT, build_app, call_tool

from meritum_backend.channels import channel_user_hash


def test_tool_returns_the_check_result_and_hashes_the_client_id(
    make_probe: MakeProbe,
) -> None:
    jobs = FinishedWorker()

    result = call_tool(build_app(jobs, make_probe), {"text": CLAIM})

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
    result = call_tool(build_app(FinishedWorker(FAILURE), make_probe), {"text": CLAIM})

    assert result.structured_content["status"] == "technical_failure"
    assert result.structured_content["failure_code"] == "provider_unavailable"
    assert not result.structured_content.get("claims")


def test_refused_input_is_a_tool_error_and_starts_nothing(
    make_probe: MakeProbe,
) -> None:
    jobs = FinishedWorker()

    with pytest.raises(ToolError):
        call_tool(build_app(jobs, make_probe), {"text": "   "})

    assert jobs.enqueued == []
