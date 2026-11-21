"""GET /api/v1/health (readiness of the API and the worker) and /api/v1/health/live.

Features:
    US-WDR-08, US-BEZ-03, F-30
"""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from meritum_backend.health.readiness import Readiness, ReadinessProbe

router = APIRouter(prefix="/api/v1/health", tags=["health"])


def get_readiness(request: Request) -> ReadinessProbe:
    """The readiness probe the app built at startup (overridden in tests).

    Args:
        request: the current request (holds the app state).

    Returns:
        The app's readiness probe.

    Features:
        US-WDR-08, F-30
    """
    # app state is untyped; main.py stores the probe build_readiness returned
    return cast("ReadinessProbe", request.app.state.readiness)


Ready = Annotated[ReadinessProbe, Depends(get_readiness)]


@router.get("/live")
async def live() -> dict[str, str]:
    """Liveness only: the process answers, no database involved.

    Returns:
        Always `{"status": "ok"}`.

    Features:
        none (infrastructure)
    """
    return {"status": "ok"}


@router.get(
    "",
    response_model=Readiness,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": Readiness}},
)
async def health(probe: Ready) -> JSONResponse:
    """Readiness: database, the API's variables and the worker's report.

    Lists only names of missing variables and unavailable providers, never values.

    Args:
        probe: the readiness probe.

    Returns:
        200 when nothing is missing, otherwise 503 with what is missing.

    Features:
        US-WDR-08, US-BEZ-03, F-30
    """
    readiness = await probe.check()
    code = (
        status.HTTP_200_OK
        if readiness.status == "ok"
        else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return JSONResponse(readiness.model_dump(), status_code=code)
