"""Deleting a person's checks: every table, every channel, only their own."""

import asyncio
import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from meritum_core.checks import SubjectKind
from meritum_core.jobs.contracts import DELETE_SUBJECT, DeleteSubjectInput
from meritum_core.jobs.fakes import InMemoryJobQueue
from meritum_core.observability import AppRepositories
from pydantic import ValidationError

from meritum_backend.checks.constants import SESSION_HEADER
from meritum_backend.jobs.api import get_jobs
from meritum_backend.limits import limiter
from meritum_backend.main import create_app
from meritum_backend.privacy import delete_subject
from meritum_backend.privacy.constants import DELETE_LIMIT_PER_MINUTE
from meritum_backend.settings import Settings

from .conftest import ALL, HASH, SESSION, USER, Remaining


@pytest.mark.parametrize(
    ("kind", "value", "gone"),
    [
        ("session_id", SESSION, "c_s"),
        ("user_id", USER, "c_u"),
        ("channel_user_hash", HASH, "c_d"),
    ],
)
def test_delete_subject_reaches_records_cases_notifications_and_the_worker(
    repos: AppRepositories,
    remaining: Remaining,
    kind: SubjectKind,
    value: str,
    gone: str,
) -> None:
    jobs = InMemoryJobQueue()
    asyncio.run(delete_subject(kind, value, repos.eraser, jobs))
    assert remaining(repos) == ALL - {gone}
    case = asyncio.run(repos.cases.get("#S-1"))
    assert case is not None
    assert gone not in case.claims[0].check_ids
    notes = asyncio.run(repos.notifications.list_for("session_id", SESSION))
    notes += asyncio.run(repos.notifications.list_for("user_id", USER))
    assert all(n.check_id != gone for n in notes)
    [job] = jobs.enqueued
    assert job.spec == DELETE_SUBJECT
    assert job.payload == DeleteSubjectInput(kind=kind, value=value)


def test_delete_subject_refuses_a_raw_channel_id_and_deletes_nothing(
    repos: AppRepositories, remaining: Remaining
) -> None:
    jobs = InMemoryJobQueue()
    with pytest.raises(ValidationError):
        asyncio.run(
            delete_subject("channel_user_hash", "discord-1234567", repos.eraser, jobs)
        )
    assert jobs.enqueued == []
    assert remaining(repos) == ALL


def client_on(repos: AppRepositories, jobs: InMemoryJobQueue) -> TestClient:
    limiter.reset()  # counters are module-level; every client starts from zero
    app = create_app(Settings(database_url="postgresql://x:x@127.0.0.1:1/x"))
    app.state.repositories = repos
    app.dependency_overrides[get_jobs] = lambda: jobs
    return TestClient(app)


def test_session_deletes_its_checks_with_the_matching_header(
    repos: AppRepositories, remaining: Remaining
) -> None:
    response = client_on(repos, InMemoryJobQueue()).delete(
        f"/api/v1/sessions/{SESSION}/checks", headers={SESSION_HEADER: SESSION}
    )
    assert response.status_code == 202
    assert response.json() == {"deleted": 2}
    assert remaining(repos) == ALL - {"c_s"}


@pytest.mark.parametrize("path_id", [HASH, "short"])
def test_path_that_is_no_browser_session_is_refused(
    repos: AppRepositories, remaining: Remaining, path_id: str
) -> None:
    jobs = InMemoryJobQueue()
    response = client_on(repos, jobs).delete(f"/api/v1/sessions/{path_id}/checks")
    assert response.status_code == 400
    assert jobs.enqueued == []
    assert remaining(repos) == ALL


def test_unreachable_queue_is_503_and_deletes_nothing(
    repos: AppRepositories, remaining: Remaining, monkeypatch: pytest.MonkeyPatch
) -> None:
    jobs = InMemoryJobQueue()
    monkeypatch.setattr(jobs, "enqueue", AsyncMock(side_effect=ConnectionError))
    response = client_on(repos, jobs).delete(f"/api/v1/sessions/{SESSION}/checks")
    assert response.status_code == 503
    assert remaining(repos) == ALL


def test_deletion_is_limited_per_client_address_across_session_ids(
    repos: AppRepositories,
) -> None:
    client = client_on(repos, InMemoryJobQueue())
    codes = [
        client.delete(f"/api/v1/sessions/{uuid.uuid4()}/checks").status_code
        for _ in range(DELETE_LIMIT_PER_MINUTE + 1)
    ]
    assert codes[:-1] == [202] * DELETE_LIMIT_PER_MINUTE
    assert codes[-1] == 429
