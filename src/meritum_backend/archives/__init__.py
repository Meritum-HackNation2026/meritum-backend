"""Archive slice: a citizen archives a public page, then reads or deletes the copy.

The worker fetches and stores it (``archive_page`` workflow); the API enqueues,
reads the metadata from ``page_archives`` and the text from the blob store.

Features:
    US-KOR-07, F-38
"""

from meritum_backend.archives.factory import build_archive_store
from meritum_backend.archives.models import ArchiveRecord, ArchiveView
from meritum_backend.archives.ports import ArchiveStore

__all__ = [
    "ArchiveRecord",
    "ArchiveStore",
    "ArchiveView",
    "build_archive_store",
]
