"""Inbound channels without a browser session: Discord, SMS and MCP.

Features:
    US-BEZ-06, US-WTY-08, F-20
"""

from meritum_backend.channels._hash import ChannelHashSalt, channel_user_hash
from meritum_backend.channels._non_verdict import non_verdict_text

__all__ = ["ChannelHashSalt", "channel_user_hash", "non_verdict_text"]
