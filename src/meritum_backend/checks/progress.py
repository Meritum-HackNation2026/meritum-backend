"""Rules for what a client may see of a running check.

Features:
    US-SPR-02, F-09
"""

import logging

from meritum_core.checks import AnalysisStatus, CheckResult
from meritum_core.jobs.contracts import CheckOutput
from meritum_core.jobs.ports import JobState
from pydantic import ValidationError

from meritum_backend.checks.constants import (
    FINISHED_STEP_STATES,
    UNKNOWN_CORPUS_VERSION,
    UNREADABLE_RESULT_MESSAGE,
    VERIFY_STEP,
)

_log = logging.getLogger(__name__)


def without_early_verdict(progress: AnalysisStatus) -> AnalysisStatus:
    """Drop a result with verdicts the worker wrote before verifying citations.

    Verdicts live only in ``result.claims``; a result without claims
    (out_of_scope, needs_clarification) is a message and passes as is.

    Args:
        progress: one progress value of the `check` workflow.

    Returns:
        The value as is once ``verify_citations`` is done or skipped or when
        the result has no claims, otherwise the same steps without ``result``.

    Features:
        US-SPR-02, F-09
    """
    has_verdict = progress.result is not None and bool(progress.result.claims)
    verified = any(
        step.code == VERIFY_STEP and step.status in FINISHED_STEP_STATES
        for step in progress.steps
    )
    if has_verdict and not verified:
        return progress.model_copy(update={"result": None})
    return progress


def check_result(state: JobState) -> CheckResult | None:
    """Read the CheckResult from a finished `check` workflow's output.

    Args:
        state: the workflow's state.

    Fields a newer worker contract added are dropped. A check's output that still
    does not validate is logged and served as a technical failure, so the client
    gets an answer instead of a 404.

    Args:
        state: the workflow's state.

    Returns:
        The result, or None while there is no output or when the output is not
        a check's (another workflow, e.g. a ping).

    Features:
        US-SPR-02, F-09
    """
    if state.output is None or "result" not in state.output:
        return None
    try:
        return CheckOutput.model_validate(state.output, extra="ignore").result
    except ValidationError:
        _log.exception("unreadable output of check %s", state.workflow_id)
    return CheckResult(
        check_id=state.workflow_id,
        status="technical_failure",
        message=UNREADABLE_RESULT_MESSAGE,
        failure_code="provider_unavailable",
        corpus_version=UNKNOWN_CORPUS_VERSION,
    )


def is_check(state: JobState) -> bool:
    """Tell whether a workflow can be a check: no output yet, or a check's output.

    Args:
        state: the workflow's state.

    Returns:
        False for a finished workflow of another kind (e.g. a ping).

    Features:
        US-SPR-02, F-09
    """
    return state.output is None or check_result(state) is not None
