import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
from meritum_core.notifications import NotificationRepository
from tests.notifications.conftest import (
    OTHER,
    SESSION,
    USER,
    Save,
    note,
    script,
    sign_in,
)

from meritum_backend.checks import SESSION_HEADER

URL = "/api/v1/notifications"
MINE = {SESSION_HEADER: SESSION}


def _events(client: TestClient, query: str) -> list[dict[str, object]]:
    with client.stream("GET", f"{URL}/stream?{query}") as response:
        assert response.status_code == 200
        lines = [line for line in response.iter_lines() if line.startswith("data:")]
    return [json.loads(line.removeprefix("data:")) for line in lines]


def test_stream_sends_only_notifications_saved_after_it_opened(
    app: FastAPI, client: TestClient, repo: NotificationRepository, save: Save
) -> None:
    save(note("old"))

    async def workflow_done() -> None:
        await repo.save(note("new"))
        await repo.save(note("theirs", session_id=OTHER))

    script(app, [workflow_done])

    events = _events(client, f"session={SESSION}")

    assert [e["id"] for e in events] == ["new"]
    assert events[0]["kind"] == "check_done"
    assert events[0]["link"] == "/sprawdzenia/c_new"


def test_stream_without_a_session_is_400(client: TestClient) -> None:
    assert client.get(f"{URL}/stream").status_code == 400


def test_inbox_lists_own_unread_notifications(client: TestClient, save: Save) -> None:
    save(note("a"))
    save(note("b"))
    save(note("x", session_id=OTHER))

    body = client.get(URL, headers=MINE).json()

    assert sorted(n["id"] for n in body) == ["a", "b"]
    assert {n["status"] for n in body} == {"unread"}


def test_mark_read_changes_the_status(client: TestClient, save: Save) -> None:
    save(note("a"))

    assert client.post(f"{URL}/a/read", headers=MINE).status_code == 204

    assert client.get(URL, headers=MINE).json()[0]["status"] == "read"


def test_a_session_cannot_read_or_mark_another_sessions_notification(
    client: TestClient, save: Save
) -> None:
    save(note("x", session_id=OTHER))

    assert client.post(f"{URL}/x/read", headers=MINE).status_code == 404
    assert client.get(URL, headers=MINE).json() == []
    assert (
        client.get(URL, headers={SESSION_HEADER: OTHER}).json()[0]["status"] == "unread"
    )


def test_signed_in_user_sees_account_notifications_on_another_device(
    app: FastAPI, client: TestClient, save: Save
) -> None:
    save(note("u", session_id=None, user_id=USER))
    sign_in(app)

    body = client.get(URL, headers={SESSION_HEADER: OTHER}).json()

    assert [n["id"] for n in body] == ["u"]


def test_clear_deletes_only_own_notifications(client: TestClient, save: Save) -> None:
    save(note("a"))
    save(note("x", session_id=OTHER))

    assert client.delete(URL, headers=MINE).status_code == 204

    assert client.get(URL, headers=MINE).json() == []
    assert len(client.get(URL, headers={SESSION_HEADER: OTHER}).json()) == 1


def test_inbox_without_a_session_or_account_is_400(client: TestClient) -> None:
    assert client.get(URL).status_code == 400
