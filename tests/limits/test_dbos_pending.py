import asyncio
import logging
from dataclasses import dataclass
from typing import cast

import pytest
from dbos import DBOSClient
from meritum_core.jobs.contracts import CHECK

from meritum_backend.limits.adapters import DbosPendingChecks


@dataclass(frozen=True)
class Filters:
    name: str
    queue_name: str
    app_version: str
    limit: int


class QueueClient:
    def __init__(self, queued: int, *, fails: bool = False) -> None:
        self.queued = queued
        self.fails = fails
        self.filters: Filters | None = None

    async def list_queued_workflows_async(  # ruff: ignore[too-many-arguments] -- the DBOS filters the adapter passes
        self,
        *,
        name: str,
        queue_name: str,
        app_version: str,
        limit: int,
        load_input: bool,
        load_output: bool,
    ) -> list[object]:
        assert not load_input
        assert not load_output
        self.filters = Filters(name, queue_name, app_version, limit)
        if self.fails:
            raise ConnectionError
        return [object()] * min(self.queued, limit)


def count(client: QueueClient, at_most: int) -> int:
    pending = DbosPendingChecks(cast("DBOSClient", client), app_version="dev")
    return asyncio.run(pending.count(at_most))


def test_counts_only_this_envs_check_workflows_up_to_the_threshold() -> None:
    client = QueueClient(queued=250)
    assert count(client, 100) == 100
    assert client.filters == Filters(CHECK.name, CHECK.queue, "dev", 100)


def test_unreachable_queue_counts_as_empty_and_logs_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        assert count(QueueClient(queued=5, fails=True), 100) == 0
    assert [r.levelno for r in caplog.records] == [logging.WARNING]
