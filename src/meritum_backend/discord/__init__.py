"""Discord channel: HTTP interactions (slash and message commands) and reply format.

Features:
    US-WTY-06, US-BEZ-07, F-03, F-21
"""

from meritum_backend.discord.messages import Message, reply_message

__all__ = ["Message", "reply_message"]
