"""Notifications HTTP API: SSE stream, inbox, read marks, clearing.

Features:
    US-POW-01, US-POW-04, F-26
"""

from meritum_backend.notifications.api._config import (
    get_configs,
)
from meritum_backend.notifications.api._config import (
    router as config_router,
)
from meritum_backend.notifications.api._inbox import (
    get_notifications,
    get_ticks,
    router,
)
from meritum_backend.notifications.api._recipients import (
    Recipient,
    recipients,
    signed_in_account,
)

__all__ = [
    "Recipient",
    "config_router",
    "get_configs",
    "get_notifications",
    "get_ticks",
    "recipients",
    "router",
    "signed_in_account",
]
