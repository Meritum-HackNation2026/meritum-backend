"""The MCP server: one tool that runs the same check as POST /api/v1/checks.

The tool calls the app's own checks API in process, so masking, limits, the
result cache, the salted client hash and the AI disclosure are the ones of every
other channel (ADR-08). Nothing here decides a verdict.

Features:
    US-WDR-06, US-WTY-09, US-BEZ-06, F-37, F-42, F-20, ADR-17
"""

import asyncio
import time
from typing import Annotated

from fastapi import FastAPI
from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_request
from fastmcp.server.http import StarletteWithLifespan
from httpx2 import ASGITransport, AsyncClient
from meritum_core.checks import AnalysisStatus, CheckResult
from pydantic import Field

from meritum_backend.limits import REGION_HEADER
from meritum_backend.mcp.constants import (
    ACCEPTED,
    CHANNEL,
    CHECKS_PATH,
    ENDPOINT,
    INTERNAL_URL,
    POLL_SECONDS,
    SERVER_NAME,
    TEXT_DESCRIPTION,
    TIMEOUT_TEXT,
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
        text: Annotated[str, Field(description=TEXT_DESCRIPTION)], ctx: Context
    ) -> CheckResult:
        # the id is hashed with the salt by the checks API; the raw id never leaves it
        body = {
            "channel": CHANNEL,
            "text": text,
            "channel_user_id": ctx.client_id or ctx.session_id,
        }
        async with _http_client(app) as http:
            started = await http.post(CHECKS_PATH, json=body)
            if started.status_code != ACCEPTED:
                msg = f"{started.status_code}: {started.text}"
                raise ToolError(msg)
            return await _result_of(http, started.json()["check_id"])

    server.tool(name=TOOL_NAME, description=TOOL_DESCRIPTION)(check_claim)
    return server.http_app(path=ENDPOINT)
