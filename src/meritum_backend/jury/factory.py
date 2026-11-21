"""Select jury link storage for the environment."""

from time import time

from meritum_backend.jury.adapters import MemoryJuryLinks, PostgresJuryLinks
from meritum_backend.jury.ports import JuryLinks
from meritum_backend.limits.adapters import MemoryRateCounter, PostgresRateCounter
from meritum_backend.limits.ports import RateCounter
from meritum_backend.settings import Settings


def build_jury_links(settings: Settings) -> JuryLinks:
    """Use the shared API schema outside local development.

    Args:
        settings: environment and API database connection.

    Returns:
        A persistent store for deployed environments, or a local memory store.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """
    if settings.env == "local":
        return MemoryJuryLinks()
    return PostgresJuryLinks(settings.database_url)


def build_jury_counter(settings: Settings) -> RateCounter:
    """Use the shared PostgreSQL rate counter in deployed environments.

    Args:
        settings: environment and API database connection.

    Returns:
        The database rate counter, or a local in-process counter.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """
    if settings.env == "local":
        return MemoryRateCounter(time)
    return PostgresRateCounter(settings.database_url)
