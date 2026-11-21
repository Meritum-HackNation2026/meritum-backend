from collections.abc import Callable
from dataclasses import replace
from typing import cast, override

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from meritum_core.checks import AnalysisStatus, CheckResult
from meritum_core.jobs.constants import PROGRESS_KEY
from meritum_core.jobs.contracts import CONTRACT_VERSION, CheckInput, CheckOutput
from meritum_core.jobs.fakes import InMemoryJobQueue
from meritum_core.jobs.ports import JobState

from meritum_backend.checks.constants import RECEIVED, SESSION_HEADER
from meritum_backend.limits import CheckGate, get_check_gate
from meritum_backend.limits.adapters import FixedPendingChecks

from .cache_fakes import FinishedWorker

type MakeClient = Callable[[InMemoryJobQueue], TestClient]

SESSION = {SESSION_HEADER: "session-0123456789"}


class FinishedJobs(InMemoryJobQueue):
    """Reports every job as finished with a result in the workflow output."""

    @override
    async def state(self, workflow_id: str) -> JobState | None:
        result = CheckResult(
            check_id=workflow_id,
            status="out_of_scope",
            message="To nie jest pytanie o informację.",
            corpus_version="test",
        )
        output = CheckOutput(result=result).model_dump(mode="json")
        return JobState(workflow_id=workflow_id, status="SUCCESS", output=output)


class PingJobs(InMemoryJobQueue):
    """Reports every job as a finished ping."""

    @override
    async def state(self, workflow_id: str) -> JobState | None:
        output = {"contract_version": CONTRACT_VERSION, "message": "pong"}
        return JobState(workflow_id=workflow_id, status="SUCCESS", output=output)


@pytest.mark.parametrize(
    ("body", "key"),
    [
        ({"channel": "web"}, "errors.empty"),
        ({"channel": "web", "text": ""}, "errors.empty"),
        ({"channel": "web", "text": "  ab  "}, "errors.empty"),
        ({"channel": "web", "text": "a" * 4001}, "errors.too_long"),
        ({"channel": "web", "url": "example.com"}, "errors.invalid_url"),
        ({"channel": "web", "text": "ftp://example.com/plik"}, "errors.invalid_url"),
    ],
)
def test_bad_input_gets_a_copy_key_and_starts_nothing(
    client: TestClient, jobs: InMemoryJobQueue, body: dict[str, str], key: str
) -> None:
    response = client.post("/api/v1/checks", json=body, headers=SESSION)
    assert response.status_code == 422
    assert response.json() == {"message_key": key}
    assert jobs.enqueued == []


@pytest.mark.parametrize(
    ("body", "headers", "detail"),
    [
        ({"channel": "web", "text": "Czy to prawda?"}, {}, SESSION_HEADER),
        ({"channel": "web", "text": "Czy to prawda?"}, {SESSION_HEADER: "x"}, "valid"),
        (
            {"channel": "web", "text": "Czy to prawda?", "session_id": "other-0123456"},
            SESSION,
            "valid",
        ),
    ],
)
def test_without_a_browser_session_nothing_starts(
    client: TestClient,
    jobs: InMemoryJobQueue,
    body: dict[str, str],
    headers: dict[str, str],
    detail: str,
) -> None:
    response = client.post("/api/v1/checks", json=body, headers=headers)
    assert response.status_code == 400
    assert detail in response.json()["detail"]
    assert jobs.enqueued == []


def test_unknown_check_is_404(client: TestClient) -> None:
    assert client.get("/api/v1/checks/nope").status_code == 404


def test_finished_check_without_result_in_progress_reads_the_output(
    make_client: MakeClient,
) -> None:
    jobs = FinishedJobs()
    status = AnalysisStatus(check_id="wf-1", steps=[RECEIVED])
    jobs.publish("wf-1", PROGRESS_KEY, status)
    response = make_client(jobs).get("/api/v1/checks/wf-1")
    assert response.json()["result"]["status"] == "out_of_scope"


def test_another_workflow_is_not_a_check(make_client: MakeClient) -> None:
    assert make_client(PingJobs()).get("/api/v1/checks/wf-1").status_code == 404


def test_running_check_has_steps_and_no_result(client: TestClient) -> None:
    body = {"channel": "web", "text": "Czy to prawda?"}
    check_id = client.post("/api/v1/checks", json=body, headers=SESSION).json()[
        "check_id"
    ]
    response = client.get(f"/api/v1/checks/{check_id}")
    assert response.json()["steps"] == [{"code": "receive", "status": "done"}]
    assert response.json()["result"] is None
    assert "AI-Disclosure" not in response.headers


def test_finished_check_reads_the_result_from_the_workflow_output(
    make_client: MakeClient,
) -> None:
    response = make_client(FinishedJobs()).get("/api/v1/checks/wf-1")
    assert response.json()["result"]["ai_disclosure"] is True
    assert response.headers["AI-Disclosure"] == "mode=ai-originated"


def test_openapi_documents_both_routes_and_the_ai_marker(client: TestClient) -> None:
    paths = client.get("/api/v1/openapi.json").json()["paths"]
    assert "post" in paths["/api/v1/checks"]
    ok = paths["/api/v1/checks/{check_id}"]["get"]["responses"]["200"]
    assert "AI-Disclosure" in ok["headers"]


WEB_TEXT = {"channel": "web", "text": "Czy szczepionki powodują autyzm?"}


def test_eleventh_check_from_one_address_gets_429(
    client: TestClient, jobs: InMemoryJobQueue
) -> None:
    for _ in range(10):
        assert client.post("/api/v1/checks", json=WEB_TEXT, headers=SESSION).is_success
    response = client.post("/api/v1/checks", json=WEB_TEXT, headers=SESSION)
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    assert response.json() == {"message_key": "errors.rate_limited"}
    assert len(jobs.enqueued) == 10


def test_full_queue_gets_429_busy_and_enqueues_nothing(
    make_client: MakeClient, jobs: InMemoryJobQueue, gate: CheckGate
) -> None:
    client = make_client(jobs)
    app = cast("FastAPI", client.app)
    app.dependency_overrides[get_check_gate] = lambda: replace(
        gate, pending=FixedPendingChecks(gate.limits.max_pending_checks)
    )
    response = client.post("/api/v1/checks", json=WEB_TEXT, headers=SESSION)
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "300"
    assert response.json() == {"message_key": "errors.busy"}
    assert jobs.enqueued == []


def test_rejected_input_does_not_use_up_the_budget(
    client: TestClient, jobs: InMemoryJobQueue
) -> None:
    bad_link = {"channel": "web", "url": "https://user:secret@example.com/a"}
    for _ in range(11):
        assert client.post(
            "/api/v1/checks", json=bad_link, headers=SESSION
        ).is_client_error
        assert client.post("/api/v1/checks", json=WEB_TEXT).status_code == 400
    assert client.post("/api/v1/checks", json=WEB_TEXT, headers=SESSION).is_success
    assert len(jobs.enqueued) == 1


def test_a_body_session_equal_to_the_header_starts_the_check(
    client: TestClient, jobs: InMemoryJobQueue
) -> None:
    body = {
        "channel": "web",
        "text": "Czy to prawda?",
        "session_id": "session-0123456789",
    }
    assert client.post("/api/v1/checks", json=body, headers=SESSION).status_code == 202
    (job,) = jobs.enqueued
    assert isinstance(job.payload, CheckInput)
    assert job.payload.session_id == job.payload.request.session_id


def test_the_ai_disclosure_header_names_the_model_of_the_ai_marker(
    make_client: MakeClient,
) -> None:
    client = make_client(FinishedWorker())
    body = {"channel": "web", "text": "Czy to prawda?"}
    check_id = client.post("/api/v1/checks", json=body, headers=SESSION).json()[
        "check_id"
    ]
    response = client.get(f"/api/v1/checks/{check_id}")
    assert response.headers["AI-Disclosure"] == (
        'mode=ai-originated; model="anthropic/claude-haiku-5-5";'
        ' provider="openrouter"; date=@1795262400'
    )
