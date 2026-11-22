"""Backend-wide constants."""

from typing import Final

LOCAL_DB: Final = "postgresql://meritum:meritum@localhost:5432/meritum"
"""Database of ``docker compose up -d db``; the default of every database URL."""

LOCAL_ENV: Final = "local"
"""MERITUM_ENV of developer machines and tests; only there adapters stay in memory."""

LIST_SEPARATORS: Final = r"[,\s]+"
"""Separators of a list in one environment variable (commas, spaces, newlines)."""

MINUTE_SECONDS: Final = 60
"""Window of the per-minute rate limits; a longer one gets a "później" answer."""
