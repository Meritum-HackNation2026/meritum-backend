"""Port of the login provider: OIDC authorization code flow, provider-neutral."""

from typing import Protocol

from meritum_backend.auth.models import Account, LoginStart, PendingLogin


class LoginProvider(Protocol):
    """Signs users in with an external OIDC provider.

    Attributes:
        providers: names of the configured providers.

    Features:
        US-MOD-05, US-SPR-10, F-25
    """

    @property
    def providers(self) -> frozenset[str]:
        """Names of the configured providers."""
        ...

    async def begin(self, provider: str, redirect_uri: str) -> LoginStart:
        """Start a login: the authorization URL and the data to keep until callback.

        Args:
            provider: the provider name.
            redirect_uri: the callback address registered with the provider.

        Returns:
            The URL to redirect to and the pending login.

        Raises:
            LoginError: the provider is not configured.
        """
        ...

    async def complete(
        self, provider: str, code: str, pending: PendingLogin
    ) -> Account:
        """Exchange the code and validate the ID token.

        The caller has already matched the returned ``state`` with ``pending``.

        Args:
            provider: the provider name from the callback path.
            code: the authorization code from the callback.
            pending: the data saved by ``begin``.

        Returns:
            The account the ID token confirms.

        Raises:
            LoginError: the exchange failed or the ID token is not valid.
        """
        ...
