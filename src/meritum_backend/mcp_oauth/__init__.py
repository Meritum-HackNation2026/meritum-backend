"""MCP OAuth: a minimal OAuth 2.1 authorization server for the /mcp connector.

Chat apps (ChatGPT, claude.ai) find it through the protected resource metadata,
register themselves, send the user through the usual Google or Microsoft login
and get short-lived tokens for /mcp. Everything is signed, nothing is stored.

Features:
    US-WDR-06, US-BEZ-02, F-37, ADR-17
"""

from meritum_backend.mcp_oauth._rules import refusal
from meritum_backend.mcp_oauth._server import OAuthServer
from meritum_backend.mcp_oauth.factory import build_signer
from meritum_backend.mcp_oauth.models import AuthorizeRequest
from meritum_backend.mcp_oauth.ports import TokenSigner

__all__ = ["AuthorizeRequest", "OAuthServer", "TokenSigner", "build_signer", "refusal"]
