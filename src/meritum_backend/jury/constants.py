"""Constants for one-time jury access."""

from datetime import timedelta
from typing import Final

JURY_LINK_TTL: Final = timedelta(hours=24)
"""Link lifetime when the administrator does not set the end of the evaluation."""

JURY_LINK_MAX_TTL: Final = timedelta(days=7)
"""Latest deadline an administrator may set, counted from issuance."""

LINK_PATTERN: Final = r"^[A-Za-z0-9_-]{43}$"
"""URL-safe encoding shape for 32 random bytes."""

JURY_PROVIDER: Final = "jury"
"""Synthetic identity provider reserved for jury access."""

JURY_LANDING: Final = "/panel/jury"
"""Frontend landing page that exchanges the fragment for a cookie."""

EVALUATION_PAGE: Final = "/panel/eval"
"""Where the signed-in juror views evaluation results."""

JURY_LINK_ATTEMPTS: Final = 10
"""Maximum redemption requests per minute and client address."""

JURY_RATE_SCOPE: Final = "jury-link"
"""Namespace of shared rate counters for jury access."""

MAX_REDEMPTION_BYTES: Final = 1024
"""Largest JSON body accepted by the jury redemption endpoint."""

SAFE_METHODS: Final = frozenset({"GET", "HEAD", "OPTIONS"})
"""HTTP methods allowed on read-only sessions."""

NO_STORE: Final = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
"""Keep link and redemption responses out of caches and referrers."""

CONNECT_TIMEOUT: Final = 3
"""Maximum seconds spent establishing a database connection."""


LOCK_JURY_SCHEMA: Final = "SELECT pg_advisory_xact_lock(hashtext('meritum_jury_links'))"
"""Serialize first-time creation of the PostgreSQL table."""

CREATE_JURY_TABLE: Final = """
CREATE TABLE IF NOT EXISTS jury_links (
    token_hash bytea PRIMARY KEY,
    expires_at timestamptz NOT NULL
)
"""
"""Store only token digests and expiry timestamps."""

INSERT_JURY_LINK: Final = "INSERT INTO jury_links VALUES (%s, %s)"
"""Store a newly issued digest and expiry."""

GET_JURY_LINK: Final = """
SELECT token_hash, expires_at FROM jury_links WHERE token_hash = %s FOR UPDATE
"""
"""Lock the matching digest until this redemption has committed."""

DELETE_JURY_LINK: Final = "DELETE FROM jury_links WHERE token_hash = %s"
"""Consume the locked digest inside the same transaction."""

PURGE_EXPIRED_JURY_LINKS: Final = "DELETE FROM jury_links WHERE expires_at <= now()"
"""Drop links past their deadline when a new one is issued, so the table stays small."""

JSON_MEDIA_TYPE: Final = "application/json"
"""The only body type redemption accepts: a cross-site form cannot send it."""
