"""Staff API: the panel's role check and the accounts an administrator manages.

Every panel endpoint takes a member through ``StaffGate``: the OIDC session
(auth slice) plus a role from ``MERITUM_ADMIN_EMAILS`` or from an administrator.
State-changing endpoints also take ``CsrfUser``.
"""

from collections.abc import Set as AbstractSet
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from meritum_core.checks.contracts import StaffRole

from meritum_backend.auth.api import CsrfUser, CurrentUser
from meritum_backend.staff import StaffAccount, StaffMember, StaffRepository, role_of
from meritum_backend.staff.constants import ADMIN_ONLY, EVERY_ROLE
from meritum_backend.staff.models import StaffEmail

router = APIRouter(prefix="/api/v1/staff", tags=["staff"])


def get_staff(request: Request) -> StaffRepository:
    """The staff account store the app built (overridden in tests).

    Args:
        request: the current request (holds the app state).

    Returns:
        The app's staff account store.

    Features:
        US-MOD-05, F-25
    """
    return request.app.state.staff


Staff = Annotated[StaffRepository, Depends(get_staff)]


class StaffGate:
    """Dependency that lets in only signed-in members with one of ``roles``.

    Args:
        roles: the roles allowed through.

    Features:
        US-MOD-05, F-25
    """

    def __init__(self, roles: AbstractSet[StaffRole]) -> None:
        self._roles = roles

    async def __call__(
        self, request: Request, account: CurrentUser, staff: Staff
    ) -> StaffMember:
        """Resolve the member's role and check it.

        Args:
            request: the request (the configured admin addresses in app state).
            account: the signed-in account (401 without a session).
            staff: the staff account store.

        Returns:
            The member.

        Raises:
            HTTPException: 403 without a role, or with a role not allowed here.

        Features:
            US-MOD-05, F-25
        """
        member = await role_of(account, request.app.state.admin_emails, staff)
        if member is None or member.role not in self._roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "no access to the panel")
        return member


AnyStaff = Annotated[StaffMember, Depends(StaffGate(EVERY_ROLE))]
Admin = Annotated[StaffMember, Depends(StaffGate(ADMIN_ONLY))]


@router.get("/me")
async def me(member: AnyStaff) -> StaffMember:
    """The signed-in member's role; 403 tells the panel the person has none.

    Args:
        member: the signed-in member.

    Returns:
        The address and role.

    Features:
        US-MOD-05, F-25
    """
    return member


@router.get("")
async def list_accounts(_admin: Admin, staff: Staff) -> list[StaffAccount]:
    """The accounts administrators granted (configured admins are not listed).

    Args:
        _admin: the signed-in administrator.
        staff: the staff account store.

    Returns:
        The accounts, sorted by address.

    Features:
        US-MOD-05, F-25
    """
    return await staff.list_accounts()


@router.post("", status_code=status.HTTP_201_CREATED)
async def grant(
    account: StaffAccount, _admin: Admin, _csrf: CsrfUser, staff: Staff
) -> StaffAccount:
    """Grant a role to an address; it replaces the address's previous role.

    Args:
        account: the address and role.
        _admin: the signed-in administrator.
        _csrf: the account, CSRF checked.
        staff: the staff account store.

    Returns:
        The stored account.

    Features:
        US-MOD-05, F-25
    """
    await staff.save_account(account)
    return account


@router.delete("/{email}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke(
    email: StaffEmail, _admin: Admin, _csrf: CsrfUser, staff: Staff
) -> None:
    """Take an address's role away.

    Args:
        email: the address.
        _admin: the signed-in administrator.
        _csrf: the account, CSRF checked.
        staff: the staff account store.

    Features:
        US-MOD-05, F-25
    """
    await staff.delete_account(email)
