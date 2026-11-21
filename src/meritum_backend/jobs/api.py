"""Jobs API: POST /api/v1/jobs/ping enqueues, GET /api/v1/jobs/{id} reads state."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from meritum_core.jobs.contracts import PING, PingInput
from meritum_core.jobs.ports import JobQueue, JobState
from pydantic import BaseModel

from meritum_backend.limits import limiter

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


class Enqueued(BaseModel):
    """Answer to an accepted job."""

    workflow_id: str


def get_jobs(request: Request) -> JobQueue:
    """The JobQueue the app built at startup (overridden in tests).

    Returns:
        The app's JobQueue.
    """
    return request.app.state.jobs


Jobs = Annotated[JobQueue, Depends(get_jobs)]


@router.post("/ping", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("10/minute")  # ty: ignore[dynamic-function-decorator-return]
async def enqueue_ping(
    request: Request,  # ruff: ignore[unused-function-argument] (slowapi reads the client address)
    jobs: Jobs,
    payload: PingInput | None = None,
) -> Enqueued:
    """Enqueue the `ping` workflow (deploy smoke test).

    Public, so limited to 10 per minute per client address (429 above that).

    Returns:
        The workflow id to poll.

    Raises:
        HTTPException: 503 when the worker's database is unreachable.
    """
    try:
        workflow_id = await jobs.enqueue(PING, payload or PingInput())
    except Exception as exc:  # DBOS wraps driver errors in its own types
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "job queue unavailable"
        ) from exc
    return Enqueued(workflow_id=workflow_id)


@router.get("/{workflow_id}")
async def job_state(jobs: Jobs, workflow_id: str) -> JobState:
    """Read one job's state.

    Returns:
        Status, output and error of the workflow.

    Raises:
        HTTPException: 404 when the id is unknown.
    """
    state = await jobs.state(workflow_id)
    if state is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    return state
