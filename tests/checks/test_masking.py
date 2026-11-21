from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlsplit

import pytest
from fastapi.testclient import TestClient
from meritum_core.checks import CheckRequest
from meritum_core.jobs.contracts import CheckInput
from meritum_core.jobs.fakes import InMemoryJobQueue

from meritum_backend.checks.constants import SESSION_HEADER

SESSION = {SESSION_HEADER: "session-0123456789"}


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


def test_masking_a_link_keeps_its_parameters(
    client: TestClient, jobs: InMemoryJobQueue
) -> None:
    sent = "https://example.com/a?q=a%26b%3Dc+d&mail=jan%40x.pl"
    body = {"channel": "web", "url": sent}
    assert client.post("/api/v1/checks", json=body, headers=SESSION).status_code == 202
    [job] = jobs.enqueued
    assert isinstance(job.payload, CheckInput)
    query = parse_qsl(urlsplit(str(job.payload.request.url)).query)
    assert query == [("q", "a&b=c d"), ("mail", "[e-mail]")]


def test_text_within_the_limit_stays_accepted_after_masking(
    client: TestClient, jobs: InMemoryJobQueue
) -> None:
    body = {"channel": "web", "text": "a@b.pl " + "x" * 3993}
    assert client.post("/api/v1/checks", json=body, headers=SESSION).status_code == 202
    [job] = jobs.enqueued
    assert isinstance(job.payload, CheckInput)
    assert job.payload.request.text is not None
    assert job.payload.request.text.startswith("[e-mail] ")
    assert len(job.payload.request.text) == 4000


def test_personal_data_in_a_link_fragment_is_masked(
    client: TestClient, jobs: InMemoryJobQueue
) -> None:
    body = {"channel": "web", "url": "https://x.pl/a#tel=600700800"}
    assert client.post("/api/v1/checks", json=body, headers=SESSION).status_code == 202
    [job] = jobs.enqueued
    assert "600700800" not in job.payload.model_dump_json()


def test_link_with_credentials_is_refused(
    client: TestClient, jobs: InMemoryJobQueue
) -> None:
    body = {"channel": "web", "url": "https://jan:600700800@x.pl/a"}
    response = client.post("/api/v1/checks", json=body, headers=SESSION)
    assert response.json() == {"message_key": "errors.invalid_url"}
    assert jobs.enqueued == []


def test_link_too_long_after_masking_is_an_invalid_link(
    client: TestClient, jobs: InMemoryJobQueue
) -> None:
    start = "https://x.pl/?mail=a%40b.pl&p="
    body = {"channel": "web", "url": start + "x" * (2083 - len(start))}
    response = client.post("/api/v1/checks", json=body, headers=SESSION)
    assert response.json() == {"message_key": "errors.invalid_url"}
    assert jobs.enqueued == []


def test_masking_never_leaves_half_a_marker(
    client: TestClient, jobs: InMemoryJobQueue
) -> None:
    body = {"channel": "web", "text": "x" * 3993 + " a@b.pl"}
    assert client.post("/api/v1/checks", json=body, headers=SESSION).status_code == 202
    [job] = jobs.enqueued
    assert isinstance(job.payload, CheckInput)
    assert job.payload.request.text == "x" * 3993 + " "


def test_link_is_enqueued_as_sent(client: TestClient, jobs: InMemoryJobQueue) -> None:
    body = {"channel": "web", "url": "https://example.com/a?b=1"}
    assert client.post("/api/v1/checks", json=body, headers=SESSION).status_code == 202
    [job] = jobs.enqueued
    assert isinstance(job.payload, CheckInput)
    assert str(job.payload.request.url) == body["url"]
