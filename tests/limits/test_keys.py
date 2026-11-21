import asyncio
import hashlib
import hmac
import logging

import psycopg
import pytest
from pydantic import SecretStr

from meritum_backend.limits import CheckGate, LimitSettings, Origin
from meritum_backend.limits.adapters import FixedPendingChecks, PostgresRateCounter

IP = "203.0.113.7"
HOME = Origin(ip=IP, region="PL")


class RecordingCounter:
    def __init__(self) -> None:
        self.keys: list[str] = []

    async def hit(self, key: str, window_seconds: int) -> int:
        del window_seconds
        self.keys.append(key)
        return 1

    async def forget_finished(self, window_seconds: int) -> None:
        del window_seconds
        self.keys.clear()


def ip_key(salt: str | None) -> str:
    counter = RecordingCounter()
    secret = SecretStr(salt) if salt is not None else None
    limits = LimitSettings(channel_hash_salt=secret)
    gate = CheckGate(counter, FixedPendingChecks(), limits)
    asyncio.run(gate.refusal(HOME, "web"))
    return counter.keys[0]


def test_ip_key_is_hmac_sha256_with_the_secret() -> None:
    digest = hmac.new(b"s3cret", f"ip:{IP}".encode(), hashlib.sha256).hexdigest()
    assert ip_key("s3cret") == f"ip:{digest}"


def test_ip_key_is_not_a_plain_hash_of_the_address() -> None:
    plain = hashlib.sha256(IP.encode()).hexdigest()
    assert plain not in ip_key("s3cret")
    assert plain not in ip_key(None)
    assert IP not in ip_key(None)


def test_another_secret_gives_another_key() -> None:
    assert ip_key("s3cret") != ip_key("other")


def test_without_a_secret_the_process_still_counts_one_address_as_one_key() -> None:
    assert ip_key(None) == ip_key(None)


def test_an_empty_secret_counts_as_unset() -> None:
    empty = hmac.new(b"", f"ip:{IP}".encode(), hashlib.sha256).hexdigest()
    assert ip_key("") == ip_key(None) != f"ip:{empty}"
    assert LimitSettings(channel_hash_salt=SecretStr("")).channel_hash_salt is None


def test_unreachable_counter_lets_through_and_logs_no_address(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise psycopg.OperationalError

    monkeypatch.setattr(psycopg.AsyncConnection, "connect", refuse)
    counter = PostgresRateCounter("postgresql://x:x@127.0.0.1:1/x")
    gate = CheckGate(counter, FixedPendingChecks(), LimitSettings())
    with caplog.at_level(logging.WARNING):
        assert asyncio.run(gate.refusal(HOME, "web")) is None
    assert caplog.records
    assert all(IP not in r.getMessage() for r in caplog.records)
    assert all(r.exc_text is None or IP not in r.exc_text for r in caplog.records)


def test_secret_comes_from_the_channel_hash_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MERITUM_CHANNEL_HASH_SALT", "s3cret")
    assert LimitSettings().channel_hash_salt == SecretStr("s3cret")


def test_event_stream_key_is_hmac_too() -> None:
    counter = RecordingCounter()
    limits = LimitSettings(channel_hash_salt=SecretStr("s3cret"))
    gate = CheckGate(counter, FixedPendingChecks(), limits)
    asyncio.run(gate.stream_refusal(HOME))
    digest = hmac.new(b"s3cret", f"events:{IP}".encode(), hashlib.sha256).hexdigest()
    assert counter.keys == [f"events:{digest}"]
