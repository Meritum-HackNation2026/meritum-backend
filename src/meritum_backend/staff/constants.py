"""Constants of the staff slice."""

from typing import Final, get_args

from meritum_core.checks.contracts import StaffRole

EMAIL_MAX_CHARS: Final = 254
"""Longest e-mail address (RFC 5321 path limit)."""

EMAIL_PATTERN: Final = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
"""Shape of a staff address: one ``@`` and a dotted domain; the provider proves it."""

ADMIN: Final[StaffRole] = "admin"
"""The role that manages staff accounts and the high-risk topic list."""

EVERY_ROLE: Final[frozenset[StaffRole]] = frozenset(get_args(StaffRole))
"""Every staff role: whoever has one may open the panel."""

ADMIN_ONLY: Final[frozenset[StaffRole]] = frozenset({ADMIN})
"""Roles allowed to manage accounts and topics."""
