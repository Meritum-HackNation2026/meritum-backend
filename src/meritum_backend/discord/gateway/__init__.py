"""Discord Gateway process: answers mentions on servers and direct messages.

Run as ``python -m meritum_backend.discord.gateway`` (the same image as the API).

Features:
    US-WTY-06, F-03, ADR-08
"""

from meritum_backend.discord.gateway._client import MeritumClient, incoming_from
from meritum_backend.discord.gateway._handler import (
    GatewayHandler,
    Incoming,
    strip_mention,
)
from meritum_backend.discord.gateway._run import run

__all__ = [
    "GatewayHandler",
    "Incoming",
    "MeritumClient",
    "incoming_from",
    "run",
    "strip_mention",
]
