"""Fixtures of the checks tests: the app on core's InMemoryJobQueue."""

from typing import Protocol

import pytest
from fastapi.testclient import TestClient
from meritum_core.jobs.fakes import InMemoryJobQueue
from tests.conftest import MakeProbe, worker_report

from meritum_backend.health.api import get_readiness
from meritum_backend.jobs.api import get_jobs
from meritum_backend.limits import (
    CheckGate,
    LimitSettings,
    get_check_gate,
)
from meritum_backend.limits.adapters import FixedPendingChecks, MemoryRateCounter
from meritum_backend.main import create_app
from meritum_backend.settings import Settings, get_settings


class MakeClient(Protocol):
    def __call__(
        self, jobs: InMemoryJobQueue, settings: Settings | None = None
    ) -> TestClient: ...


OFFLINE_DB = "postgresql://x:x@127.0.0.1:1/x"


@pytest.fixture
def gate() -> CheckGate:
    return CheckGate(MemoryRateCounter(), FixedPendingChecks(), LimitSettings())


@pytest.fixture
def make_client(gate: CheckGate, make_probe: MakeProbe) -> MakeClient:
    def make(jobs: InMemoryJobQueue, settings: Settings | None = None) -> TestClient:
        settings = settings or Settings(database_url=OFFLINE_DB)
        app = create_app(settings)
        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_jobs] = lambda: jobs
        app.dependency_overrides[get_check_gate] = lambda: gate
        # own queue: the readiness job stays out of `jobs.enqueued`
        probe = make_probe(InMemoryJobQueue(), report=worker_report())
        app.dependency_overrides[get_readiness] = lambda: probe
        return TestClient(app)

    return make


@pytest.fixture
def jobs() -> InMemoryJobQueue:
    return InMemoryJobQueue()


@pytest.fixture
def client(make_client: MakeClient, jobs: InMemoryJobQueue) -> TestClient:
    return make_client(jobs)
