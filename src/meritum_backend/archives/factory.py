"""Select the archive store for the environment.

Features:
    US-KOR-07, F-38
"""

from meritum_backend.archives.adapters import MemoryArchiveStore, PostgresArchiveStore
from meritum_backend.archives.ports import ArchiveStore
from meritum_backend.constants import LOCAL_ENV
from meritum_backend.settings import Settings


def build_archive_store(settings: Settings) -> ArchiveStore:
    """Use the app tables outside local development.

    Args:
        settings: environment and API database connection.

    Returns:
        PostgreSQL in deployed environments, in-process memory locally.

    Features:
        US-KOR-07, F-38
    """
    if settings.env == LOCAL_ENV:
        return MemoryArchiveStore()
    return PostgresArchiveStore(settings.database_url)
