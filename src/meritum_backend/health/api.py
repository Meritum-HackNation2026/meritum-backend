"""GET /api/v1/health (readiness of the API and the worker) and /api/v1/health/live.

Features:
    US-WDR-08, US-BEZ-03, F-30
"""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from meritum_backend.health.constants import OPTIONAL_HEALTH_PROVIDERS
from meritum_backend.health.models import NotReady, Readiness
from meritum_backend.health.readiness import ReadinessProbe

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


def not_ready_response() -> JSONResponse:
    """The 503 a check gets while the service is not ready; it names no keys.

    Returns:
        503 with NotReady (technical_failure, not_ready, a copy key).

    Features:
        US-WDR-08, US-BEZ-03, F-30
    """
    body = NotReady().model_dump()
    return JSONResponse(body, status_code=status.HTTP_503_SERVICE_UNAVAILABLE)


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
        200 when required dependencies are ready, even if health is degraded
        by optional providers. Otherwise 503 with the same report.

    Features:
        US-WDR-08, US-BEZ-03, F-30
    """
    readiness = await probe.check()
    required_providers_down = not OPTIONAL_HEALTH_PROVIDERS.issuperset(
        readiness.unavailable_providers
    )
    required_dependency_down = (
        readiness.database != "ok"
        or readiness.worker != "ok"
        or bool(readiness.missing_env)
        or required_providers_down
    )
    code = (
        status.HTTP_503_SERVICE_UNAVAILABLE
        if required_dependency_down
        else status.HTTP_200_OK
    )
    return JSONResponse(readiness.model_dump(), status_code=code)
