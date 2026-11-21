"""HMAC signature of the gateway's webhooks.

Features:
    US-WTY-07, F-32
"""

import hashlib
import hmac

from meritum_backend.sms.constants import MAX_CLOCK_SKEW_SECONDS


def signature_is_valid(
    key: str, signature: str, timestamp: str, body: bytes, now: float
) -> bool:
    """Check ``hex(HMAC_SHA256(key, raw body + timestamp))`` and the clock skew.

    Args:
        key: the webhook signing key.
        signature: the X-Signature header, hex.
        timestamp: the X-Timestamp header, Unix seconds.
        body: the raw request body, before any JSON parsing.
        now: the current Unix time.

    Returns:
        True only for a valid signature made within MAX_CLOCK_SKEW_SECONDS.

    Features:
        US-WTY-07, F-32
    """
    try:
        is_fresh = abs(now - int(timestamp)) <= MAX_CLOCK_SKEW_SECONDS
    except ValueError:
        return False
    expected = hmac.new(key.encode(), body + timestamp.encode(), hashlib.sha256)
    # bytes: compare_digest rejects non-ASCII str, and the header is untrusted
    given = signature.lower().encode()
    return is_fresh and hmac.compare_digest(expected.hexdigest().encode(), given)
