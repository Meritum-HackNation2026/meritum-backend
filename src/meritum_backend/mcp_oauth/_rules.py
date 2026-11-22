"""Pure checks of the MCP OAuth server: redirect URIs, PKCE and scope.

Features:
    US-WDR-06, US-BEZ-02, F-37, ADR-17
"""

import base64
import hashlib
import hmac
from urllib.parse import urlsplit

from meritum_backend.mcp_oauth.constants import (
    CHALLENGE_LENGTH,
    LOOPBACK_HOSTS,
    PKCE_METHOD,
    SCOPE,
    URI_MAX,
    URL_SAFE,
    VERIFIER_MAX,
    VERIFIER_MIN,
)
from meritum_backend.mcp_oauth.models import AuthorizeRequest


def redirect_allowed(uri: str) -> bool:
    """Whether a client may register this redirect URI.

    Args:
        uri: the redirect URI.

    Returns:
        True for an https URI with a host, or http to a loopback host, without
        a fragment or credentials and at most ``URI_MAX`` characters.

    Features:
        US-WDR-06, F-37, ADR-17
    """
    try:
        parts = urlsplit(uri)
        host = parts.hostname
    except ValueError:
        return False
    is_clean = len(uri) <= URI_MAX and not parts.fragment and "@" not in parts.netloc
    is_https = parts.scheme == "https" and bool(host)
    is_loopback = parts.scheme == "http" and host in LOOPBACK_HOSTS
    return is_clean and (is_https or is_loopback)


def challenge_valid(challenge: str) -> bool:
    """Whether a value looks like an S256 code challenge.

    Args:
        challenge: the ``code_challenge`` parameter.

    Returns:
        True for 43 base64url characters.

    Features:
        US-WDR-06, F-37, ADR-17
    """
    return len(challenge) == CHALLENGE_LENGTH and set(challenge) <= URL_SAFE


def pkce_matches(verifier: str, challenge: str) -> bool:
    """RFC 7636 S256: the verifier hashes to the challenge.

    Args:
        verifier: the ``code_verifier`` from the token request.
        challenge: the challenge the code was issued with.

    Returns:
        Whether they match (constant-time comparison).

    Features:
        US-WDR-06, F-37, ADR-17
    """
    length_ok = VERIFIER_MIN <= len(verifier) <= VERIFIER_MAX
    is_well_formed = length_ok and set(verifier) <= URL_SAFE
    digest = hashlib.sha256(verifier.encode()).digest()
    hashed = base64.urlsafe_b64encode(digest).rstrip(b"=")
    return is_well_formed and hmac.compare_digest(hashed, challenge.encode())


def scope_known(scope: str) -> bool:
    """Whether every requested scope exists.

    Args:
        scope: space-separated scopes; empty means the default.

    Returns:
        True when nothing but ``mcp`` is asked for.

    Features:
        US-WDR-06, F-37, ADR-17
    """
    return set(scope.split()) <= {SCOPE}


def refusal(request: AuthorizeRequest, *, resource_known: bool) -> str | None:
    """The OAuth error of an authorization request whose client checks out.

    Args:
        request: the request.
        resource_known: whether its ``resource`` names this server.

    Returns:
        The error code to send to the redirect URI, or None when valid.

    Features:
        US-WDR-06, F-37, ADR-17
    """
    if request.response_type != "code":
        return "unsupported_response_type"
    pkce_ok = request.code_challenge_method == PKCE_METHOD and challenge_valid(
        request.code_challenge
    )
    if not pkce_ok:
        return "invalid_request"
    if not scope_known(request.scope):
        return "invalid_scope"
    return None if resource_known else "invalid_target"
