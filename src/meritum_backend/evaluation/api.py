"""Evaluation API: start, list and compare runs, upload case files.

For analysts and administrators; the latest golden-set summary is public (US-ZRD-12).
The worker scores a run; the API enqueues it and reads the result from the queue.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from meritum_core.checks.contracts import EvalRun

from meritum_backend.auth.api import CsrfUser
from meritum_backend.evaluation._datasets import parse_cases
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
from meritum_backend.evaluation.constants import (
    MAX_UPLOAD_BYTES,
    NO_DATASET_DETAIL,
    NO_FINISHED_RUN_DETAIL,
    NO_RUN_DETAIL,
    QUEUE_DOWN_DETAIL,
    RUN_LIST_LIMIT,
    RUN_ROLES,
)
from meritum_backend.evaluation.models import (
    CaseVerdict,
    Comparison,
    Dataset,
    DatasetSaved,
    RunSummary,
    Started,
    StartRun,
)
from meritum_backend.evaluation.ports import EvalStore
from meritum_backend.jobs.api import Jobs
from meritum_backend.staff import StaffMember
from meritum_backend.staff.api import StaffGate

router = APIRouter(prefix="/api/v1/eval", tags=["evaluation"])


def get_eval_store(request: Request) -> EvalStore:
    """The run index the app built (overridden in tests).

    Args:
        request: the current request (holds the app state).

    Returns:
        The app's evaluation store.

    Features:
        US-OBS-06, F-28
    """
    return request.app.state.eval_store


Store = Annotated[EvalStore, Depends(get_eval_store)]
Analyst = Annotated[StaffMember, Depends(StaffGate(RUN_ROLES, allow_jury=True))]
Starter = Annotated[StaffMember, Depends(StaffGate(RUN_ROLES))]


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


@router.post("/datasets", status_code=status.HTTP_201_CREATED)
async def upload_dataset(
    file: UploadFile, _member: Starter, _csrf: CsrfUser, store: Store
) -> DatasetSaved:
    """Store a case file (CSV or JSON, at least 30 cases) to run on later.

    Args:
        file: the uploaded file.
        _member: the analyst or administrator.
        _csrf: the account, CSRF checked (rejects a read-only session).
        store: the run index.

    Returns:
        The dataset id and its case count.

    Raises:
        HTTPException: 413 above the size limit, 422 for an invalid file.

    Features:
        US-OBS-05, F-26
    """
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "case file too large")
    name = file.filename or "cases.csv"
    try:
        cases = parse_cases(name, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    dataset = Dataset(id=uuid.uuid4().hex, name=name[:200], cases=tuple(cases))
    await store.add_dataset(dataset)
    return DatasetSaved(id=dataset.id, cases=len(cases))
