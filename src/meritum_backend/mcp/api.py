"""The MCP server: one tool that runs the same check as POST /api/v1/checks.

The tool calls the app's own checks API in process, so masking, limits, the
result cache, the salted client hash and the AI disclosure are the ones of every
other channel (ADR-08). Nothing here decides a verdict.

Features:
    US-WDR-06, US-WTY-09, US-BEZ-06, F-37, F-42, F-20, ADR-17, ADR-32
"""

import asyncio
import time
from typing import Annotated

from fastapi import FastAPI
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_request
from fastmcp.server.http import StarletteWithLifespan
from httpx2 import ASGITransport, AsyncClient
from meritum_core.checks import AnalysisStatus, CheckResult
from pydantic import Field
from starlette.routing import Route

from meritum_backend.limits import REGION_HEADER, origin_of
from meritum_backend.mcp._search import SourceSearch, search_sources
from meritum_backend.mcp.adapters import McpAuthMiddleware
from meritum_backend.mcp.constants import (
    ACCEPTED,
    CHANNEL,
    CHECKS_PATH,
    ENDPOINT,
    INTERNAL_URL,
    POLL_SECONDS,
    QUERY_DESCRIPTION,
    RATE_LIMITED_CHECK_TEXT,
    SEARCH_TOOL_DESCRIPTION,
    SEARCH_TOOL_NAME,
    SERVER_NAME,
    TEXT_DESCRIPTION,
    TIMEOUT_TEXT,
    TOO_MANY_REQUESTS,
    TOOL_DESCRIPTION,
    TOOL_NAME,
    WAIT_SECONDS,
)


def _http_client(app: FastAPI) -> AsyncClient:
    # the client of the app itself, with the caller's address and region
    request = get_http_request()
    caller = request.client
    transport = (
        ASGITransport(app, client=(caller.host, caller.port or 0))
        if caller
        else ASGITransport(app)
    )
    region = request.headers.get(REGION_HEADER)
    headers = {REGION_HEADER: region} if region is not None else {}
    return AsyncClient(transport=transport, base_url=INTERNAL_URL, headers=headers)


async def _result_of(http: AsyncClient, check_id: str) -> CheckResult:
    # polls the check until it has a result; ToolError after WAIT_SECONDS
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        polled = await http.get(f"{CHECKS_PATH}/{check_id}")
        polled.raise_for_status()
        status = AnalysisStatus.model_validate_json(polled.content)
        if status.result is not None:
            return status.result
        await asyncio.sleep(POLL_SECONDS)
    msg = f"{TIMEOUT_TEXT} (id: {check_id})"
    raise ToolError(msg)


def build_mcp(app: FastAPI) -> StarletteWithLifespan:
    """Build the MCP ASGI app that serves the check tool at ``/mcp``.

    Args:
        app: the FastAPI app whose checks API the tool calls.

    Returns:
        The Streamable HTTP app; the caller adds its routes and runs its lifespan.

    Features:
        US-WDR-06, US-WTY-09, F-37, F-42, ADR-17
    """
    server = FastMCP(SERVER_NAME)

    async def check_claim(
        text: Annotated[str, Field(description=TEXT_DESCRIPTION)],
    ) -> CheckResult:
        # the authenticated client, never a name the caller picks; the checks API
        # hashes it with the salt and limits by the hash, the raw id never leaves it
        client = get_http_request().state.mcp_client
        body = {
            "channel": CHANNEL,
            "text": text,
            "channel_user_id": client.client_id,
        }
        async with _http_client(app) as http:
            started = await http.post(CHECKS_PATH, json=body)
            if started.status_code == TOO_MANY_REQUESTS:
                raise ToolError(RATE_LIMITED_CHECK_TEXT)
            if started.status_code != ACCEPTED:
                msg = f"{started.status_code}: {started.text}"
                raise ToolError(msg)
            return await _result_of(http, started.json()["check_id"])

    async def search(
        query: Annotated[str, Field(description=QUERY_DESCRIPTION)],
    ) -> SourceSearch:
        state = app.state
        return await search_sources(
            query,
            origin=origin_of(get_http_request()),
            gate=state.check_gate,
            pii=state.pii_gate,
            corpus=state.corpus_search,
            catalogue=state.source_catalogue,
            corpus_version=state.mcp_corpus_version,
        )

    server.tool(name=TOOL_NAME, description=TOOL_DESCRIPTION)(check_claim)
    server.tool(name=SEARCH_TOOL_NAME, description=SEARCH_TOOL_DESCRIPTION)(search)
    mcp_app = server.http_app(path=ENDPOINT)
    # main.py mounts only these routes, so app-level middleware would not run
    for route in mcp_app.routes:
        if isinstance(route, Route):
            route.app = McpAuthMiddleware(route.app, owner=app)
    return mcp_app
