"""Salted hash of a channel user id: the session id of Discord, SMS and MCP.

Features:
    US-BEZ-06, US-WTY-08, F-20
"""

import hashlib
import hmac
from typing import Annotated

from meritum_core.checks.contracts import Channel
from pydantic import AfterValidator, SecretStr


def _empty_is_unset(salt: SecretStr | None) -> SecretStr | None:
    return salt if salt is not None and salt.get_secret_value() else None


type ChannelHashSalt = Annotated[SecretStr | None, AfterValidator(_empty_is_unset)]
"""MERITUM_CHANNEL_HASH_SALT as every settings class reads it: empty means unset.

Features:
    US-BEZ-06, US-WTY-08, F-20
"""


def channel_user_hash(channel: Channel, channel_user_id: str, salt: SecretStr) -> str:
    """Hash a channel user id with HMAC-SHA-256 keyed by the configured salt.

    The Discord bot, the Discord mock, the SMS gateway and the MCP server all go
    through this one function, so one person always gets the same session id.

    The channel is part of the hashed message, so the same id in two channels
    (a Discord id and an MCP client id) never becomes one session.

    Args:
        channel: discord, sms or mcp.
        channel_user_id: the Discord user id, phone number or MCP client id.
        salt: MERITUM_CHANNEL_HASH_SALT; never in the repository.

    Returns:
        64 lowercase hex characters (core's HASH_PATTERN).

    Features:
        US-BEZ-06, US-WTY-08, F-20
    """
    key = salt.get_secret_value().encode()
    message = f"{channel}:{channel_user_id}".encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()
