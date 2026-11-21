"""Builds the interaction replies sender.

Features:
    US-WTY-06, F-03
"""

from meritum_backend.discord.adapters import WebhookReplies
from meritum_backend.discord.ports import InteractionReplies


def build_replies() -> InteractionReplies:
    """Build the webhook sender; interaction tokens need no credentials.

    Returns:
        The Discord webhook sender.

    Features:
        US-WTY-06, F-03
    """
    return WebhookReplies()
