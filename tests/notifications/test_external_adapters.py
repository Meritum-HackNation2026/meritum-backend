"""The webhook, Google Chat and e-mail Worker adapters against a mock transport."""

import asyncio
import hashlib
import hmac
import json

import httpx2
import pytest

from meritum_backend.notifications import CaseAlert, NotifyError
from meritum_backend.notifications.adapters import (
    EmailWorkerNotifier,
    GoogleChatNotifier,
    WebhookNotifier,
)

ALERT = CaseAlert(
    case_id="#S-12",
    reasons=["insufficient_evidence", "user_dispute"],
    panel_url="https://meritum.example/moderator/cases/S-12",
)
SHARED_KEY = "s3cret"


def _expected_signature(request: httpx2.Request) -> str:
    stamp = request.headers["X-Meritum-Timestamp"].encode()
    mac = hmac.new(SHARED_KEY.encode(), stamp + b"." + request.content, hashlib.sha256)
    return "sha256=" + mac.hexdigest()


def test_webhook_posts_the_case_signed_with_the_secret() -> None:
    seen: list[httpx2.Request] = []

    def target(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(204)

    notifier = WebhookNotifier(
        "https://hooks.example/meritum", SHARED_KEY, httpx2.MockTransport(target)
    )

    asyncio.run(notifier.send(ALERT))

    [request] = seen
    assert request.headers["X-Meritum-Signature"] == _expected_signature(request)
    assert json.loads(request.content) == {
        "event": "case_assigned",
        "case_id": "#S-12",
        "reasons": ["insufficient_evidence", "user_dispute"],
        "panel_url": "https://meritum.example/moderator/cases/S-12",
    }


def test_google_chat_posts_the_case_number_and_link_as_text() -> None:
    seen: list[httpx2.Request] = []

    def space(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={})

    notifier = GoogleChatNotifier(
        "https://chat.example/v1/spaces/x", httpx2.MockTransport(space)
    )

    asyncio.run(notifier.send(ALERT))

    text = json.loads(seen[0].content)["text"]
    assert "#S-12" in text
    assert ALERT.panel_url in text


def test_email_asks_the_worker_once_per_moderator_with_the_number_and_link() -> None:
    seen: list[httpx2.Request] = []

    def worker(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(202)

    notifier = EmailWorkerNotifier(
        "https://worker.example",
        SHARED_KEY,
        ["a@example.com", "b@example.com"],
        httpx2.MockTransport(worker),
    )

    asyncio.run(notifier.send(ALERT))

    assert [json.loads(r.content) for r in seen] == [
        {"to": to, "case": "S-12", "panel_url": ALERT.panel_url}
        for to in ("a@example.com", "b@example.com")
    ]
    assert all(r.headers["X-Meritum-Signature"] == _expected_signature(r) for r in seen)


def test_email_reports_a_refused_mail_after_trying_every_address() -> None:
    calls: list[str] = []

    def worker(request: httpx2.Request) -> httpx2.Response:
        calls.append(json.loads(request.content)["to"])
        return httpx2.Response(502 if len(calls) == 1 else 202)

    notifier = EmailWorkerNotifier(
        "https://worker.example",
        SHARED_KEY,
        ["a@example.com", "b@example.com"],
        httpx2.MockTransport(worker),
    )

    with pytest.raises(NotifyError):
        asyncio.run(notifier.send(ALERT))
    assert calls == ["a@example.com", "b@example.com"]


@pytest.mark.parametrize("status", [500, 401])
def test_an_error_status_raises_without_leaking_the_address(status: int) -> None:
    notifier = WebhookNotifier(
        "https://hooks.example/key=abc",
        SHARED_KEY,
        httpx2.MockTransport(lambda _: httpx2.Response(status)),
    )

    with pytest.raises(NotifyError) as raised:
        asyncio.run(notifier.send(ALERT))
    assert "abc" not in str(raised.value)
