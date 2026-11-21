"""Staff slice: panel accounts with a role, granted by an administrator.

Features:
    US-MOD-05, F-25
"""

from meritum_backend.staff.models import StaffAccount, StaffMember
from meritum_backend.staff.ports import StaffRepository
from meritum_backend.staff.roles import role_of

__all__ = ["StaffAccount", "StaffMember", "StaffRepository", "role_of"]
