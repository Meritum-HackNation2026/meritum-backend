import asyncio

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
