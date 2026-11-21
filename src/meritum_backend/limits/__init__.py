"""Request limits: slowapi per route, and the shared limits of the check intake.

The check intake counts every check per client address, region and channel on a
counter shared by all API instances (ADR-18), and refuses new checks while too
many wait in the worker's queue.

Features:
    US-BEZ-02, US-WDR-03, F-20, F-23, ADR-18
"""

from slowapi.errors import RateLimitExceeded

from meritum_backend.limits._slowapi import limiter, too_many_requests
from meritum_backend.limits.adapters import FixedPendingChecks, MemoryRateCounter
from meritum_backend.limits.api import ClientOrigin, Gate, get_check_gate
from meritum_backend.limits.constants import (
    BUSY_KEY,
    BUSY_RETRY_SECONDS,
    RATE_LIMITED_KEY,
    RATE_LIMITED_RETRY_SECONDS,
)
from meritum_backend.limits.factory import build_check_gate
from meritum_backend.limits.gate import CheckGate, Origin
from meritum_backend.limits.settings import LimitSettings

__all__ = [
    "BUSY_KEY",
    "BUSY_RETRY_SECONDS",
    "RATE_LIMITED_KEY",
    "RATE_LIMITED_RETRY_SECONDS",
    "CheckGate",
    "ClientOrigin",
    "FixedPendingChecks",
    "Gate",
    "LimitSettings",
    "MemoryRateCounter",
    "Origin",
    "RateLimitExceeded",
    "build_check_gate",
    "get_check_gate",
    "limiter",
    "too_many_requests",
]
