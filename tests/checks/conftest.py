"""Fixtures of the checks tests: the app on core's InMemoryJobQueue."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from meritum_core.jobs.fakes import InMemoryJobQueue

from meritum_backend.jobs.api import get_jobs
from meritum_backend.main import create_app
from meritum_backend.settings import Settings

type MakeClient = Callable[[InMemoryJobQueue], TestClient]


@pytest.fixture
def make_client() -> MakeClient:
    def make(jobs: InMemoryJobQueue) -> TestClient:
        app = create_app(Settings(database_url="postgresql://x:x@127.0.0.1:1/x"))
        app.dependency_overrides[get_jobs] = lambda: jobs
        return TestClient(app)

    return make


@pytest.fixture
def jobs() -> InMemoryJobQueue:
    return InMemoryJobQueue()


@pytest.fixture
def client(make_client: MakeClient, jobs: InMemoryJobQueue) -> TestClient:
    return make_client(jobs)
