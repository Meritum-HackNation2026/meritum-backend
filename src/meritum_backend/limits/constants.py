"""Limits of the check intake: per IP, region and channel, and pending checks.

Every value is a default; ``LimitSettings`` reads the MERITUM_* variable named
next to it.

Features:
    US-BEZ-02, US-WDR-03, F-20, F-23, ADR-18
"""

import re
from typing import Final, LiteralString

from meritum_backend.limits.models import Refusal

WINDOW_SECONDS: Final = 60
"""Length of one fixed counting window; the limits below are per window."""

CHECKS_PER_IP_PER_MINUTE: Final = 10
"""Checks one client address may start per minute (MERITUM_CHECKS_PER_IP_PER_MINUTE)."""

CHECKS_PER_REGION_PER_MINUTE: Final = 3000
"""Checks one country may start per minute (MERITUM_CHECKS_PER_REGION_PER_MINUTE).

A safety valve against a distributed flood, well above normal traffic: almost all
checks come from PL, so a low value would refuse every user in the country."""

CHECKS_PER_CHANNEL_PER_MINUTE: Final = 6000
"""Checks one channel may start per minute (MERITUM_CHECKS_PER_CHANNEL_PER_MINUTE).

A safety valve like the region limit; most checks come through the web form."""

EVENT_STREAMS_PER_IP_PER_MINUTE: Final = 60
"""Progress streams one client address may open per minute; reconnects count too
(MERITUM_EVENT_STREAMS_PER_IP_PER_MINUTE)."""

MAX_PENDING_CHECKS: Final = 100
"""Queued checks at which new ones get 429 busy (MERITUM_MAX_PENDING_CHECKS)."""

RATE_LIMITED_KEY: Final = "errors.rate_limited"
"""copy/pl.json key: too many checks in a short time; try again in a minute."""

RATE_LIMITED_DAILY_KEY: Final = "errors.rate_limited_daily"
"""copy/pl.json key: a daily limit is used up (e.g. audio uploads, backend#23)."""

DAY_SECONDS: Final = 24 * 60 * 60
"""A limit window this long or longer is a daily limit (RATE_LIMITED_DAILY_KEY)."""

BUSY_KEY: Final = "errors.busy"
"""copy/pl.json key: too many pending checks; try again in a few minutes."""

BUSY_RETRY_SECONDS: Final = 300
"""Retry-After of a busy answer: the "few minutes" of errors.busy."""

RATE_LIMITED: Final = Refusal(RATE_LIMITED_KEY, WINDOW_SECONDS)
"""Refusal over a rate limit: try again in the next window."""

BUSY: Final = Refusal(BUSY_KEY, BUSY_RETRY_SECONDS)
"""Refusal while too many checks wait in the worker's queue."""

CONNECT_TIMEOUT_SECONDS: Final = 3
"""How long the rate counter waits for a database connection."""

IP_SCOPE: Final = "ip"
"""Key prefix of per-address counters; every instance must write the same keys."""

REGION_SCOPE: Final = "region"
"""Key prefix of per-country counters in the shared table."""

CHANNEL_SCOPE: Final = "channel"
"""Key prefix of per-channel counters in the shared table."""

EVENTS_SCOPE: Final = "events"
"""Key prefix of per-address counters of progress streams (GET .../events)."""

RETRY_AFTER_HEADER: Final = "Retry-After"
"""Header with the seconds a refused client should wait."""

REGION_HEADER: Final = "CF-IPCountry"
"""Cloudflare's header with the client's ISO 3166 country code."""

UNKNOWN_REGION: Final = "XX"
"""Region of a request without a valid country code (Cloudflare's own "unknown")."""

REGION_CODE: Final = re.compile(r"[A-Z]{2}")
"""A valid region: two uppercase letters; anything else counts as UNKNOWN_REGION."""

UNKNOWN_IP: Final = "unknown"
"""Client address when the server saw none (test clients, unix sockets)."""

CREATE_RATE_TABLE: Final[tuple[LiteralString, ...]] = (
    """
    CREATE TABLE IF NOT EXISTS rate_limit_hits (
        key text NOT NULL,
        window_start timestamptz NOT NULL,
        hits integer NOT NULL,
        PRIMARY KEY (key, window_start)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS rate_limit_hits_window_start
    ON rate_limit_hits (window_start)
    """,
)
"""The table in the API role's own schema (its search_path), made on first use."""

HIT_RATE_KEY: Final[LiteralString] = """
    INSERT INTO rate_limit_hits AS h (key, window_start, hits)
    VALUES (
        %(key)s,
        to_timestamp(floor(extract(epoch FROM now()) / %(window)s) * %(window)s),
        1
    )
    ON CONFLICT (key, window_start) DO UPDATE SET hits = h.hits + 1
    RETURNING hits
"""
"""One atomic upsert: concurrent instances never lose a hit."""

PRUNE_RATE_WINDOWS: Final[LiteralString] = """
    WITH turn AS (
        SELECT pg_try_advisory_xact_lock(hashtext('meritum.rate_limit_prune')) AS mine
    )
    DELETE FROM rate_limit_hits USING turn
    WHERE turn.mine AND window_start < now() - make_interval(secs => %(window)s)
"""
"""Drops finished windows; one instance at a time, the others skip (no lock waits)."""

LOCK_RATE_TABLE: Final[LiteralString] = (
    "SELECT pg_advisory_xact_lock(hashtext('meritum.rate_limit_hits'))"
)
"""Serializes the first-use CREATE of every instance; released at commit."""
