"""Discovery: RFC 9728 protected resource and RFC 8414 server metadata.

Features:
    US-WDR-06, US-BEZ-02, F-37, ADR-17
"""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request

from meritum_backend.mcp_oauth import OAuthServer
from meritum_backend.mcp_oauth.constants import (
    AUTHORIZE_PATH,
    MCP_PATH,
    PKCE_METHOD,
    REGISTER_PATH,
    RESOURCE_METADATA_PATH,
    SCOPE,
    SERVER_METADATA_PATH,
    TOKEN_PATH,
)

router = APIRouter(tags=["mcp-oauth"])


def get_oauth(request: Request) -> OAuthServer:
    """The OAuth server the app built.

    Args:
        request: the current request.

    Returns:
        The app's MCP OAuth server.

    Features:
        US-WDR-06, F-37
    """
    return cast("OAuthServer", request.app.state.mcp_oauth)


Server = Annotated[OAuthServer, Depends(get_oauth)]


@router.get(RESOURCE_METADATA_PATH)
@router.get(RESOURCE_METADATA_PATH + MCP_PATH)
async def resource_metadata(oauth: Server) -> dict[str, object]:
    """Which authorization server protects /mcp.

    Args:
        oauth: the OAuth server.

    Returns:
        The RFC 9728 document.

    Features:
        US-WDR-06, F-37, ADR-17
    """
    return {
        "resource": oauth.resource,
        "authorization_servers": [oauth.issuer],
        "scopes_supported": [SCOPE],
        "bearer_methods_supported": ["header"],
    }


@router.get(SERVER_METADATA_PATH)
async def server_metadata(oauth: Server) -> dict[str, object]:
    """Endpoints and capabilities of the authorization server.

    Args:
        oauth: the OAuth server.

    Returns:
        The RFC 8414 document.

    Features:
        US-WDR-06, F-37, ADR-17
    """
    return {
        "issuer": oauth.issuer,
        "authorization_endpoint": oauth.issuer + AUTHORIZE_PATH,
        "token_endpoint": oauth.issuer + TOKEN_PATH,
        "registration_endpoint": oauth.issuer + REGISTER_PATH,
        "scopes_supported": [SCOPE],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none"],
        "code_challenge_methods_supported": [PKCE_METHOD],
        "authorization_response_iss_parameter_supported": True,
    }
