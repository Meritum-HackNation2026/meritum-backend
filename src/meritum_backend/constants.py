"""Backend-wide constants."""

from typing import Final

LOCAL_DB: Final = "postgresql://meritum:meritum@localhost:5432/meritum"
"""Database of ``docker compose up -d db``; the default of every database URL."""

LIST_SEPARATORS: Final = r"[,\s]+"
"""Separators of a list in one environment variable (commas, spaces, newlines)."""
