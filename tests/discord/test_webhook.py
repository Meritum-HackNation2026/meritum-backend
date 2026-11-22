import asyncio
import json
from typing import Any

import httpx2

from meritum_backend.discord.adapters import WebhookReplies

BODY = {"embeds": [{"title": "Wynik"}], "components": []}


def _send(*, public: bool) -> tuple[httpx2.Request, dict[str, Any]]:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={})

    replies = WebhookReplies(httpx2.MockTransport(handler))
    asyncio.run(replies.edit_original("app", "tok", BODY, public=public))
    return seen[0], json.loads(seen[0].content)


def test_ephemeral_by_default_and_never_pings() -> None:
    request, body = _send(public=False)
    assert (request.method, request.url.path) == (
        "PATCH",
        "/api/v10/webhooks/app/tok/messages/@original",
    )
    assert body["flags"] == 64
    assert body["allowed_mentions"] == {"parse": []}
    assert body["embeds"] == BODY["embeds"]


def test_public_has_no_ephemeral_flag_and_still_no_pings() -> None:
    _, body = _send(public=True)
    assert "flags" not in body
    assert body["allowed_mentions"] == {"parse": []}
