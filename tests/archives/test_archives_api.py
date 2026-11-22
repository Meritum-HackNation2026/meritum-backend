"""Archiving a page: enqueue, poll, read, download and delete, owner or moderator."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any, override

from fastapi.testclient import TestClient
from meritum_core.jobs.contracts import ARCHIVE_PAGE
from meritum_core.jobs.fakes import InMemoryJobQueue
from meritum_core.jobs.ports import JobState
from meritum_core.shared.blobs import (
    BlobKind,
    BlobProvider,
    BlobSettings,
    build_blob_store,
)

from meritum_backend.archives import ArchiveRecord
from meritum_backend.archives.adapters import MemoryArchiveStore
from meritum_backend.archives.api import get_archive_store, is_moderator
from meritum_backend.checks.constants import SESSION_HEADER
from meritum_backend.jobs.api import get_jobs
from meritum_backend.limits import limiter
from meritum_backend.main import create_app
from meritum_backend.settings import Settings

OWNER = "0b6f3c1e-5d2a-4f7b-9c8e-1a2b3c4d5e6f"
STRANGER = "9f8e7d6c-5b4a-4321-8fed-cba987654321"
URL = "https://www.gov.pl/web/rcb"
NOW = datetime.now(UTC)


class Queue(InMemoryJobQueue):
    """The fake queue with a finished output per workflow."""

    def __init__(self) -> None:
        super().__init__()
        self.outputs: dict[str, dict[str, Any]] = {}

    @override
    async def state(self, workflow_id: str) -> JobState | None:
        if workflow_id in self.outputs:
            return JobState(
                workflow_id=workflow_id,
                status="SUCCESS",
                output=self.outputs[workflow_id],
            )
        return await super().state(workflow_id)


def _client(
    store: MemoryArchiveStore, jobs: Queue, *, moderator: bool = False
) -> TestClient:
    limiter.reset()
    app = create_app(Settings())
    app.state.blobs = build_blob_store(BlobSettings(provider=BlobProvider.MEMORY))
    app.dependency_overrides[get_jobs] = lambda: jobs
    app.dependency_overrides[get_archive_store] = lambda: store
    app.dependency_overrides[is_moderator] = lambda: moderator
    return TestClient(app)


def _stored(client: TestClient, store: MemoryArchiveStore) -> ArchiveRecord:
    blobs = client.app.state.blobs  # ty: ignore[missing-attribute]
    ref = asyncio.run(
        blobs.put(
            b"RCB ostrzega.",
            kind=BlobKind.DATASET,
            content_type="text/plain; charset=utf-8",
            expires_at=NOW + timedelta(days=30),
        )
    )
    record = ArchiveRecord(
        archive_id="a" * 32,
        blob_id=ref.blob_id,
        url=URL,
        owner_id=OWNER,
        sha256="f" * 64,
        archived_at=NOW,
        expires_at=NOW + timedelta(days=30),
    )
    store.records[record.archive_id] = record
    return record


def test_post_enqueues_archive_page_for_the_session() -> None:
    jobs = Queue()
    response = _client(MemoryArchiveStore(), jobs).post(
        "/api/v1/archives", json={"url": URL}, headers={SESSION_HEADER: OWNER}
    )
    assert response.status_code == 202
    archive_id = response.json()["archive_id"]
    [job] = jobs.enqueued
    assert job.spec == ARCHIVE_PAGE
    assert job.workflow_id == archive_id
    assert job.payload == ARCHIVE_PAGE.input(
        archive_id=archive_id, url=URL, owner_id=OWNER
    )


def test_post_refuses_a_non_http_url_and_an_anonymous_caller() -> None:
    client = _client(MemoryArchiveStore(), Queue())
    bad = client.post(
        "/api/v1/archives",
        json={"url": "file:///etc/passwd"},
        headers={SESSION_HEADER: OWNER},
    )
    anonymous = client.post("/api/v1/archives", json={"url": URL})
    assert bad.status_code == 422
    assert anonymous.status_code == 400


def test_get_shows_pending_then_the_copy_to_its_owner_only() -> None:
    store, jobs = MemoryArchiveStore(), Queue()
    client = _client(store, jobs)
    archive_id = client.post(
        "/api/v1/archives", json={"url": URL}, headers={SESSION_HEADER: OWNER}
    ).json()["archive_id"]
    pending = client.get(f"/api/v1/archives/{archive_id}")
    assert pending.json()["status"] == "pending"
    record = _stored(client, store)
    done = client.get(
        f"/api/v1/archives/{record.archive_id}", headers={SESSION_HEADER: OWNER}
    )
    assert done.json()["status"] == "done"
    assert done.json()["sha256"] == record.sha256
    stranger = client.get(
        f"/api/v1/archives/{record.archive_id}", headers={SESSION_HEADER: STRANGER}
    )
    assert stranger.status_code == 404


def test_a_moderator_reads_and_downloads_any_copy() -> None:
    store = MemoryArchiveStore()
    client = _client(store, Queue(), moderator=True)
    record = _stored(client, store)
    content = client.get(f"/api/v1/archives/{record.archive_id}/content")
    assert content.status_code == 200
    assert content.content == b"RCB ostrzega."


def test_a_refusal_is_shown_with_its_message() -> None:
    jobs = Queue()
    archive_id = "b" * 32
    jobs.outputs[archive_id] = ARCHIVE_PAGE.output(
        archive_id=archive_id, owner_id=OWNER, refusal="login_wall", message="Logowanie"
    ).model_dump(mode="json")
    client = _client(MemoryArchiveStore(), jobs)
    response = client.get(
        f"/api/v1/archives/{archive_id}", headers={SESSION_HEADER: OWNER}
    )
    assert response.json() == {
        "archive_id": archive_id,
        "status": "refused",
        "refusal": "login_wall",
        "message": "Logowanie",
    }


def test_the_owner_deletes_the_copy_and_its_text() -> None:
    store = MemoryArchiveStore()
    client = _client(store, Queue())
    record = _stored(client, store)
    other = client.delete(
        f"/api/v1/archives/{record.archive_id}", headers={SESSION_HEADER: STRANGER}
    )
    assert other.status_code == 404
    gone = client.delete(
        f"/api/v1/archives/{record.archive_id}", headers={SESSION_HEADER: OWNER}
    )
    assert gone.status_code == 204
    assert store.records == {}
