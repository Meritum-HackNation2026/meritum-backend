"""Adapters of the MCP channel: source catalogue in memory and in PostgreSQL."""

from meritum_backend.mcp.adapters._memory import MemorySourceCatalogue
from meritum_backend.mcp.adapters._postgres import PostgresSourceCatalogue

__all__ = ["MemorySourceCatalogue", "PostgresSourceCatalogue"]
