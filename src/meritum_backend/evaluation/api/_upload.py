"""Uploading a validated case file to the blob store and evaluation index."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from meritum_core.shared.blobs import BlobKind, BlobStore

from meritum_backend.auth.api import CsrfUser
from meritum_backend.evaluation._datasets import parse_cases
from meritum_backend.evaluation.api._deps import Starter, Store
from meritum_backend.evaluation.constants import (
    DATASET_CSV_TYPE,
    DATASET_JSON_TYPE,
    DATASET_RETENTION,
    MAX_UPLOAD_BYTES,
    QUEUE_DOWN_DETAIL,
)
from meritum_backend.evaluation.errors import EvalStoreUnavailableError
from meritum_backend.evaluation.models import Dataset, DatasetSaved

router = APIRouter()


def get_blobs(request: Request) -> BlobStore:
    """The blob store the app built (overridden in tests).

    Args:
        request: the current request (holds the app state).

    Returns:
        The app's blob store.

    Features:
        US-OBS-05, F-26, ADR-31
    """
    return request.app.state.blobs


Blobs = Annotated[BlobStore, Depends(get_blobs)]


@router.post("/datasets", status_code=status.HTTP_201_CREATED)
async def upload_dataset(
    file: UploadFile,
    _member: Starter,
    _csrf: CsrfUser,
    store: Store,
    blobs: Blobs,
) -> DatasetSaved:
    """Store a case file (CSV or JSON, at least 30 cases) to run on later.

    Args:
        file: the uploaded file.
        _member: the analyst or administrator.
        _csrf: the account, CSRF checked (rejects a read-only session).
        store: the run index.
        blobs: the shared blob store.

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
    content_type = (
        DATASET_JSON_TYPE if name.lower().endswith(".json") else DATASET_CSV_TYPE
    )
    try:
        blob = await blobs.put(
            data,
            kind=BlobKind.DATASET,
            content_type=content_type,
            expires_at=datetime.now(UTC) + DATASET_RETENTION,
        )
    except Exception as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, QUEUE_DOWN_DETAIL
        ) from exc
    dataset = Dataset(
        id=uuid.uuid4().hex,
        name=name[:200],
        cases=tuple(cases),
        blob_id=blob.blob_id,
    )
    try:
        await store.add_dataset(dataset)
    except EvalStoreUnavailableError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, QUEUE_DOWN_DETAIL
        ) from exc
    return DatasetSaved(id=dataset.id, cases=len(cases))
