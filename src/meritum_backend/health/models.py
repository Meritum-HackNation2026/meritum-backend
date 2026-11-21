"""Models of the readiness report: what the API and the worker lack.

Features:
    US-WDR-08, US-BEZ-03, F-30
"""

from typing import Literal, NamedTuple

from pydantic import BaseModel

from meritum_backend.health.constants import NOT_READY_CODE, NOT_READY_KEY


class Problems(NamedTuple):
    """What one part of the service lacks.

    Attributes:
        missing_env: names of unset required variables.
        unavailable_providers: providers that are configured but unusable.

    Features:
        US-WDR-08, F-30
    """

    missing_env: list[str]
    unavailable_providers: list[str]


class Readiness(BaseModel):
    """Body of GET /api/v1/health: what the API and the worker lack.

    Attributes:
        status: ok when nothing is missing, otherwise degraded.
        env: the environment name.
        database: whether the API's database role can run a query.
        worker: whether the worker published its readiness report.
        missing_env: names of unset required variables (API and worker).
        unavailable_providers: providers the API or the worker cannot use.

    Features:
        US-WDR-08, US-BEZ-03, F-30
    """

    status: Literal["ok", "degraded"]
    env: str
    database: Literal["ok", "unavailable"]
    worker: Literal["ok", "not_reported"]
    missing_env: list[str]
    unavailable_providers: list[str]

    @property
    def ready(self) -> bool:
        """Whether nothing is missing.

        Returns:
            True when ``status`` is ok.
        """
        return self.status == "ok"


class NotReady(BaseModel):
    """503 answer to a check while the service is not ready; names no keys.

    Attributes:
        status: always technical_failure, which is not a verdict.
        code: always not_ready.
        message_key: the copy/pl.json key to show.

    Features:
        US-WDR-08, US-BEZ-03, F-30
    """

    status: Literal["technical_failure"] = "technical_failure"
    # shortcut: a plain string until core contract v4 (core#27) types failure codes.
    code: str = NOT_READY_CODE
    message_key: str = NOT_READY_KEY
