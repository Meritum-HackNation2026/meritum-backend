"""Builds the staff account store."""

from meritum_backend.staff.adapters import InMemoryStaffRepository
from meritum_backend.staff.ports import StaffRepository


def build_staff() -> StaffRepository:
    """Build the staff account store.

    shortcut: accounts live in memory and go with a restart (configured admins
    stay); switch to the core repository of meritum-core#72 when it ships.

    Returns:
        The in-memory store.

    Features:
        US-MOD-05, F-25
    """
    return InMemoryStaffRepository()
