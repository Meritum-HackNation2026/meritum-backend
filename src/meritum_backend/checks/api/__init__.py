"""Checks HTTP API: start and poll a check, and stream its progress.

Features:
    US-SPR-01, US-SPR-02, US-SPR-07, US-BEZ-04, US-BEZ-07, F-01, F-09, F-20, F-21,
    ADR-08
"""

from meritum_backend.checks.api._events import router as events_router
from meritum_backend.checks.api._status import router

__all__ = ["events_router", "router"]
