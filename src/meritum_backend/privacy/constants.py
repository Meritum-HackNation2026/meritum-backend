"""Constants of the privacy slice.

Features:
    US-BEZ-05, US-BEZ-06, F-20
"""

from typing import Final

NOT_OWN_SESSION_DETAIL: Final = "a session deletes only its own checks"
"""403 detail: the X-Meritum-Session header names another session than the path."""

BAD_SUBJECT_DETAIL: Final = "invalid session id"
"""400 detail: the path is not a browser session id (or is a channel user hash)."""

UNAVAILABLE_DETAIL: Final = "deletion unavailable"
"""503 detail: the job queue or the app database is unreachable."""
