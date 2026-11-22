import asyncio

import pytest

from meritum_backend.limits import (
    BUSY,
    RATE_LIMITED,
    CheckGate,
    LimitSettings,
    Origin,
    Refusal,
)
from meritum_backend.limits.adapters import FixedPendingChecks, MemoryRateCounter

LIMITS = LimitSettings(
    checks_per_ip_per_minute=10,
    checks_per_region_per_minute=100,
    checks_per_channel_per_minute=1000,
    max_pending_checks=50,
)
HOME = Origin(ip="203.0.113.7", region="PL")


def refusals(
    gate: CheckGate, origin: Origin, times: int, channel: str = "web"
) -> list[Refusal | None]:
    async def run() -> list[Refusal | None]:
        return [await gate.refusal(origin, channel) for _ in range(times)]

    return asyncio.run(run())


def gate(counter: MemoryRateCounter, pending: int = 0, **limits: int) -> CheckGate:
    settings = LIMITS.model_copy(update=limits)
    return CheckGate(counter, FixedPendingChecks(pending), settings)


def test_eleventh_check_from_one_ip_in_a_minute_is_refused() -> None:
    answers = refusals(gate(MemoryRateCounter()), HOME, 11)
    assert answers == [None] * 10 + [RATE_LIMITED]


def test_other_ips_keep_their_own_budget() -> None:
    shared = gate(MemoryRateCounter())
    refusals(shared, HOME, 10)
    assert refusals(shared, Origin(ip="198.51.100.1", region="PL"), 1) == [None]


def test_two_instances_on_one_counter_share_the_limit() -> None:
    counter = MemoryRateCounter()
    first, second = gate(counter), gate(counter)
    assert refusals(first, HOME, 6) == [None] * 6
    assert refusals(second, HOME, 5) == [None] * 4 + [RATE_LIMITED]


def test_region_limit_counts_every_ip_of_the_region() -> None:
    shared = gate(MemoryRateCounter(), checks_per_region_per_minute=2)
    refusals(shared, HOME, 2)
    other = Origin(ip="198.51.100.1", region="PL")
    assert refusals(shared, other, 1) == [RATE_LIMITED]
    assert refusals(shared, Origin(ip="198.51.100.1", region="DE"), 1) == [None]


def test_channel_limit_counts_every_client_of_the_channel() -> None:
    shared = gate(MemoryRateCounter(), checks_per_channel_per_minute=2)
    refusals(shared, HOME, 2, channel="extension")
    other = Origin(ip="198.51.100.1", region="DE")
    assert refusals(shared, other, 1, channel="extension") == [RATE_LIMITED]
    assert refusals(shared, other, 1, channel="web") == [None]


@pytest.mark.parametrize(("pending", "answer"), [(49, None), (50, BUSY)])
def test_pending_checks_threshold_answers_busy(
    pending: int, answer: Refusal | None
) -> None:
    assert refusals(gate(MemoryRateCounter(), pending), HOME, 1) == [answer]


def test_window_restarts_the_count() -> None:
    times = iter([0.0, 59.0, 60.0])
    counter = MemoryRateCounter(clock=lambda: next(times))

    async def hits() -> list[int]:
        return [await counter.hit("k", window_seconds=60) for _ in range(3)]

    assert asyncio.run(hits()) == [1, 2, 1]


def test_limits_come_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MERITUM_CHECKS_PER_IP_PER_MINUTE", "3")
    monkeypatch.setenv("MERITUM_MAX_PENDING_CHECKS", "7")
    settings = LimitSettings()
    assert settings.checks_per_ip_per_minute == 3
    assert settings.max_pending_checks == 7
