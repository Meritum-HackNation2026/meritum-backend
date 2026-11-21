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

POLL_SECONDS: Final = 0.2
"""Pause between two reads of the escalate_claim workflow's state."""

RUNNING_STATUSES: Final = frozenset({"ENQUEUED", "PENDING", "DELAYED"})
"""DBOS workflow statuses of a job that has not finished yet."""

SUCCESS_STATUS: Final = "SUCCESS"
"""DBOS workflow status of a job that returned its output."""

NOT_SAVED: Final = Escalation(state="recommended")
"""What the citizen gets when no case was saved: no number, still only recommended."""

NOT_SAVED_KEY: Final = "escalation.recommended"
"""copy/pl.json key: the case suits a moderator but was not handed over yet."""

ESCALATION_KEY_PREFIX: Final = "escalation."
"""copy/pl.json prefix of escalation.created and escalation.updated."""

DISPUTE_DONE_KEY: Final = "result.report_error_done"
"""copy/pl.json key: the dispute reached the moderators, with the case number."""

CLAIM_NOT_FOUND_DETAIL: Final = "claim not found"
"""404 detail: no finished check with this id, or no claim at this index."""
