"""Turning what the worker keeps in the job queue into an ``EvalRun``."""

from datetime import datetime
from typing import get_args

from meritum_core.checks.contracts import EvalMetrics, EvalRun, Verdict
from meritum_core.jobs.contracts import EvalRunOutput
from meritum_core.jobs.ports import JobQueue, JobState
from pydantic import ValidationError

from meritum_backend.evaluation.constants import (
    GOLDEN_DATASET,
    RUN_FAILED_STATES,
    RUN_RUNNING_STATES,
)
from meritum_backend.evaluation.models import (
    CaseVerdict,
    ChangedCase,
    Comparison,
    MetricPair,
    RunRef,
    RunSummary,
)


def _pending(ref: RunRef, status: str, finished: datetime | None = None) -> EvalRun:
    return EvalRun(
        id=ref.run_id,
        case_set=ref.case_set,
        case_file=ref.case_file,
        status=status,  # ty: ignore[invalid-argument-type]
        corpus_version=ref.corpus_version,
        user_id=ref.user_id,
        models=(),
        started_at=ref.started_at,
        finished_at=finished,
        metrics=None,
        scenarios=(),
        cases=(),
    )


def run_of(ref: RunRef, state: JobState | None) -> EvalRun:
    """The run as the worker last reported it.

    Args:
        ref: what the backend stored when it enqueued the run.
        state: the workflow's state; None when the queue does not know it.

    Returns:
        The finished run from the workflow output; otherwise a queued, running or
        failed run built from the reference (a failed one when the output does not
        validate).

    Features:
        US-OBS-06, F-28
    """
    if state is None or state.status not in {
        "SUCCESS",
        *RUN_FAILED_STATES,
        *RUN_RUNNING_STATES,
    }:
        return _pending(ref, "queued")
    if state.status in RUN_RUNNING_STATES:
        return _pending(ref, "running")
    if state.status == "SUCCESS" and state.output is not None:
        try:
            return EvalRunOutput.model_validate(state.output, extra="ignore").run
        except ValidationError:
            pass
    return _pending(ref, "failed", ref.started_at)


async def load_run(jobs: JobQueue, ref: RunRef) -> EvalRun:
    """Read one run's state from the queue.

    Args:
        jobs: the job queue port.
        ref: the run.

    Returns:
        The run.

    Features:
        US-OBS-06, F-28
    """
    return run_of(ref, await jobs.state(ref.run_id))


def measured(metrics: EvalMetrics | None) -> dict[str, float]:
    """Only the metrics that were measured.

    Args:
        metrics: the run's metrics; None before it finishes.

    Returns:
        The numeric metrics by name, without the unmeasured (None) ones.

    Features:
        US-OBS-06, F-28
    """
    if metrics is None:
        return {}
    return {k: v for k, v in metrics.model_dump().items() if v is not None}


def summary(run: EvalRun) -> RunSummary:
    """A run for the list.

    Args:
        run: the run.

    Returns:
        Its id, state, dataset, dates and measured metrics.

    Features:
        US-OBS-06, F-28
    """
    return RunSummary(
        id=run.id,
        status=run.status,
        dataset=run.case_file or GOLDEN_DATASET,
        started_at=run.started_at,
        finished_at=run.finished_at,
        metrics=measured(run.metrics),
    )


def verdict_of(label: str) -> Verdict | None:
    """The label when it is a verdict.

    Args:
        label: a predicted verdict or check state.

    Returns:
        The verdict, or None for a state that is not one.

    Features:
        US-OBS-06, F-28
    """
    return next((v for v in get_args(Verdict) if v == label), None)


def case_verdicts(run: EvalRun) -> list[CaseVerdict]:
    """The page's view of every case of a run.

    Args:
        run: the run.

    Returns:
        Each case with its predicted verdict.

    Features:
        US-OBS-06, F-28
    """
    return [
        CaseVerdict(case_id=c.case_id, verdict=verdict_of(c.predicted))
        for c in run.cases
    ]


def compare(a: EvalRun, b: EvalRun) -> Comparison:
    """Metric pairs and the cases whose predicted label differs.

    Args:
        a: the first run.
        b: the second run.

    Returns:
        The metrics both runs measured, and the cases in both runs that changed.

    Features:
        US-OBS-06, F-28
    """
    left, right = measured(a.metrics), measured(b.metrics)
    after = {c.case_id: c.predicted for c in b.cases}
    changed = [
        ChangedCase(
            case_id=c.case_id, a=verdict_of(c.predicted), b=verdict_of(after[c.case_id])
        )
        for c in a.cases
        if c.case_id in after and after[c.case_id] != c.predicted
    ]
    return Comparison(
        metrics={k: MetricPair(a=left[k], b=right[k]) for k in left if k in right},
        changed_cases=changed,
    )
