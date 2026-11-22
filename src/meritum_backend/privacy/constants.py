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

DELETE_LIMIT_SCOPE: Final = "delete_session_checks"
"""One rate-limit bucket for every session id: slowapi keys a plain limit by URL,
which would give each id its own bucket and put the id in its 429 log line."""

ACCESS_LOGGER: Final = "uvicorn.access"
"""The logger uvicorn writes one access line per response to."""

ACCESS_PATH_ARG: Final = 2
"""Index of the path in the access record's args: uvicorn (h11 and httptools)
logs ``'%s - "%s %s HTTP/%s" %d'`` with client, method, path, version, status."""

SESSION_IN_PATH: Final = re.compile(r"(/api/v1/sessions/)[^/?]+(/checks)")
"""The deletion path, also behind a root path; its middle segment is a session
id, which works as a key."""

SESSION_REPLACEMENT: Final = r"\1{session_id}\2"
"""Regex replacement: the access log shows ``{session_id}`` instead of the id."""

DEMO_IN_PATH: Final = re.compile(r"(/api/v1/auth/demo/)[^/?\s]+")
"""The demo link path, also behind a root path; its last segment is a login key."""

DEMO_REPLACEMENT: Final = r"\1{token}"
"""Regex replacement: the access log shows ``{token}`` instead of the demo token."""

SESSION_IN_QUERY: Final = re.compile(r"([?&]session=)[^&#\s]+")
"""The notification stream's ``?session=`` (EventSource sends no headers); the
id works as a key to that session's inbox."""

SESSION_QUERY_REPLACEMENT: Final = r"\1{session_id}"
"""Regex replacement: the access log shows ``session={session_id}``."""
