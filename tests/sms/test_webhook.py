import asyncio
import time
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from meritum_core.checks.contracts import CheckRecord
from meritum_core.jobs.contracts import CHECK, DELETE_SUBJECT, CheckInput
from meritum_core.jobs.fakes import InMemoryJobQueue
from meritum_core.observability import AppRepositories

from meritum_backend.jobs.api import get_jobs
from meritum_backend.limits import CheckGate, LimitSettings, get_check_gate
from meritum_backend.limits.adapters import FixedPendingChecks, MemoryRateCounter
from meritum_backend.main import create_app
from meritum_backend.settings import Settings, get_settings
from meritum_backend.sms.constants import AI_NOTICE, FAILURE_TEXT, TOO_LONG_TEXT

from .conftest import GATEWAY_NUMBER, SENDER, URL, FakeSms, Post, event

CLAIM = "Wczoraj w Gdańsku wyłączono wszystkie bankomaty."
T0 = datetime(2026, 11, 21, 12, tzinfo=UTC)


def record_of(check_id: str, payload: CheckInput) -> CheckRecord:
    return CheckRecord(
        check_id=check_id,
        session_id=payload.session_id or "",
        channel="sms",
        channel_user_hash=payload.channel_user_hash,
        received_at=T0,
        answered_at=T0,
        question_masked=CLAIM,
        status="done",
        verdicts=["insufficient_evidence"],
        source_ids=[],
        corpus_version="test",
        models=[],
        retention_until=T0 + timedelta(days=30),
    )


def test_signed_sms_starts_one_check_with_hashed_sender(
    post: Post, jobs: InMemoryJobQueue
) -> None:
    response = post(event(CLAIM))

    assert response.status_code == 202
    [job] = jobs.enqueued
    assert job.spec == CHECK
    assert isinstance(job.payload, CheckInput)
    assert job.payload.request.channel == "sms"
    assert job.payload.request.text == CLAIM
    assert job.payload.channel_user_hash == job.payload.session_id
    assert SENDER not in job.payload.model_dump_json()


def test_same_number_gets_the_same_hash(post: Post, jobs: InMemoryJobQueue) -> None:
    post(event(CLAIM, event_id="e1"))
    post(event(CLAIM, event_id="e2"))

    first, second = (job.payload for job in jobs.enqueued)
    assert isinstance(first, CheckInput)
    assert isinstance(second, CheckInput)
    assert first.channel_user_hash == second.channel_user_hash


def test_bad_signature_is_401(post: Post, jobs: InMemoryJobQueue) -> None:
    response = post(event(CLAIM), key="another-key")

    assert response.status_code == 401
    assert jobs.enqueued == []


def test_timestamp_older_than_five_minutes_is_401(
    post: Post, jobs: InMemoryJobQueue
) -> None:
    stale = str(int(time.time()) - 301)

    response = post(event(CLAIM), timestamp=stale)

    assert response.status_code == 401
    assert jobs.enqueued == []


def test_repeated_event_starts_one_check(post: Post, jobs: InMemoryJobQueue) -> None:
    first = post(event(CLAIM))
    again = post(event(CLAIM))

    assert first.status_code == again.status_code == 202
    assert again.json() == {"status": "duplicate"}
    assert len(jobs.enqueued) == 1


def test_usun_deletes_the_numbers_checks(post: Post, jobs: InMemoryJobQueue) -> None:
    response = post(event(" usun "))

    assert response.status_code == 202
    assert response.json() == {"status": "deleted"}
    [job] = jobs.enqueued
    assert job.spec == DELETE_SUBJECT
    assert SENDER not in job.payload.model_dump_json()


def test_accepted_sms_gets_the_ai_notice_first(post: Post, sms: FakeSms) -> None:
    post(event(CLAIM))

    # the fake queue never finishes the check, so the reply is the failure text
    assert [text for _, text in sms.sent] == [AI_NOTICE, FAILURE_TEXT]
    assert {phone for phone, _ in sms.sent} == {SENDER}


def test_too_long_sms_gets_the_too_long_reply(
    post: Post, jobs: InMemoryJobQueue, sms: FakeSms
) -> None:
    response = post(event("a" * 4001))

    assert response.json() == {"status": "rejected"}
    assert jobs.enqueued == []
    assert sms.sent == [(SENDER, TOO_LONG_TEXT)]


def test_sms_from_the_gateway_itself_is_ignored(
    post: Post, jobs: InMemoryJobQueue
) -> None:
    response = post(event(CLAIM, sender=GATEWAY_NUMBER))

    assert response.status_code == 202
    assert response.json() == {"status": "ignored"}
    assert jobs.enqueued == []


def test_without_signing_key_the_endpoint_does_not_exist(
    jobs: InMemoryJobQueue, gate: CheckGate
) -> None:
    settings = Settings()
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_jobs] = lambda: jobs
    app.dependency_overrides[get_check_gate] = lambda: gate

    assert TestClient(app).post(URL, json=event(CLAIM)).status_code == 404


def test_timestamp_from_the_future_is_401(post: Post, jobs: InMemoryJobQueue) -> None:
    ahead = str(int(time.time()) + 301)

    assert post(event(CLAIM), timestamp=ahead).status_code == 401
    assert jobs.enqueued == []


def test_non_numeric_timestamp_is_401(post: Post) -> None:
    assert post(event(CLAIM), timestamp="yesterday").status_code == 401


def test_non_ascii_signature_is_401(client: TestClient) -> None:
    headers = {
        b"X-Signature": "zażółć".encode(),
        b"X-Timestamp": str(int(time.time())).encode(),
    }

    response = client.post(URL, content=b"{}", headers=headers)

    assert response.status_code == 401


def test_empty_sms_is_rejected_without_a_reply(
    post: Post, jobs: InMemoryJobQueue, sms: FakeSms
) -> None:
    response = post(event("  "))

    assert response.json() == {"status": "rejected"}
    assert jobs.enqueued == []
    assert sms.sent == []


def test_one_number_in_two_formats_gets_one_hash(
    post: Post, jobs: InMemoryJobQueue
) -> None:
    post(event(CLAIM, event_id="e1", sender="600 700 800"))
    post(event(CLAIM, event_id="e2", sender="+48600700800"))

    first, second = (job.payload for job in jobs.enqueued)
    assert isinstance(first, CheckInput)
    assert isinstance(second, CheckInput)
    assert first.channel_user_hash == second.channel_user_hash


def test_gateway_number_in_another_format_is_still_its_own(
    post: Post, jobs: InMemoryJobQueue
) -> None:
    response = post(event(CLAIM, sender="+48500000000"))

    assert response.json() == {"status": "ignored"}
    assert jobs.enqueued == []


def test_usun_with_diacritics_deletes_too(post: Post, jobs: InMemoryJobQueue) -> None:
    response = post(event("Usuń"))

    assert response.json() == {"status": "deleted"}
    [job] = jobs.enqueued
    assert job.spec == DELETE_SUBJECT


def test_busy_service_refuses_without_queueing_or_replying(
    client: TestClient, post: Post, jobs: InMemoryJobQueue, sms: FakeSms
) -> None:
    busy = FixedPendingChecks(pending=10_000)
    gate = CheckGate(MemoryRateCounter(), busy, LimitSettings())
    app = client.app  # the FastAPI app the fixture built
    app.dependency_overrides[get_check_gate] = lambda: gate  # ty: ignore[missing-attribute]  # TestClient types app as a bare ASGI callable

    response = post(event(CLAIM))

    assert response.status_code == 202
    assert response.json() == {"status": "refused"}
    assert jobs.enqueued == []
    assert sms.sent == []


def test_number_with_earlier_checks_gets_no_ai_notice(
    post: Post, jobs: InMemoryJobQueue, sms: FakeSms, repositories: AppRepositories
) -> None:
    post(event(CLAIM, event_id="e1"))
    [job] = jobs.enqueued
    assert isinstance(job.payload, CheckInput)
    asyncio.run(repositories.records.save(record_of(job.workflow_id, job.payload)))
    sms.sent.clear()

    post(event(CLAIM, event_id="e2"))

    assert [text for _, text in sms.sent] == [FAILURE_TEXT]
