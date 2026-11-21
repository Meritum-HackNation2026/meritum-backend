"""Constants of the auth slice."""

from typing import Final

SESSION_COOKIE: Final = "meritum_session"
"""Name of the signed, httpOnly session cookie."""

SESSION_MAX_AGE: Final = 8 * 60 * 60
"""Session lifetime in seconds (8 h of a moderator's shift), counted from login:
the cookie is re-signed only when the session changes, never on reads."""

TOKEN_BYTES: Final = 32
"""Random bytes in the CSRF token and in the fake provider's state and nonce."""

PKCE_METHOD: Final = "S256"
"""PKCE code challenge method sent to every provider."""

CALLBACK_PATH: Final = "/api/v1/auth/callback/{provider}"
"""Path of the OIDC callback, appended to the public address."""

HOME: Final = "/"
"""Where the browser goes after a successful login: the web app's home page."""

CSRF_HEADER: Final = "X-CSRF-Token"
"""Header that state-changing requests repeat the session's CSRF token in."""

SCOPE: Final = "openid email profile"
"""OIDC scopes asked for: the account id and the e-mail address."""

LEEWAY: Final = 60
"""Clock skew in seconds tolerated when checking ID token times."""

GOOGLE: Final = "google"
"""Provider name of Google accounts (path segment of login and callback)."""

MICROSOFT: Final = "microsoft"
"""Provider name of Microsoft accounts (path segment of login and callback)."""

GOOGLE_METADATA: Final = "https://accounts.google.com/.well-known/openid-configuration"
"""Google's OIDC discovery document."""

MICROSOFT_METADATA: Final = (
    "https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration"
)
"""Microsoft identity platform discovery document; ``{tenant}`` from settings."""

TENANT_PLACEHOLDER: Final = "{tenantid}"
"""Placeholder in Microsoft's multi-tenant issuer, replaced by the ``tid`` claim."""

PUBLIC_URLS: Final[dict[str, str]] = {
    "dev": "https://meritum-dev.gburek.app",
    "prd": "https://meritum.gburek.app",
}
"""Public address per environment: the base of the OIDC callback URLs."""

LOCAL_URL: Final = "http://localhost:8000"
"""Public address of any other environment (local uvicorn)."""

FAKE_CODE: Final = "fake-valid-code"
"""The only authorization code the fake login provider accepts (tests)."""

SESSION_PENDING: Final = "pending_login"
"""Session key of the login in progress (state, nonce, PKCE verifier)."""

SESSION_ACCOUNT: Final = "account"
"""Session key of the signed-in account."""

SESSION_SINCE: Final = "since"
"""Session key of the login time (Unix seconds); bounds the session lifetime."""

SESSION_CSRF: Final = "csrf"
"""Session key of the CSRF token, drawn anew at every login."""

SESSION_EXPIRES: Final = "expires"
"""Optional absolute expiry for sessions tied to a short-lived grant."""

SESSION_READ_ONLY: Final = "read_only"
"""Signed session flag for accounts that may only read evaluation data."""
