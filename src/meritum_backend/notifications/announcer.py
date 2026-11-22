"""Announce a new or updated case: the staff inbox and the configured target.

A failing target is retried a fixed number of times, then logged; it never
stops the case from being created.

Features:
    US-POW-05, US-MOD-01, F-26
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from meritum_core.checks.contracts import Notification
from meritum_core.moderation import ModeratorCaseRepository, StaffRepository
from meritum_core.notifications import NotificationRepository

from meritum_backend.notifications.constants import (
    CASE_PANEL_PATH,
    NOTIFICATION_RETENTION_DAYS,
    RETRY_BASE_SECONDS,
    SEND_ATTEMPTS,
    STAFF_INBOX_HASH_CHARS,
    STAFF_INBOX_PREFIX,
)
from meritum_backend.notifications.models import CaseAlert, NotifierConfig
from meritum_backend.notifications.ports import (
    ExternalNotifier,
    NotifierConfigStore,
    NotifyError,
)

type NotifierFactory = Callable[
    [NotifierConfig, Sequence[str]], ExternalNotifier | None
]
"""Builds the sender for a configuration and the moderators' addresses."""

type Sleep = Callable[[float], Awaitable[None]]

log = logging.getLogger(__name__)


def staff_inbox_id(email: str) -> str:
    """The inbox id (Notification.user_id) of a staff address.

    Args:
        email: the verified address.

    Returns:
        ``staff:`` and a hash of the lower-cased address, so no address is stored.

    Features:
        US-POW-05, F-26
    """
    digest = sha256(email.strip().lower().encode()).hexdigest()
    return STAFF_INBOX_PREFIX + digest[:STAFF_INBOX_HASH_CHARS]


class CaseAnnouncer:
    """Puts ``case_assigned`` in the moderators' inboxes and tells the target.

    Args:
        cases: where the case is read from.
        staff: the accounts administrators granted.
        admin_emails: the configured administrators (moderators too).
        inbox: the notifications store.
        configs: the administrator's target.
        make_notifier: builds the sender for a configuration.
        panel_base: the panel's origin, the base of the alert's link.
        sleep: pauses between retries (replaced in tests).

    Features:
        US-POW-05, US-MOD-01, F-26
    """

    def __init__(  # ruff: ignore[too-many-arguments, too-many-positional-arguments] (one wiring point)
        self,
        cases: ModeratorCaseRepository,
        staff: StaffRepository,
        admin_emails: frozenset[str],
        inbox: NotificationRepository,
        configs: NotifierConfigStore,
        make_notifier: NotifierFactory,
        panel_base: str,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._cases = cases
        self._staff = staff
        self._admins = admin_emails
        self._inbox = inbox
        self._configs = configs
        self._make = make_notifier
        self._base = panel_base.rstrip("/")
        self._sleep = sleep

    async def announce(self, case_id: str) -> None:
        """Tell the moderators about the case; never raises.

        Args:
            case_id: the case created or updated.

        Features:
            US-POW-05, US-MOD-01, F-26
        """
        try:
            await self._announce(case_id)
        except Exception:  # a failing announcement must not touch the case
            log.exception("announcing %s failed", case_id)

    async def _announce(self, case_id: str) -> None:
        case = await self._cases.get(case_id)
        alert = CaseAlert(
            case_id=case_id,
            reasons=[] if case is None else list(case.reasons),
            panel_url=self._base + CASE_PANEL_PATH,
        )
        emails = await self._moderators()
        now = datetime.now(UTC)
        for email in emails:
            await self._inbox.save(self._note(email, case_id, CASE_PANEL_PATH, now))
        config = await self._configs.get()
        notifier = None if config is None else self._make(config, emails)
        if notifier is not None:
            await self._send(notifier, alert)

    async def _moderators(self) -> list[str]:
        granted = {
            a.email for a in await self._staff.list_accounts() if a.role != "analyst"
        }
        return sorted(granted | self._admins)

    @staticmethod
    def _note(email: str, case_id: str, path: str, now: datetime) -> Notification:
        user_id = staff_inbox_id(email)
        return Notification(
            id=sha256(f"{case_id}:{user_id}:{now.isoformat()}".encode()).hexdigest()[
                :40
            ],
            kind="case_assigned",
            user_id=user_id,
            case_id=case_id,
            link=path,
            created_at=now,
            retention_until=now + timedelta(days=NOTIFICATION_RETENTION_DAYS),
        )

    async def _send(self, notifier: ExternalNotifier, alert: CaseAlert) -> None:
        for attempt in range(SEND_ATTEMPTS):
            try:
                await notifier.send(alert)
            except NotifyError as error:
                log.warning("notifying about %s failed: %s", alert.case_id, error)
                if attempt + 1 < SEND_ATTEMPTS:
                    await self._sleep(RETRY_BASE_SECONDS * 2**attempt)
            else:
                return
        log.error("gave up notifying about %s", alert.case_id)
