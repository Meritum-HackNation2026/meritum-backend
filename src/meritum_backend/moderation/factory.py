"""Builds the moderation repositories."""

from meritum_core.moderation import HighRiskTopicRepository, ModeratorCaseRepository
from meritum_core.moderation.fakes import (
    InMemoryHighRiskTopicRepository,
    InMemoryModeratorCaseRepository,
)


def build_moderation() -> tuple[ModeratorCaseRepository, HighRiskTopicRepository]:
    """Build the case and high-risk topic repositories.

    shortcut: core's in-memory repositories, so the worker does not see the
    topics and a restart empties both; switch to the PostgreSQL adapters of
    core/031 when they ship.

    Returns:
        The case repository and the topic repository.

    Features:
        US-MOD-01, US-MOD-05, F-20, F-25
    """
    return InMemoryModeratorCaseRepository(), InMemoryHighRiskTopicRepository()
