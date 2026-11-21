"""Constants of the privacy slice.

Features:
    US-BEZ-05, US-BEZ-06, F-20
"""

import re
from typing import Final

NOT_OWN_SESSION_DETAIL: Final = "a session deletes only its own checks"
"""403 detail: the X-Meritum-Session header names another session than the path."""

BAD_SUBJECT_DETAIL: Final = "invalid session id"
"""400 detail: the path is not a browser session id (or is a channel user hash)."""

UNAVAILABLE_DETAIL: Final = "deletion unavailable"
"""503 detail: the job queue or the app database is unreachable."""

DELETE_LIMIT_PER_MINUTE: Final = 10
"""Deletions one client address may request per minute (429 above that); each one
starts a ``delete_subject`` workflow, so the endpoint is not an open queue."""

ACCESS_LOGGER: Final = "uvicorn.access"
"""The logger uvicorn writes one access line per response to."""

ACCESS_PATH_ARG: Final = 2
"""Index of the path in the access record's args: uvicorn (h11 and httptools)
logs ``'%s - "%s %s HTTP/%s" %d'`` with client, method, path, version, status."""

SESSION_IN_PATH: Final = re.compile(r"^(/api/v1/sessions/)[^/?]+(/checks)")
"""The deletion path; its middle segment is a session id, which works as a key."""

SESSION_PLACEHOLDER: Final = r"\1{session_id}\2"
"""What the access log shows instead of the session id."""
