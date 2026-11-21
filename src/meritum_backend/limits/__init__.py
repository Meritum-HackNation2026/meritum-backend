"""Request limits: slowapi per route, and the shared limits of the check intake.

The check intake counts every check per client address, region and channel on a
counter shared by all API instances (ADR-18), and refuses new checks while too
many wait in the worker's queue.

Features:
    US-BEZ-02, US-WDR-03, F-20, F-23, ADR-18
"""

from meritum_backend.limits._slowapi import (
    RateLimitExceeded,
    limiter,
    too_many_requests,
)
from meritum_backend.limits.api import (
    ClientOrigin,
    Gate,
    TooManyChecks,
    admit_stream,
    check_refused,
    get_check_gate,
    start_pruning,
)
from meritum_backend.limits.constants import BUSY, RATE_LIMITED
from meritum_backend.limits.errors import CheckRefusedError
from meritum_backend.limits.factory import build_check_gate
from meritum_backend.limits.gate import CheckGate
from meritum_backend.limits.models import Origin, Refusal
from meritum_backend.limits.settings import LimitSettings

__all__ = [
    "BUSY",
    "RATE_LIMITED",
    "CheckGate",
    "CheckRefusedError",
    "ClientOrigin",
    "Gate",
    "LimitSettings",
    "Origin",
    "RateLimitExceeded",
    "Refusal",
    "TooManyChecks",
    "admit_stream",
    "build_check_gate",
    "check_refused",
    "get_check_gate",
    "limiter",
    "start_pruning",
    "too_many_requests",
]
