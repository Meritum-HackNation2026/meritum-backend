"""A case closed without an answer: who closed it, why and when.

Features:
    US-MOD-01, US-MOD-07, F-25, F-39
"""

from datetime import datetime
from typing import Annotated, Protocol

from pydantic import BaseModel, Field

from meritum_backend.moderation.constants import CLOSE_REASON_MAX_CHARS


class ClosureDraft(BaseModel):
    """Body of a close: the moderator's reason, e.g. a test or groundless case.

    Attributes:
        reason: why the case is closed.

    Features:
        US-MOD-01, F-25
    """

    reason: Annotated[str, Field(min_length=1, max_length=CLOSE_REASON_MAX_CHARS)]


class CaseClosure(BaseModel):
    """What the panel keeps about a close; the askers are not told.

    Attributes:
        case_id: the closed case.
        closed_by: the moderator's address.
        reason: why the case was closed.
        closed_at: when it was closed.

    Features:
        US-MOD-01, US-MOD-07, F-25
    """

    case_id: str
    closed_by: str | None
    reason: str
    closed_at: datetime


class ClosureStore(Protocol):
    """Keeps the closes by case (port).

    Features:
        US-MOD-01, F-25
    """

    async def save(self, closure: CaseClosure) -> None:
        """Store the close of a case.

        Args:
            closure: the close.
        """
        ...

    async def get(self, case_id: str) -> CaseClosure | None:
        """Read the close of a case.

        Args:
            case_id: the case id.

        Returns:
            The close, or None.
        """
        ...


class InMemoryClosureStore:
    """ClosureStore over a dict.

    shortcut: lost on restart, like the answers; move both to the app schema
    together. The case's ``closed`` state itself lives in the case repository.

    Features:
        US-MOD-01, F-25
    """

    def __init__(self) -> None:
        self._closures: dict[str, CaseClosure] = {}

    async def save(self, closure: CaseClosure) -> None:
        """Store the close of a case.

        Args:
            closure: the close.
        """
        self._closures[closure.case_id] = closure

    async def get(self, case_id: str) -> CaseClosure | None:
        """Read the close of a case.

        Args:
            case_id: the case id.

        Returns:
            The close, or None.
        """
        return self._closures.get(case_id)
