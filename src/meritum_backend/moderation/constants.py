"""Constants of the moderation slice."""

from typing import Final

from meritum_core.checks.contracts import StaffRole

CASE_ROLES: Final[frozenset[StaffRole]] = frozenset({"moderator", "admin"})
"""Roles that see the moderator cases."""
