"""Access log without session ids: the id in the deletion path is a key.

The notification stream takes it as ``?session=`` too; both are masked.

Anyone holding a session id can delete that session's checks, and access logs
are kept for 14 days, so uvicorn's access line shows ``{session_id}`` instead.

Features:
    US-BEZ-05, US-BEZ-06, F-20
"""

import logging
from typing import override

from meritum_backend.privacy.constants import (
    ACCESS_LOGGER,
    ACCESS_PATH_ARG,
    SESSION_IN_PATH,
    SESSION_IN_QUERY,
    SESSION_QUERY_REPLACEMENT,
    SESSION_REPLACEMENT,
)


class SessionIdFilter(logging.Filter):
    """Replaces the session id in the deletion path and the stream query.

    Features:
        US-BEZ-05, F-20
    """

    @override
    def filter(self, record: logging.LogRecord) -> bool:
        """Mask the path argument in place; every record is kept.

        Args:
            record: an access log record from uvicorn.

        Returns:
            Always True.
        """
        args = record.args
        if not isinstance(args, tuple) or len(args) <= ACCESS_PATH_ARG:
            return True
        path = args[ACCESS_PATH_ARG]
        if isinstance(path, str):
            masked = SESSION_IN_PATH.sub(SESSION_REPLACEMENT, path)
            masked = SESSION_IN_QUERY.sub(SESSION_QUERY_REPLACEMENT, masked)
            record.args = (
                *args[:ACCESS_PATH_ARG],
                masked,
                *args[ACCESS_PATH_ARG + 1 :],
            )
        return True


def mask_sessions_in_access_log() -> None:
    """Install SessionIdFilter on uvicorn's access logger once per process.

    Features:
        US-BEZ-05, F-20
    """
    access = logging.getLogger(ACCESS_LOGGER)
    if not any(isinstance(f, SessionIdFilter) for f in access.filters):
        access.addFilter(SessionIdFilter())
