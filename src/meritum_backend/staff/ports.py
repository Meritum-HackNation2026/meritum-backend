"""Port of the staff account store."""

from typing import Protocol

from meritum_core.checks.contracts import StaffRole

from meritum_backend.staff.models import StaffAccount


class StaffRepository(Protocol):
    """Stores the roles administrators grant (port).

    Features:
        US-MOD-05, F-25
    """

    async def list_accounts(self) -> list[StaffAccount]:
        """List every account, sorted by address.

        Returns:
            The accounts.
        """
        ...

    async def save_account(self, account: StaffAccount) -> None:
        """Grant a role, replacing the address's previous one.

        Args:
            account: the address and its role.
        """
        ...

    async def delete_account(self, email: str) -> None:
        """Take the role away; an unknown address does nothing.

        Args:
            email: the lower-cased address.
        """
        ...

    async def role(self, email: str) -> StaffRole | None:
        """The role granted to an address.

        Args:
            email: the lower-cased address.

        Returns:
            The role, or None when the address has no account.
        """
        ...
