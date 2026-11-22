"""The worker's readiness report, read through the `readiness` workflow (ADR-03).

The API enqueues the workflow and reads its `readiness` event. It enqueues a new
workflow when the last report is older than WORKER_REFRESH_SECONDS (so a restarted
worker is seen) and when an enqueued one stayed unanswered that long (it failed or
no worker knew it). While the worker is down, a polled API therefore adds one
`readiness` workflow per WORKER_REFRESH_SECONDS to the queue.

Features:
    US-WDR-08, F-30, ADR-03
"""

import asyncio
import logging
from collections.abc import Callable
from uuid import uuid4

from meritum_core.jobs.constants import READINESS_KEY
from meritum_core.jobs.contracts import READINESS, ReadinessInput, ReadinessReport
from meritum_core.jobs.ports import JobQueue

from meritum_backend.health.constants import WORKER_REFRESH_SECONDS, WORKFLOW_ID_PREFIX

_logger = logging.getLogger(__name__)


def _new_workflow_id() -> str:
    return f"{WORKFLOW_ID_PREFIX}{uuid4().hex}"


class WorkerReports:
    """Asks the worker for its readiness report and keeps the latest one.

    Attributes:
        workflow_id: the `readiness` workflow being read; replaced when a new one
            is enqueued.

    Args:
        jobs: the job queue the report comes through.
        clock: monotonic seconds.

    Features:
        US-WDR-08, F-30, ADR-03
    """

    def __init__(self, jobs: JobQueue, clock: Callable[[], float]) -> None:
        self._jobs = jobs
        self._clock = clock
        self.workflow_id = _new_workflow_id()
        self._enqueued_at: float | None = None  # None: not enqueued yet
        # (workflow id, when its report arrived, the report)
        self._report: tuple[str, float, ReadinessReport] | None = None
        self._refreshed_at: float | None = None  # when a due refresh was enqueued

    def _since(self, moment: float | None) -> float:
        return 0.0 if moment is None else self._clock() - moment

    def _answered(self) -> bool:
        return self._report is not None and self._report[0] == self.workflow_id

    def _ask_again(self) -> None:
        self.workflow_id = _new_workflow_id()
        self._enqueued_at = None

    async def _read_event(self, wait: float) -> ReadinessReport | None:
        try:
            async with asyncio.timeout(wait):
                if self._enqueued_at is None:
                    payload = ReadinessInput()
                    await self._jobs.enqueue(
                        READINESS, payload, workflow_id=self.workflow_id
                    )
                    self._enqueued_at = self._clock()
                return await self._jobs.event(
                    self.workflow_id,
                    READINESS_KEY,
                    ReadinessReport,
                    timeout_seconds=wait,
                )
        except TimeoutError:  # no answer yet; the caller decides what that means
            return None
        except Exception as exc:  # ruff: ignore[blind-except] -- DBOS wraps driver errors; a bad report is no report
            _logger.warning(
                "worker readiness report unreadable: %s", type(exc).__name__
            )
            return None

    async def latest(self, wait: float) -> ReadinessReport | None:
        """The worker's latest report, refreshing it when due.

        Args:
            wait: how long to wait for an answer, in seconds.

        Returns:
            The report, or None when the worker never answered or left a refresh
            unanswered for WORKER_REFRESH_SECONDS.

        Features:
            US-WDR-08, F-30
        """
        if (
            self._answered()
            and self._report
            and (self._since(self._report[1]) >= WORKER_REFRESH_SECONDS)
        ):
            self._refreshed_at = self._clock()
            self._ask_again()
        report = await self._read_event(wait)
        if report is not None and not self._answered():
            self._report = (self.workflow_id, self._clock(), report)
            self._refreshed_at = None
        elif not self._answered() and (
            self._since(self._enqueued_at) >= WORKER_REFRESH_SECONDS
        ):
            self._ask_again()
        expired = self._since(self._refreshed_at) >= WORKER_REFRESH_SECONDS
        return None if self._report is None or expired else self._report[2]
