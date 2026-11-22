"""Test addresses shared by the staff scenarios."""

from typing import Final

STAFF_ADMIN: Final = "admin@example.com"
"""Configured administrator in the staff scenarios."""

STAFF_MODERATOR: Final = "moderator@example.com"
"""Account that receives the moderator role."""

STAFF_TEST_DBOS_URL: Final = "postgresql://x:x@127.0.0.1:1/x"
"""Unused DBOS endpoint for the staff persistence scenario."""

STAFF_TEST_PROCESS_TIMEOUT: Final = 15
"""Maximum seconds for a backend process to complete a staff test step."""
