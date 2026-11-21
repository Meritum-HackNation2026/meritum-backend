"""role_of: a role only for a verified address on one of the lists."""

import asyncio

import pytest
from meritum_core.moderation.fakes import InMemoryStaffRepository

from meritum_backend.auth import Account
from meritum_backend.settings import Settings
from meritum_backend.staff import StaffAccount, StaffMember, role_of

ADMINS = frozenset({"boss@example.com"})


def resolve(email: str | None, *, verified: bool = True) -> StaffMember | None:
    staff = InMemoryStaffRepository()
    asyncio.run(
        staff.save_account(StaffAccount(email="mod@example.com", role="moderator"))
    )
    account = Account(
        provider="microsoft", subject="s", email=email, email_verified=verified
    )
    return asyncio.run(role_of(account, ADMINS, staff))


@pytest.mark.parametrize("email", ["boss@example.com", "mod@example.com"])
def test_unverified_address_gets_no_role(email: str) -> None:
    assert resolve(email, verified=False) is None


def test_account_without_address_gets_no_role() -> None:
    assert resolve(None) is None


def test_configured_admin_wins() -> None:
    assert resolve("Boss@Example.com") == StaffMember(
        email="boss@example.com", role="admin"
    )


def test_granted_role() -> None:
    assert resolve("mod@example.com") == StaffMember(
        email="mod@example.com", role="moderator"
    )


def test_unknown_address_gets_no_role() -> None:
    assert resolve("someone@example.com") is None


def test_admin_emails_split_on_commas_and_whitespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MERITUM_ADMIN_EMAILS", "A@x.pl, b@x.pl\nc@x.pl")
    assert Settings().admin_emails == {"a@x.pl", "b@x.pl", "c@x.pl"}


def test_no_admin_emails_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MERITUM_ADMIN_EMAILS", raising=False)
    assert Settings(_env_file=None).admin_emails == frozenset()
