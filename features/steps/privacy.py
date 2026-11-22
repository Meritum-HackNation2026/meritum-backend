"""Steps for deleting a session's checks (security.feature).

The app runs on core's in-memory app repositories and InMemoryJobQueue, so the
steps see every table the deletion must reach, with no database.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from http import HTTPStatus

from behave import given, then, when
from behave.runner import Context
from fastapi.testclient import TestClient
from meritum_core.checks.contracts import CheckRecord, ModeratorCase, Notification
from meritum_core.jobs.contracts import DELETE_SUBJECT, DeleteSubjectInput
from meritum_core.jobs.fakes import InMemoryJobQueue
from meritum_core.observability import AppRepositories

from meritum_backend.checks.constants import SESSION_HEADER
from meritum_backend.jobs.api import get_jobs
from meritum_backend.main import create_app
from meritum_backend.settings import Settings

SESSION = "0b6f3c1e-5d2a-4f7b-9c8e-1a2b3c4d5e6f"
OTHER = "9f8e7d6c-5b4a-4321-8fed-cba987654321"
T0 = datetime(2026, 11, 21, 12, tzinfo=UTC)
CHECK_IDS = ("c_1", "c_2", "c_3")
CLAIM = "Wczoraj w Gdańsku wyłączono wszystkie bankomaty."


def _record(check_id: str, session_id: str) -> CheckRecord:
    return CheckRecord(
        check_id=check_id,
        session_id=session_id,
        channel="web",
        received_at=T0,
        answered_at=T0,
        question_masked=CLAIM,
        status="done",
        verdicts=["insufficient_evidence"],
        source_ids=[],
        corpus_version="2026-11-21.1",
        models=[],
        retention_until=T0 + timedelta(days=30),
    )


def _note(note_id: str, check_id: str, session_id: str) -> Notification:
    return Notification(
        id=note_id,
        kind="check_done",
        session_id=session_id,
        check_id=check_id,
        link=f"/sprawdzenia/{check_id}",
        created_at=T0,
        retention_until=T0 + timedelta(days=30),
    )


def _case(*check_ids: str) -> ModeratorCase:
    return ModeratorCase.model_validate(
        {
            "id": "#S-1",
            "state": "open",
            "reasons": ["insufficient_evidence"],
            "summary": "Bankomaty w Gdańsku.",
            "claims": [{"claim": CLAIM, "check_ids": list(check_ids)}],
            "first_seen": T0,
            "last_seen": T0,
        }
    )


async def _seed(repos: AppRepositories) -> None:
    for check_id in CHECK_IDS:
        await repos.records.save(_record(check_id, SESSION))
        await repos.notifications.save(_note(f"n_{check_id}", check_id, SESSION))
    await repos.records.save(_record("c_other", OTHER))
    await repos.cases.save(_case("c_1", "c_other"))


@given("sesja ma 3 sprawdzenia, z których jedno jest w sprawie moderatora")
def session_has_checks(context: Context) -> None:
    """Three records and notifications of one session; one record is in a case.

    Args:
        context: the behave context; gets ``client``, ``jobs`` and ``repos``.

    Features:
        US-BEZ-05, US-BEZ-06, US-POW-04, F-20
    """
    context.jobs = InMemoryJobQueue()
    app = create_app(Settings(database_url="postgresql://x:x@127.0.0.1:1/x"))
    app.dependency_overrides[get_jobs] = lambda: context.jobs
    context.repos = app.state.repositories
    asyncio.run(_seed(context.repos))
    context.client = TestClient(app)


@when(
    "obywatel klika „Usuń moje sprawdzenia”, a klient wysyła"
    " DELETE /api/v1/sessions/{{session_id}}/checks"
)
def session_deletes(context: Context) -> None:
    """The extension's request: the session id in the path, no header.

    Args:
        context: the behave context; gets ``response``.

    Features:
        US-BEZ-05, US-BEZ-06, F-20
    """
    context.response = context.client.delete(f"/api/v1/sessions/{SESSION}/checks")


@when(
    "inna sesja wysyła DELETE /api/v1/sessions/{{session_id}}/checks"
    " z własnym nagłówkiem sesji"
)
def other_session_deletes(context: Context) -> None:
    """Another session asks to delete this session's checks.

    Args:
        context: the behave context; gets ``response``.

    Features:
        US-BEZ-05, F-20
    """
    context.response = context.client.delete(
        f"/api/v1/sessions/{SESSION}/checks", headers={SESSION_HEADER: OTHER}
    )


@then("wszystkie 3 zapisy, ich dane workflowów DBOS i powiadomienia sesji znikają")
def checks_are_gone(context: Context) -> None:
    """No record or notification of the session is left; the worker got the job.

    Args:
        context: the behave context with ``response``, ``repos`` and ``jobs``.

    Features:
        US-BEZ-05, US-BEZ-06, US-POW-04, F-20
    """
    assert context.response.status_code == HTTPStatus.ACCEPTED
    repos = context.repos
    assert asyncio.run(repos.records.list_for("session_id", SESSION)) == []
    assert asyncio.run(repos.notifications.list_for("session_id", SESSION)) == []
    [job] = context.jobs.enqueued
    assert job.spec == DELETE_SUBJECT
    assert job.payload == DeleteSubjectInput(kind="session_id", value=SESSION)


@then(
    "sprawa moderatora traci powiązanie z tymi sprawdzeniami,"
    " ale zostaje dla innych pytających"
)
def case_stays(context: Context) -> None:
    """The case keeps only the other session's check.

    Args:
        context: the behave context with ``repos``.

    Features:
        US-BEZ-05, F-20
    """
    case = asyncio.run(context.repos.cases.get("#S-1"))
    assert case is not None
    assert [c.check_ids for c in case.claims] == [["c_other"]]


@then("odpowiedź ma status 403, a zapisy sesji zostają")
def nothing_deleted(context: Context) -> None:
    """The request is refused and nothing is deleted or enqueued.

    Args:
        context: the behave context with ``response``, ``repos`` and ``jobs``.

    Features:
        US-BEZ-05, F-20
    """
    assert context.response.status_code == HTTPStatus.FORBIDDEN
    left = asyncio.run(context.repos.records.list_for("session_id", SESSION))
    assert {r.check_id for r in left} == set(CHECK_IDS)
    assert context.jobs.enqueued == []
