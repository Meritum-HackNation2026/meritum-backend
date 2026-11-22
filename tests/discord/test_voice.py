import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import httpx2
import pytest
from meritum_core.checks.transcription import MAX_AUDIO_BYTES
from meritum_core.shared.blobs.adapters import MemoryBlobStore
from tests.checks.cache_fakes import RESULT, FinishedWorker
from tests.conftest import MakeProbe
from tests.discord.fakes import flat
from tests.discord.test_gateway import gateway_setup, make_incoming

import discord
from meritum_backend.discord.adapters import CdnVoiceDownloader
from meritum_backend.discord.constants import FAILURE_TEXT, TRANSCRIPT_HINT
from meritum_backend.discord.errors import VoiceDownloadError, VoiceTooLargeError
from meritum_backend.discord.gateway import GatewayHandler, Incoming, incoming_from
from meritum_backend.discord.messages import reply_message

CDN = "https://cdn.discordapp.com/attachments/1/2/voice-message.ogg?ex=abc"


def ogg(seconds: int) -> bytes:
    head = b"OggS\x00" + bytes(23) + b"OpusHead" + bytes(8)
    last = bytearray(b"OggS\x00" + bytes(23))  # the page that holds the length
    last[6:14] = (seconds * 48_000).to_bytes(8, "little")
    return head + bytes(last)


class FakeCdn:
    def __init__(self, data: bytes | Exception) -> None:
        self.data = data
        self.urls: list[str] = []

    async def download(self, url: str) -> bytes:
        self.urls.append(url)
        if isinstance(self.data, Exception):
            raise self.data
        return self.data


def _voice_handler(
    make_probe: MakeProbe, data: bytes | Exception
) -> tuple[GatewayHandler, list[str], FinishedWorker, MemoryBlobStore, FakeCdn]:
    jobs = FinishedWorker()
    handler, sent = gateway_setup(make_probe, jobs)
    blobs, cdn = MemoryBlobStore(), FakeCdn(data)
    ports = replace(handler.ports, blobs=blobs)
    return GatewayHandler(ports, voice=cdn), sent, jobs, blobs, cdn


def _voice_incoming(sent: list[str]) -> Incoming:
    base = make_incoming(sent, "")
    return Incoming(base.message_id, base.user_id, "", base.reply, CDN)


def test_voice_message_is_downloaded_stored_and_checked_by_audio_id(
    make_probe: MakeProbe,
) -> None:
    handler, sent, jobs, _, cdn = _voice_handler(make_probe, ogg(40))
    asyncio.run(handler.handle(_voice_incoming(sent)))
    assert cdn.urls == [CDN]
    payload = jobs.enqueued[0].payload.model_dump_json()
    assert '"audio_id":"' in payload
    assert len(sent) == 1


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"nie nagranie", "Przyjmujemy pliki: OGG, MP3, M4A, WAV."),
        (ogg(10_000), "za długie"),
        (VoiceTooLargeError(), "za duży"),
    ],
)
def test_refused_recording_gets_a_reason_and_starts_nothing(
    make_probe: MakeProbe, data: bytes | Exception, expected: str
) -> None:
    handler, sent, jobs, _, _ = _voice_handler(make_probe, data)
    asyncio.run(handler.handle(_voice_incoming(sent)))
    assert len(sent) == 1
    assert expected in sent[0]
    assert not jobs.enqueued


def test_failed_download_is_a_technical_failure(make_probe: MakeProbe) -> None:
    handler, sent, jobs, _, _ = _voice_handler(make_probe, VoiceDownloadError())
    asyncio.run(handler.handle(_voice_incoming(sent)))
    assert sent == [FAILURE_TEXT]
    assert not jobs.enqueued


def test_voice_without_a_downloader_is_a_technical_failure(
    make_probe: MakeProbe,
) -> None:
    handler, sent = gateway_setup(make_probe, FinishedWorker())
    asyncio.run(handler.handle(_voice_incoming(sent)))
    assert sent == [FAILURE_TEXT]


def test_transcript_is_shown_with_the_automatic_hint() -> None:
    result = RESULT.model_copy(update={"transcript": "Ziemia jest płaska"})
    text = flat(reply_message(result, "https://x/c", first_contact=False))
    assert "„Ziemia jest płaska”" in text
    assert TRANSCRIPT_HINT in text


def _message(*, voice: bool) -> MagicMock:
    message = MagicMock(spec=discord.Message)
    message.author = MagicMock(bot=False, id=7)
    message.id = 99
    message.content = ""
    message.guild = None
    message.mentions = []
    attachment = MagicMock(url=CDN, is_voice_message=lambda: voice)
    message.attachments = [attachment]
    message.channel = MagicMock(send=AsyncMock())
    return message


def test_gateway_message_with_a_voice_attachment_carries_its_url() -> None:
    incoming = incoming_from(_message(voice=True), MagicMock(id=42))
    assert incoming is not None
    assert incoming.voice_url == CDN
    other = incoming_from(_message(voice=False), MagicMock(id=42))
    assert other is not None
    assert other.voice_url is None


def _cdn(handler: httpx2.MockTransport) -> CdnVoiceDownloader:
    return CdnVoiceDownloader(handler)


def test_cdn_downloads_the_attachment() -> None:
    cdn = _cdn(httpx2.MockTransport(lambda _: httpx2.Response(200, content=b"abc")))
    assert asyncio.run(cdn.download(CDN)) == b"abc"


def test_cdn_refuses_other_hosts_and_plain_http() -> None:
    cdn = _cdn(httpx2.MockTransport(lambda _: httpx2.Response(200, content=b"abc")))
    for url in ("https://evil.example/a.ogg", CDN.replace("https", "http")):
        with pytest.raises(VoiceDownloadError):
            asyncio.run(cdn.download(url))


def test_cdn_error_and_oversize_are_distinct() -> None:
    gone = _cdn(httpx2.MockTransport(lambda _: httpx2.Response(404)))
    with pytest.raises(VoiceDownloadError):
        asyncio.run(gone.download(CDN))
    big = _cdn(
        httpx2.MockTransport(
            lambda _: httpx2.Response(200, content=bytes(MAX_AUDIO_BYTES + 1))
        )
    )
    with pytest.raises(VoiceTooLargeError):
        asyncio.run(big.download(CDN))
