"""What a channel tells the user about a result without verdicts.

``CheckResult.message`` is written by the worker for logs and may be English;
channels word the status from copy instead.

Features:
    US-WTY-06, US-WTY-07, F-21
"""

import logging

from meritum_core.checks import CheckResult

from meritum_backend.channels.constants import (
    FAILURE_CODES,
    OUT_OF_SCOPE_CODES,
    STATUS_HINTS,
)

_log = logging.getLogger(__name__)


def non_verdict_text(result: CheckResult) -> str | None:
    """The copy text for a needs_clarification, out_of_scope or failed result.

    Args:
        result: a finished check.

    Returns:
        The text by failure_code or out_of_scope_code, else by status; None
        for a done result. The worker's message goes to the log only.

    Features:
        US-WTY-06, US-WTY-07, F-21
    """
    if result.status == "done":
        return None
    if result.message is not None:
        _log.info("check %s %s: %s", result.check_id, result.status, result.message)
    text = None
    if result.failure_code is not None:
        text = FAILURE_CODES.get(result.failure_code)
    if result.out_of_scope_code is not None:
        text = OUT_OF_SCOPE_CODES.get(result.out_of_scope_code)
    if text is not None:
        return text
    return STATUS_HINTS.get(result.status, STATUS_HINTS["technical_failure"])
