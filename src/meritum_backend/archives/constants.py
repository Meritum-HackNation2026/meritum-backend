"""Constants of the archive API: limits, SQL over ``page_archives``, details.

Features:
    US-KOR-07, F-38
"""

from typing import Final

ARCHIVE_LIMIT: Final = "5/hour"
"""Archiving requests per client address; the worker also counts 5 per person."""

READ_LIMIT: Final = "120/minute"
"""Reads, downloads and deletions per client address (the client polls)."""

CONNECT_TIMEOUT: Final = 3
"""Maximum seconds spent establishing a database connection."""

SELECT_ARCHIVE: Final = """
SELECT archive_id, blob_id, url, owner_id, sha256, archived_at, expires_at
FROM page_archives WHERE archive_id = %s AND expires_at > now()
"""
"""One copy still within retention (core migration 0008; the worker writes it)."""

DELETE_ARCHIVE: Final = "DELETE FROM page_archives WHERE archive_id = %s"
"""Forgets one copy."""

RUNNING_STATUSES: Final = frozenset({"ENQUEUED", "PENDING"})
"""DBOS statuses of a job that has not finished yet."""

DOWNLOAD_NAME: Final = "archiwum-{archive_id}.txt"
"""File name of a downloaded copy."""

NO_OWNER_DETAIL: Final = "Send the X-Meritum-Session header or sign in."
"""400: nobody to own the copy."""

NOT_FOUND_DETAIL: Final = "No such archive."
"""404: no copy, or the caller may not see it (the same answer either way)."""

UNAVAILABLE_DETAIL: Final = "Archiving is unavailable right now."
"""503: the queue, database or blob store is unreachable."""

TEXT_TYPE: Final = "text/plain; charset=utf-8"
"""Media type of a downloaded copy."""
