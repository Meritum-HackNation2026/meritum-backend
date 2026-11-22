"""Adapters of the MCP channel: source catalogue and client authentication."""

from meritum_backend.mcp.adapters._any import AnyOfAuthenticator
from meritum_backend.mcp.adapters._keys import ApiKeyAuthenticator
from meritum_backend.mcp.adapters._memory import MemorySourceCatalogue
from meritum_backend.mcp.adapters._middleware import McpAuthMiddleware
from meritum_backend.mcp.adapters._oauth import IntrospectionAuthenticator
from meritum_backend.mcp.adapters._postgres import PostgresSourceCatalogue

__all__ = [
    "AnyOfAuthenticator",
    "ApiKeyAuthenticator",
    "IntrospectionAuthenticator",
    "McpAuthMiddleware",
    "MemorySourceCatalogue",
    "PostgresSourceCatalogue",
]
