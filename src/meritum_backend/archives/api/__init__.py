"""Inbound HTTP adapter of the archive slice.

Features:
    US-KOR-07, F-38
"""

from meritum_backend.archives.api._access import get_archive_store, is_moderator
from meritum_backend.archives.api._routes import router

__all__ = ["get_archive_store", "is_moderator", "router"]
