"""CaseAnnouncer: inbox notifications, retries and failures that stay inside."""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime

import pytest
from meritum_core.checks.contracts import CaseClaim, ModeratorCase
from meritum_core.moderation import StaffAccount
from meritum_core.moderation.fakes import (
    InMemoryModeratorCaseRepository,
    InMemoryStaffRepository,
)
from meritum_core.notifications.fakes import InMemoryNotificationRepository
from pydantic import SecretStr

from meritum_backend.notifications import (
    CaseAlert,
    CaseAnnouncer,
    NotifierConfig,
    NotifyError,
    staff_inbox_id,
)
from meritum_backend.notifications.adapters import MemoryNotifierConfigStore
from meritum_backend.notifications.constants import SEND_ATTEMPTS

NOW = datetime(2026, 11, 22, tzinfo=UTC)
CASE = ModeratorCase(
    id="#S-12",
    state="open",
    reasons=["insufficient_evidence"],
    summary="Twierdzenie bez dowodów",
    claims=[CaseClaim(claim="Lokal jest zamknięty.", check_ids=["c_1"])],
    first_seen=NOW,
    last_seen=NOW,
)
CONFIG = NotifierConfig(
    kind="webhook", url="https://hooks.example/x", secret=SecretStr("k")
)


class FlakyNotifier:
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.sent: list[CaseAlert] = []

    async def send(self, alert: CaseAlert) -> None:
        if self.failures > 0:
            self.failures -= 1
            msg = "500"
            raise NotifyError(msg)
        self.sent.append(alert)


class Rig:
    def __init__(self, notifier: FlakyNotifier, *, configured: bool = True) -> None:
        self.notifier = notifier
        self.recipients: list[Sequence[str]] = []
        self.pauses: list[float] = []
        self.inbox = InMemoryNotificationRepository()
        self.cases = InMemoryModeratorCaseRepository()
        self.staff = InMemoryStaffRepository()
        self.configs = MemoryNotifierConfigStore()
        asyncio.run(self._seed(configured=configured))
        self.announcer = CaseAnnouncer(
            self.cases,
            self.staff,
            frozenset({"boss@example.com"}),
            self.inbox,
            self.configs,
            self._make,
            "https://meritum.example/",
            self._sleep,
        )

    async def _seed(self, *, configured: bool) -> None:
        await self.cases.save(CASE)
        await self.staff.save_account(
            StaffAccount(email="mod@example.com", role="moderator")
        )
        await self.staff.save_account(
            StaffAccount(email="ana@example.com", role="analyst")
        )
        if configured:
            await self.configs.save(CONFIG)

    def _make(self, config: NotifierConfig, recipients: Sequence[str]) -> FlakyNotifier:
        del config
        self.recipients.append(recipients)
        return self.notifier

    async def _sleep(self, seconds: float) -> None:
        self.pauses.append(seconds)


def test_a_new_case_reaches_the_target_with_number_reasons_and_panel_link() -> None:
    rig = Rig(FlakyNotifier(0))

    asyncio.run(rig.announcer.announce("#S-12"))

    assert rig.notifier.sent == [
        CaseAlert(
            case_id="#S-12",
            reasons=["insufficient_evidence"],
            panel_url="https://meritum.example/panel",
        )
    ]


def test_moderators_and_admins_get_case_assigned_in_their_inbox_analysts_do_not() -> (
    None
):
    rig = Rig(FlakyNotifier(0))

    asyncio.run(rig.announcer.announce("#S-12"))

    for email in ("mod@example.com", "boss@example.com"):
        [note] = asyncio.run(rig.inbox.list_for("user_id", staff_inbox_id(email)))
        assert (note.kind, note.case_id) == ("case_assigned", "#S-12")
        assert note.link == "/panel"
    assert not asyncio.run(
        rig.inbox.list_for("user_id", staff_inbox_id("ana@example.com"))
    )
    assert rig.recipients == [["boss@example.com", "mod@example.com"]]


def test_a_failing_target_is_retried_then_given_up_without_raising() -> None:
    rig = Rig(FlakyNotifier(failures=99))

    asyncio.run(rig.announcer.announce("#S-12"))

    assert rig.notifier.failures == 99 - SEND_ATTEMPTS
    assert rig.pauses == [1.0, 2.0, 4.0]


def test_a_target_that_recovers_is_not_asked_again() -> None:
    rig = Rig(FlakyNotifier(failures=2))

    asyncio.run(rig.announcer.announce("#S-12"))

    assert len(rig.notifier.sent) == 1
    assert rig.pauses == [1.0, 2.0]


def test_without_a_target_only_the_inbox_is_filled() -> None:
    rig = Rig(FlakyNotifier(0), configured=False)

    asyncio.run(rig.announcer.announce("#S-12"))

    assert not rig.notifier.sent
    assert asyncio.run(rig.inbox.list_for("user_id", staff_inbox_id("mod@example.com")))


def test_an_unexpected_error_does_not_escape(caplog: pytest.LogCaptureFixture) -> None:
    rig = Rig(FlakyNotifier(0))
    rig.cases.get = _boom

    asyncio.run(rig.announcer.announce("#S-12"))

    assert "announcing #S-12 failed" in caplog.text


async def _boom(case_id: str) -> ModeratorCase:
    await asyncio.sleep(0)
    raise RuntimeError(case_id)
