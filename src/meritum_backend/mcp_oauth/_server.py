"""The MCP OAuth server: clients, codes and tokens, all signed, none stored.

Features:
    US-WDR-06, US-BEZ-02, F-37, ADR-17
"""

import secrets
import time
from collections.abc import Callable, Sequence

from pydantic import ValidationError

from meritum_backend.mcp import McpClient
from meritum_backend.mcp_oauth._rules import pkce_matches, redirect_allowed
from meritum_backend.mcp_oauth.constants import (
    ACCESS_SECONDS,
    CLIENT_PREFIX,
    CODE_SECONDS,
    MCP_PATH,
    PENDING_SECONDS,
    REDIRECT_URIS,
    REDIRECTS_MAX,
    REFRESH_SECONDS,
    SCOPE,
)
from meritum_backend.mcp_oauth.models import AuthorizeRequest, Claims, TokenResponse
from meritum_backend.mcp_oauth.ports import TokenSigner


class OAuthServer:
    """Issues and checks everything the connector flow needs.

    Args:
        signer: signs and reads the tokens.
        base: the public address; the issuer, with ``/mcp`` the resource.
        clock: Unix seconds now; tests pass a fixed one.
        redirects: the redirect URIs a client may use besides loopback ones.

    Attributes:
        issuer: the issuer identifier (no trailing slash).
        resource: the canonical URI of /mcp, the audience of every token.

    Features:
        US-WDR-06, US-BEZ-02, F-37, ADR-17
    """

    def __init__(
        self,
        signer: TokenSigner,
        base: str,
        clock: Callable[[], float] = time.time,
        redirects: frozenset[str] = REDIRECT_URIS,
    ) -> None:
        self._signer = signer
        self._clock = clock
        self._redirects = redirects
        self.issuer = base.rstrip("/")
        self.resource = self.issuer + MCP_PATH
        # shortcut: single-use codes in memory, so one API process; a shared
        # store when the API runs in several replicas
        self._used: dict[str, float] = {}

    def _read(self, kind: str, token: str) -> Claims | None:
        raw = self._signer.read(kind, token)
        try:
            claims = Claims.model_validate(raw)
        except ValidationError:
            return None
        is_live = claims.exp == 0 or claims.exp > self._clock()
        return claims if is_live else None

    def _sign(self, kind: str, seconds: int, **claims: str) -> str:
        expiry = self._clock() + seconds if seconds else 0
        return self._signer.sign(kind, {"exp": expiry, **claims})

    def register(self, redirect_uris: Sequence[str]) -> str | None:
        """Register a public client; the id carries its redirect URIs.

        Args:
            redirect_uris: the URIs the client may receive codes at.

        Returns:
            The client id, or None when a URI is not allowed.
        """
        uris = list(redirect_uris)
        if not 0 < len(uris) <= REDIRECTS_MAX or not all(
            redirect_allowed(uri, self._redirects) for uri in uris
        ):
            return None
        return self._signer.sign("client", {"exp": 0, "uris": uris})

    def redirect_uris(self, client_id: str) -> list[str]:
        """The redirect URIs of a client.

        Args:
            client_id: the client id.

        Returns:
            Its URIs still allowed (ids never expire, the allowlist may shrink);
            empty for an id this server did not issue.
        """
        claims = self._read("client", client_id)
        uris = claims.uris if claims is not None else []
        return [uri for uri in uris if redirect_allowed(uri, self._redirects)]

    def resource_known(self, resource: str) -> bool:
        """Whether an RFC 8707 resource names this server (or is absent).

        Args:
            resource: the ``resource`` parameter.

        Returns:
            True for none, the /mcp URI or the bare public address.
        """
        return resource.rstrip("/") in {"", self.issuer, self.resource}

    def pending(self, request: AuthorizeRequest) -> str:
        """Sign an authorization request to keep it while the user signs in.

        Args:
            request: the checked request.

        Returns:
            The signed request.
        """
        return self._sign("pending", PENDING_SECONDS, **request.model_dump())

    def resume(self, signed: str) -> AuthorizeRequest | None:
        """Read back a request kept by ``pending``.

        Args:
            signed: the signed request.

        Returns:
            The request, or None when forged or older than PENDING_SECONDS.
        """
        if self._read("pending", signed) is None:
            return None
        return AuthorizeRequest.model_validate(self._signer.read("pending", signed))

    def code(self, sub: str, client_id: str, redirect_uri: str, challenge: str) -> str:
        """Issue an authorization code.

        Args:
            sub: the signed-in user id.
            client_id: the client.
            redirect_uri: the URI the code goes to.
            challenge: the PKCE challenge.

        Returns:
            A code valid for CODE_SECONDS, once.
        """
        jti = secrets.token_urlsafe(16)
        return self._sign(
            "code",
            CODE_SECONDS,
            sub=sub,
            cid=client_id,
            uri=redirect_uri,
            pkce=challenge,
            jti=jti,
        )

    def redeem(
        self, code: str, client_id: str, redirect_uri: str, verifier: str
    ) -> str | None:
        """Exchange a code once.

        Args:
            code: the code.
            client_id: must be the client the code was issued to.
            redirect_uri: must be the URI the code was issued for.
            verifier: must hash to the code's challenge.

        Returns:
            The user id, or None.
        """
        claims = self._read("code", code)
        now = self._clock()
        self._used = {j: t for j, t in self._used.items() if t > now}
        is_valid = (
            claims is not None
            and claims.jti not in self._used
            and secrets.compare_digest(claims.cid, client_id)
            and claims.uri == redirect_uri
            and pkce_matches(verifier, claims.pkce)
        )
        if claims is None or not is_valid:
            return None
        self._used[claims.jti] = claims.exp
        return claims.sub

    def tokens(self, sub: str, client_id: str) -> TokenResponse:
        """Issue an access and a refresh token.

        Args:
            sub: the user id.
            client_id: the client.

        Returns:
            The RFC 6749 token response.
        """
        access = self._sign(
            "access", ACCESS_SECONDS, sub=sub, cid=client_id, aud=self.resource
        )
        refresh = self._sign("refresh", REFRESH_SECONDS, sub=sub, cid=client_id)
        return TokenResponse(
            access_token=access,
            expires_in=ACCESS_SECONDS,
            refresh_token=refresh,
            scope=SCOPE,
        )

    def refresh(self, token: str, client_id: str) -> TokenResponse | None:
        """New tokens for a refresh token of the same client.

        Args:
            token: the refresh token.
            client_id: the client.

        Returns:
            The token response, or None.
        """
        claims = self._read("refresh", token)
        if claims is None or not secrets.compare_digest(claims.cid, client_id):
            return None
        return self.tokens(claims.sub, client_id)

    async def authenticate(self, credential: str) -> McpClient | None:
        """McpAuthenticator: a live access token of this server.

        Args:
            credential: the bearer token.

        Returns:
            The client named after the user, or None.
        """
        claims = self._read("access", credential)
        if claims is None or not claims.sub or claims.aud != self.resource:
            return None
        return McpClient(client_id=CLIENT_PREFIX + claims.sub)
