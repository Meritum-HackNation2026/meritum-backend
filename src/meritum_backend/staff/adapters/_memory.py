"""Staff accounts kept in the process's memory."""

from meritum_core.checks.contracts import StaffRole

from meritum_backend.staff.models import StaffAccount


class InMemoryStaffRepository:
    """StaffRepository that keeps the accounts in a dict.

    Features:
        US-MOD-05, F-25
    """

    def __init__(self) -> None:
        self._roles: dict[str, StaffRole] = {}

    async def list_accounts(self) -> list[StaffAccount]:
        """List every account, sorted by address.

        Returns:
            The accounts.
        """
        return [StaffAccount(email=e, role=self._roles[e]) for e in sorted(self._roles)]

    async def save_account(self, account: StaffAccount) -> None:
        """Grant a role, replacing the previous one.

        Args:
            account: the address and its role.
        """
        self._roles[account.email] = account.role

    async def delete_account(self, email: str) -> None:
        """Take the role away, if any.

        Args:
            email: the lower-cased address.
        """
        self._roles.pop(email, None)

    async def role(self, email: str) -> StaffRole | None:
        """The role granted to an address.

        Args:
            email: the lower-cased address.

        Returns:
            The role or None.
        """
        return self._roles.get(email)
