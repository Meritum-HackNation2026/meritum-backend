"""Staff slice: panel accounts with a role, granted by an administrator.

Features:
    US-MOD-05, F-25
"""

from meritum_core.moderation import StaffAccount, StaffRepository

from meritum_backend.staff.models import StaffMember
from meritum_backend.staff.roles import role_of

__all__ = ["StaffAccount", "StaffMember", "StaffRepository", "role_of"]
