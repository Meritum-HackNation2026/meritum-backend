"""Models of the MCP OAuth server: the requests and the signed claims.

Features:
    US-WDR-06, US-BEZ-02, F-37, ADR-17
"""

from pydantic import BaseModel, ConfigDict

from meritum_backend.mcp_oauth.constants import PUBLIC_CLIENT, TOKEN_TYPE


class AuthorizeRequest(BaseModel):
    """Query of the authorization endpoint; every field is checked by the server.

    Attributes:
        response_type: must be ``code``.
        client_id: the id the registration returned.
        redirect_uri: one of the client's registered redirect URIs.
        code_challenge: the PKCE S256 challenge.
        code_challenge_method: must be ``S256``.
        state: echoed back to the client.
        scope: space-separated; only ``mcp`` is known.
        resource: RFC 8707 resource indicator; this server's /mcp.

    Features:
        US-WDR-06, F-37, ADR-17
    """

    model_config = ConfigDict(frozen=True)

    response_type: str = ""
    client_id: str = ""
    redirect_uri: str = ""
    code_challenge: str = ""
    code_challenge_method: str = ""
    state: str = ""
    scope: str = ""
    resource: str = ""


class TokenRequest(BaseModel):
    """Form of the token endpoint.

    Attributes:
        grant_type: ``authorization_code`` or ``refresh_token``.
        code: the authorization code.
        redirect_uri: the redirect URI the code was issued for.
        client_id: the client's id.
        code_verifier: the PKCE verifier.
        refresh_token: the refresh token.
        resource: RFC 8707 resource indicator.

    Features:
        US-WDR-06, F-37, ADR-17
    """

    grant_type: str = ""
    code: str = ""
    redirect_uri: str = ""
    client_id: str = ""
    code_verifier: str = ""
    refresh_token: str = ""
    resource: str = ""


class RegisterRequest(BaseModel):
    """RFC 7591 client metadata; the rest of it is ignored.

    Attributes:
        redirect_uris: https or loopback URIs, exact match at authorize.
        client_name: shown nowhere yet, echoed back.
        token_endpoint_auth_method: only ``none`` (public client with PKCE).

    Features:
        US-WDR-06, F-37, ADR-17
    """

    redirect_uris: list[str] = []
    client_name: str | None = None
    token_endpoint_auth_method: str = PUBLIC_CLIENT


class TokenResponse(BaseModel):
    """RFC 6749 token response.

    Attributes:
        access_token: the bearer token for /mcp.
        token_type: always ``Bearer``.
        expires_in: seconds the access token lives.
        refresh_token: gets the next pair.
        scope: the granted scope.

    Features:
        US-WDR-06, F-37, ADR-17
    """

    access_token: str
    token_type: str = TOKEN_TYPE
    expires_in: int
    refresh_token: str
    scope: str


class Claims(BaseModel):
    """What a signed client id, code or token carries.

    Attributes:
        exp: expiry in Unix seconds; 0 for a client id, which never expires.
        sub: the user id (codes and tokens).
        cid: the client id (codes and tokens).
        uri: the redirect URI (codes).
        pkce: the code challenge (codes).
        jti: random id that makes a code single-use.
        aud: the resource a token is for (tokens).
        uris: the redirect URIs (client ids).

    Features:
        US-WDR-06, F-37, ADR-17
    """

    exp: float = 0
    sub: str = ""
    cid: str = ""
    uri: str = ""
    pkce: str = ""
    jti: str = ""
    aud: str = ""
    uris: list[str] = []
