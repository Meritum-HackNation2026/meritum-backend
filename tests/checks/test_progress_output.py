import logging
from typing import Any

import pytest
from meritum_core.jobs.contracts import CONTRACT_VERSION, CheckOutput
from meritum_core.jobs.ports import JobState

from meritum_backend.checks.progress import check_result, is_check

from .cache_fakes import RESULT


def _finished(output: dict[str, Any]) -> JobState:
    return JobState(workflow_id="w1", status="SUCCESS", output=output)


def test_output_from_a_newer_contract_still_gives_the_result() -> None:
    output = CheckOutput(result=RESULT).model_dump(mode="json")
    result = output["result"]
    assert isinstance(result, dict)
    newer = {**output, "from_v_next": 1, "result": {**result, "from_v_next": 1}}
    assert check_result(_finished(newer)) == RESULT


def test_unreadable_check_output_is_a_logged_technical_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    broken = {"contract_version": CONTRACT_VERSION, "result": {"status": "?"}}
    with caplog.at_level(logging.ERROR):
        result = check_result(_finished(broken))
    assert result is not None
    assert result.status == "technical_failure"
    assert result.check_id == "w1"
    assert is_check(_finished(broken))
    assert "w1" in caplog.text


def test_output_of_another_workflow_is_not_a_check() -> None:
    pong = {"contract_version": CONTRACT_VERSION, "message": "pong"}
    assert check_result(_finished(pong)) is None
    assert not is_check(_finished(pong))
