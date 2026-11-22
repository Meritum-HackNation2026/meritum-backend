"""„Usuń moją historię” keeps the account's case and system notifications (#142)."""

import asyncio
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from meritum_core.checks.contracts import Notification
from meritum_core.jobs.fakes import InMemoryJobQueue
from meritum_core.observability import AppRepositories

from .conftest import USER
from .test_citizen_account import citizen

T0 = datetime(2026, 11, 22, 12, tzinfo=UTC)


def _to_user(note_id: str, kind: str, **fields: object) -> Notification:
    times = {"created_at": T0, "retention_until": T0 + timedelta(days=30)}
    return Notification.model_validate(
        {"id": note_id, "kind": kind, "user_id": USER, "link": "/"} | times | fields
    )


def _seed_inbox(repos: AppRepositories) -> None:
    notes = [
        _to_user("n_case", "case_assigned", case_id="#S-1"),
        _to_user("n_sys", "system", message_code="maintenance_planned"),
        _to_user("n_eval", "eval_run_done"),
        _to_user("n_answer", "moderator_answer", case_id="#S-2"),
    ]
    for note in notes:
        asyncio.run(repos.notifications.save(note))


def _inbox(client: TestClient) -> list[str]:
    return sorted(n["id"] for n in client.get("/api/v1/notifications").json())


def test_delete_history_keeps_case_system_and_eval_notifications(
    repos: AppRepositories,
) -> None:
    _seed_inbox(repos)
    client = citizen(repos, InMemoryJobQueue())
    assert client.delete("/api/v1/me/checks").status_code == 202
    assert _inbox(client) == ["n_case", "n_eval", "n_sys"]
    assert client.get("/api/v1/me/checks").json() == []


def test_delete_account_removes_every_notification_of_the_account(
    repos: AppRepositories,
) -> None:
    _seed_inbox(repos)
    client = citizen(repos, InMemoryJobQueue())
    assert client.delete("/api/v1/me").status_code == 202
    assert asyncio.run(repos.notifications.list_for("user_id", USER)) == []
