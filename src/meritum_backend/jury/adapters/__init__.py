"""Concrete jury link stores."""

from meritum_backend.jury.adapters._memory import MemoryJuryLinks
from meritum_backend.jury.adapters._postgres import PostgresJuryLinks

__all__ = ["MemoryJuryLinks", "PostgresJuryLinks"]
