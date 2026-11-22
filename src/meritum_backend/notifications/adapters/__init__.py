"""Adapters of the external notification ports.

Features:
    US-POW-05, US-MOD-01, F-26
"""

from meritum_backend.notifications.adapters._email import EmailWorkerNotifier
from meritum_backend.notifications.adapters._google_chat import GoogleChatNotifier
from meritum_backend.notifications.adapters._memory import MemoryNotifierConfigStore
from meritum_backend.notifications.adapters._postgres import (
    PostgresNotifierConfigStore,
)
from meritum_backend.notifications.adapters._webhook import WebhookNotifier

__all__ = [
    "EmailWorkerNotifier",
    "GoogleChatNotifier",
    "MemoryNotifierConfigStore",
    "PostgresNotifierConfigStore",
    "WebhookNotifier",
]
