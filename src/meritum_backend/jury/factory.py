"""Select jury link storage for the environment."""

from meritum_backend.constants import LOCAL_ENV
from meritum_backend.jury.adapters import MemoryJuryLinks, PostgresJuryLinks
from meritum_backend.jury.ports import JuryLinks
from meritum_backend.limits.factory import build_rate_counter
from meritum_backend.limits.ports import RateCounter
from meritum_backend.settings import Settings


def build_jury(settings: Settings) -> tuple[JuryLinks, RateCounter]:
    """Use the shared API schema outside local development.

    Args:
        settings: environment and API database connection.

    Returns:
        The link store and the redemption rate counter: PostgreSQL in deployed
        environments, in-process memory locally.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """
    links: JuryLinks = (
        MemoryJuryLinks()
        if settings.env == LOCAL_ENV
        else PostgresJuryLinks(settings.database_url)
    )
    return links, build_rate_counter(settings)
