"""VoiceDownloader over Discord's CDN with httpx2.

Features:
    US-SPR-11, US-WTY-06, F-08, F-03
"""

import logging
from urllib.parse import urlsplit

import httpx2
from meritum_core.checks.transcription import MAX_AUDIO_BYTES

from meritum_backend.discord.constants import VOICE_HOSTS, VOICE_TIMEOUT_SECONDS
from meritum_backend.discord.errors import VoiceDownloadError, VoiceTooLargeError

# the signed attachment URL is a credential: never log it
logging.getLogger("httpx2").setLevel(logging.WARNING)


async def _read_capped(client: httpx2.AsyncClient, url: str) -> bytes:
    chunks: list[bytes] = []
    size = 0
    async with client.stream("GET", url) as response:
        response.raise_for_status()
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > MAX_AUDIO_BYTES:
                raise VoiceTooLargeError
            chunks.append(chunk)
    return b"".join(chunks)


class CdnVoiceDownloader:
    """Downloads one attachment, capped at MAX_AUDIO_BYTES.

    Args:
        transport: a mock transport in tests; the network when None.

    Features:
        US-SPR-11, US-WTY-06, F-08, F-03
    """

    def __init__(self, transport: httpx2.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def download(self, url: str) -> bytes:
        """GET the attachment from Discord's CDN, streaming up to the size cap.

        Args:
            url: the signed attachment URL.

        Returns:
            The file's bytes.

        Raises:
            VoiceDownloadError: Not an https Discord CDN URL, the fetch failed or
                the file is over MAX_AUDIO_BYTES (VoiceTooLargeError).
        """
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname not in VOICE_HOSTS:
            raise VoiceDownloadError
        try:
            async with httpx2.AsyncClient(
                transport=self._transport,
                timeout=VOICE_TIMEOUT_SECONDS,
                follow_redirects=False,
            ) as client:
                return await _read_capped(client, url)
        except httpx2.HTTPError as exc:
            raise VoiceDownloadError from exc
