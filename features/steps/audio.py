"""Steps for POST /api/v1/audio (checks.feature): upload, then check by audio_id.

The app runs with core's in-memory BlobStore and InMemoryJobQueue, so no disk,
bucket or database.
"""

import asyncio
from http import HTTPStatus
from typing import override

from behave import given, then, when
from behave.runner import Context
from fastapi.testclient import TestClient
from meritum_core.checks import AnalysisStatus, AnalysisStep
from meritum_core.checks.transcription import MAX_AUDIO_BYTES
from meritum_core.jobs.constants import PROGRESS_KEY
from meritum_core.jobs.fakes import InMemoryJobQueue
from meritum_core.shared.blobs import BlobKind, BlobRef
from meritum_core.shared.blobs.adapters import MemoryBlobStore
from pydantic import AwareDatetime

from meritum_backend.checks import get_blobs
from meritum_backend.checks.constants import SESSION_HEADER
from meritum_backend.jobs.api import get_jobs
from meritum_backend.main import create_app
from meritum_backend.settings import Settings

SESSION = "session-0123456789"
M4A_TIMESCALE = 1000


class _Blobs(MemoryBlobStore):
    """In-memory store that remembers every id it handed out."""

    def __init__(self) -> None:
        super().__init__()
        self.stored: list[str] = []

    @override
    async def put(
        self,
        data: bytes,
        *,
        kind: BlobKind,
        content_type: str,
        expires_at: AwareDatetime,
    ) -> BlobRef:
        ref = await super().put(
            data, kind=kind, content_type=content_type, expires_at=expires_at
        )
        self.stored.append(ref.blob_id)
        return ref


def _box(kind: bytes, body: bytes) -> bytes:
    return (8 + len(body)).to_bytes(4) + kind + body


def _m4a(seconds: int) -> bytes:
    """Build a minimal M4A: ``ftyp`` and a ``moov`` with only its movie header.

    Returns:
        The file's bytes.
    """
    times = bytes(8)  # creation and modification time (version 0)
    duration = (seconds * M4A_TIMESCALE).to_bytes(4)
    header = bytes(4) + times + M4A_TIMESCALE.to_bytes(4) + duration
    return _box(b"ftyp", b"M4A " + bytes(4)) + _box(b"moov", _box(b"mvhd", header))


def _prepare(context: Context, data: bytes, content_type: str) -> None:
    context.jobs = InMemoryJobQueue()
    context.blobs = _Blobs()
    app = create_app(Settings(database_url="postgresql://x:x@127.0.0.1:1/x"))
    app.dependency_overrides[get_jobs] = lambda: context.jobs
    app.dependency_overrides[get_blobs] = lambda: context.blobs
    context.client = TestClient(app)
    context.audio = (data, content_type)


@given("plik M4A o długości {seconds:d} s")
def m4a_file(context: Context, seconds: int) -> None:
    """A recording from the web form.

    Args:
        context: the behave context.
        seconds: the recording's length.

    Features:
        US-SPR-11, F-08
    """
    _prepare(context, _m4a(seconds), "audio/mp4")


@given('plik "{name}"')
def unknown_file(context: Context, name: str) -> None:
    """A file that is no supported recording.

    Args:
        context: the behave context.
        name: the file name; only its bytes are sent.

    Features:
        US-SPR-11, F-08
    """
    _prepare(context, f"to nie jest nagranie: {name}".encode(), "audio/x-xyz")


@given("plik większy niż limit rozmiaru z core/013")
def too_large_file(context: Context) -> None:
    """A recording one byte over MAX_AUDIO_BYTES.

    Args:
        context: the behave context.

    Features:
        US-SPR-11, F-08
    """
    _prepare(context, _m4a(40) + bytes(MAX_AUDIO_BYTES), "audio/mp4")


@when("klient wysyła POST /api/v1/audio")
@when("klient wysyła go do sprawdzenia")
def post_audio(context: Context) -> None:
    """Send the file as the request body.

    Args:
        context: the behave context; gets ``response``.

    Features:
        US-SPR-11, F-08
    """
    data, content_type = context.audio
    context.response = context.client.post(
        "/api/v1/audio", content=data, headers={"Content-Type": content_type}
    )


@then("odpowiedź ma kod 201 i audio_id")
def audio_stored(context: Context) -> None:
    """The file is in the BlobStore under the returned id.

    Args:
        context: the behave context; gets ``audio_id``.

    Features:
        US-SPR-11, F-08
    """
    assert context.response.status_code == HTTPStatus.CREATED
    context.audio_id = context.response.json()["audio_id"]
    assert context.audio_id.startswith("audio_")
    assert asyncio.run(context.blobs.get(context.audio_id)) == context.audio[0]


@then('POST /api/v1/checks z tym audio_id startuje sprawdzenie z krokiem "{step}"')
def check_by_audio_id(context: Context, step: str) -> None:
    """The check carries the audio id and shows the worker's transcription step.

    Args:
        context: the behave context with ``client``, ``jobs`` and ``audio_id``.
        step: the step the worker reports first for a recording.

    Features:
        US-SPR-11, F-08
    """
    body = {"channel": "web", "audio_id": context.audio_id}
    response = context.client.post(
        "/api/v1/checks", json=body, headers={SESSION_HEADER: SESSION}
    )
    assert response.status_code == HTTPStatus.ACCEPTED
    check_id = response.json()["check_id"]
    [job] = context.jobs.enqueued
    assert job.payload.request.audio_id == context.audio_id
    running = AnalysisStep.model_validate({"code": step, "status": "active"})
    progress = AnalysisStatus(check_id=check_id, steps=[running])
    context.jobs.publish(check_id, PROGRESS_KEY, progress)
    polled = AnalysisStatus.model_validate(
        context.client.get(f"/api/v1/checks/{check_id}").json()
    )
    assert [s.code for s in polled.steps] == [step]


@then('wynik ma stan "{state}" z komunikatem, jakie pliki można wysłać')
def unsupported_format(context: Context, state: str) -> None:
    """Rejected as out of scope with the formats hint; nothing stored.

    Args:
        context: the behave context with ``response`` and ``blobs``.
        state: the expected check status.

    Features:
        US-SPR-11, F-08
    """
    assert context.response.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    assert context.response.json() == {
        "status": state,
        "message_key": "status_hint.out_of_scope_audio_format",
    }
    assert context.blobs.stored == []


@then("odpowiedź ma kod 413 z komunikatem po polsku, bez werdyktu")
def too_large(context: Context) -> None:
    """Rejected with the size copy key and no verdict; nothing stored.

    Args:
        context: the behave context with ``response`` and ``blobs``.

    Features:
        US-SPR-11, F-08
    """
    assert context.response.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    body = context.response.json()
    assert body == {"status": "out_of_scope", "message_key": "errors.audio_too_large"}
    assert "verdict" not in body
    assert context.blobs.stored == []
