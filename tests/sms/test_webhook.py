import time

from fastapi.testclient import TestClient
from meritum_core.jobs.contracts import CHECK, DELETE_SUBJECT, CheckInput
from meritum_core.jobs.fakes import InMemoryJobQueue

from meritum_backend.jobs.api import get_jobs
from meritum_backend.main import create_app
from meritum_backend.settings import Settings, get_settings
from meritum_backend.sms.constants import AI_NOTICE, FAILURE_TEXT, TOO_LONG_TEXT

from .conftest import GATEWAY_NUMBER, SENDER, URL, FakeSms, Post, event

CLAIM = "Wczoraj w Gdańsku wyłączono wszystkie bankomaty."


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
    jobs: InMemoryJobQueue,
) -> None:
    settings = Settings()
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_jobs] = lambda: jobs

    assert TestClient(app).post(URL, json=event(CLAIM)).status_code == 404
