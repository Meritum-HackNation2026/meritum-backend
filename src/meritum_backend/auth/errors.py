"""Errors of the auth slice."""


class LoginError(Exception):
    """The provider did not confirm who the user is; no session is created.

    Covers an unknown provider, a failed code exchange and an ID token that fails
    any check (signature, issuer, audience, expiry, nonce).

    Features:
        US-MOD-05, US-SPR-10, F-25
    """
