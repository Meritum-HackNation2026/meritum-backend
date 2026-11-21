"""The personal-data masking gate as a FastAPI dependency.

Features:
    US-BEZ-04, F-20
"""

from typing import Annotated

from fastapi import Depends, Request
from meritum_core.security import PiiGatePort


def get_pii_gate(request: Request) -> PiiGatePort:
    """The masking gate the app built at startup (overridden in tests).

    Args:
        request: the current request (holds the app state).

    Returns:
        The app's PII gate; the null gate unless ``MERITUM_PII_*`` names one.

    Features:
        US-BEZ-04, F-20
    """
    return request.app.state.pii_gate


PiiGate = Annotated[PiiGatePort, Depends(get_pii_gate)]
