"""Constants of the notifications slice.

Features:
    US-POW-01, US-POW-04, F-26
"""

from typing import Final

POLL_SECONDS: Final = 2.0
"""How often an open stream looks for new notifications in the inbox store."""

STREAM_POLLS: Final = 150
"""Polls before a stream closes (5 minutes); EventSource then reconnects by itself."""

SESSION_QUERY: Final = "session"
"""Query parameter with the session id: EventSource cannot send headers."""

NO_RECIPIENT_DETAIL: Final = "send the session id or sign in"
"""400 detail: the request names no session and no signed-in account."""

NOT_FOUND_DETAIL: Final = "notification not found"
"""404 detail: no notification with that id belongs to the caller."""

SESSION_ID_MIN: Final = 8
"""Shortest session id, as Notification.session_id allows."""

SESSION_ID_MAX: Final = 64
"""Longest session id, as Notification.session_id allows."""
