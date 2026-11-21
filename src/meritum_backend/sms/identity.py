"""The sender's number as the salted hash every sessionless channel uses.

Features:
    US-BEZ-06, US-WTY-07, F-20
"""

import hashlib
import hmac

from pydantic import SecretStr


def sender_hash(phone_number: str, salt: SecretStr) -> str:
    """Hash the sender's number; nothing keeps or forwards the raw number.

    SEAM (backend#24): until ``meritum_backend.channels.channel_user_hash`` is on
    develop this repeats its formula, HMAC-SHA-256 of ``sms:<number>`` keyed by the
    salt; after the rebase this body becomes ``channel_user_hash("sms", ...)``.

    Args:
        phone_number: the sender, E.164.
        salt: MERITUM_CHANNEL_HASH_SALT.

    Returns:
        64 lowercase hex characters: the session id and ``channel_user_hash``.

    Features:
        US-BEZ-06, US-WTY-07, F-20
    """
    message = f"sms:{phone_number}".encode()
    return hmac.new(
        salt.get_secret_value().encode(), message, hashlib.sha256
    ).hexdigest()
