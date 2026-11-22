"""Notifications slice: the inbox, its live stream over SSE and the moderators' alerts.

A new or updated moderator case goes to the staff inbox (``case_assigned``) and
to the target the administrator chose: webhook, Google Chat or e-mail.

Features:
    US-POW-01, US-POW-04, US-POW-05, US-MOD-01, F-26
"""

from meritum_backend.notifications.announcer import CaseAnnouncer, staff_inbox_id
from meritum_backend.notifications.models import (
    CaseAlert,
    NotifierConfig,
    NotifierConfigView,
)
from meritum_backend.notifications.ports import (
    ExternalNotifier,
    NotifierConfigStore,
    NotifyError,
)

__all__ = [
    "CaseAlert",
    "CaseAnnouncer",
    "ExternalNotifier",
    "NotifierConfig",
    "NotifierConfigStore",
    "NotifierConfigView",
    "NotifyError",
    "staff_inbox_id",
]
