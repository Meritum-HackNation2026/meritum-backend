"""Backend-wide constants."""

from typing import Final

LOCAL_DB: Final = "postgresql://meritum:meritum@localhost:5432/meritum"
"""Database of ``docker compose up -d db``; the default of every database URL."""
