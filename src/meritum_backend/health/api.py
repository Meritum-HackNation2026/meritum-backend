"""GET /api/v1/health (readiness, checks the database) and /api/v1/health/live."""

from typing import Annotated

import psycopg
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from meritum_backend.settings import Settings, get_settings

router = APIRouter(prefix="/api/v1/health", tags=["health"])


@router.get("/live")
async def live() -> dict[str, str]:
    """Liveness only: the process answers, no database involved.

    Returns:
        Always `{"status": "ok"}`.
    """
    return {"status": "ok"}


@router.get("")
async def health(settings: Annotated[Settings, Depends(get_settings)]) -> JSONResponse:
    """Readiness: the API's own database role can run a query.

    Returns:
        200 with `database: ok`, or 503 with `database: unavailable`.
    """
    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, connect_timeout=3
        ) as conn:
            await conn.execute("SELECT 1")
    except psycopg.Error:
        body = {"status": "degraded", "env": settings.env, "database": "unavailable"}
        return JSONResponse(body, status_code=503)
    return JSONResponse({"status": "ok", "env": settings.env, "database": "ok"})
