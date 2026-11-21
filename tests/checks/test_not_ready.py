from fastapi.testclient import TestClient
from meritum_core.jobs.constants import READINESS_KEY
from meritum_core.jobs.fakes import InMemoryJobQueue
from tests.conftest import FakeClock, MakeProbe, worker_report

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


def test_fixed_worker_lets_checks_through_without_an_api_restart(
    make_probe: MakeProbe,
) -> None:
    clock = FakeClock()
    queue = InMemoryJobQueue()
    probe = make_probe(queue, report=worker_report(["LLM_KEY"]), clock=clock)
    app = create_app(Settings())
    app.dependency_overrides[get_jobs] = InMemoryJobQueue
    app.dependency_overrides[get_readiness] = lambda: probe
    client = TestClient(app)
    assert client.post("/api/v1/checks", json=CHECK, headers=SESSION).status_code == 503
    clock.now = 61.0  # the report is due: the API enqueues a new workflow
    assert client.post("/api/v1/checks", json=CHECK, headers=SESSION).status_code == 503
    ids = [job.workflow_id for job in queue.enqueued]
    assert len(set(ids)) == 2  # a finished workflow never runs again in DBOS
    # the restarted worker answers the readiness workflow the API enqueued next
    queue.set_event(ids[-1], READINESS_KEY, worker_report())
    clock.now = 92.0  # past the 30 s cache of the last answer
    assert client.post("/api/v1/checks", json=CHECK, headers=SESSION).status_code == 202
