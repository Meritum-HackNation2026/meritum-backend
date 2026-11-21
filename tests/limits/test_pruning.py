import asyncio
import logging
from typing import override

import pytest

from meritum_backend.limits import CheckGate, LimitSettings, Origin, start_pruning
from meritum_backend.limits.adapters import FixedPendingChecks, MemoryRateCounter


def test_finished_windows_go_without_new_traffic() -> None:
    now = [0.0]
    counter = MemoryRateCounter(clock=lambda: now[0])
    gate = CheckGate(counter, FixedPendingChecks(), LimitSettings())

    async def run() -> tuple[int, int]:
        await gate.refusal(Origin(ip="203.0.113.7", region="PL"), "web")
        during = len(counter.keys)
        now[0] += 60  # the window ended; nobody sends anything
        pruner = start_pruning(gate, every_seconds=0.01)
        await asyncio.sleep(0.05)
        pruner.cancel()
        return during, len(counter.keys)

    assert asyncio.run(run()) == (3, 0)


class FlakyCounter(MemoryRateCounter):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    @override
    async def forget_finished(self, window_seconds: int) -> None:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError
        await super().forget_finished(window_seconds)


def test_an_unexpected_error_does_not_stop_the_clean_up(
    caplog: pytest.LogCaptureFixture,
) -> None:
    counter = FlakyCounter()
    gate = CheckGate(counter, FixedPendingChecks(), LimitSettings())

    async def run() -> None:
        pruner = start_pruning(gate, every_seconds=0.01)
        await asyncio.sleep(0.05)
        pruner.cancel()

    with caplog.at_level(logging.WARNING):
        asyncio.run(run())
    assert counter.calls > 1
    assert any(r.levelno == logging.WARNING for r in caplog.records)
