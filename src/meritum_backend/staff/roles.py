"""Which panel role, if any, a signed-in account has."""

from collections.abc import Set as AbstractSet

from meritum_core.moderation import StaffRepository

from meritum_backend.auth import Account
from meritum_backend.staff.constants import ADMIN
from meritum_backend.staff.models import StaffMember


async def role_of(
    account: Account, admins: AbstractSet[str], staff: StaffRepository
) -> StaffMember | None:
    """Give a role only to an address the provider verified.

    Microsoft's ``common`` tenant does not verify addresses, so an unverified
    address never gets a role, whatever the lists say.

    Args:
        account: the signed-in account.
        admins: the lower-cased administrator addresses from the configuration.
        staff: the accounts administrators granted.

    Returns:
        The member with ``admin`` for a configured address, else with the
        granted role; None without a verified address or a role.

    Features:
        US-MOD-05, F-25
    """
    if account.email is None or not account.email_verified:
        return None
    email = account.email.lower()
    role = ADMIN if email in admins else await staff.role(email)
    return None if role is None else StaffMember(email=email, role=role)
