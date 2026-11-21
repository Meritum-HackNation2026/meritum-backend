"""Models of the auth slice: the signed-in account and a login in progress."""

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict

from meritum_backend.auth.constants import HOME, RETURN_PATH_CHARS, RETURN_PATH_MAX


def _same_origin_path(path: str) -> str:
    """Keep ``path`` only when it is a relative path on this site.

    Args:
        path: the return path the login was started with.

    Returns:
        ``path``, or ``HOME`` for anything that could leave the site: a scheme,
        ``//host``, a backslash, whitespace, control characters or a long value.
    """
    is_absolute_path = path.startswith("/") and not path.startswith("//")
    is_plain = len(path) <= RETURN_PATH_MAX and set(path) <= RETURN_PATH_CHARS
    return path if is_absolute_path and is_plain else HOME


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
        return_to: the page to open after login; anything but a relative path
            on this site becomes ``HOME`` (no open redirect).

    Features:
        US-MOD-05, US-SPR-10, F-25
    """

    model_config = ConfigDict(frozen=True)

    provider: str
    state: str
    nonce: str
    code_verifier: str
    redirect_uri: str
    return_to: Annotated[str, AfterValidator(_same_origin_path)] = HOME


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
