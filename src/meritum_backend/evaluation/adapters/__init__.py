"""Concrete evaluation indexes."""

from meritum_backend.evaluation.adapters._memory import MemoryEvalStore
from meritum_backend.evaluation.adapters._postgres import PostgresEvalStore

__all__ = ["MemoryEvalStore", "PostgresEvalStore"]
