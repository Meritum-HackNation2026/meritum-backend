"""Fixtures of the evaluation tests: the app over a fake worker."""

import pytest
from fastapi import FastAPI
from meritum_core.shared.blobs.adapters import MemoryBlobStore
from tests.evaluation.fakes import ADMIN, Queue

from meritum_backend.evaluation.api import get_blobs
from meritum_backend.jobs.api import get_jobs
from meritum_backend.main import create_app
from meritum_backend.settings import Settings


@pytest.fixture
def queue() -> Queue:
    return Queue()


@pytest.fixture
def app(queue: Queue) -> FastAPI:
    settings = Settings(
        database_url="postgresql://x:x@127.0.0.1:1/x",
        admin_emails=ADMIN,
        public_url="https://meritum.example",
    )
    app = create_app(settings)
    blobs = MemoryBlobStore()
    app.dependency_overrides[get_jobs] = lambda: queue
    app.dependency_overrides[get_blobs] = lambda: blobs
    return app
