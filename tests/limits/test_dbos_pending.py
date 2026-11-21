import asyncio
from typing import Any, cast

from dbos import DBOSClient
from meritum_core.jobs.contracts import CHECK

from meritum_backend.limits.adapters import DbosPendingChecks


class QueueClient:
    def __init__(self, queued: int, *, fails: bool = False) -> None:
        self.queued = queued
        self.fails = fails
        self.filters: dict[str, Any] = {}

    async def list_queued_workflows_async(self, **filters: Any) -> list[object]:  # ruff: ignore[any-type] -- mirrors the untyped DBOS filters
        self.filters = filters
        if self.fails:
            raise ConnectionError
        return [object()] * min(self.queued, int(filters["limit"]))


def count(client: QueueClient, at_most: int) -> int:
    pending = DbosPendingChecks(cast("DBOSClient", client), app_version="dev")
    return asyncio.run(pending.count(at_most))


def test_counts_only_this_envs_check_workflows_up_to_the_threshold() -> None:
    client = QueueClient(queued=250)
    assert count(client, 100) == 100
    assert client.filters["name"] == CHECK.name
    assert client.filters["queue_name"] == CHECK.queue
    assert client.filters["app_version"] == "dev"
    assert client.filters["limit"] == 100


def test_unreachable_queue_counts_as_empty() -> None:
    assert count(QueueClient(queued=5, fails=True), 100) == 0
