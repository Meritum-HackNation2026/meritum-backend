"""Discord channel: HTTP interactions (slash and message commands) and reply format.

Features:
    US-WTY-06, US-BEZ-07, F-03, F-21
"""

from meritum_backend.discord.constants import MESSAGE_MAX_CHARS
from meritum_backend.discord.messages import reply_messages, split_text

__all__ = ["MESSAGE_MAX_CHARS", "reply_messages", "split_text"]
