from typing import Any

import pytest
from fastapi.testclient import TestClient
from meritum_core.jobs.contracts import CONTRACT_VERSION, WorkflowSpec
from meritum_core.jobs.ports import JobState
from pydantic import BaseModel

from meritum_backend.jobs.api import get_jobs
from meritum_backend.limits import limiter
from meritum_backend.main import create_app
from meritum_backend.settings import Settings, get_settings


class FakeJobs:
    def __init__(self) -> None:
        self.enqueued: list[tuple[str, dict[str, Any]]] = []
        self.states = {
            "wf-1": JobState(
                workflow_id="wf-1", status="SUCCESS", output={"message": "hej"}
            )
        }

    async def enqueue[In: BaseModel](
        self,
        spec: WorkflowSpec[In, Any],
        payload: In,
        *,
        workflow_id: str | None = None,
    ) -> str:
        self.enqueued.append((spec.name, payload.model_dump(mode="json")))
        return workflow_id or "wf-1"

    async def state(self, workflow_id: str) -> JobState | None:
        return self.states.get(workflow_id)


@pytest.fixture
def jobs() -> FakeJobs:
    return FakeJobs()


@pytest.fixture
def client(jobs: FakeJobs) -> TestClient:
    limiter.reset()  # counters are module-level; every test starts from zero
    settings = Settings(database_url="postgresql://x:x@127.0.0.1:1/x")
    app = create_app(settings)
    app.dependency_overrides[get_jobs] = lambda: jobs
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)  # no `with`: lifespan (DBOSClient) does not run


def test_liveness(client: TestClient) -> None:
    assert client.get("/api/v1/health/live").json() == {"status": "ok"}


def test_health_reports_unreachable_database(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json()["database"] == "unavailable"


def test_ping_enqueues_and_reads_state(client: TestClient, jobs: FakeJobs) -> None:
    response = client.post("/api/v1/jobs/ping", json={"message": "hej"})
    assert response.status_code == 202
    assert jobs.enqueued == [
        ("ping", {"contract_version": CONTRACT_VERSION, "message": "hej"})
    ]
    assert client.get("/api/v1/jobs/wf-1").json()["status"] == "SUCCESS"
    assert client.get("/api/v1/jobs/nope").status_code == 404


def test_ping_is_rate_limited_per_client(client: TestClient) -> None:
    for _ in range(10):
        assert client.post("/api/v1/jobs/ping").status_code == 202
    response = client.post("/api/v1/jobs/ping")
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    assert "Spróbuj ponownie" in response.json()["detail"]
    assert client.get("/api/v1/jobs/wf-1").status_code == 200  # reads are not limited
