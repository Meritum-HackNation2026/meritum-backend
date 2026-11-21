"""Audio upload: POST /api/v1/audio stores a recording and returns its audio_id.

The form sends the file as the request body; POST /api/v1/checks then carries
only the ``audio_id`` and the worker transcribes it (ADR-30, ADR-31).

Features:
    US-SPR-11, F-08, ADR-31
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from meritum_core.checks.contracts import CheckStatus
from meritum_core.checks.transcription import (
    MAX_AUDIO_BYTES,
    UnsupportedAudioError,
    inspect_audio,
)
from meritum_core.shared.blobs import BlobKind, BlobStore
from pydantic import BaseModel

from meritum_backend.checks.constants import (
    AUDIO_CONTENT_TYPES,
    AUDIO_FORMAT_KEY,
    AUDIO_FORMATS,
    AUDIO_MAX_MB,
    AUDIO_MAX_MINUTES,
    AUDIO_RETENTION,
    AUDIO_TOO_LARGE_KEY,
    AUDIO_TOO_LONG_ERROR,
    AUDIO_TOO_LONG_KEY,
    AUDIO_UPLOAD_LIMIT,
    STORAGE_DETAIL,
)
from meritum_backend.limits import limiter

router = APIRouter(prefix="/api/v1/audio", tags=["checks"])


class AudioAccepted(BaseModel):
    """201 answer: the recording is stored.

    Attributes:
        audio_id: the id to send as ``audio_id`` to POST /api/v1/checks.

    Features:
        US-SPR-11, F-08
    """

    audio_id: str


class AudioRejected(BaseModel):
    """413, 415 or 422 answer: no recording to check, so no verdict.

    Attributes:
        status: always ``out_of_scope``, as core's UnsupportedAudioError.
        message_key: errors.audio_too_large, errors.audio_too_long or
            status_hint.out_of_scope_audio_format (copy/pl.json).
        formats: the formats that can be sent ({formats} of form.audio_limits).
        max_mb: the size limit ({max_mb} of the copy).
        max_minutes: the length limit ({max_minutes} of the copy).

    Features:
        US-SPR-11, F-08
    """

    status: CheckStatus
    message_key: str
    formats: tuple[str, ...] = AUDIO_FORMATS
    max_mb: int = AUDIO_MAX_MB
    max_minutes: int = AUDIO_MAX_MINUTES


def get_blobs(request: Request) -> BlobStore:
    """The BlobStore the app built at startup (overridden in tests).

    Args:
        request: the current request (holds the app state).

    Returns:
        The app's BlobStore.

    Features:
        US-SPR-11, F-08, ADR-31
    """
    return request.app.state.blobs


Blobs = Annotated[BlobStore, Depends(get_blobs)]


def _rejected(code: int, key: str) -> JSONResponse:
    body = AudioRejected(status=UnsupportedAudioError.check_status, message_key=key)
    return JSONResponse(body.model_dump(), status_code=code)


async def _read_capped(request: Request) -> bytes | None:
    """Read the body, giving up past MAX_AUDIO_BYTES so memory stays bounded.

    Returns:
        The body, or None when it is (or says it is) over MAX_AUDIO_BYTES.
    """
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_AUDIO_BYTES:
        return None
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_AUDIO_BYTES:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


def _unsupported(error: UnsupportedAudioError) -> JSONResponse:
    # shortcut: core has one error for format and length; tell them apart by its
    # message until core adds a subclass (tests/checks/test_uploads.py pins it).
    if str(error).startswith(AUDIO_TOO_LONG_ERROR):
        return _rejected(status.HTTP_422_UNPROCESSABLE_CONTENT, AUDIO_TOO_LONG_KEY)
    return _rejected(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, AUDIO_FORMAT_KEY)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=AudioAccepted,
    responses={
        code: {"model": AudioRejected}
        for code in (
            status.HTTP_413_CONTENT_TOO_LARGE,
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    },
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"audio/*": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
@limiter.limit(AUDIO_UPLOAD_LIMIT)  # ty: ignore[dynamic-function-decorator-return]
async def upload_audio(request: Request, blobs: Blobs) -> AudioAccepted | JSONResponse:
    """Store a recording for the check record's retention and return its id.

    The bytes decide the format (core's ``inspect_audio``), not the MIME type.
    Public, so limited per client address (429 above AUDIO_UPLOAD_LIMIT).

    Args:
        request: the request; its body is the file (OGG Opus, MP3, M4A or WAV).
        blobs: the blob store port.

    Returns:
        The audio id, or AudioRejected: 413 over MAX_AUDIO_BYTES, 422 over
        MAX_AUDIO_SECONDS, 415 for any other file.

    Raises:
        HTTPException: 503 when the store fails.

    Features:
        US-SPR-11, F-08, ADR-13, ADR-31
    """
    data = await _read_capped(request)
    if data is None:
        return _rejected(status.HTTP_413_CONTENT_TOO_LARGE, AUDIO_TOO_LARGE_KEY)
    try:
        info = inspect_audio(data)
    except UnsupportedAudioError as error:
        return _unsupported(error)
    try:
        ref = await blobs.put(
            data,
            kind=BlobKind.AUDIO,
            content_type=AUDIO_CONTENT_TYPES[info.format],
            expires_at=datetime.now(UTC) + AUDIO_RETENTION,
        )
    except Exception as exc:  # disk, bucket or SDK errors: none is the user's fault
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, STORAGE_DETAIL
        ) from exc
    return AudioAccepted(audio_id=ref.blob_id)
