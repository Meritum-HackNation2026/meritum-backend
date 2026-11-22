"""Adapters of the MCP OAuth server."""

from meritum_backend.mcp_oauth.adapters._itsdangerous import ItsdangerousSigner

__all__ = ["ItsdangerousSigner"]
