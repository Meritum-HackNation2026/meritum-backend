import asyncio
import logging

import pytest
from fastapi.testclient import TestClient
from meritum_core.jobs.constants import READINESS_KEY
from meritum_core.jobs.fakes import InMemoryJobQueue
from pydantic import SecretStr
from tests.conftest import FakeBlobStore, FakeClock, MakeProbe, worker_report

from meritum_backend.health.api import get_readiness
from meritum_backend.health.models import Problems
from meritum_backend.health.readiness import ReadinessProbe
from meritum_backend.main import create_app
from meritum_backend.settings import Settings

SALT = "very-secret-salt"


def client_for(probe: ReadinessProbe) -> TestClient:
    app = create_app(Settings())
    app.dependency_overrides[get_readiness] = lambda: probe
    return TestClient(app)


def test_everything_set_is_ready(make_probe: MakeProbe) -> None:
    probe = make_probe(InMemoryJobQueue(), report=worker_report())
    response = client_for(probe).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "env": "local",
        "database": "ok",
        "worker": "ok",
        "missing_env": [],
        "unavailable_providers": [],
    }


def test_unreachable_database_is_not_ready(make_probe: MakeProbe) -> None:
    probe = make_probe(InMemoryJobQueue(), report=worker_report(), database_ok=False)
    response = client_for(probe).get("/api/v1/health")
    assert response.status_code == 503
    assert response.json()["database"] == "unavailable"


@pytest.mark.parametrize(
    ("settings", "missing"),
    [
        (Settings(), ["MERITUM_CHANNEL_HASH_SALT"]),
        (
            Settings(channel_hash_salt=SecretStr(SALT), discord_public_key="ab"),
            ["MERITUM_DISCORD_BOT_TOKEN"],
        ),
    ],
)
def test_api_variables_are_named_without_values(
    make_probe: MakeProbe, settings: Settings, missing: list[str]
) -> None:
    probe = make_probe(InMemoryJobQueue(), report=worker_report(), settings=settings)
    response = client_for(probe).get("/api/v1/health")
    assert response.status_code == 503
    assert response.json()["missing_env"] == missing
    assert SALT not in response.text


def test_api_and_worker_lists_are_joined(make_probe: MakeProbe) -> None:
    blob = FakeBlobStore(Problems(["MERITUM_BLOB_PROVIDER"], ["blob_store"]))
    report = worker_report(["MERITUM_LLM_API_KEY", "MERITUM_BLOB_PROVIDER"])
    probe = make_probe(InMemoryJobQueue(), report=report, blob=blob)
    body = client_for(probe).get("/api/v1/health").json()
    assert body["missing_env"] == ["MERITUM_BLOB_PROVIDER", "MERITUM_LLM_API_KEY"]
    assert body["unavailable_providers"] == ["blob_store"]


async def unreachable(*_: object, **__: object) -> str:  # ruff: ignore[unused-async] -- replaces an async method
    raise OSError


def test_unreachable_queue_means_worker_not_reported(
    make_probe: MakeProbe, monkeypatch: pytest.MonkeyPatch
) -> None:
    jobs = InMemoryJobQueue()
    monkeypatch.setattr(jobs, "enqueue", unreachable)
    body = client_for(make_probe(jobs)).get("/api/v1/health").json()
    assert (body["status"], body["worker"]) == ("degraded", "not_reported")


def test_fresh_report_enqueues_no_new_workflow(make_probe: MakeProbe) -> None:
    jobs = InMemoryJobQueue()
    client = client_for(make_probe(jobs, report=worker_report()))
    client.get("/api/v1/health")
    client.get("/api/v1/health")
    assert [job.spec.name for job in jobs.enqueued] == ["readiness"]


def test_quiet_period_keeps_a_live_worker_ready(make_probe: MakeProbe) -> None:
    clock = FakeClock()
    jobs = InMemoryJobQueue()
    probe = make_probe(jobs, report=worker_report(), clock=clock)
    client = client_for(probe)
    assert client.get("/api/v1/health").json()["worker"] == "ok"
    clock.now = 130.0  # nobody asked for over two minutes
    assert client.get("/api/v1/health").json()["worker"] == "ok"
    jobs.set_event(
        probe.workflow_id, READINESS_KEY, worker_report()
    )  # answers the refresh
    clock.now = 200.0
    assert client.get("/api/v1/health").json()["worker"] == "ok"


def test_worker_silent_after_a_refresh_is_not_reported(make_probe: MakeProbe) -> None:
    clock = FakeClock()
    probe = make_probe(InMemoryJobQueue(), report=worker_report(), clock=clock)
    client = client_for(probe)
    assert client.get("/api/v1/health").json()["worker"] == "ok"
    clock.now = 60.0  # the report is due: a new workflow is enqueued
    assert client.get("/api/v1/health").json()["worker"] == "ok"
    clock.now = 119.0
    assert client.get("/api/v1/health").json()["worker"] == "ok"
    clock.now = 120.0  # no answer for a whole refresh period
    body = client.get("/api/v1/health").json()
    assert (body["status"], body["worker"]) == ("degraded", "not_reported")


def test_startup_log_names_variables_never_values(
    make_probe: MakeProbe, caplog: pytest.LogCaptureFixture
) -> None:
    settings = Settings(discord_public_key="ab", discord_bot_token=None)
    probe = make_probe(InMemoryJobQueue(), settings=settings)
    with caplog.at_level(logging.INFO, logger="meritum_backend"):
        asyncio.run(probe.log_startup())
    assert "MERITUM_CHANNEL_HASH_SALT" in caplog.text
    assert "MERITUM_DISCORD_BOT_TOKEN" in caplog.text
    assert "worker not_reported" in caplog.text


def test_checks_reuse_a_fresh_report(make_probe: MakeProbe) -> None:
    jobs = InMemoryJobQueue()
    probe = make_probe(jobs)
    assert not asyncio.run(probe.ready())
    jobs.set_event(probe.workflow_id, READINESS_KEY, worker_report())
    assert not asyncio.run(probe.ready())  # the cached report
    assert asyncio.run(probe.check()).status == "ok"
    assert asyncio.run(probe.ready())


def test_unanswered_workflow_is_asked_again(make_probe: MakeProbe) -> None:
    clock = FakeClock()
    jobs = InMemoryJobQueue()
    client = client_for(make_probe(jobs, clock=clock))
    client.get("/api/v1/health")
    clock.now = 61.0  # e.g. failed or taken by a worker that did not know it
    client.get("/api/v1/health")  # gives up on the first workflow
    body = client.get("/api/v1/health").json()  # enqueues the next one
    assert body["worker"] == "not_reported"
    assert len({job.workflow_id for job in jobs.enqueued}) == 2


def test_rare_requests_still_see_a_worker_that_came_back(make_probe: MakeProbe) -> None:
    clock = FakeClock()
    jobs = InMemoryJobQueue()
    client = client_for(make_probe(jobs, clock=clock))
    seen = []
    for now in (0.0, 61.0, 200.0, 300.0, 400.0, 500.0):  # less than once a minute
        clock.now = now
        seen.append(client.get("/api/v1/health").json()["worker"])
        if now >= 100.0:  # the worker is back and answers what was enqueued
            for job in jobs.enqueued:
                jobs.set_event(job.workflow_id, READINESS_KEY, worker_report())
    assert seen[-1] == "ok"
