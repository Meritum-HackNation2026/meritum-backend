import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import override

import limits.storage.memory
import pytest
from fastapi.testclient import TestClient
from meritum_core.checks.transcription import MAX_AUDIO_SECONDS
from meritum_core.shared.blobs import BlobKind, BlobRef
from meritum_core.shared.blobs.adapters import FilesystemBlobStore, MemoryBlobStore
from pydantic import AwareDatetime, ValidationError

from meritum_backend.checks import get_blobs
from meritum_backend.checks.constants import AUDIO_RETENTION
from meritum_backend.checks.factory import build_blobs
from meritum_backend.limits import limiter
from meritum_backend.main import create_app
from meritum_backend.settings import Settings

DB = "postgresql://x:x@127.0.0.1:1/x"
BYTE_RATE = 100
DISK_FULL = "disk full"


def wav(seconds: int) -> bytes:
    fmt = b"fmt " + (16).to_bytes(4, "little") + bytes(8)
    fmt += BYTE_RATE.to_bytes(4, "little") + bytes(4)
    size = seconds * BYTE_RATE
    data = b"data" + size.to_bytes(4, "little") + bytes(size)
    body = b"WAVE" + fmt + data
    return b"RIFF" + len(body).to_bytes(4, "little") + body


class Blobs(MemoryBlobStore):
    """Keeps the BlobRef of every put."""

    def __init__(self) -> None:
        super().__init__()
        self.refs: list[BlobRef] = []

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
        self.refs.append(ref)
        return ref


class BrokenBlobs(MemoryBlobStore):
    @override
    async def put(
        self,
        data: bytes,
        *,
        kind: BlobKind,
        content_type: str,
        expires_at: AwareDatetime,
    ) -> BlobRef:
        raise OSError(DISK_FULL)


def client_on(blobs: MemoryBlobStore) -> TestClient:
    limiter.reset()  # counters are module-level; every test starts from zero
    app = create_app(Settings(database_url=DB))
    app.dependency_overrides[get_blobs] = lambda: blobs
    return TestClient(app)


def test_recording_is_kept_as_wav_for_the_check_retention() -> None:
    blobs = Blobs()
    sent = datetime.now(UTC)
    response = client_on(blobs).post(
        "/api/v1/audio", content=wav(5), headers={"Content-Type": "text/plain"}
    )
    assert response.status_code == 201
    [ref] = blobs.refs
    assert response.json() == {"audio_id": ref.blob_id}
    assert ref.kind == BlobKind.AUDIO
    assert ref.content_type == "audio/wav"  # from the bytes, not the header
    assert sent + AUDIO_RETENTION <= ref.expires_at
    assert ref.expires_at <= datetime.now(UTC) + AUDIO_RETENTION


def test_too_long_recording_gets_its_own_copy_key() -> None:
    blobs = Blobs()
    response = client_on(blobs).post(
        "/api/v1/audio", content=wav(MAX_AUDIO_SECONDS + 1)
    )
    assert response.status_code == 422
    body = response.json()
    assert body["status"] == "out_of_scope"
    assert body["message_key"] == "errors.audio_too_long"
    assert body["max_minutes"] == 10
    assert blobs.refs == []


def test_empty_body_is_an_unsupported_format() -> None:
    response = client_on(Blobs()).post("/api/v1/audio", content=b"")
    assert response.status_code == 415
    assert response.json()["message_key"] == "status_hint.out_of_scope_audio_format"


def test_storage_failure_is_503_without_details() -> None:
    response = client_on(BrokenBlobs()).post("/api/v1/audio", content=wav(1))
    assert response.status_code == 503
    assert "disk" not in response.text


def test_uploads_are_limited_per_minute_and_per_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = client_on(Blobs())
    now = [time.time()]
    clock = SimpleNamespace(time=lambda: now[0])
    monkeypatch.setattr(limits.storage.memory, "time", clock)  # slowapi's counters

    def burst(count: int) -> list[int]:
        return [
            client.post("/api/v1/audio", content=b"").status_code for _ in range(count)
        ]

    assert 429 not in burst(10)
    assert burst(1) == [429]  # 11th in a minute
    for _ in range(2):
        now[0] += 61
        assert 429 not in burst(10)
    now[0] += 61
    assert burst(1) == [429]  # 31st in a day, in a fresh minute


def test_files_volume_gives_the_filesystem_store(tmp_path: Path) -> None:
    store = build_blobs(Settings(database_url=DB, files_dir=tmp_path))
    assert isinstance(store, FilesystemBlobStore)


def test_nothing_configured_gives_the_memory_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MERITUM_BLOB_PROVIDER", raising=False)
    assert isinstance(build_blobs(Settings(database_url=DB)), MemoryBlobStore)


def test_declared_oversize_is_413_before_reading() -> None:
    response = client_on(Blobs()).post(
        "/api/v1/audio", content=b"x", headers={"Content-Length": str(21 * 2**20)}
    )
    assert response.status_code == 413
    assert response.json()["max_mb"] == 20


def test_outside_local_a_missing_store_fails_at_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MERITUM_BLOB_PROVIDER", raising=False)
    with pytest.raises(ValidationError):
        build_blobs(Settings(database_url=DB, env="dev"))
