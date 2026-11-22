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

STAFF_INBOX_PREFIX: Final = "staff:"
"""Prefix of a staff member's inbox id (then a hash of the address)."""

STAFF_INBOX_HASH_CHARS: Final = 32
"""Hex chars of the address hash; with ``staff:`` it fits the 64 allowed."""

CASE_PANEL_PATH: Final = "/moderator/cases/{case}"
"""Panel path of one case; ``{case}`` is the number without ``#``."""

NOTIFICATION_RETENTION_DAYS: Final = 30
"""How long a ``case_assigned`` notification stays in the inbox."""

SEND_ATTEMPTS: Final = 4
"""Sends of one alert: the first and three retries; then the failure is logged."""

RETRY_BASE_SECONDS: Final = 1.0
"""Pause before the first retry; each next one doubles it (1 s, 2 s, 4 s)."""

HTTP_TIMEOUT_SECONDS: Final = 5.0
"""Time one call to a webhook or to the e-mail Worker may take."""

TIMESTAMP_HEADER: Final = "X-Meritum-Timestamp"
"""Header with the request time in Unix seconds, part of the signed text."""

SIGNATURE_HEADER: Final = "X-Meritum-Signature"
"""Header with ``sha256=<hex HMAC-SHA256 of "<timestamp>.<body>">``."""

SIGNATURE_PREFIX: Final = "sha256="
"""Prefix of the signature header value."""

CASE_EVENT: Final = "case_assigned"
"""The ``event`` of a webhook body, as the Notification kind."""

CHAT_TEXT: Final = "Nowa sprawa {case} czeka na moderatora ({reasons}): {url}"
"""Google Chat message; mirrors copy/pl.json ``notifications.kind.case_assigned``."""

CONFIG_NOT_SET_DETAIL: Final = "no notification target configured"
"""404 detail: the administrator has not set a target yet."""

CREATE_CONFIG_TABLE: Final = """
CREATE TABLE IF NOT EXISTS notifier_config (
    id boolean PRIMARY KEY DEFAULT true CHECK (id),
    kind text NOT NULL,
    url text,
    secret text
)
"""
"""One row: the administrator's target for moderator notifications."""

LOCK_CONFIG_SCHEMA: Final = (
    "SELECT pg_advisory_xact_lock(hashtext('meritum_notifier_config'))"
)
"""Serialize first-time creation of the PostgreSQL table."""

GET_CONFIG: Final = "SELECT kind, url, secret FROM notifier_config"
"""Read the single row."""

UPSERT_CONFIG: Final = """
INSERT INTO notifier_config (kind, url, secret) VALUES (%s, %s, %s)
ON CONFLICT (id) DO UPDATE SET kind = excluded.kind, url = excluded.url,
    secret = excluded.secret
"""
"""Replace the single row."""

DELETE_CONFIG: Final = "DELETE FROM notifier_config"
"""Remove the target: no external notifications."""

CONNECT_TIMEOUT: Final = 3
"""Maximum seconds spent establishing a database connection."""
