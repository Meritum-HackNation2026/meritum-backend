"""OIDC login with Authlib's Starlette client (Google, Microsoft)."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx2
from authlib.common.errors import AuthlibBaseError
from authlib.integrations.starlette_client import OAuth, StarletteOAuth2App
from joserfc.errors import JoseError

from meritum_backend.auth.constants import LEEWAY, SCOPE, TENANT_PLACEHOLDER
from meritum_backend.auth.errors import LoginError
from meritum_backend.auth.models import Account, LoginStart, PendingLogin


@dataclass(frozen=True)
class OidcClient:
    """One provider's client registration.

    Attributes:
        client_id: the OAuth client id; the ID token's audience must equal it.
        client_secret: the OAuth client secret.
        metadata_url: the OIDC discovery document (issuer, endpoints, JWKS).
        metadata: discovery values given inline instead of fetched (tests).

    Features:
        US-MOD-05, US-SPR-10, F-25
    """

    client_id: str
    client_secret: str
    metadata_url: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


def _issuer_check(expected: str) -> Any:  # ruff: ignore[any-type]  # Authlib's hook type is private
    """Build the ``iss`` validation hook.

    Microsoft's multi-tenant issuer has a ``{tenantid}`` placeholder that must
    equal the token's own ``tid``; Google may send its issuer without https://.

    Args:
        expected: the issuer from the discovery document.

    Returns:
        A hook that tells whether a token's ``iss`` is the expected issuer.

    Features:
        US-MOD-05, F-25
    """

    def check(claims: Mapping[str, Any], value: object) -> bool:
        issuer = expected.replace(TENANT_PLACEHOLDER, str(claims.get("tid", "")))
        return value in {issuer, issuer.removeprefix("https://")}

    return check


class AuthlibLogin:
    """Authorization code flow with PKCE; ID tokens checked by Authlib.

    The signature is checked against the provider's JWKS, plus issuer, audience
    (our client id), expiry and nonce.

    Args:
        clients: the client registration per provider name.
        transport: the HTTP transport for provider calls (a mock in tests).

    Attributes:
        providers: names of the registered providers.

    Features:
        US-MOD-05, US-SPR-10, F-25, F-31
    """

    def __init__(
        self,
        clients: Mapping[str, OidcClient],
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        oauth = OAuth()
        extra: dict[str, Any] = {"transport": transport} if transport else {}
        self._apps: dict[str, StarletteOAuth2App] = {
            name: oauth.register(
                name,
                client_id=client.client_id,
                client_secret=client.client_secret,
                server_metadata_url=client.metadata_url,
                client_kwargs={"scope": SCOPE, "code_challenge_method": "S256"} | extra,
                **client.metadata,
            )
            for name, client in clients.items()
        }

    @property
    def providers(self) -> frozenset[str]:
        """Names of the registered providers."""
        return frozenset(self._apps)

    def _app(self, provider: str) -> StarletteOAuth2App:
        app = self._apps.get(provider)
        if app is None:
            msg = f"unknown provider {provider!r}"
            raise LoginError(msg)
        return app

    async def begin(self, provider: str, redirect_uri: str) -> LoginStart:
        """Build the authorization URL with fresh state, nonce and PKCE verifier.

        Args:
            provider: the provider name.
            redirect_uri: the callback address registered with the provider.

        Returns:
            The URL and the pending login to keep in the session.

        Raises:
            LoginError: unknown provider or unreachable discovery document.

        Features:
            US-MOD-05, US-SPR-10, F-25
        """
        app = self._app(provider)
        try:
            found = await app.create_authorization_url(redirect_uri)
        except (
            AuthlibBaseError,
            JoseError,
            httpx2.HTTPError,
            KeyError,
            ValueError,
        ) as exc:
            raise LoginError(str(exc)) from exc
        pending = PendingLogin(
            provider=provider,
            state=found["state"],
            nonce=found["nonce"],
            code_verifier=found["code_verifier"],
            redirect_uri=redirect_uri,
        )
        return LoginStart(url=found["url"], pending=pending)

    async def complete(
        self, provider: str, code: str, pending: PendingLogin
    ) -> Account:
        """Exchange the code and validate the ID token.

        Args:
            provider: the provider name from the callback path.
            code: the authorization code.
            pending: the data saved by ``begin``.

        Returns:
            The account confirmed by the ID token.

        Raises:
            LoginError: wrong provider, failed exchange or invalid ID token.

        Features:
            US-MOD-05, US-SPR-10, F-25
        """
        app = self._app(provider)
        if pending.provider != provider:
            msg = "callback provider differs from the started login"
            raise LoginError(msg)
        try:
            claims = await self._id_token(app, code, pending)
        except (
            AuthlibBaseError,
            JoseError,
            httpx2.HTTPError,
            KeyError,
            ValueError,
        ) as exc:
            raise LoginError(str(exc)) from exc
        return Account(
            provider=provider,
            subject=str(claims["sub"]),
            email=claims.get("email"),
            email_verified=claims.get("email_verified") is True,
        )

    @staticmethod
    async def _id_token(
        app: StarletteOAuth2App, code: str, pending: PendingLogin
    ) -> Mapping[str, Any]:
        token = await app.fetch_access_token(
            redirect_uri=pending.redirect_uri,
            code=code,
            code_verifier=pending.code_verifier,
        )
        if "id_token" not in token:
            msg = "the provider sent no ID token"
            raise LoginError(msg)
        metadata = await app.load_server_metadata()
        options = {
            "iss": {"essential": True, "validate": _issuer_check(metadata["issuer"])},
            "aud": {"essential": True, "value": app.client_id},
        }
        return await app.parse_id_token(
            token, nonce=pending.nonce, claims_options=options, leeway=LEEWAY
        )
