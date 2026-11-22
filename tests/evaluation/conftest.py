"""Fixtures of the evaluation tests: the app over a fake worker."""

import pytest
from fastapi import FastAPI
from tests.evaluation.fakes import ADMIN, Queue

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
    app.dependency_overrides[get_jobs] = lambda: queue
    return app
