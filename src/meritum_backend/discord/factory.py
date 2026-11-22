"""Builds the interaction replies sender.

Features:
    US-WTY-06, F-03
"""

from meritum_backend.discord.adapters import CdnVoiceDownloader, WebhookReplies
from meritum_backend.discord.ports import InteractionReplies, VoiceDownloader


def build_replies() -> InteractionReplies:
    """Build the webhook sender; interaction tokens need no credentials.

    Returns:
        The Discord webhook sender.

    Features:
        US-WTY-06, F-03
    """
    return WebhookReplies()


def build_voice_downloader() -> VoiceDownloader:
    """Build the CDN downloader of voice messages.

    Returns:
        The Discord CDN downloader.

    Features:
        US-SPR-11, US-WTY-06, F-08, F-03
    """
    return CdnVoiceDownloader()
