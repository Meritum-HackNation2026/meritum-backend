from fastapi.testclient import TestClient
from meritum_core.jobs.fakes import InMemoryJobQueue
from tests.conftest import MakeProbe, worker_report

from meritum_backend.health.api import get_readiness
from meritum_backend.jobs.api import get_jobs
from meritum_backend.main import create_app
from meritum_backend.settings import Settings

SESSION = {"X-Meritum-Session": "session-0123456789"}
CHECK = {"channel": "web", "text": "Czy jutro jest strajk generalny?"}


def client_with(
    make_probe: MakeProbe, jobs: InMemoryJobQueue, missing: str
) -> TestClient:
    probe = make_probe(InMemoryJobQueue(), report=worker_report([missing]))
    app = create_app(Settings())
    app.dependency_overrides[get_jobs] = lambda: jobs
    app.dependency_overrides[get_readiness] = lambda: probe
    return TestClient(app)


def test_not_ready_service_refuses_checks_without_naming_keys(
    make_probe: MakeProbe,
) -> None:
    jobs = InMemoryJobQueue()
    response = client_with(make_probe, jobs, "LLM_KEY").post(
        "/api/v1/checks", json=CHECK, headers=SESSION
    )
    assert response.status_code == 503
    assert response.json() == {
        "status": "technical_failure",
        "code": "not_ready",
        "message_key": "status_hint.technical_failure",
    }
    assert "LLM_KEY" not in response.text
    assert jobs.enqueued == []


def test_bad_input_is_still_422_when_not_ready(make_probe: MakeProbe) -> None:
    client = client_with(make_probe, InMemoryJobQueue(), "LLM_KEY")
    response = client.post("/api/v1/checks", json={"channel": "web"}, headers=SESSION)
    assert response.status_code == 422
