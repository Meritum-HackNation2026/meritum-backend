"""Rules for what a client may see of a running check.

Features:
    US-SPR-02, F-09
"""

import contextlib

from meritum_core.checks import AnalysisStatus, CheckResult
from meritum_core.jobs.contracts import CheckOutput
from meritum_core.jobs.ports import JobState
from pydantic import ValidationError

from meritum_backend.checks.constants import FINISHED_STEP_STATES, VERIFY_STEP


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

    Returns:
        The result, or None while there is no output or when the output is not
        a check's (another workflow, e.g. a ping).

    Features:
        US-SPR-02, F-09
    """
    if state.output is None:
        return None
    with contextlib.suppress(ValidationError):
        return CheckOutput.model_validate(state.output).result
    return None
