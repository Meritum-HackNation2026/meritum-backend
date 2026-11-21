"""Auth slice: OIDC login with Google or Microsoft and a session in a signed cookie.

Features:
    US-MOD-05, US-SPR-10, F-25, F-31
"""

from meritum_backend.auth.errors import LoginError
from meritum_backend.auth.models import Account, LoginStart, PendingLogin
from meritum_backend.auth.ports import LoginProvider

__all__ = ["Account", "LoginError", "LoginProvider", "LoginStart", "PendingLogin"]
