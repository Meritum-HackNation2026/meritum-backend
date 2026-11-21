"""Fake login provider for tests and behave: no network, one known code."""

import secrets
from urllib.parse import urlencode

from meritum_backend.auth.constants import FAKE_CODE, GOOGLE, MICROSOFT, TOKEN_BYTES
from meritum_backend.auth.errors import LoginError
from meritum_backend.auth.models import Account, LoginStart, PendingLogin


class FakeLogin:
    """Accepts ``FAKE_CODE`` and returns the same account on every provider.

    Never built by the factory: tests put it in place of the real provider.

    Args:
        subject: the account id every login returns.
        email: the e-mail address every login returns.

    Attributes:
        providers: ``google`` and ``microsoft``.

    Features:
        US-MOD-05, US-SPR-10, F-25
    """

    def __init__(self, subject: str, email: str) -> None:
        self._subject = subject
        self._email = email

    @property
    def providers(self) -> frozenset[str]:
        """``google`` and ``microsoft``."""
        return frozenset({GOOGLE, MICROSOFT})

    async def begin(self, provider: str, redirect_uri: str) -> LoginStart:
        """Return a fake authorization URL with a fresh state.

        Args:
            provider: the provider name.
            redirect_uri: the callback address.

        Returns:
            The URL (carrying ``state``) and the pending login.

        Raises:
            LoginError: unknown provider.

        Features:
            US-MOD-05, F-25
        """
        if provider not in self.providers:
            msg = f"unknown provider {provider!r}"
            raise LoginError(msg)
        pending = PendingLogin(
            provider=provider,
            state=secrets.token_urlsafe(TOKEN_BYTES),
            nonce=secrets.token_urlsafe(TOKEN_BYTES),
            code_verifier=secrets.token_urlsafe(TOKEN_BYTES),
            redirect_uri=redirect_uri,
        )
        query = urlencode({"state": pending.state, "redirect_uri": redirect_uri})
        return LoginStart(url=f"https://idp.invalid/authorize?{query}", pending=pending)

    async def complete(
        self, provider: str, code: str, pending: PendingLogin
    ) -> Account:
        """Accept only ``FAKE_CODE`` for the provider the login started with.

        Args:
            provider: the provider name.
            code: the authorization code.
            pending: the data saved by ``begin``.

        Returns:
            The fake account.

        Raises:
            LoginError: another code or provider.

        Features:
            US-MOD-05, F-25
        """
        if code != FAKE_CODE or provider != pending.provider:
            msg = "fake provider refused the code"
            raise LoginError(msg)
        return Account(
            provider=provider,
            subject=self._subject,
            email=self._email,
            email_verified=True,
        )
