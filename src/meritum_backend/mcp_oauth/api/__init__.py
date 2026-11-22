"""HTTP API of the MCP OAuth server: metadata, registration, authorize, token."""

from meritum_backend.mcp_oauth.api._metadata import router as metadata_router
from meritum_backend.mcp_oauth.api._routes import router

__all__ = ["metadata_router", "router"]
