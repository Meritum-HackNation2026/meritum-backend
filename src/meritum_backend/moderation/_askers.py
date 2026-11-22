"""Tell the people who asked that a moderator answered.

Only checks whose records still exist are reached: a session that deleted its
data (US-BEZ-05) left no record, so it gets nothing. Nobody learns who else asked.

Features:
    US-MOD-07, US-POW-02, F-39
"""

from datetime import UTC, datetime, timedelta
from hashlib import sha256

from meritum_core.checks.contracts import ModeratorCase, Notification
from meritum_core.checks.ports import CheckRecordRepository
from meritum_core.notifications import NotificationRepository

from meritum_backend.moderation.constants import (
    ANSWER_NOTIFICATION_DAYS,
    ANSWER_PATH,
)


async def notify_askers(
    case: ModeratorCase,
    records: CheckRecordRepository,
    inbox: NotificationRepository,
) -> int:
    """Put ``moderator_answer`` in each remaining asker's inbox, once per person.

    Args:
        case: the answered case.
        records: where the askers' check records are.
        inbox: the notifications store.

    Returns:
        How many people were notified.

    Features:
        US-MOD-07, US-POW-02, F-39
    """
    now = datetime.now(UTC)
    askers: set[tuple[str, str]] = set()
    for claim in case.claims:
        for check_id in claim.check_ids:
            record = await records.get(check_id)
            if record is None:
                continue
            if record.user_id is not None:
                askers.add(("user_id", record.user_id))
            else:
                askers.add(("session_id", record.session_id))
    for kind, value in sorted(askers):
        digest = sha256(f"{case.id}:{kind}:{value}".encode()).hexdigest()[:40]
        await inbox.save(
            Notification.model_validate(
                {
                    "id": digest,
                    "kind": "moderator_answer",
                    kind: value,
                    "case_id": case.id,
                    "link": ANSWER_PATH.format(case=case.id.removeprefix("#")),
                    "created_at": now,
                    "retention_until": now + timedelta(days=ANSWER_NOTIFICATION_DAYS),
                }
            )
        )
    return len(askers)
