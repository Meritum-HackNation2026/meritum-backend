"""Models of the auth slice: the signed-in account and a login in progress."""

from pydantic import BaseModel, ConfigDict


class Account(BaseModel):
    """An account confirmed by an OIDC provider; login alone grants no role.

    Attributes:
        provider: the provider name (``google`` or ``microsoft``).
        subject: the provider's stable account id (the ``sub`` claim).
        email: the e-mail address from the ID token, when the provider sent one.
        email_verified: whether the provider says it verified the address.

    Features:
        US-MOD-05, US-SPR-10, F-25, F-31
    """

    model_config = ConfigDict(frozen=True)

    provider: str
    subject: str
    email: str | None = None
    email_verified: bool = False


class PendingLogin(BaseModel):
    """What the callback needs to finish a login; kept in the session meanwhile.

    Attributes:
        provider: the provider the user was sent to.
        state: the anti-forgery value the provider must send back unchanged.
        nonce: the value the ID token must carry (replay protection).
        code_verifier: the PKCE secret matching the code challenge sent.
        redirect_uri: the callback address registered with the provider.

    Features:
        US-MOD-05, US-SPR-10, F-25
    """

    model_config = ConfigDict(frozen=True)

    provider: str
    state: str
    nonce: str
    code_verifier: str
    redirect_uri: str


class LoginStart(BaseModel):
    """Where to send the user and what to remember until they come back.

    Attributes:
        url: the provider's authorization URL.
        pending: the data to keep in the session until the callback.

    Features:
        US-MOD-05, US-SPR-10, F-25
    """

    model_config = ConfigDict(frozen=True)

    url: str
    pending: PendingLogin


class Me(BaseModel):
    """The signed-in account and the token for state-changing requests.

    Attributes:
        provider: the provider name.
        subject: the provider's account id.
        email: the e-mail address from the ID token.
        email_verified: whether the provider verified the address.
        csrf_token: the value to send in ``X-CSRF-Token``.

    Features:
        US-MOD-05, US-SPR-10, F-25
    """

    model_config = ConfigDict(frozen=True)

    provider: str
    subject: str
    email: str | None
    email_verified: bool
    csrf_token: str
