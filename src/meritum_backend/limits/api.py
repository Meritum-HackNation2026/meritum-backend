"""FastAPI dependencies of the check limits: the app's gate and the client origin.

Features:
    US-BEZ-02, US-WDR-03, F-20, F-23
"""

from typing import Annotated, cast

from fastapi import Depends, Request

from meritum_backend.limits.constants import (
    REGION_CODE,
    REGION_HEADER,
    UNKNOWN_IP,
    UNKNOWN_REGION,
)
from meritum_backend.limits.gate import CheckGate, Origin


def get_check_gate(request: Request) -> CheckGate:
    """The gate the app built at startup (overridden in tests).

    Args:
        request: the current request (holds the app state).

    Returns:
        The app's CheckGate.

    Features:
        US-BEZ-02, US-WDR-03, F-20, F-23
    """
    # the app state is untyped; create_app stores a CheckGate there
    return cast("CheckGate", request.app.state.check_gate)


def origin_of(request: Request) -> Origin:
    """Read the client address and its Cloudflare country.

    Args:
        request: the current request; uvicorn --proxy-headers sets the client.

    Returns:
        The origin; a missing or malformed country is ``XX``.

    Features:
        US-BEZ-02, F-20
    """
    ip = request.client.host if request.client else UNKNOWN_IP
    region = request.headers.get(REGION_HEADER, "").upper()
    if not REGION_CODE.fullmatch(region):
        region = UNKNOWN_REGION
    return Origin(ip=ip, region=region)


Gate = Annotated[CheckGate, Depends(get_check_gate)]
"""The app's check gate as a route parameter."""

ClientOrigin = Annotated[Origin, Depends(origin_of)]
"""The request's origin as a route parameter."""
