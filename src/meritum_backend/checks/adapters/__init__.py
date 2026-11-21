"""Adapters of the result cache: in memory and on PostgreSQL.

Features:
    US-WTY-03, F-05, ADR-22
"""

from meritum_backend.checks.adapters._memory import MemoryResultCache
from meritum_backend.checks.adapters._postgres import PostgresResultCache

__all__ = ["MemoryResultCache", "PostgresResultCache"]
