from datetime import UTC, datetime
from typing import override

import pytest
from fastapi.testclient import TestClient
from meritum_core.checks import CheckRequest, CheckResult
from meritum_core.jobs.contracts import CONTRACT_VERSION, CheckInput, CheckOutput
from meritum_core.jobs.fakes import InMemoryJobQueue
from meritum_core.jobs.ports import JobState

from meritum_backend.checks.constants import SESSION_HEADER
from meritum_backend.jobs.api import get_jobs
from meritum_backend.main import create_app
from meritum_backend.settings import Settings

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


@pytest.fixture
def jobs() -> InMemoryJobQueue:
    return InMemoryJobQueue()


@pytest.fixture
def client(jobs: InMemoryJobQueue) -> TestClient:
    app = create_app(Settings(database_url="postgresql://x:x@127.0.0.1:1/x"))
    app.dependency_overrides[get_jobs] = lambda: jobs
    return TestClient(app)


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


def test_422_does_not_echo_the_sent_text(client: TestClient) -> None:
    body = {"channel": "web", "text": "mail jan@example.com " + "a" * 4000}
    response = client.post("/api/v1/checks", json=body, headers=SESSION)
    assert "jan@example.com" not in response.text


def test_text_is_masked_and_enqueued_with_session_and_time(
    client: TestClient, jobs: InMemoryJobQueue
) -> None:
    before = datetime.now(UTC)
    body = {"channel": "extension", "text": "Pisz na jan@example.com"}
    response = client.post("/api/v1/checks", json=body, headers=SESSION)
    assert response.status_code == 202
    [job] = jobs.enqueued
    assert job.spec.name == "check"
    assert job.workflow_id == response.json()["check_id"]
    assert isinstance(job.payload, CheckInput)
    assert job.payload.request == CheckRequest(
        channel="extension", text="Pisz na [e-mail]"
    )
    assert job.payload.session_id == SESSION[SESSION_HEADER]
    assert before <= job.payload.received_at <= datetime.now(UTC)


@pytest.mark.parametrize(
    ("sent", "kept"),
    [
        ("tel. 600 700 800, PESEL 44051401359", "tel. [telefon], PESEL [PESEL]"),
        ("Czy to prawda?", "Czy to prawda?"),
    ],
)
def test_phone_and_pesel_are_masked(
    client: TestClient, jobs: InMemoryJobQueue, sent: str, kept: str
) -> None:
    body = {"channel": "web", "text": sent}
    assert client.post("/api/v1/checks", json=body, headers=SESSION).status_code == 202
    [job] = jobs.enqueued
    assert isinstance(job.payload, CheckInput)
    assert job.payload.request.text == kept


def test_personal_data_in_a_link_query_is_masked(
    client: TestClient, jobs: InMemoryJobQueue
) -> None:
    body = {"channel": "web", "url": "https://example.com/post/1?mail=jan%40x.pl"}
    assert client.post("/api/v1/checks", json=body, headers=SESSION).status_code == 202
    [job] = jobs.enqueued
    assert isinstance(job.payload, CheckInput)
    url = str(job.payload.request.url)
    assert url.startswith("https://example.com/post/1?mail=")
    assert "jan" not in url


def test_link_is_enqueued_as_sent(client: TestClient, jobs: InMemoryJobQueue) -> None:
    body = {"channel": "web", "url": "https://example.com/a?b=1"}
    assert client.post("/api/v1/checks", json=body, headers=SESSION).status_code == 202
    [job] = jobs.enqueued
    assert isinstance(job.payload, CheckInput)
    assert str(job.payload.request.url) == body["url"]


@pytest.mark.parametrize(
    ("body", "headers"),
    [
        ({"channel": "web", "text": "Czy to prawda?"}, {}),
        ({"channel": "discord", "text": "Czy to prawda?"}, SESSION),
    ],
)
def test_without_a_browser_session_nothing_starts(
    client: TestClient,
    jobs: InMemoryJobQueue,
    body: dict[str, str],
    headers: dict[str, str],
) -> None:
    assert client.post("/api/v1/checks", json=body, headers=headers).status_code == 400
    assert jobs.enqueued == []


def test_unknown_check_is_404(client: TestClient) -> None:
    assert client.get("/api/v1/checks/nope").status_code == 404


def test_another_workflow_is_not_a_check() -> None:
    app = create_app(Settings(database_url="postgresql://x:x@127.0.0.1:1/x"))
    app.dependency_overrides[get_jobs] = PingJobs
    assert TestClient(app).get("/api/v1/checks/wf-1").status_code == 404


def test_running_check_has_steps_and_no_result(client: TestClient) -> None:
    body = {"channel": "web", "text": "Czy to prawda?"}
    check_id = client.post("/api/v1/checks", json=body, headers=SESSION).json()[
        "check_id"
    ]
    response = client.get(f"/api/v1/checks/{check_id}")
    assert response.json()["steps"] == [{"code": "receive", "status": "done"}]
    assert response.json()["result"] is None
    assert "AI-Disclosure" not in response.headers


def test_finished_check_reads_the_result_from_the_workflow_output() -> None:
    app = create_app(Settings(database_url="postgresql://x:x@127.0.0.1:1/x"))
    app.dependency_overrides[get_jobs] = FinishedJobs
    response = TestClient(app).get("/api/v1/checks/wf-1")
    assert response.json()["result"]["ai_disclosure"] is True
    assert response.headers["AI-Disclosure"] == "mode=ai-originated"


def test_openapi_documents_both_routes_and_the_ai_marker(client: TestClient) -> None:
    paths = client.get("/api/v1/openapi.json").json()["paths"]
    assert "post" in paths["/api/v1/checks"]
    ok = paths["/api/v1/checks/{check_id}"]["get"]["responses"]["200"]
    assert "AI-Disclosure" in ok["headers"]
