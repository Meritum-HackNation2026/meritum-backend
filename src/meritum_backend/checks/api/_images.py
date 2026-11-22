"""Image upload: POST /api/v1/images stores a screenshot or photo, returns its image_id.

Mirrors POST /api/v1/audio: POST /api/v1/checks then carries only the ``image_id``
and the worker reads it with OCR (ADR-30, ADR-31).

Features:
    US-SPR-08, F-33, ADR-13, ADR-31
"""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse
from meritum_core.checks.contracts import CheckStatus
from meritum_core.checks.ocr import (
    MAX_IMAGE_BYTES,
    UnsupportedImageError,
    inspect_image,
)
from meritum_core.shared.blobs import BlobKind
from pydantic import BaseModel

from meritum_backend.checks.api._uploads import Blobs, read_capped
from meritum_backend.checks.constants import (
    IMAGE_CONTENT_TYPES,
    IMAGE_FORMAT_KEY,
    IMAGE_FORMATS,
    IMAGE_MAX_MB,
    IMAGE_RETENTION,
    IMAGE_UPLOAD_LIMIT,
    STORAGE_DETAIL,
)
from meritum_backend.limits import limiter

router = APIRouter(prefix="/api/v1/images", tags=["checks"])


class ImageAccepted(BaseModel):
    """201 answer: the image is stored.

    Attributes:
        image_id: the id to send as ``image_id`` to POST /api/v1/checks.

    Features:
        US-SPR-08, F-33
    """

    image_id: str


class ImageRejected(BaseModel):
    """413 or 415 answer: no image to check, so no verdict.

    Attributes:
        status: always ``out_of_scope``, as core's UnsupportedImageError.
        message_key: out_of_scope_code.image (copy/pl.json).
        formats: the formats that can be sent.
        max_mb: the size limit.

    Features:
        US-SPR-08, F-33
    """

    status: CheckStatus
    message_key: str = IMAGE_FORMAT_KEY
    formats: tuple[str, ...] = IMAGE_FORMATS
    max_mb: int = IMAGE_MAX_MB


def _rejected(code: int) -> JSONResponse:
    body = ImageRejected(status=UnsupportedImageError.check_status)
    return JSONResponse(body.model_dump(), status_code=code)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ImageAccepted,
    responses={
        code: {"model": ImageRejected}
        for code in (
            status.HTTP_413_CONTENT_TOO_LARGE,
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )
    },
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"image/*": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
@limiter.limit(IMAGE_UPLOAD_LIMIT)  # ty: ignore[dynamic-function-decorator-return]
async def upload_image(request: Request, blobs: Blobs) -> ImageAccepted | JSONResponse:
    """Store a screenshot or photo for the check record's retention, return its id.

    The bytes decide the format (core's ``inspect_image``), not the MIME type.
    Public, so limited per client address (429 above IMAGE_UPLOAD_LIMIT).

    Args:
        request: the request; its body is the file (PNG, JPEG or WebP).
        blobs: the blob store port.

    Returns:
        The image id, or ImageRejected: 413 over MAX_IMAGE_BYTES, 415 for any
        other file.

    Raises:
        HTTPException: 503 when the store fails.

    Features:
        US-SPR-08, F-33, ADR-13, ADR-31
    """
    data = await read_capped(request, MAX_IMAGE_BYTES)
    if data is None:
        return _rejected(status.HTTP_413_CONTENT_TOO_LARGE)
    try:
        info = inspect_image(data)
    except UnsupportedImageError:
        return _rejected(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)
    try:
        ref = await blobs.put(
            data,
            kind=BlobKind.IMAGE,
            content_type=IMAGE_CONTENT_TYPES[info.format],
            expires_at=datetime.now(UTC) + IMAGE_RETENTION,
        )
    except Exception as exc:  # disk, bucket or SDK errors: none is the user's fault
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, STORAGE_DETAIL
        ) from exc
    return ImageAccepted(image_id=ref.blob_id)
