"""Select evaluation storage for the environment."""

from meritum_backend.constants import LOCAL_ENV
from meritum_backend.evaluation.adapters import MemoryEvalStore, PostgresEvalStore
from meritum_backend.evaluation.ports import EvalStore
from meritum_backend.settings import Settings


def build_eval_store(settings: Settings) -> EvalStore:
    """Use the shared API schema outside local development.

    Args:
        settings: environment and API database connection.

    Returns:
        The run and dataset index (PostgreSQL in deployed environments, in-process
        memory locally).

    Features:
        US-OBS-06, US-OBS-05, F-28
    """
    if settings.env == LOCAL_ENV:
        return MemoryEvalStore()
    return PostgresEvalStore(settings.database_url)
