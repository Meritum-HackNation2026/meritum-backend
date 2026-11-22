import asyncio
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from meritum_core.jobs.constants import READINESS_KEY
from meritum_core.jobs.fakes import InMemoryJobQueue
from tests.conftest import FakeClock, MakeProbe, worker_report

from meritum_backend.health import readiness
from meritum_backend.health.api import get_readiness
from meritum_backend.health.readiness import ReadinessProbe
from meritum_backend.jobs.api import get_jobs
from meritum_backend.limits import CheckGate, LimitSettings, get_check_gate
from meritum_backend.limits.adapters import FixedPendingChecks, MemoryRateCounter
from meritum_backend.main import create_app
from meritum_backend.settings import Settings


def app_with(probe: ReadinessProbe) -> FastAPI:
    app = create_app(Settings())
    gate = CheckGate(MemoryRateCounter(), FixedPendingChecks(), LimitSettings())
    app.dependency_overrides[get_check_gate] = lambda: gate
    app.dependency_overrides[get_readiness] = lambda: probe
    return app


SESSION = {"X-Meritum-Session": "session-0123456789"}
CHECK = {"channel": "web", "text": "Czy jutro jest strajk generalny?"}


def client_with(
    make_probe: MakeProbe, jobs: InMemoryJobQueue, missing: str
) -> TestClient:
    probe = make_probe(InMemoryJobQueue(), report=worker_report([missing]))
    app = app_with(probe)
    app.dependency_overrides[get_jobs] = lambda: jobs
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
    app = app_with(probe)
    app.dependency_overrides[get_jobs] = InMemoryJobQueue
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


def post_without_worker_report(make_probe: MakeProbe) -> int:
    probe = make_probe(InMemoryJobQueue())  # the worker never answered
    app = app_with(probe)
    app.dependency_overrides[get_jobs] = InMemoryJobQueue
    return (
        TestClient(app).post("/api/v1/checks", json=CHECK, headers=SESSION).status_code
    )


def test_missing_worker_report_does_not_block_checks(
    make_probe: MakeProbe, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="meritum_backend"):
        assert post_without_worker_report(make_probe) == 202
    assert "no worker readiness report" in caplog.text


def test_switch_blocks_checks_without_worker_report(
    make_probe: MakeProbe, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(readiness, "BLOCK_CHECKS_WITHOUT_WORKER_REPORT", True)
    assert post_without_worker_report(make_probe) == 503


EUVS_DOWN = worker_report().model_copy(
    update={"unavailable_providers": ["euvsdisinfo"]}
)


def test_unreachable_optional_provider_does_not_block_checks(
    make_probe: MakeProbe,
) -> None:
    app = app_with(make_probe(InMemoryJobQueue(), report=EUVS_DOWN))
    app.dependency_overrides[get_jobs] = InMemoryJobQueue
    response = TestClient(app).post("/api/v1/checks", json=CHECK, headers=SESSION)
    assert response.status_code == 202


def test_unreachable_provider_is_logged_as_degraded(
    make_probe: MakeProbe, caplog: pytest.LogCaptureFixture
) -> None:
    probe = make_probe(InMemoryJobQueue(), report=EUVS_DOWN)
    with caplog.at_level(logging.WARNING, logger="meritum_backend"):
        asyncio.run(probe.log_startup())
    assert "degraded" in caplog.text
    assert "not ready" not in caplog.text
