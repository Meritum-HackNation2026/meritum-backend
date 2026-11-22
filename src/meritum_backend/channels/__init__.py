"""Inbound channels without a browser session: Discord, SMS and MCP.

Features:
    US-BEZ-06, US-WTY-08, F-20
"""

from meritum_backend.channels._hash import ChannelHashSalt, channel_user_hash

__all__ = ["ChannelHashSalt", "channel_user_hash"]
