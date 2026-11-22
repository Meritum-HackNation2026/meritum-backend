"""Constants of the moderation slice."""

from typing import Final

from meritum_core.checks import Escalation
from meritum_core.checks.contracts import StaffRole

CASE_ROLES: Final[frozenset[StaffRole]] = frozenset({"moderator", "admin"})
"""Roles that see the moderator cases."""

ESCALATION_WAIT_SECONDS: Final = 10.0
"""How long a hand-off waits for the escalate_claim workflow to save the case."""

HANDOFF_LIMIT: Final = "10/minute"
"""Hand-offs per client address; each one creates or updates a moderator case."""

JUSTIFICATION_INPUT_MAX_CHARS: Final = 4000
"""Longest reason read from a dispute; once masked it is cut to 1000 characters."""

POLL_SECONDS: Final = 0.2
"""Pause between two reads of the escalate_claim workflow's state."""

RUNNING_STATUSES: Final = frozenset({"ENQUEUED", "PENDING", "DELAYED"})
"""DBOS workflow statuses of a job that has not finished yet."""

SUCCESS_STATUS: Final = "SUCCESS"
"""DBOS workflow status of a job that returned its output."""

NOT_SAVED: Final = Escalation(state="recommended")
"""What the citizen gets when no case was saved: no number, still only recommended."""

NOT_SAVED_KEY: Final = "escalation.not_saved"
"""copy/pl.json key: the hand-off failed and no case was saved."""

ESCALATION_KEY_PREFIX: Final = "escalation."
"""copy/pl.json prefix of escalation.created and escalation.updated."""

DISPUTE_DONE_KEY: Final = "result.report_error_done"
"""copy/pl.json key: the dispute reached the moderators, with the case number."""

CLAIM_NOT_FOUND_DETAIL: Final = "claim not found"
"""404 detail: no finished check with this id, or no claim at this index."""

ANSWER_TEXT_MAX_CHARS: Final = 2000
"""Longest moderator answer."""

ANSWER_QUOTES_MAX: Final = 5
"""Most quotes one answer carries."""

QUOTE_MAX_CHARS: Final = 500
"""Longest quoted fragment."""

ANSWER_PATH: Final = "/odpowiedzi/{case}"
"""In-app path of an answer; ``{case}`` is the case number without ``#``."""

ANSWER_NOTIFICATION_DAYS: Final = 30
"""How long a ``moderator_answer`` notification stays in the inbox."""

CLOSE_REASON_MAX_CHARS: Final = 500
"""Longest reason for closing a case without an answer."""

CLOSURE_NOT_FOUND_DETAIL: Final = "closure not found"
"""404 detail: the case was not closed without an answer."""

CASE_ID_PATTERN: Final = r"^#S-\d+$"
"""Shape of a moderator case id."""

CASE_NOT_FOUND_DETAIL: Final = "case not found"
"""404 detail: no case with this id."""

ANSWER_NOT_FOUND_DETAIL: Final = "answer not found"
"""404 detail: no answer, or the caller was not told about it."""

CASE_NOT_OPEN_DETAIL: Final = "case is not open"
"""409 detail: the case was already answered or closed."""

QUOTES_REFUSED_DETAIL: Final = "quote not found verbatim in its source"
"""422 message: names the rejected quotes by index."""
