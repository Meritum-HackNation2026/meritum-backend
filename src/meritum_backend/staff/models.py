"""Models of the staff slice: an account the admin granted and the signed-in member."""

from typing import Annotated

from meritum_core.checks.contracts import StaffRole
from pydantic import BaseModel, ConfigDict, StringConstraints

from meritum_backend.staff.constants import EMAIL_MAX_CHARS, EMAIL_PATTERN

type StaffEmail = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        max_length=EMAIL_MAX_CHARS,
        pattern=EMAIL_PATTERN,
    ),
]
"""A staff address, lower-cased so lookups ignore case."""


class StaffAccount(BaseModel):
    """A role an administrator granted to an e-mail address.

    Attributes:
        email: the address the OIDC provider must confirm (and verify).
        role: the role in the panel.

    Features:
        US-MOD-05, F-25
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    email: StaffEmail
    role: StaffRole


class StaffMember(BaseModel):
    """The signed-in person and their role in the panel.

    Attributes:
        email: the verified address from the ID token.
        role: the role from the configuration or from an administrator.

    Features:
        US-MOD-05, F-25
    """

    model_config = ConfigDict(frozen=True)

    email: str
    role: StaffRole
