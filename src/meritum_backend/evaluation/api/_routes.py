"""Evaluation API: start, list and compare runs, upload case files.

For analysts and administrators; the latest golden-set summary is public (US-ZRD-12).
The worker scores a run; the API enqueues it and reads the result from the queue.
"""

from fastapi import APIRouter, HTTPException, Request, status
from meritum_core.checks.contracts import EvalRun

from meritum_backend.auth.api import CsrfUser
from meritum_backend.evaluation._runs import (
    case_verdicts,
    compare,
    load_run,
    measured,
    summary,
)
from meritum_backend.evaluation._start import (
    QueueUnavailableError,
    UnknownDatasetError,
    enqueue_run,
)
from meritum_backend.evaluation.api._deps import Analyst, Starter, Store
from meritum_backend.evaluation.api._upload import router as upload_router
from meritum_backend.evaluation.constants import (
    NO_DATASET_DETAIL,
    NO_FINISHED_RUN_DETAIL,
    NO_RUN_DETAIL,
    QUEUE_DOWN_DETAIL,
    RUN_LIST_LIMIT,
)
from meritum_backend.evaluation.models import (
    CaseVerdict,
    Comparison,
    RunSummary,
    Started,
    StartRun,
)
from meritum_backend.evaluation.ports import EvalStore
from meritum_backend.jobs.api import Jobs

router = APIRouter(prefix="/api/v1/eval", tags=["evaluation"])
router.include_router(upload_router)


async def _run_or_404(store: EvalStore, jobs: Jobs, run_id: str) -> EvalRun:
    ref = await store.run(run_id)
    if ref is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_RUN_DETAIL)
    return await load_run(jobs, ref)


@router.post("/runs", status_code=status.HTTP_202_ACCEPTED)
async def start_run(
    body: StartRun,
    member: Starter,
    _csrf: CsrfUser,
    store: Store,
    jobs: Jobs,
    request: Request,
) -> Started:
    """Enqueue an evaluation run on the golden set or an uploaded one.

    Args:
        body: the dataset: ``golden`` or an uploaded set's id.
        member: the analyst or administrator.
        _csrf: the account, CSRF checked (rejects a read-only session).
        store: the run index.
        jobs: the job queue port.
        request: the request (settings in app state).

    Returns:
        The run id.

    Raises:
        HTTPException: 422 for an unknown dataset, 503 when the queue is down.

    Features:
        US-OBS-06, US-POW-05, F-28
    """
    try:
        return await enqueue_run(
            body.dataset, member, store, jobs, request.app.state.eval_corpus_version
        )
    except UnknownDatasetError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, NO_DATASET_DETAIL
        ) from exc
    except QueueUnavailableError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, QUEUE_DOWN_DETAIL
        ) from exc


@router.get("/runs")
async def list_runs(_member: Analyst, store: Store, jobs: Jobs) -> list[RunSummary]:
    """The latest runs with their metrics, newest first.

    Args:
        _member: an analyst, administrator or jury session.
        store: the run index.
        jobs: the job queue port.

    Returns:
        Up to the list limit of runs.

    Features:
        US-OBS-06, F-28
    """
    refs = (await store.runs())[:RUN_LIST_LIMIT]
    return [summary(await load_run(jobs, ref)) for ref in refs]


@router.get("/runs/latest")
async def latest_run(request: Request, store: Store, jobs: Jobs) -> dict[str, object]:
    """Public: when the latest golden-set run finished and what it measured.

    Args:
        request: the request (settings in app state).
        store: the run index.
        jobs: the job queue port.

    Returns:
        ``finished_at``, ``bundle_url`` and the measured ``metrics``; no case results.

    Raises:
        HTTPException: 404 while no golden-set run has finished.

    Features:
        US-ZRD-12, F-29, F-28
    """
    for ref in await store.runs():
        if ref.case_set != "golden":
            continue
        run = await load_run(jobs, ref)
        if run.status == "done" and run.finished_at is not None:
            return {
                "finished_at": run.finished_at,
                "bundle_url": request.app.state.eval_bundle_url.format(run_id=run.id),
                "metrics": measured(run.metrics),
            }
    raise HTTPException(status.HTTP_404_NOT_FOUND, NO_FINISHED_RUN_DETAIL)


@router.get("/runs/compare")
async def compare_runs(
    a: str, b: str, _member: Analyst, store: Store, jobs: Jobs
) -> Comparison:
    """Metric differences and the cases that changed result between two runs.

    Args:
        a: the first run id.
        b: the second run id.
        _member: an analyst, administrator or jury session.
        store: the run index.
        jobs: the job queue port.

    Returns:
        The metrics both measured and the changed cases.

    Features:
        US-OBS-06, F-28
    """
    return compare(await _run_or_404(store, jobs, a), await _run_or_404(store, jobs, b))


@router.get("/runs/{run_id}/cases")
async def run_cases(
    run_id: str, _member: Analyst, store: Store, jobs: Jobs
) -> list[CaseVerdict]:
    """Every case's predicted verdict so far.

    Args:
        run_id: the run id.
        _member: an analyst, administrator or jury session.
        store: the run index.
        jobs: the job queue port.

    Returns:
        The cases of the run.

    Features:
        US-OBS-06, F-28
    """
    return case_verdicts(await _run_or_404(store, jobs, run_id))
