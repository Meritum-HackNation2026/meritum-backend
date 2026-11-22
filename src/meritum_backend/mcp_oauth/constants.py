"""Constants of the MCP OAuth server.

Features:
    US-WDR-06, US-BEZ-02, F-37, ADR-17
"""

from typing import Final

MCP_PATH: Final = "/mcp"
"""The protected resource: the MCP endpoint, appended to the public address."""

RESOURCE_METADATA_PATH: Final = "/.well-known/oauth-protected-resource"
"""RFC 9728 metadata; also served with ``MCP_PATH`` appended (path insertion)."""

SERVER_METADATA_PATH: Final = "/.well-known/oauth-authorization-server"
"""RFC 8414 metadata of the issuer, which is the public address without a path."""

REGISTER_PATH: Final = "/api/v1/oauth/register"
"""RFC 7591 dynamic client registration."""

AUTHORIZE_PATH: Final = "/api/v1/oauth/authorize"
"""Authorization endpoint."""

RESUME_PATH: Final = "/api/v1/oauth/authorize/resume"
"""Where the login returns to finish an authorization request."""

TOKEN_PATH: Final = "/api/v1/oauth/token"  # ruff: ignore[hardcoded-password-string]
"""Token endpoint."""

COOKIE_PATH: Final = "/api/v1/oauth"
"""Path of the cookie that keeps an authorization request during login."""

PENDING_COOKIE: Final = "meritum_oauth_request"
"""Signed cookie with the authorization request while the user signs in."""

SCOPE: Final = "mcp"
"""The only scope: call the MCP tools."""

CODE_SECONDS: Final = 60
"""Lifetime of an authorization code."""

ACCESS_SECONDS: Final = 60 * 60
"""Lifetime of an access token."""

REFRESH_SECONDS: Final = 7 * 24 * 60 * 60
"""Lifetime of a refresh token."""

PENDING_SECONDS: Final = 10 * 60
"""How long a login may take before the authorization request is dropped."""

PKCE_METHOD: Final = "S256"
"""The only PKCE method accepted."""

CHALLENGE_LENGTH: Final = 43
"""Length of an S256 code challenge (base64url of 32 bytes, no padding)."""

VERIFIER_MIN: Final = 43
"""Shortest PKCE code verifier (RFC 7636)."""

VERIFIER_MAX: Final = 128
"""Longest PKCE code verifier (RFC 7636)."""

REDIRECTS_MAX: Final = 5
"""Most redirect URIs one client may register."""

URI_MAX: Final = 512
"""Longest redirect URI accepted."""

LOOPBACK_HOSTS: Final = frozenset({"localhost", "127.0.0.1", "::1"})
"""Hosts a redirect URI may reach over http or https, any port (native apps)."""

REDIRECT_URIS: Final = frozenset(
    {
        "https://claude.ai/api/mcp/auth_callback",
        "https://claude.com/api/mcp/auth_callback",
        "https://chatgpt.com/connector_platform_oauth_redirect",
        "https://chat.openai.com/connector_platform_oauth_redirect",
    }
)
"""Redirect URIs a client may register besides loopback ones: the chat apps.

``MERITUM_MCP_OAUTH_REDIRECT_URIS`` replaces the list (#146)."""

CLIENT_PREFIX: Final = "oauth:"
"""Prefix of the MCP client id of a token holder; the rest is the user id."""

URL_SAFE: Final = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
)
"""Characters of a PKCE verifier and challenge (RFC 7636 unreserved)."""

NO_STORE: Final = {"Cache-Control": "no-store", "Pragma": "no-cache"}
"""Headers of every token endpoint answer: tokens never land in a cache."""

TOKEN_TYPE: Final = "Bearer"  # ruff: ignore[hardcoded-password-string] -- a scheme name
"""Type of every access token."""

SALT_PREFIX: Final = "meritum-mcp-oauth-"
"""Prefix of the signer salt per kind, so one kind never passes as another."""

PUBLIC_CLIENT: Final = "none"
"""The only client authentication: a public client that proves itself with PKCE."""
