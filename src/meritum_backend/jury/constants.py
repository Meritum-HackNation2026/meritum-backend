"""Constants for jury and demo access links."""

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

NO_STORE: Final = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
"""Keep link and redemption responses out of caches and referrers."""

CONNECT_TIMEOUT: Final = 3
"""Maximum seconds spent establishing a database connection."""


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


DEMO_PROVIDER: Final = "demo"
"""Synthetic identity provider of the technical demo accounts."""

DEMO_ADMIN: Final = "admin"
"""Subject of the demo administrator account."""

DEMO_ACCOUNTS: Final = {"obywatel": "/", DEMO_ADMIN: "/panel"}
"""Technical demo accounts and the page each one lands on."""

DEMO_ENVS: Final = frozenset({"local", "dev"})
"""Environments where demo links exist; never ``prd`` (issue #53)."""

DEMO_PATH: Final = "/api/v1/auth/demo/"
"""Path of the demo link; the token is the last segment."""

PEEK_JURY_LINK: Final = "SELECT expires_at FROM jury_links WHERE token_hash = %s"
"""Read a reusable link without locking or consuming it."""


DEMO_ID_PATTERN: Final = r"^[0-9a-f]{64}$"
"""Hex representation of the demo token digest."""

INSERT_DEMO_METADATA: Final = """
INSERT INTO demo_link_metadata (token_hash, account, issued_at) VALUES (%s, %s, %s)
"""
"""Record the metadata in the same transaction as the digest."""

LIST_DEMO_LINKS: Final = """
SELECT encode(l.token_hash, 'hex') AS id, d.account, d.issued_at, l.expires_at
FROM demo_link_metadata d JOIN jury_links l USING (token_hash)
WHERE l.expires_at > %s
ORDER BY d.issued_at DESC, l.token_hash DESC
"""
"""List active demo metadata without including one-time jury links."""

DELETE_DEMO_LINK: Final = """
DELETE FROM jury_links l USING demo_link_metadata d
WHERE l.token_hash = d.token_hash AND l.token_hash = %s
"""
"""Revoke by digest only if the row represents a demo link."""
