"""Archive API: POST /api/v1/archives, GET/DELETE /api/v1/archives/{id}.

The copy's id is the ``archive_page`` workflow id, so the client polls it. Only
the person who asked (session or account) and moderators see a copy; anyone
else gets the same 404 as for a missing one.

Features:
    US-KOR-07, F-38
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, Response, status
from meritum_core.jobs.contracts import ARCHIVE_PAGE, ArchivePageInput
from pydantic import BaseModel, Field

from meritum_backend.archives.api._access import Caller, Callers
from meritum_backend.archives.constants import (
    ARCHIVE_LIMIT,
    DOWNLOAD_NAME,
    NO_OWNER_DETAIL,
    NOT_FOUND_DETAIL,
    READ_LIMIT,
    RUNNING_STATUSES,
    TEXT_TYPE,
    UNAVAILABLE_DETAIL,
)
from meritum_backend.archives.models import ArchiveView, Enqueued
from meritum_backend.jobs.api import Jobs
from meritum_backend.limits import limiter

router = APIRouter(prefix="/api/v1/archives", tags=["archives"])


class ArchiveBody(BaseModel):
    """Body of POST /api/v1/archives.

    Attributes:
        url: the public http(s) page; the worker's fetcher blocks private hosts.

    Features:
        US-KOR-07, F-38
    """

    url: Annotated[str, Field(max_length=2048, pattern=r"^https?://\S+$")]


@router.post("", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(ARCHIVE_LIMIT)  # ty: ignore[dynamic-function-decorator-return]
async def request_archive(
    request: Request,  # ruff: ignore[unused-function-argument] (slowapi reads the client address)
    body: ArchiveBody,
    jobs: Jobs,
    callers: Callers,
) -> Enqueued:
    """Enqueue ``archive_page`` for the caller („Zarchiwizuj stronę”).

    Args:
        request: the request; slowapi reads the client address from it.
        body: the page to archive.
        jobs: the job queue port.
        callers: the caller's account and session ids.

    Returns:
        The copy's id to poll.

    Raises:
        HTTPException: 400 without a session or account, 503 when the queue is
            unreachable (429 above the limit comes from slowapi).

    Features:
        US-KOR-07, F-38
    """
    if not callers:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, NO_OWNER_DETAIL)
    archive_id = uuid.uuid4().hex
    job = ArchivePageInput(archive_id=archive_id, url=body.url, owner_id=callers[0])
    try:
        await jobs.enqueue(ARCHIVE_PAGE, job, workflow_id=archive_id)
    except Exception as exc:  # DBOS wraps driver errors in its own types
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE_DETAIL
        ) from exc
    return Enqueued(archive_id=archive_id)


@router.get("/{archive_id}", response_model_exclude_none=True)
@limiter.limit(READ_LIMIT)  # ty: ignore[dynamic-function-decorator-return]
async def read_archive(
    request: Request,  # ruff: ignore[unused-function-argument] (slowapi reads the client address)
    archive_id: str,
    jobs: Jobs,
    access: Caller,
) -> ArchiveView:
    """The copy's state: pending, done (hash, dates), refused or failed.

    A pending job shows no data, so its random id is enough to poll it.

    Args:
        request: the request; slowapi reads the client address from it.
        archive_id: the copy's id.
        jobs: the job queue port.
        access: the caller and the stores.

    Returns:
        What the caller may see.

    Raises:
        HTTPException: 404 for no copy, or one the caller may not see.

    Features:
        US-KOR-07, F-38
    """
    record = await access.visible(archive_id)
    if record is not None:
        data = record.model_dump(exclude={"blob_id", "owner_id"})
        return ArchiveView(status="done", **data)
    state = await jobs.state(archive_id)
    if state is not None and state.status in RUNNING_STATUSES:
        return ArchiveView(archive_id=archive_id, status="pending")
    if state is not None and state.output is None:
        return ArchiveView(archive_id=archive_id, status="failed")
    output = None if state is None else ARCHIVE_PAGE.output.model_validate(state.output)
    # done but deleted since, or someone else's refusal: the same 404 as none
    if output is None or output.refusal is None or not access.may_see(output.owner_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_DETAIL)
    return ArchiveView(
        archive_id=archive_id,
        status="refused",
        refusal=output.refusal,
        message=output.message,
    )


@router.get("/{archive_id}/content")
@limiter.limit(READ_LIMIT)  # ty: ignore[dynamic-function-decorator-return]
async def download_archive(
    request: Request,  # ruff: ignore[unused-function-argument] (slowapi reads the client address)
    archive_id: str,
    access: Caller,
) -> Response:
    """Download the archived text as a .txt file.

    Args:
        request: the request; slowapi reads the client address from it.
        archive_id: the copy's id.
        access: the caller and the stores.

    Returns:
        The text, as an attachment.

    Raises:
        HTTPException: 404 for no copy, or one the caller may not see.

    Features:
        US-KOR-07, F-38
    """
    record = await access.visible(archive_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_DETAIL)
    name = DOWNLOAD_NAME.format(archive_id=archive_id)
    return Response(
        await access.blobs.get(record.blob_id),
        media_type=TEXT_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.delete("/{archive_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(READ_LIMIT)  # ty: ignore[dynamic-function-decorator-return]
async def delete_archive(
    request: Request,  # ruff: ignore[unused-function-argument] (slowapi reads the client address)
    archive_id: str,
    access: Caller,
) -> None:
    """Delete a copy and its text, on the request of its owner or a moderator.

    Args:
        request: the request; slowapi reads the client address from it.
        archive_id: the copy's id.
        access: the caller and the stores.

    Raises:
        HTTPException: 404 for no copy, or one the caller may not delete.

    Features:
        US-KOR-07, F-38
    """
    record = await access.visible(archive_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_DETAIL)
    await access.blobs.delete(record.blob_id)
    await access.store.delete(archive_id)
