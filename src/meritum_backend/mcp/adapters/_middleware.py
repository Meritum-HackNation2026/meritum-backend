"""ASGI middleware: no MCP request without a known client.

Features:
    US-WDR-06, US-BEZ-02, F-37, ADR-17
"""

from fastapi import FastAPI
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from meritum_backend.mcp.constants import (
    API_KEY_HEADER,
    BEARER_PREFIX,
    REALM,
    UNAUTHORIZED_TEXT,
)


def _credential(headers: Headers) -> str | None:
    value = headers.get("authorization", "")
    if value.lower().startswith(BEARER_PREFIX):
        return value[len(BEARER_PREFIX) :].strip() or None
    return headers.get(API_KEY_HEADER.lower()) or None


class McpAuthMiddleware:
    """Answers 401 unless the credential belongs to a client.

    Args:
        app: the app behind the check.
        owner: the FastAPI app whose ``state.mcp_auth`` decides who gets in.

    Features:
        US-WDR-06, US-BEZ-02, F-37, ADR-17
    """

    def __init__(self, app: ASGIApp, owner: FastAPI) -> None:
        self.app = app
        self._owner = owner

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Let a known client through with ``mcp_client`` in the request state.

        Args:
        scope: the ASGI scope.
        receive: the ASGI receive channel.
        send: the ASGI send channel.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        secret = _credential(Headers(scope=scope))
        client = (
            await self._owner.state.mcp_auth.authenticate(secret)
            if secret is not None
            else None
        )
        if client is None:
            metadata = getattr(self._owner.state, "mcp_resource_metadata", None)
            challenge = f'Bearer realm="{REALM}"' + (
                f', resource_metadata="{metadata}"' if metadata else ""
            )
            reply = JSONResponse(
                {"error": "unauthorized", "message": UNAUTHORIZED_TEXT},
                status_code=401,
                headers={"WWW-Authenticate": challenge},
            )
            await reply(scope, receive, send)
            return
        scope.setdefault("state", {})["mcp_client"] = client
        await self.app(scope, receive, send)
