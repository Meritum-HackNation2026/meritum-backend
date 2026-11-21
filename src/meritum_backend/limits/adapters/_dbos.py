"""PendingChecks over the worker's DBOS queue.

Features:
    US-WDR-03, F-23
"""

import logging

from dbos import DBOSClient
from meritum_core.jobs.contracts import CHECK

_log = logging.getLogger(__name__)


class DbosPendingChecks:
    """Counts the enqueued and running ``check`` workflows of one environment.

    Args:
        client: client bound to the worker's system database and schema.
        app_version: the environment name, as the jobs are enqueued with it.

    Features:
        US-WDR-03, F-23
    """

    def __init__(self, client: DBOSClient, app_version: str) -> None:
        self._client = client
        self._app_version = app_version

    async def count(self, at_most: int) -> int:
        """Count queued checks, reading at most ``at_most`` rows.

        Args:
            at_most: the threshold.

        Returns:
            The count, at most ``at_most``; 0 when DBOS is unreachable (the
            enqueue then answers 503 on its own).
        """
        try:
            queued = await self._client.list_queued_workflows_async(
                name=CHECK.name,
                queue_name=CHECK.queue,
                app_version=self._app_version,
                limit=at_most,
                load_input=False,
                load_output=False,
            )
        except Exception:  # ruff: ignore[blind-except] -- DBOS wraps driver errors in its own types
            _log.warning("pending checks unavailable; let through", exc_info=True)
            return 0
        return len(queued)
