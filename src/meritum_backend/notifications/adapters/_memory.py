"""In-process notifier configuration, for local development and tests.

Features:
    US-POW-05, US-MOD-01, F-26
"""

from meritum_backend.notifications.models import NotifierConfig


class MemoryNotifierConfigStore:
    """Keeps the target in memory (lost on restart).

    Features:
        US-POW-05, US-MOD-01, F-26
    """

    def __init__(self) -> None:
        self._config: NotifierConfig | None = None

    async def get(self) -> NotifierConfig | None:
        """Read the target.

        Returns:
            The configuration, or None.
        """
        return self._config

    async def save(self, config: NotifierConfig) -> None:
        """Replace the target.

        Args:
            config: the new configuration.
        """
        self._config = config

    async def delete(self) -> None:
        """Remove the target."""
        self._config = None
